---
type: Decision Record
title: Architecture decisions
description: The load-bearing design choices and why they were made.
updated: 2026-10-09
---

# Architecture decisions

ADR-lite: the decisions that shaped the app, recorded with their reasoning so they aren't re-litigated. Each entry is what was decided and *why* — including the alternative that was rejected, where it matters.

## Data lives outside the repo, in a configurable data directory

RAW exports and the master file (with your labels) live in a `data_dir` resolved from `FINANCE_DATA_DIR` → `config.json` → bundled `Test Data/` — **not** in the app folder.

**Why:** the master is the irreplaceable artifact (your manual labels). Co-locating it with its source data means backup/move/cloud-sync carries the labels along; separate data dirs give independent datasets; and keeping real financial data *outside* the tracked tree avoids ever committing it. Storing it app-side was rejected — it ties labels to the install, breaks the multi-dataset model, and risks committing finances.

## Rebuild the master from RAW every run — never append

`main()` regenerates every unified column from RAW on each run; only `master_category` / `sub_category` are carried forward, matched via `MATCH_COLUMNS`.

**Why:** adding a source or re-downloading a statement is idempotent — unified columns can't drift or double up, because nothing is appended. The cost — recomputing everything — is trivial at personal scale. See [features/ingest-pipeline.md](features/ingest-pipeline.md).

**Label safety:** the labels are the one thing RAW can't regenerate, so every write to the master goes through `Modules/safety.py`: the prior master is *copied* to `SORTED/backups/` (newest 10 kept), the new one is written to a temp file and swapped in atomically, and a master missing (or emptied) after a failed run is restored from the newest backup before anything else happens — at the very start of `main()`, even when RAW turns out to be empty. Labels are carried by the exact match key first, then by a looser date + description + amount + source key; any label neither places is written to `SORTED/orphaned_labels.csv` and flagged in the header — never silently dropped.

**Still open:** a late-posting charge can fall on a coverage boundary, and `card_last4` only comes from Chase filenames (see *Folder-authoritative institution identity*).

## Every master write is a backup + atomic swap

