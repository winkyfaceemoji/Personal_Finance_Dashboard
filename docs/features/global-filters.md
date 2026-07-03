# Global filters

The filter bar sits at the top of every page and applies to **both tabs** simultaneously — changing any filter updates the Summary charts and the All Transactions table at the same time.

---

## Controls

| Control | ID | Default | Notes |
|---------|----|---------|-------|
| Source | `global-source-filter` | All Sources | One entry per distinct `source` value in the data |
| Year | `global-year-filter` | All Years | One entry per distinct year |
| Month | `global-month-filter` | All Months | Options update based on active Source + Year; resets to All when either changes |
| Show on Charts | `toggle-income-expenses` | Expenses | Checklist to include/exclude expenses and income bars |
| View | `overview-view-toggle` | Month by Month | Switches between monthly and yearly chart mode |
| Uncategorized badge | `uncategorized-count` | — | Shows "⚠ N uncategorized" when transactions have no master category; empty when all are categorized |
| Reload Data | `reload-data-btn` | — | Re-runs `main.main()` in-process, reloads `df`, increments `refresh-trigger` |

---

## `apply_global_filters(source, year, month)`

Single function in `app.py` that every chart callback and the transaction table call to narrow the global `df`:

```python
def apply_global_filters(source, year, month="all"):
    filtered = df.copy()
    if source != "all":
        filtered = filtered[filtered["source"] == source]
    if year != "all":
        filtered = filtered[filtered["year"] == int(year)]
    if month != "all":
        filtered = filtered[filtered["month_str"] == month]
    return filtered
```

---

## Filter scope

All three dropdowns apply consistently. The same `filtered` DataFrame drives the net chart, category bar chart, summary stat cards, category drilldown, and the All Transactions table.

The one deliberate exception is the **ALL YEARS bar chart** (VIEW = ALL YEARS). That chart uses a source-only slice so all years appear side-by-side even when a specific year is selected. All other panels use the fully filtered data.

---

## Filter interaction rules

| Event | What updates |
|-------|-------------|
| Source changes | Month dropdown options + value reset; all charts and table re-render |
| Year changes | Month dropdown options + value reset; all charts and table re-render |
| Month changes | All charts and table re-render; month dropdown options unchanged |
| View changes | Summary charts re-render (monthly vs yearly mode) |
| Reload Data clicked | Ingest runs, `df` reloads, all charts and table re-render |
| Any filter changes | Category drilldown clears (stale data is not shown) |

---

## Stat card labels

The `period_label` shown in the stat card titles reflects the active filter scope:

| Filters active | Label |
|----------------|-------|
| Month selected | "Mar 2024" (formatted from the month_str value) |
| Year only | "2024" |
| Neither | "ALL YEARS" |

---

## Expense exclusions

`Transfer Out` and `Credit Card Payment` categories are always excluded from expense totals, regardless of filters. This prevents internal transfers and credit card payment transactions on the debit account from being double-counted alongside the individual credit card purchases. The exclusion set is defined in `EXCLUDED_CATEGORIES` in `app.py`.
