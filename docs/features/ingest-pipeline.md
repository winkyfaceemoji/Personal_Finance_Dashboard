# Ingest pipeline (`main.py`)

The pipeline converts raw bank CSVs into a single, schema-normalised master file, rebuilt fresh from `RAW/` on every run. Run it once per batch of new exports before starting the dashboard — or click **RELOAD DATA** in the browser (Settings menu, top right) to run it without leaving the app. Both paths call the exact same `main()` function, so there's only one code path to reason about.

---

## Launch modes

| Mode | Command | Hot-reload |
|------|---------|-----------|
| venv (local) | `.venv\Scripts\python main.py` | No — restart manually |
| Docker (dev) | `docker run -p 8050:8050 -v "%cd%:/app" personal-finance` | Yes — Dash reloads on `.py` save |
| Docker (prod) | `docker run -p 8050:8050 personal-finance` | No — code is baked into image |

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

Drop CSV files into the configured `RAW/` folder (default: `Test Data/RAW/`). The pipeline auto-detects the bank format from the column headers. Three formats are supported:

| Format constant | Source | Key columns used |
|----------------|--------|-----------------|
| `chase_debit` | Chase chequing/debit | `Posting Date`, `Description`, `Amount`, `Type`, `Balance`, `Check or Slip #` |
| `chase_credit` | Chase credit card | `Transaction Date`, `Post Date`, `Description`, `Category`, `Type`, `Amount`, `Memo` |
| `discover_credit` | Discover credit card | `Trans. Date`, `Post Date`, `Description`, `Amount`, `Category` |

Files with unrecognised headers are skipped with a `[SKIP]` log line. Multiple files from the same source — including overlapping re-exports of the same account's history — can coexist in the configured `RAW/` folder; the pipeline resolves the overlap itself (see [Merging overlapping exports](#merging-overlapping-exports-_merge_by_coverage) below).

**Chase file naming:** Chase exports follow the pattern `Chase{last4}_Activity...csv`. The pipeline extracts the 4-digit card number from the filename and stores it in the `card_last4` column.

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
| `source` | str | `"Chase Debit"`, `"Chase Credit"`, or `"Discover Credit"` |
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
   d. Extract card_last4 from filename (Chase files only)
4. Group normalised frames by physical account: (source, card_last4)
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
For each (source, card_last4) account:
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
Build a match key (MATCH_COLUMNS = all unified columns except card_last4)
  for every row in both the prior master file and the freshly rebuilt data.

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

**Backup:** before rebuilding, the existing master file is renamed to `edited_combined_transactions.csv.bak` (overwriting any previous backup). This is a rolling one-generation backup, not a full history — enough to recover from a bad run without accumulating files indefinitely.

---

## Outputs

| File | Updated by | Used by |
|------|-----------|---------|
| `SORTED/combined_transactions.csv` | Every pipeline run (full rebuild) | Not read by the app directly |
| `SORTED/edited_combined_transactions.csv` | Every pipeline run (full rebuild; categorization carried forward by match key) | `app.py` on startup and after reload |
| `SORTED/edited_combined_transactions.csv.bak` | Every pipeline run (overwritten each time) | Manual recovery only — not read by the app |

Paths are relative to the configured data directory (default: `Test Data/`).
