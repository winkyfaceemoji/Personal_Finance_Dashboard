---
type: Feature Doc
title: Ingest pipeline
description: Converts raw bank CSVs into a normalized master file — overlapping exports merged by date coverage — rebuilt from RAW each run.
resource: main.py, config.py
updated: 2026-10-09
---

# Ingest pipeline (`main.py`)

The pipeline converts raw bank CSVs into a single, schema-normalised master file, rebuilt fresh from `RAW/` on every run. Run it once per batch of new exports before starting the dashboard — or click **RELOAD DATA** in the browser (Settings menu, top right) to run it without leaving the app. Both paths call the exact same `main()` function, so there's only one code path to reason about.

---

## Launch modes

| Mode | Command | Hot-reload |
|------|---------|-----------|
| venv (local) | `.venv\Scripts\python main.py` | No — restart manually |
| Docker (dev) | `docker run -p 127.0.0.1:8050:8050 -v "%cd%:/app" personal-finance` | Yes — Dash reloads on `.py` save |
| Docker (prod) | `docker run -p 127.0.0.1:8050:8050 personal-finance` | No — code is baked into image. Labels are written inside the container and lost when it's removed, so mount your data folder for real use |

Run directly, the app listens on `127.0.0.1` with debug off; set `FINANCE_HOST=0.0.0.0` to reach it from other devices and `FINANCE_DEBUG=1` for hot reload and tracebacks. The Docker image sets both (a container must listen on all interfaces for port forwarding), which is why the commands publish to `127.0.0.1` only — see [decisions.md](../decisions.md#local-only-and-debug-off-by-default).

In dev Docker mode the local project directory is mounted into the container at `/app`. Dash's built-in reloader watches `.py` files and restarts the server automatically on save. Only rebuild the image (`docker build -t personal-finance .`) when `requirements.txt` changes.

---

## Data directory

`main(data_dir: Path | None = None)` resolves its working folder from the `data_dir` argument if one is passed, otherwise falls back to `config.get_data_dir()`, which checks in order:

1. `FINANCE_DATA_DIR` environment variable
2. `config.json` in the project root (written by the in-app setup screen)
3. `Test Data/` folder in the project root (built-in demo data)

`input_folder`, `output_file`, and `master_file` (the latter via `config.get_master_path(data_dir)`) are all derived from this resolved directory, so `main()` always operates on the currently configured — or explicitly passed — data location.

The explicit-argument form matters for `save_setup` (see [setup-screen.md](setup-screen.md#save--launch-save_setup)): it passes the just-picked folder directly instead of relying on `config.json` already being updated, since `get_data_dir()` alone would otherwise resolve the *previous* directory.

`app.py` also runs this pipeline automatically at startup if the resolved directory has no master file yet — see [setup-screen.md](setup-screen.md#first-launch-auto-ingest).

---

## Inputs

Organise `RAW/` by institution — one folder per data source — and drop that institution's exports inside it:

```
RAW/
  Chase/      Chase{last4}_Activity...csv
  Discover/   Discover-Statement-...csv
  <institution>/ ...
```

`RAW/` is walked recursively (`rglob`), so files can sit at any depth. The **top-level folder under `RAW/` is the institution** and is recorded on every row as the `institution` column (folder-authoritative identity; files dropped directly in `RAW/` get a blank institution). The CSV **format** is still auto-detected from the column headers — independent of the folder — so a single institution folder can hold multiple formats (e.g. Chase debit and Chase credit together). Three formats are supported:

| Format constant | Source | Key columns used |
|----------------|--------|-----------------|
| `chase_debit` | Chase chequing/debit | `Posting Date`, `Description`, `Amount`, `Type`, `Balance`, `Check or Slip #` |
| `chase_credit` | Chase credit card | `Transaction Date`, `Post Date`, `Description`, `Category`, `Type`, `Amount`, `Memo` |
| `discover_credit` | Discover credit card | `Trans. Date`, `Post Date`, `Description`, `Amount`, `Category` |

A file that can't be used — unreadable, unrecognised headers, or a normalizer error on a malformed statement — is skipped with a `[SKIP]` log line and recorded, with its reason, in `SORTED/skipped_files.csv`; the dashboard header turns that into a red warning, because a skipped file's whole account is missing from every total. One bad file never aborts the import of the others. The record describes the latest run only (written even when nothing could be imported, removed when nothing was skipped). Multiple files from the same account — including overlapping re-exports of its history — can coexist; the pipeline resolves the overlap itself (see [Merging overlapping exports](#merging-overlapping-exports-_merge_by_coverage) below). Each account is keyed by `(institution, source, card_last4)`, so two institutions that happen to export the same CSV format never collapse into one account.

**Chase file naming:** Chase exports follow the pattern `Chase{last4}_Activity...csv`. The pipeline extracts the 4-digit card number from the filename and stores it in the `card_last4` column. (No per-card subfolder is needed — the last-4 comes from the filename.)

**Discover amount signs:** Discover CSVs record purchases as positive and credits as negative — the opposite of Chase. The pipeline negates all Discover amounts on normalisation so the sign convention is consistent (`amount < 0` = expense, `amount > 0` = income/credit).

---

## Unified schema

Every normalised row has these columns:

| Column | Type | Notes |
|--------|------|-------|
| `date` | datetime | Transaction date (not post date) |
| `post_date` | datetime | Settlement date |
| `description` | str | Merchant / memo text |
| `amount` | float | Negative = expense, positive = income/credit |
| `original_category` | str | Bank-provided category (credit cards only; debit = `None`) |
| `type` | str | Bank-provided transaction type |
| `balance` | float | Running balance (debit only; credit = `None`) |
| `memo` | str | Additional memo (Chase Credit only) |
| `check_or_slip` | str | Chase Debit only |
| `institution` | str | Top-level `RAW/` folder the file came from (e.g. `Chase`, `Discover`); blank if the file sat directly in `RAW/` |
| `source` | str | Account type / format: `"Chase Debit"`, `"Chase Credit"`, or `"Discover Credit"` |
| `card_last4` | str | Last 4 digits of card number (Chase only; blank for Discover) |

---

## Processing steps

```
1. Resolve data directory via config.get_data_dir()
2. Glob RAW/ for *.csv (recursive)
3. For each file:
   a. Read with pandas, strip column-header whitespace
   b. detect_format() → match header set against known signatures
   c. Call the matching normaliser → unified-schema DataFrame
   d. Set institution = top-level RAW/ subfolder; extract card_last4 from
      filename (Chase files only)
4. Group normalised frames by physical account: (institution, source, card_last4)
5. Within each account, merge overlapping files by date coverage
   (see "Merging overlapping exports" below) — never by comparing row values
6. Concatenate every account's merged result, sort by date ascending
7. Write SORTED/combined_transactions.csv  (raw pipeline output)
8. rebuild_master()
```

---

## Merging overlapping exports (`_merge_by_coverage`)

Banks get re-exported periodically with overlapping, shifting date ranges — e.g. a "since account opening" export downloaded in 2025 fully contains an earlier "last 12 months" export from 2024. The overlapping segment between two such exports covers the exact same real transactions.

Earlier versions of this pipeline deduplicated by comparing row values (date, description, amount, ...) across the whole RAW folder at once. That breaks on genuine same-day repeat purchases — two subway swipes, two identical bakery visits — because they're indistinguishable from a real duplicate by value alone. A blanket value-based dedup silently collapsed both cases into one row.

`_merge_by_coverage` instead decides *which file owns a given date*, and never compares rows to each other at all:

```
For each (institution, source, card_last4) account:
  Sort that account's files by (date span, row count) descending
    — i.e. the file with the widest verified date range goes first;
    file modification time is deliberately NOT used, since bulk copies,
    git checkouts, and drive migrations rewrite mtimes with no relation
    to when a statement was actually downloaded.
  covered = []  (list of claimed date intervals, empty at first)
  For each file in that order:
    Keep only the rows whose date falls outside every interval in `covered`
    Add (min date, max date) of the newly-kept rows to `covered`
  Concatenate everything kept for this account
```

Whichever file owns a date contributes *all* of its rows for that date — duplicates included — so genuine repeat transactions on the same day survive intact. Rows with an unparseable date are always kept, since their coverage can't be checked.

---

## Master file rebuild (`rebuild_master`)

The master file `edited_combined_transactions.csv` adds user-assigned columns: `master_category` and `sub_category`. Every other column is **regenerated from RAW on every run** — the master file is fully rebuilt, not appended to. Only the categorization is carried forward, by matching each rebuilt row's key against the prior master file:

```
Build a match key (MATCH_COLUMNS = all unified columns except card_last4
  and institution) for every row in both the prior master file and the
  freshly rebuilt data.

For each match key, collect the prior master's (master_category, sub_category)
  values for that key, in the order they appeared (a queue per key — a key
  that occurred N times previously has N entries).

For each rebuilt row, in order:
  If its key still has an unused entry in that queue → inherit it
    (pop the next entry, in order)
  Otherwise → it's a genuinely new occurrence of that key → leave blank

Sort the rebuilt data by date, write it as the new master file.
```

This means a match key that occurs *more* times in the rebuilt data than it did before (e.g. a same-day repeat transaction an older, value-based dedup had collapsed away) has its first N occurrences inherit the N prior categorizations, and any occurrences beyond that start uncategorized for manual review.

If the master file doesn't exist yet (first run), it's created directly from the combined data with `master_category` and `sub_category` set to `None` — there's nothing to inherit from.

**Backups:** once the existing master has been read successfully, it is *copied* to `SORTED/backups/edited_combined_transactions.<timestamp>.csv` (UTC timestamp; a `_001` counter is added if two land on the same stamp); the newest 10 are kept, and no copy is made when the master is identical to the newest backup (a legacy `.csv.bak` from older versions is left alone and used as a last resort). A master that can't be parsed is never backed up — the run fails instead — so repeated failed Reloads can't push the good backups out. If the master is missing or empty when `main()` starts — e.g. after a failed run or a save torn by power loss — the newest backup is restored first (even if RAW is empty) and the console says so. To deliberately start over, delete the master, `SORTED/backups/`, `SORTED/orphaned_labels.csv`, and any old `edited_combined_transactions.csv.bak` — any one left behind brings its labels back on a later rebuild.

**Fallback match & orphans:** labels the exact `MATCH_COLUMNS` key can't place are tried again by `FALLBACK_COLUMNS` (date, description, amount, source) — so a re-export that changes a bank category, memo, or running balance keeps its labels. Labels neither key places are kept in `SORTED/orphaned_labels.csv`, re-tried on every later rebuild (so they re-attach if the transaction reappears in a new export), counted in the dashboard header, and the file is deleted once it's empty. The orphans file is only written *after* the new master is safely on disk, so a failed master write (e.g. the file is open in Excel) never loses a label that was re-attaching. Updating it is best effort: if the orphans file itself is open in Excel, the rebuild still succeeds and the console names the file to close. Its dates are re-read whatever format Excel saved them in, and an orphan identical to a row already in the master (one that re-attached while the file was locked) is dropped rather than reported again or handed to a later same-day repeat.

The new master is written atomically (temp file + `os.replace`), so a crash mid-write can't truncate it. The file keeps its existing permissions (a new file gets the normal umask default), so a master written from Docker stays readable on the host. On a Linux host, files the container creates (the master, `SORTED/backups/`) are owned by root — readable, but not writable, by your user. In the app, every rebuild and import holds one lock (`MASTER_LOCK`), so a Reload and an Import can't interleave and drop each other's labels.

---

## Outputs

| File | Updated by | Used by |
|------|-----------|---------|
| `SORTED/combined_transactions.csv` | Every pipeline run (full rebuild) | Not read by the app directly |
| `SORTED/edited_combined_transactions.csv` | Every pipeline run (full rebuild; categorization carried forward by match key) | `app.py` on startup and after reload |
| `SORTED/backups/edited_combined_transactions.<timestamp>.csv` | Every rebuild and every import, unless the master is unchanged since the last backup (newest 10 kept) | Auto-restore when the master is missing or empty; manual rollback |
| `SORTED/orphaned_labels.csv` | Every rebuild: labels not yet placed (removed when empty) | Re-tried on the next rebuild; header note |
| `SORTED/not_transfers.csv` | Labeling panel: pairs you marked NOT A TRANSFER | Those pairs are never flagged again |
| `SORTED/skipped_files.csv` | Every import: RAW files that couldn't be used, with the reason (removed when none) | Header warning (`skipped-note`) |
| `SORTED/last_import.csv` | A rebuild that added rows: their `row_id`s (left alone when nothing is new) | The header's `Last import: …` line and the labeling panel's `REVIEW →` filter |
| `SORTED/backups/before-labeling-YYYY-MM-DD.csv` | The app, when the labeling panel first opens that day (outside the backup rotation, never pruned) | Manual rollback to the state before that day's labeling |

Paths are relative to the configured data directory (default: `Test Data/`).
