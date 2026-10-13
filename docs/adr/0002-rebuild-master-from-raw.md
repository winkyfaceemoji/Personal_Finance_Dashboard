# 0002. Rebuild the master from RAW every run, never append

Status: Accepted

## Context
New statements and re-downloads keep arriving, often overlapping earlier exports. An append-based master drifts and can double up.

## Decision
`main()` regenerates every unified column from RAW on every run. Only `master_category` / `sub_category` are carried forward, in this order:

1. By the exact `MATCH_COLUMNS` key. Each key has a queue, so the Nth occurrence inherits the Nth label.
2. By the looser `FALLBACK_COLUMNS` key: date, description, amount, source.
3. A label neither key places goes to `SORTED/orphaned_labels.csv`. It is retried on every later rebuild and flagged in the header, never silently dropped.

## Consequences
- Adding a source or re-downloading a statement is idempotent. Unified columns can't drift or double up, and recomputing everything is trivial at personal scale.
- A re-export that changes a bank category, memo or running balance keeps its labels through the fallback key.
- Still open: a late-posting charge can fall on a coverage boundary, and `card_last4` comes only from Chase filenames (see 0004).