`Modules/safety.py` is the only code that writes the master: `backup_master` (UTC-timestamped copy, keep 10; skipped when the master is identical to the newest backup, and a rebuild backs up only a master that parsed — so failed runs and no-change Reloads can't rotate good backups out), then `atomic_write_csv` (temp file in the same folder, then `os.replace`). Rebuild and Import both use it, each holding `MASTER_LOCK` so a Reload and an Import running on the dev server's threads can't overwrite each other. The swap keeps the file's existing permissions (a new file gets the normal umask default), so a master written from inside Docker stays readable on the host. On a Linux host, files the container creates (the master, `SORTED/backups/`) are owned by root — readable, but not writable, by your user.

**Why:** the old rebuild renamed the master to a single `.bak` before reading it, so one failed run plus the startup auto-ingest and a Reload could destroy every label. A copy keeps the original in place; the atomic swap means a crash leaves either the old file or the complete new one; ten generations mean one bad import can be rolled back by hand.

## Folder-authoritative institution identity

The top-level `RAW/<institution>/` folder is recorded as the `institution` column and is part of the account key `(institution, source, card_last4)`.

**Why:** scaling past three sources, header detection plus a Chase-only filename regex can't identify institutions, and two banks can export the same CSV format (which would collapse into one account and mis-merge). The folder disambiguates *institutions* — but not cards within one: `card_last4` still comes only from Chase filenames, so two non-Chase cards in one institution folder share an account key and their overlapping dates merge. `institution` is deliberately excluded from `MATCH_COLUMNS` so masters built before the column still carry their labels forward on the first rebuild.

## Totals are label-based; merges are coverage-based

Only rows labeled `Expense` / `Income` count; `Transfer` and unlabeled rows are excluded from every total. Overlapping re-exports are merged by date-range ownership, not row-value dedup.

**Why:** value-based dedup collapses genuine same-day repeat purchases (two identical coffees); date-coverage ownership never compares rows to each other. Label-based totals keep transfers from double-counting. Details in [features/ingest-pipeline.md](features/ingest-pipeline.md).

## Label in the app through the import matcher; remember only provably safe rules; show unreviewed money instead of counting it

The labeling panel ([features/labeling-panel.md](features/labeling-panel.md)) labels by merchant group, one click per group. Four choices shape it:

- **In-app labeling shares the Excel import's matcher.** `label_rows` builds an import frame and runs `apply_label_import`, so the panel and the CSV round-trip match rows the same way (date + description + amount + source + card) and write through the same lock, backup and atomic swap. It touches only rows with no valid label, and a stale list or a count mismatch writes nothing.
- **A rule is remembered only when it is provably safe, and the checkbox starts ticked only then.** A `rules.csv` keyword labels every unlabeled row containing it, forever, first match wins. So `rule_check` requires a keyword of at least 4 characters, that matches no other merchant across all rows (labeled ones too), that no existing rule overlaps or would win first, and that the group is one direction of money. Anything else starts unticked with the reason shown, and the box is disabled wherever it can't apply (a blocking reason, or a fallback or mixed card, which has no group buttons). A group with a single transaction passes but starts unticked: one row is thin evidence for a rule.
- **Unreviewed money is shown, not counted.** The stat cards print `+ $X unreviewed` under Spent and Income. Counting unlabeled rows by sign would double-count card payments (the purchase and the bill payment), so they stay out of every total.
- **No built-in transfer rules.** Card-payment phrases cover about 1% of unlabeled dollars on the demo data, and an unreviewed rule that is wrong corrupts totals silently. Groups that look like card payments get a highlighted *suggested* TRANSFER button instead, never auto-applied.

**Why:** the Excel round-trip is slow enough that the backlog never got labeled (562 of 1,343 demo rows, $152,346, missing from every number), and weekly tracking makes it worse because each week arrives unlabeled. A one-click, merchant-level flow clears most of it in one sitting: the top 25 groups cover 87.7% of unlabeled dollars. But one click labels many rows, and a remembered rule labels rows nobody has seen, so each safeguard exists because the failure is silent: the shared matcher means two labeling paths can't disagree, the safety check means a short keyword like `pay` can't sweep up other merchants, and the unreviewed line means a total that is incomplete looks incomplete. Rejected: grouping by raw description (transaction ids split one merchant into several groups), starter rules (unreviewed, wrong ones are silent), and counting unlabeled money by sign (double-counts transfers).

**Recovery:** every click takes a rotating backup and Undo reverts the last action while nothing else has written the files; opening the panel also copies the master to `SORTED/backups/before-labeling-YYYY-MM-DD.csv` (once per day), outside the ten-file rotation, so the state from before a long session can't be pruned away.

## Net worth needs balance snapshots, not transactions *(direction — not yet built)*

Net worth should come from periodic account-balance snapshots, kept as a parallel input; it should **not** be inferred by summing transactions.

**Why:** investment/savings/loan balances aren't derivable from transaction streams — market moves produce no transaction, and a complete gap-free history rarely exists. Transactions drive cash flow; a separate balance input should drive net worth. Recorded here so the transaction pipeline doesn't get bent into the wrong shape.

## No Dash background callbacks

Reload and import run synchronously; loading feedback is a `dcc.Loading` overlay, not a `background=True` callback.

**Why:** background callbacks can execute in a separate process, which would break the module-global `df` that the reload mutates and every callback reads. `dcc.Loading` gives feedback without that infrastructure or that risk.

## Category selection lives in a Store and is patched — not driven by clickData

The clicked category bar is held in a `selected-category` `dcc.Store`; `highlight_category` applies the highlight via a `Patch` of the bar opacities.

**Why:** rebuilding the figure clears its `clickData`, which would fight the very click that triggered the rebuild. A Store decouples selection from the figure; patching only the opacities avoids rebuilding the chart on every click; and `clickData` is reset after each click so re-clicking the same bar registers as a change (Dash only fires on changed inputs). The same reset is used for the spending-over-time chart, where a bar click navigates to that period.

## Track spending by week, month, and year — through one period control

A single period bar (WEEK / MONTH / YEAR plus a ‹ › stepper) drives the stat cards, the pace strip, the spending chart's highlight, and the category breakdown. It replaced separate per-card controls (YTD/1Y/3Y chips on one chart, year chips on the pie).

**Why:** the app's job is "am I on track, and where did it go?" at whichever granularity you're checking in at. Per-card controls answered different questions about different time spans on the same screen — the YTD cards, a trailing-3Y chart, and a 2023 pie could all be showing at once. One period means every number on the page is about the same span.

## Periods are anchored to the latest transaction, not today

"Latest" means the period containing your newest transaction; ranges and comparisons are measured from it. The header names the data's end date, flags any source lagging by more than a week, and shows a notice when the newest transaction is over a week old.

**Why:** exports are manual and always lag. Anchored to today, a dashboard whose data ends Dec 26 showed `$0.00 ▼100%` on every card in October and an empty current-period chart — the first screen was wrong whenever the data was stale. Anchoring to the data keeps the numbers meaningful, and the freshness line keeps the staleness visible instead of hiding it in zeros.

## Weeks run Monday → Sunday

Weeks are ISO weeks (pandas `W-SUN`: periods ending Sunday).

**Why:** chosen by the user. Monday-start weeks keep a weekend's spending inside one week.

## In-progress periods are compared like-for-like; "typical" is a median

While a period is in progress (day 26 of 31), its comparisons use the same number of days of each earlier period. "Typical" is the median of up to the previous 12 weeks or months, or of every earlier year.

**Why:** comparing a part-finished month with whole months always looks like an improvement. A median rather than a mean stops one unusual period (a tax payment, a holiday) from redefining normal. Zero-spend gap periods count toward the median rather than vanishing, so a quiet stretch reads as quiet.

## Local-only and debug-off by default

`app.py` binds to `127.0.0.1` with debug off unless `FINANCE_HOST` / `FINANCE_DEBUG` say otherwise. The Docker image sets `FINANCE_HOST=0.0.0.0` (required inside a container) and `FINANCE_DEBUG=1` (hot reload), and the documented `docker run` publishes to `127.0.0.1` only.

**Why:** the app has no login, and its settings menu can export every transaction, overwrite labels, and repoint the data folder. Bound to every interface, anyone on the same network could do all of that; debug mode also exposes tracebacks and the Werkzeug debugger. Making network exposure an explicit opt-in costs nothing for the normal single-machine use.

## Transfer pairs are suggested only when the match is certain

The TRANSFER PAIRS tab pairs an exact opposite amount on another account within 5 days, and shows a pair only when neither row has any other candidate. Sides labeled Expense or Income are never touched; nothing is labeled without a click, and LABEL ALL covers only the pairs on screen.

**Why:** a wrong pair mislabels real spending as Transfer, which silently removes it from every total — worse than leaving it unlabeled, where it is at least counted as unreviewed. Exact amounts, different accounts and a short window make coincidences rare; refusing ambiguous matches removes the rest. The cost is that some real transfers (two equal payments the same week) stay for the merchant list. The same certain matches with a side already labeled Expense or Income are *flagged*, never changed: relabeling one is an explicit click (the only place the panel overwrites a label), and NOT A TRANSFER silences a pair for good.

> New load-bearing decision? Add it here with the *why* — future-you will want the reasoning, not just the outcome.
