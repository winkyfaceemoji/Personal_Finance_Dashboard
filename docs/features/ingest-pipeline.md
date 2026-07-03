# Ingest pipeline (`main.py`)

The pipeline converts raw bank CSVs into a single, deduplicated, schema-normalised master file. Run it once per batch of new exports before starting the dashboard — or click **RELOAD DATA** in the browser to run it without leaving the app.

---

## Inputs

Drop CSV files into `Data/RAW/`. The pipeline auto-detects the bank format from the column headers. Three formats are supported:

| Format constant | Source | Key columns used |
|----------------|--------|-----------------|
| `chase_debit` | Chase chequing/debit | `Posting Date`, `Description`, `Amount`, `Type`, `Balance`, `Check or Slip #` |
| `chase_credit` | Chase credit card | `Transaction Date`, `Post Date`, `Description`, `Category`, `Type`, `Amount`, `Memo` |
| `discover_credit` | Discover credit card | `Trans. Date`, `Post Date`, `Description`, `Amount`, `Category` |

Files with unrecognised headers are skipped with a `[SKIP]` log line. Multiple files from the same source can coexist in `Data/RAW/` — duplicates are removed later.

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
1. Glob Data/RAW/ for *.csv (recursive)
2. For each file:
   a. Read with pandas, strip column-header whitespace
   b. detect_format() → match header set against known signatures
   c. Call the matching normaliser → unified-schema DataFrame
   d. Extract card_last4 from filename (Chase files only)
3. Concatenate all normalised frames
4. Deduplicate on all columns except card_last4
   (same transaction exported from two overlapping date-range files → one row)
5. Sort by date ascending
6. Write Data/SORTED/combined_transactions.csv  (raw pipeline output)
7. merge_into_master()
```

---

## Master file merge (`merge_into_master`)

The master file `edited_combined_transactions.csv` adds user-assigned columns: `master_category` and `sub_category`. The merge logic ensures existing assignments are never overwritten.

```
For each row in the freshly combined data:
  Build a match key from all unified columns except card_last4
  If that exact key already exists in the master file → skip (preserve master_category / sub_category)
  If it is new → append with master_category = None, sub_category = None

Backfill card_last4 for any existing rows where it is blank.
Re-sort the master file by date, write back.
```

If the master file does not exist yet (first run), it is created from the combined data with `master_category` and `sub_category` set to `None`.

**Match key detail:** `MATCH_COLUMNS` = all unified columns except `card_last4`. Excluding `card_last4` means existing rows are matched correctly even if the card number wasn't captured in a previous run.

---

## Schema migrations

On each run, `merge_into_master` checks for and automatically applies these one-time migrations to the master file:

| Migration | Condition | Action |
|-----------|-----------|--------|
| Rename `category` → `original_category` | Old `category` column present | Renames in-place |
| Add `sub_category` | Column missing | Added with blank values |
| Add `card_last4` | Column missing | Added, then backfilled from current ingest |
| Fix Discover amount signs | Flag file absent | Removes wrong-sign duplicate Discover rows |

---

## Outputs

| File | Updated by | Used by |
|------|-----------|---------|
| `Data/SORTED/combined_transactions.csv` | Every pipeline run | Not read by the app directly |
| `Data/SORTED/edited_combined_transactions.csv` | Every pipeline run (append-only for new rows) | `app.py` on startup and after reload |
