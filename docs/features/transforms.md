---
type: Feature Doc
title: Data transforms layer
description: Loads the master file and provides auto-labeling rules and aggregation helpers.
resource: Modules/transforms.py
updated: 2026-07-06
---

# Data transforms layer (`Modules/transforms.py`)

All data loading and aggregation logic lives here. `app.py` imports from this module and never builds aggregations inline, keeping the dashboard callbacks free of raw pandas work.

---

## Category constants

```python
PREDEFINED_CATEGORIES = ["Expense", "Income", "Transfer"]
```

These are the three valid values for `master_category`. `available_categories(df)` merges this list with any custom values already present in the data for dropdown population.

---

## `apply_auto_categories(df, rules_path)`

Keyword-based **auto-labeling**: rules assign `master_category` (and optionally `sub_category`) to rows that arrive from the ingest with no label — so new statements count in the totals without waiting for the Excel round-trip.

- Loads `rules.csv` (columns: `keyword`, `master_category`, `sub_category` — both labels optional but a rule needs at least one; legacy files with a single `category` column are read as `master_category`)
- Keyword matching is a case-insensitive raw substring match (not regex) against the description — note that bank descriptions can be column-padded (`venmo            payment`), so a multi-word keyword may not match where a single word does
- **Master labels** apply only to rows whose `master_category` is blank — a hand-assigned label always wins, and the first matching rule wins per row. Rules whose `master_category` isn't one of `Expense` / `Income` / `Transfer` are skipped (a typo would otherwise create rows that every total ignores)
- **Sub-categories** fill any matching row whose own `sub_category` is blank, provided the rule's master (when it has one) agrees with the row's label — so a rule never puts its sub on a row the user labeled as something else. **Sub-only rules** (blank master) apply to any matching row; they exist for descriptions like `venmo` that are too ambiguous to master-label but still deserve a display category in the pie
- Labels are applied **in-memory on every load and never written to the master file** — editing `rules.csv` retroactively re-labels all history, and deleting a rule un-labels those rows on the next load
- If `rules_path` is None or the file does not exist, returns `df` unchanged

One consequence of the in-memory design: **EXPORT CSV exports the loaded frame**, so exports include rule-applied labels, and importing that file back writes them into the master permanently. Rule labels become durable only through that round-trip.

---

## `load_transactions(path, rules_path=None)`

Called once at `app.py` startup and again after any data-modifying operation (import, reload). Returns the global `df` DataFrame that every callback reads from.

Steps:
1. Read `edited_combined_transactions.csv` with `parse_dates=["date", "post_date"]` and `dtype={"card_last4": str}`
2. Ensure `master_category`, `sub_category`, `card_last4`, and `institution` columns exist (blank-backfilled for masters built before a column was added)
3. Coerce `amount` to numeric; drop rows where it could not be parsed
4. Backward-compat rename: `category` → `original_category` if the old column name is present
5. Normalise string columns: strip whitespace, fill NaN with `""`
6. Call `apply_auto_categories(df, rules_path)` — auto-labels unlabeled rows so the derived columns below pick the labels up
7. Compute `effective_category`:
   - `master_category` if non-empty (user's override or rule label)
   - else `original_category` if non-empty (bank-provided)
   - else `"Uncategorized"`
8. Add convenience columns: `month` (Period), `month_str` (YYYY-MM string), `year` (int)

---

## Row-type helpers

Bucketing is **label-based**: only the `master_category` label decides whether a row counts, never the sign of the amount.

| Function | Returns |
|----------|---------|
| `get_expenses(df)` | Copy of rows where `master_category == "Expense"` |
| `get_income(df)` | Copy of rows where `master_category == "Income"` |

Everything else is ignored by every income and expense calculation: `Transfer` rows deliberately, and unlabeled rows (or rows with any other label) because they haven't been classified yet. A note in the page header shows a count of ignored rows that aren't Transfers.

---

## Aggregation helpers

All accept a filtered DataFrame and return a small summary DataFrame ready for Plotly.

### Monthly

| Function | Output columns | Sort |
|----------|---------------|------|
| `monthly_expenses(df)` | `month_str`, `total_expenses` (positive) | `month_str` ascending |
| `monthly_income(df)` | `month_str`, `total_income` | same |

### Yearly

| Function | Output columns | Sort |
|----------|---------------|------|
| `yearly_expenses(df)` | `year`, `total_expenses` (positive) | `year` ascending |
| `yearly_income(df)` | `year`, `total_income` | same |

Expense totals are negated sums (not absolute values), so a refund row labeled `Expense` (positive amount) nets against — reduces — the expense total rather than inflating it.

### By category

`expenses_by_category(df, month_str=None)` — groups Expense-labeled rows by `category_display`, optionally pre-filtered to a single month. Returns `category`, `total_expenses` sorted by total descending.

---

## Enumeration helpers

Used at startup to populate filter dropdowns.

| Function | Returns |
|----------|---------|
| `available_months(df)` | Sorted list of `month_str` values present in the data (NaN-safe) |
| `available_years(df)` | Sorted list of integer years |
| `available_sources(df)` | Sorted list of source strings |
| `available_categories(df)` | Merged sorted list of `PREDEFINED_CATEGORIES` + any custom `master_category` values already in the data |
| `get_uncategorized(df)` | Rows where `master_category == ""` |
