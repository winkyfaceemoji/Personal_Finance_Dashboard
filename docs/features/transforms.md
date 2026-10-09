---
type: Feature Doc
title: Data transforms layer
description: Loads the master file and provides auto-labeling rules, period (week / month / year) maths, and aggregation helpers.
resource: Modules/transforms.py
updated: 2026-10-09
---

# Data transforms layer (`Modules/transforms.py`)

Data loading, labeling, and the money maths live here: totals, period windows, "typical" medians, and pace. `app.py` calls these and keeps only presentation-level grouping — the merchant rollup and the top-N category split in the drilldown. The period helpers are pure functions covered by `tests/test_periods.py`.

Two sibling modules sit beside it: `Modules/safety.py` (backups, atomic writes, restore — the only code that writes the master) and `Modules/labels.py` (applying an imported CSV's labels). See [ingest-pipeline.md](ingest-pipeline.md) and [import-export.md](import-export.md).

---

## Category constants

```python
PREDEFINED_CATEGORIES = ["Expense", "Income", "Transfer"]
```

These are the three valid values for `master_category`.

---

## `apply_auto_categories(df, rules_path)`

Keyword-based **auto-labeling**: rules assign `master_category` (and optionally `sub_category`) to rows that arrive from the ingest with no label — so new statements count in the totals without waiting for the Excel round-trip.

- Loads `rules.csv` (columns: `keyword`, `master_category`, `sub_category` — both labels optional but a rule needs at least one; legacy files with a single `category` column are read as `master_category`)
- Keyword matching is a case-insensitive raw substring match (not regex) against the description — note that bank descriptions can be column-padded (`venmo            payment`), so a multi-word keyword may not match where a single word does
- **Master labels** apply only to rows whose `master_category` is blank — a hand-assigned label always wins, and the first matching rule wins per row. Rules whose `master_category` isn't one of `Expense` / `Income` / `Transfer` are skipped (a typo would otherwise create rows that every total ignores)
- **Sub-categories** fill any matching row whose own `sub_category` is blank, provided the rule's master (when it has one) agrees with the row's label — so a rule never puts its sub on a row the user labeled as something else. **Sub-only rules** (blank master) apply to any matching row; they exist for descriptions like `venmo` that are too ambiguous to master-label but still deserve a display category in the category breakdown
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
7. Compute `effective_category` (vectorised):
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

## Periods

Everything time-based in the dashboard goes through these. Granularities are named `"week"`, `"month"`, `"year"`; **weeks run Monday → Sunday** (`PERIOD_FREQS`: `W-SUN`, `M`, `Y`). Periods are pandas `Period` objects.

| Function | Returns |
|----------|---------|
| `to_period(ts, freq)` | The week / month / year containing a timestamp |
| `period_label(p, freq)` | `Dec 22 – 28, 2025` · `Dec 29, 2025 – Jan 4, 2026` · `Dec 2025` · `2025` (built from `.day`, not `%-d`, which Windows doesn't support) |
| `period_short_label(p, freq)` | Axis labels: `Dec 22` (week start) · `Dec '25` · `2025` |
| `filter_window(df, start, end)` / `filter_period(df, p)` | Rows dated inside a window / period, both ends inclusive |
| `window_totals(df)` | `{"exp", "inc", "net"}` for a slice of rows — label-based, expenses positive, refunds netting |
| `period_totals(df, freq)` | One row per period from the first to the last transaction, **gap periods included as zeros**; columns `exp`, `inc`, `net` |
| `previous_periods(p, freq, first)` | The periods "typical" is measured over: up to `TYPICAL_LOOKBACK` (12 weeks / 12 months / every year) before `p` |
| `to_date_totals(df, p, days)` | Totals for the first `days` days of `p` — the like-for-like comparison for an in-progress period |
| `period_summary(df, freq, p, as_of)` | Everything the stat cards and pace strip need — see below |

`period_summary` treats `p` as **in progress** when it contains `as_of` (the newest transaction date) and runs past it. It returns:

- `cur` — totals for `p` (to date, if in progress)
- `prev` — the previous period, truncated to the same number of days when `p` is in progress
- `typical` — medians over `previous_periods`, truncated the same way; `typical_full` — the same medians over whole periods (the pace target)
- `rate`, `prev_rate`, `typical_rate` — savings rate (net ÷ income, %), `None` without income
- `partial`, `days_elapsed`, `days_total`, `prev_period`, `n_typical`

`prev` / `typical` are `None` when there's no earlier period in the data.

## Header helpers

| Function | Returns |
|----------|---------|
| `unlabeled_summary(df)` | `{"count", "total", "amount"}` — rows with no valid label (not Expense / Income / Transfer) and their absolute dollar size, for the header note |
| `source_freshness(df)` | Newest transaction date per source, newest first — drives `data through …` and the `behind:` list |

## Enumeration helpers

| Function | Returns |
|----------|---------|
| `available_months(df)` | Sorted list of `month_str` values present in the data (NaN-safe) |
| `available_years(df)` | Sorted list of integer years |
| `available_sources(df)` | Sorted list of source strings |
| `available_categories(df)` | Merged sorted list of `PREDEFINED_CATEGORIES` + any custom `master_category` values already in the data |
| `get_uncategorized(df)` | Rows where `master_category == ""` |

These aren't used by the dashboard today; they're kept for scripting against the master file.
