# Transaction filters

The Source / Year / Month filter card lives on the **All Transactions tab only** and drives the transaction table and unlabeled-rows note. The Summary tab has its own, simpler controls — the 1M/YTD/1Y/3Y range chips and a source dropdown on the graph card (see [overview-charts.md](overview-charts.md)) — and is unaffected by anything on this card.

---

## Controls

| Control | ID | Default | Notes |
|---------|----|---------|-------|
| Quick range chips | `range-this-month` / `range-last-month` / `range-this-year` / `range-all` | — | One click sets Year + Month. "This month" is the current calendar month clamped to the newest month with data; "Last month" is the data month before that |
| Reset | `filters-reset` | — | Sets Source, Year, and Month back to All in one click |
| Period stepper | `period-prev` / `period-next` / `period-stepper-label` | ALL DATA | ‹ › arrows step to the adjacent data month (or year, when no month is selected), crossing year boundaries; disabled at the edges of the data |
| Source | `global-source-filter` | All Sources | One entry per distinct `source` value in the data |
| Year | `global-year-filter` | All Years | One entry per distinct year |
| Month | `global-month-filter` | All Months | Options update based on active Source + Year; the selection is preserved when possible (see interaction rules) |
| Uncategorized badge | `uncategorized-count` | — | Shows "⚠ N uncategorized" when transactions have no master category; empty when all are categorized |
| Reload Data | `reload-data-btn` | — | Re-runs `main.main()` in-process, reloads `df`, increments `refresh-trigger` |

The chips and steppers only ever write the same three dropdown values — everything downstream still flows through `apply_global_filters`, so they add no new filtering semantics.

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

All three dropdowns apply consistently through `apply_global_filters`, which drives the transaction table and the unlabeled-rows note.

---

## Filter interaction rules

| Event | What updates |
|-------|-------------|
| Source changes | Month dropdown options refresh; the selected month is **preserved** if the new source has data for it, otherwise resets to All |
| Year changes | Month dropdown options refresh; the selected **calendar month follows the year** (Feb 2025 → Feb 2024) when that month has data, otherwise resets to All |
| Month changes | The table re-renders; month dropdown options unchanged |
| Quick chip / stepper / reset clicked | Writes the dropdown values; everything above follows |
| Reload Data clicked | Ingest runs, `df` reloads, everything re-renders |

---

## Expense exclusions

Totals are label-based: `get_expenses`/`get_income` in `Modules/transforms.py` select rows by `master_category` (`Expense` / `Income`), so `Transfer` rows and unlabeled rows are excluded from all income and expense totals regardless of filters. This prevents internal transfers, brokerage moves, and credit card payments from being double-counted alongside actual spending.
