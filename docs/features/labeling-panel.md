---
type: Feature Doc
title: Labeling panel
description: The full-screen panel that labels unlabeled transactions in the app, one merchant group at a time, with safe rule memory, undo and a pre-session snapshot.
resource: app.py, Modules/labels.py
updated: 2026-10-09
---

# Labeling panel

Every total in the app is label-based, so a transaction with no `Expense` / `Income` / `Transfer` label counts for nothing. The panel is the in-app way to fix that: it groups the unlabeled rows by merchant, shows the biggest first, and labels a whole group with one click. The Excel round-trip in [import-export.md](import-export.md) still works and is still the tool for bulk edits and for changing labels that are already set. The panel never edits an existing label.

The decision record is in [decisions.md](../decisions.md#label-in-the-app-through-the-import-matcher-remember-only-provably-safe-rules-show-unreviewed-money-instead-of-counting-it). The pure functions live in `Modules/labels.py` (covered by `tests/`); the layout, cards and callbacks are in `app.py`.

---

## Entry points

| Where | Button | Opens |
|-------|--------|-------|
| Header, next to the unlabeled note (`unlabeled-note`) | `LABEL THEM →` (`open-label-panel`) | every unlabeled row. Hidden when nothing is unlabeled |
| Header, next to the last-import line (`last-import-note`) | `REVIEW →` (`open-label-review`) | only the rows the last import added (the summary adds `· from the last import`). Hidden unless some of those rows are still unlabeled |

Both always open on the **TO LABEL** tab. **DONE** (`close-label-panel`) closes the panel and bumps `refresh-trigger`, so the stat cards, the header notes and every chart pick up what was labeled while it was open. The panel is `#label-panel`, fixed full-screen at z-index 90 (see [design.md](../design.md#layering)).

The stat cards show what is still unlabeled in the period (`+ $292 unreviewed` under SPENT and INCOME) so the totals look incomplete rather than quietly short; see [overview-charts.md](overview-charts.md#stat-cards-period-stats).

---

## The labeling guide

A collapsible **How to choose a label** box (`LABEL_GUIDE` in `app.py`, rendered as Markdown):

> **Ask one question: did money enter or leave *you* — all your accounts counted as one pot?**
>
> - **Expense** — it left you for someone else (groceries, rent, a Zelle to a friend for dinner).
> - **Income** — it came to you from someone else (paycheck, client payment, tax refund).
> - **Transfer** — it moved between your own accounts (credit-card payment, savings or investments, Venmo cash-out). Card purchases were already counted, so the bill payment must not count again.
>
> **Tricky cases** — card payment ("AUTOPAY", "PAYMENT THANK YOU"): Transfer, on both sides · refund: Expense (it reduces spending) · friend paying you back: Expense · Venmo / Zelle / PayPal: depends who's on the other end — expand and label row by row · ATM cash: Expense · loan or mortgage payment: Expense.

---

## Grouping

`unlabeled_groups(df, only_row_ids=None)` takes the rows whose `master_category` is not one of `PREDEFINED_CATEGORIES`, groups them by `merchant_key`, and sorts the groups by absolute dollars, largest first.

`merchant_key(description)` answers "who is this with?":

1. `normalize_description` — lowercase, `*` and `#` become spaces, whitespace collapsed.
2. Cut at the first ` web id`, ` ppd id`, ` ccd id`, ` id:` or ` ach ` (reference-id tails).
3. Drop ACH code tokens (`rtl-…`, `ppd-…`, `ccd-…`, `web-…`). The pattern is narrow on purpose: a generic `xx-…` pattern would eat names like `wal-mart`.
4. Keep the first word, then each following word until one contains a digit. Store numbers and dates drop off, but a name that **starts with a number or contains a hyphen** survives (`7-eleven`, `99 ranch market`, `1-800-flowers`).
5. Trim ` -.,/`.

`STARBUCKS STORE 01234 SEATTLE` and `STARBUCKS STORE 09876 NEW YORK` both become `starbucks store`.

A description with **no recognizable name** (nothing with a letter is left, e.g. `#1234`) becomes its own one-row **fallback** group, keyed on its full normalized description. Unrelated nameless rows are never lumped into a shared catch-all.

Each group carries: `key` (a short hash), `merchant`, `count`, `total`, `abs_total`, `first` / `last` date, one `example` description, `mixed`, `fallback`, `sig`, `suggest_transfer` and `rows`. Rows are one entry per distinct `row_id` (a hash of date, description, amount, source and card), with identical twin rows merged into one entry with a `count`, the same way the import matcher treats them. `sig` is a hash of the group's row ids and counts, used to detect a stale list (see Writes).

**Card layout (`_group_card`).** Merchant name, a `MIXED` badge (`.lg-badge`) when the group has money both in and out, `N txns · total · date span`, the example description, then the three buttons, an optional **Subcategory** box (suggestions from subcategories already in use), the **Remember for future statements** checkbox with its note, and a `Label rows one at a time (N)` expander listing each row (date · description · amount, with `×N` when identical twin rows share it) with its own three buttons.

**Card state survives a re-render.** Every label, Undo or rule delete re-renders the list. `render_label_list` reads back what you'd set on each card — the typed Subcategory, the Remember tick, and whether the row list is open — and re-applies it, so labeling one merchant doesn't wipe what you were doing on the next. Dash doesn't report a `<details>` toggle, so each summary (`lbl-rows-sum`) counts its clicks and the parity flips the last-rendered `open`. Switching the TO LABEL / RULES tab clears the status line (the UNDO button stays).

**Suggested Transfer.** A group whose descriptions match card-payment or own-account-transfer wording (`payment thank`, `autopay`, `online transfer`, `transfer to`, `transfer from`, `epay`, `card payment`, `directpay`, `internet payment`; `looks_like_transfer`) gets its TRANSFER button filled and starred (`★ TRANSFER`, `.suggested`) — plain buttons are already accent-outlined, so colour alone wasn't enough. It is only ever a suggestion; nothing is applied for you.

---

## Which groups get one-click labels

A group gets the EXPENSE / INCOME / TRANSFER group buttons only when it is **neither fallback nor mixed-direction**. Otherwise the card shows `Label these one at a time below` and its row list is already expanded.

**Why:** one click labels every row in the group, so the group has to be one thing. A fallback group has no merchant name to vouch for it. A mixed group (Coinbase buys and sells, Zelle both ways, a refund among purchases) has rows that legitimately need different labels. Both are labeled row by row; a row click labels that row and its identical twins (shown `×N`: same date, description, amount, source and card, so no click could tell them apart) and never creates a rule.

---

## Rule safety

A rule in `rules.csv` applies to every unlabeled row whose description contains its keyword, past and future, on every load; the first match wins. So *Remember for future statements* must provably mean only this merchant. `rule_check` returns `{ok, keyword, reason, blocking, rows_now, dollars_now, others, direction}` after four checks, in this order:

1. **Long enough** — the keyword (`rule_keyword`: the longest word-aligned prefix all the group's descriptions share, always a real substring of every one) is at least `MIN_KEYWORD` = 4 characters.
2. **This merchant only** — across **all** rows, labeled ones included, every row the keyword matches belongs to this merchant group. The reason names up to three other merchants (`also matches CENTRAL BANK COLLECTION, …`).
3. **Not overridden** — no existing rule's keyword equals, contains, or is contained by the new keyword, or matches any description in the group (it would win first match). The reason is `existing rule "x" would override it`.
4. **One direction of money** — all rows money out, or all money in.

A fallback group fails up front (`no recognizable merchant name`). Failing 1, 2 or 3 is **blocking**: the checkbox is disabled and unticked, with the reason shown. Failing 4 (mixed sign) is the only **non-blocking** reason, shown as a note. When all four pass, the note reads `rule "starbucks" (money out) · labels 14 rows ($87) now`.

The checkbox's starting state (`_group_card`):

| Card | Checkbox |
|------|----------|
| All four checks pass, **2 or more** transactions | enabled, ticked |
| All four checks pass, **one** transaction | enabled, unticked; the note adds `only one transaction — tick to remember anyway`. One row is thin evidence for a rule that labels every future match, so it is the user's call |
| A blocking reason | disabled, unticked |
| No group buttons (fallback or mixed — labeled row by row) | disabled, unticked. Remember only acts on a group click, and row clicks never create rules, so a ticked box there could never do anything |

---

## Writes

A click on a group or row button runs `_do_label`:

1. **Resolve.** A button whose category isn't Expense / Income / Transfer is refused with a plain status and nothing is written. For a group click, find the group by key and compare its `sig` with the one on the button; for a row click, find the row by id anywhere in the list. If the group is gone or its `sig` differs, nothing is written and the status reads `The list changed — it has been refreshed.` Rows the user didn't see are never labeled.
2. **Under `MASTER_LOCK`**, re-read the master from disk and run `label_rows`, which goes through the same matcher an Excel import uses (date + description + amount + source + card) and touches **only rows with no valid label yet**: a hand-labeled twin of an unlabeled row keeps its label.
3. **Count check.** If the number of rows labeled differs from what the list showed, nothing is written; the frame is reloaded and the status reads as above.
4. `backup_master` (the rotating backup), then `atomic_write_csv` for the master.
5. The undo record is built right after the master write, so nothing that follows can lose it.
6. **Then** the rule: only for a group click with *remember* ticked and a non-blocking `rule_check`. The rule is written strictly after the master write succeeded, so a failure can never leave a rule without its labels.
7. Reload the frame, set the status (`Labeled 14 STARBUCKS rows as Expense · rule "starbucks" added`), store the undo record and show **UNDO**.

If the **master** is open in another program, the status reads `⚠ The data file is open in another program (Excel?) — close it and try again.` and nothing is written. Once the master is written, the labels and **UNDO** always stand: a **`rules.csv` problem** (open in Excel, unreadable, can't be written) keeps the labels and the status ends `· not remembered: rules.csv is open in another program` (or `… couldn't be read or written`), and a failed reload ends `· couldn't reload the data — use RELOAD DATA`. Re-rendering the list adds buttons with `n_clicks` 0, which fires the pattern-matching callbacks too; `_is_real_click` ignores those.

Writes to `rules.csv` (`add_rule`, `delete_rule`) are atomic and run under `MASTER_LOCK`. Reads (`read_rules`, and the loader's `apply_auto_categories`, through the shared `read_rules_csv` in `Modules/transforms.py`) tolerate what Excel saves — UTF-8 with a BOM, or Windows-1252 from a plain "CSV" save — and treat a zero-byte file as no rules. `add_rule` appends `keyword, master_category, sub_category, added` (an ISO date; the loader ignores the extra column) and refuses a keyword under 4 characters, a duplicate, or a category that isn't Expense / Income / Transfer.

---

## The `before-labeling-YYYY-MM-DD.csv` snapshot

Labeling takes a rotating backup per click, and the rotation keeps ten, so a long session would prune away the state from before it started. When the panel opens, `snapshot_master` copies the master to **`SORTED/backups/before-labeling-YYYY-MM-DD.csv`** (today's local date), a name outside the backup rotation: the rotation's glob doesn't match it, so it is never pruned, and the automatic restore of a missing master never picks it. It is written **once per day** — opening the panel again the same day (open → DONE → reopen) keeps the first copy, so it is always the state from before that day's first labeling. One file accumulates per day you label; delete old ones by hand. If the copy fails (disk full, read-only folder), the panel opens anyway and the console prints a warning; each click still takes its rotating backup.

To go back to it: stop the app, copy `SORTED/backups/before-labeling-YYYY-MM-DD.csv` (the day you want) over `SORTED/edited_combined_transactions.csv`, and start it again (or use **RELOAD DATA**). Restoring does not touch `rules.csv`; delete any rules the session added on the Rules tab.

---

## Undo

**UNDO** reverts the last action only, and only while nothing else has written the master or `rules.csv` since. The undo record (`label-undo` Store) is `{backup, master_mtime, rules_mtime, rule}`: the backup the click made, both files' modification times, and the keyword of the rule it added (if any).

The mtimes are stored as **strings** of `st_mtime_ns`: nanosecond times are past 2^53, and the record travels through the browser's JSON, which would round an integer and make every undo look stale.

Undo compares both current mtimes to the stored ones. If they differ the status reads `Can't undo — the data changed since.` and the button hides. Otherwise `restore_backup` puts the backup back atomically, the added rule is deleted, and the status reads `Undone.`

---

## Transfer pairs

A card payment shows up twice: money out of checking ("Payment to Chase card ending in 3094") and money into the card ("AUTOMATIC PAYMENT - THANK"). Both sides are Transfer, and labeling either as Expense counts the same money twice. The **TRANSFER PAIRS** tab (`transfer_pairs` in `Modules/labels.py`) finds them:

- one row **out** and one row **in** of exactly the same amount, to the cent;
- on **different accounts** (source + card) — a refund on the same card is money back, not a move;
- within **`TRANSFER_PAIR_DAYS` = 5 days** of each other (posting delays, weekends, holidays);
- **certain matches only**: if either row has more than one candidate (two equal payments, identical twin rows), which one pairs is a guess, so neither is shown. Every row counts as a candidate here, labeled or not.

A pair with a side already labeled **Expense or Income** is left alone (that was your call); a pair labeled Transfer on both sides has nothing to do. A pair with one side already Transfer offers **LABEL AS TRANSFER** for the other. Each card shows both rows (date, OUT/IN, account, description, current label, amount) with **LABEL BOTH TRANSFER**; **LABEL ALL N PAIRS** labels every pair shown in one write. Clicks are checked against the pair key (or, for LABEL ALL, a signature of the whole list) and go through the same locked write as every other label (`_write_labels`: count check, backup, atomic write) with the same **UNDO**. The TO LABEL summary says how many pairs were found.

Your existing rules may already cover the common card payments (`payment thank you`, `automatic payment`, `payment to chase card`); pairs then catch the rest — moves to savings, other banks, wallets.

## The Rules tab

The **RULES** pill swaps the list for two sections:

- **Added from this panel** — rules with an `added` date, each with a **DELETE** button.
- **In rules.csv (edit the file to change)** — hand-written rules, read-only.

Each row shows the keyword, its label (and subcategory), `matches N row(s)` (every row containing the keyword, labeled or not) and the date added. **DELETE** (`_do_delete_rule`) removes the rule under `MASTER_LOCK`, then reloads. Deleting a rule removes only the rule: rows already labeled in the master keep their labels, because panel clicks write labels into the master. Rows that were being labeled only by that rule, in memory, go back to unlabeled on the next load. See [transforms.md](transforms.md#apply_auto_categoriesdf-rules_path).

---

## The last import: `last_import.csv`

`rebuild_master` in `main.py` writes `SORTED/last_import.csv` (one `row_id` column, written atomically) holding the rows the run added, meaning the rows neither carried over nor rescued from the previous master. It is written **only when the run added rows**: a Reload that finds nothing new must not wipe the record of the last real import. Nothing is written on the very first import (no previous master, so every row would be "new").

The header line `Last import: 31 new · 27 labeled · 4 need you` is computed from that file and the loaded frame, and `REVIEW →` appears while any of those rows are still unlabeled.

---

## `FINANCE_RULES_PATH`

`app.py` reads rules from `RULES_PATH`: the `FINANCE_RULES_PATH` environment variable if set, otherwise `rules.csv` in the project folder. Because the app can now add and delete rules, tests and scripted checks point this at a copy so they never rewrite the real file. `FINANCE_DATA_DIR` does the same for the data folder.

---

## The top-25 limit

The panel shows only the **top 25 groups** by dollars (`LABEL_TOP_N`); the summary says `· showing the top 25` when there are more. On the demo data the top 25 of 286 groups cover about 88% of unlabeled dollars. Labeled groups drop out of the list, so the next 25 appear as you go, and anything left waits for the next session. There is no pagination.
