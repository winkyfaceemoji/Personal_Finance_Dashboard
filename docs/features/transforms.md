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

Called inside `load_transactions` after `effective_category` is computed. Applies keyword-based auto-categorization to rows that have no `master_category`.

- Loads `rules.csv` (columns: `keyword`, `category`)
- For each rule, matches rows where `master_category == ""` and the description contains the keyword (case-insensitive, substring match, not regex)
- First matching rule wins; earlier rules in the file take priority
- `master_category` always takes precedence — rules only affect rows with no user override
- If `rules_path` is None or the file does not exist, returns `df` unchanged

---

## `load_transactions(path, rules_path=None)`

Called once at `app.py` startup and again after any data-modifying operation (import, reload). Returns the global `df` DataFrame that every callback reads from.

Steps:
1. Read `edited_combined_transactions.csv` with `parse_dates=["date", "post_date"]` and `dtype={"card_last4": str}`
2. Ensure `master_category`, `sub_category`, and `card_last4` columns exist
3. Coerce `amount` to numeric; drop rows where it could not be parsed
4. Backward-compat rename: `category` → `original_category` if the old column name is present
5. Normalise string columns: strip whitespace, fill NaN with `""`
6. Compute `effective_category`:
   - `master_category` if non-empty (user's override wins)
   - else `original_category` if non-empty (bank-provided)
   - else `"Uncategorized"`
7. Add convenience columns: `month` (Period), `month_str` (YYYY-MM string), `year` (int)
8. Call `apply_auto_categories(df, rules_path)` — fills `effective_category` for uncategorized rows that match a keyword rule

**`effective_category`** is the single label used throughout the dashboard for filtering and aggregation.

---

## Row-type helpers

Bucketing is **label-based**: only the `master_category` label decides whether a row counts, never the sign of the amount.

| Function | Returns |
|----------|---------|
| `get_expenses(df)` | Copy of rows where `master_category == "Expense"` |
| `get_income(df)` | Copy of rows where `master_category == "Income"` |

Everything else is ignored by every income and expense calculation: `Transfer` rows deliberately, and unlabeled rows (or rows with any other label) because they haven't been classified yet. The All Transactions tab shows a count of ignored rows that aren't Transfers.

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
