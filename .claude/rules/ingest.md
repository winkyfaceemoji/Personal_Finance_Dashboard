---
paths:
  - main.py
  - config.py
  - Modules/safety.py
  - Modules/linked_cards.py
  - check_data.py
  - convert_check.py
---

# Ingest pipeline & master safety

## The master is the one irreplaceable file
- `SORTED/edited_combined_transactions.csv` is rebuilt from RAW every run. Only `master_category` / `sub_category` carry forward. Never append (ADR 0002).
- Only `Modules/safety.py` writes it: `backup_master`, then `atomic_write_csv`, under `MASTER_LOCK` (ADR 0003). Reload and Import run on the dev server's threads, so a write outside the lock can drop labels.
- At the very start of `main()`, a missing or empty master is restored from the newest backup. Keep that step before any early return, including when RAW is empty.
- Never back up a master that failed to parse, and skip the backup when the master is identical to the newest one. Otherwise repeated failed or no-change Reloads rotate the 10 good backups out.
- Write `orphaned_labels.csv` only *after* the new master is on disk. A failed master write (file open in Excel) must not lose a label that was re-attaching. Updating the orphans file is best effort.
- Starting over means deleting the master, `SORTED/backups/`, `orphaned_labels.csv` and any legacy `.csv.bak`. Any one of them left behind brings labels back.

## Label carry-forward
- Labels match by `MATCH_COLUMNS` first. Each key has a queue, so the Nth repeat inherits the Nth label and extra repeats start blank. Then they match by `FALLBACK_COLUMNS` (date, description, amount, source). Anything unplaced goes to `orphaned_labels.csv` and is retried every rebuild.
- `institution` and `card_last4` are excluded from `MATCH_COLUMNS` on purpose, so masters built before those columns existed still carry their labels. Adding a column to the unified schema has the same problem: exclude it or old labels orphan.
- `last_import.csv` is written only when a run added rows, so a no-change Reload doesn't wipe the record. It is never written on the first import.

## Merging overlapping exports
- Merge by date coverage per account `(institution, source, card_last4)`. Never compare row values: value dedup collapses genuine same-day repeat purchases (ADR 0007).
- File order is `(FORMAT_PRIORITY, span, row count)`. **Never use file mtime.** Bulk copies, git checkouts and drive migrations rewrite it.
- Rows with an unparseable date are always kept, because their coverage can't be checked.
- Dropped rows from a losing file of *another format*, or from another card number's export in a linked account, go to `overlap_only.csv` when nothing in the result has the same date and amount. They are reported, never added back. A pending charge whose amount changed would count twice. Same-card re-downloads are deliberately not checked.
- Capital One files are the Discover account whatever folder they sit in (`CAPITAL_ONE_ACCOUNT`), and Discover-format files own their dates. This is the only exception to folder-authoritative institution identity (ADR 0004, 0005).
- `card_last4` comes only from Chase filenames. Two non-Chase cards in one institution folder share an account key and merge (known gap).
- Discover amounts are negated on normalise. Everywhere: `amount < 0` means money out.

## Replacement cards (`Modules/linked_cards.py`, ADR 0006)
- Nothing merges until the user answers. An unrecognised status reads as `proposed`.
- If `linked_cards.csv` exists but can't be read (Excel renamed a header), stop **before writing anything**: master, `exported_through.csv`, `skipped_files.csv`, `overlap_only.csv`. Never rewrite that file. Falling back to "no links" re-splits a confirmed card and double-counts.
- `same` files rows under the *oldest* number, so row ids stay stable. Chains (A→B→C) file under A.
- A leftover label is absorbed as a duplicate only up to the number of second-number copies the prior master held. A set would let a genuinely lost label vanish.

## Failure handling
- One bad RAW file never aborts the import. It is skipped with a `[SKIP]` line and recorded in `skipped_files.csv`, which covers the latest run only. A skipped file's whole account is missing, so the header warns.
- `filename_date` ignores dates after today. It only feeds `exported_through.csv`, so a quiet card with a recent export isn't flagged as lagging.
- `check_data.py` must stay read-only, apart from its `--save` file. It exits 1 when it reports a problem.
- `convert_check.py` must stay read-only too: it sets `FINANCE_DATA_DIR` to a temp copy of `SORTED/` *before* `import app`, because importing app reads the data folder and the conversion writes it. Never import app at module top there. It exits 1 when it can't convert.

## Data directory
- Callers that know the folder must pass it: `main(data_dir)`. `save_setup` runs before `config.json` is updated, and `reload_data` must rebuild the on-screen folder. A bare `get_data_dir()` resolves the previous folder, or `FINANCE_DATA_DIR`.
- The atomic swap preserves file permissions, so a master written from Docker stays readable on the host. On Linux, files the container creates are root-owned.
