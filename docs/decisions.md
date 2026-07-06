---
type: Decision Record
title: Architecture decisions
description: The load-bearing design choices and why they were made.
updated: 2026-07-06
---

# Architecture decisions

ADR-lite: the decisions that shaped the app, recorded with their reasoning so they aren't re-litigated. Each entry is what was decided and *why* — including the alternative that was rejected, where it matters.

## Data lives outside the repo, in a configurable data directory

RAW exports and the master file (with your labels) live in a `data_dir` resolved from `FINANCE_DATA_DIR` → `config.json` → bundled `Test Data/` — **not** in the app folder.

**Why:** the master is the irreplaceable artifact (your manual labels). Co-locating it with its source data means backup/move/cloud-sync carries the labels along; separate data dirs give independent datasets; and keeping real financial data *outside* the tracked tree avoids ever committing it. Storing it app-side was rejected — it ties labels to the install, breaks the multi-dataset model, and risks committing finances.

## Rebuild the master from RAW every run — never append

`main()` regenerates every unified column from RAW on each run; only `master_category` / `sub_category` are carried forward, matched via `MATCH_COLUMNS`.

**Why:** adding a source or re-downloading a statement is idempotent and can never corrupt existing data. The cost — recomputing everything — is trivial at personal scale. See [features/ingest-pipeline.md](features/ingest-pipeline.md).

## Folder-authoritative institution identity

The top-level `RAW/<institution>/` folder is recorded as the `institution` column and is part of the account key `(institution, source, card_last4)`.

**Why:** scaling past three sources, header detection plus a Chase-only filename regex can't identify institutions, and two banks can export the same CSV format (which would collapse into one account and mis-merge). The folder disambiguates. `institution` is deliberately excluded from `MATCH_COLUMNS` so masters built before the column still carry their labels forward on the first rebuild.

## Totals are label-based; merges are coverage-based

Only rows labeled `Expense` / `Income` count; `Transfer` and unlabeled rows are excluded from every total. Overlapping re-exports are merged by date-range ownership, not row-value dedup.

**Why:** value-based dedup collapses genuine same-day repeat purchases (two identical coffees); date-coverage ownership never compares rows to each other. Label-based totals keep transfers from double-counting. Details in [features/ingest-pipeline.md](features/ingest-pipeline.md).

## Net worth needs balance snapshots, not transactions *(direction — not yet built)*

Net worth should come from periodic account-balance snapshots, kept as a parallel input; it should **not** be inferred by summing transactions.

**Why:** investment/savings/loan balances aren't derivable from transaction streams — market moves produce no transaction, and a complete gap-free history rarely exists. Transactions drive cash flow; a separate balance input should drive net worth. Recorded here so the transaction pipeline doesn't get bent into the wrong shape.

## No Dash background callbacks

Reload and import run synchronously; loading feedback is a `dcc.Loading` overlay, not a `background=True` callback.

**Why:** background callbacks can execute in a separate process, which would break the module-global `df` that the reload mutates and every callback reads. `dcc.Loading` gives feedback without that infrastructure or that risk.

## Pie selection lives in a Store and is patched — not driven by clickData

The clicked slice is held in a `selected-category` `dcc.Store`; `pop_slice` applies the slice pull via a `Patch`.

**Why:** rebuilding the pie figure clears its `clickData`, which would fight the very click that triggered the rebuild. A Store decouples selection from the figure; patching only the `pull` avoids rebuilding the whole dashboard on every click; and `clickData` is reset after each click so re-clicking the same slice registers as a change (Dash only fires on changed inputs).

> New load-bearing decision? Add it here with the *why* — future-you will want the reasoning, not just the outcome.
