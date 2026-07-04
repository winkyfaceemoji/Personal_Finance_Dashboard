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

All three dropdowns apply consistently. The same `filtered` DataFrame drives the main bar chart, category bar chart, summary stat cards, category drilldown, and the All Transactions table.

There is no separate view toggle — the main chart's granularity is derived directly from the Year/Month filters (see [overview-charts.md](overview-charts.md#chart-granularity)), so there's no combination where a chart silently ignores the active filters.

---

## Filter interaction rules

| Event | What updates |
|-------|-------------|
| Source changes | Month dropdown options + value reset; all charts and table re-render |
| Year changes | Month dropdown options + value reset; all charts and table re-render (main chart granularity may switch monthly/yearly) |
| Month changes | All charts and table re-render; month dropdown options unchanged (main chart granularity may switch monthly/yearly) |
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

Rows tagged `Transfer` in `master_category` are excluded from all income and expense totals regardless of filters. This prevents internal transfers, brokerage moves, and credit card payments from being double-counted alongside actual spending. The exclusion set is `EXCLUDED_CATEGORIES = {"Transfer"}` in `app.py`, passed to every `get_expenses` and `get_income` call.
