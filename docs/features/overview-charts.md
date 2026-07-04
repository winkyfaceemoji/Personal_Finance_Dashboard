# Overview charts

All charts live on the Summary tab and are produced by the `update_overview` callback. They re-render together whenever any global filter or the refresh trigger changes.

---

## Chart granularity

There is no separate view control — `update_overview` derives the granularity directly from the Year/Month filters already selected:

```python
view_mode = "yearly" if (year == "all" and month == "all") else "monthly"
```

| Filters | `view_mode` | Main chart shows |
|---------|------------|-----------------|
| Year = All, Month = All | `"yearly"` | One bar per calendar year |
| A specific year (Month = All), or a specific month | `"monthly"` | One bar per calendar month in the filtered data |

This means every combination of filters maps to exactly one chart granularity — there's no state where a toggle disagrees with the Year/Month filters, or where the chart silently ignores them.

---

## Main bar chart (`overview-main-chart`)

Grouped bar chart of expenses and/or income, toggled by the **SHOW ON CHARTS** checklist.

### Monthly mode

- **Expenses bar**: `monthly_expenses(filtered)` → one bar per `month_str`.
- **Income bar**: `monthly_income(filtered)` → one bar per `month_str`.
- X-axis labels: abbreviated month names (`"Jan"`, `"Feb"`, …) when a specific year is filtered; `"Jan '24"` style when year = All (prevents duplicate labels across years).
- **3-month rolling average** (expenses only): shown as a dashed line overlay whenever there are 2 or more months in view. Computed with `rolling(3, min_periods=1).mean()` so it degrades gracefully to a 1-month window at the start of the series.
- **Average-spend reference line**: a dotted horizontal line at the average spend per period in view (monthly average in monthly mode, yearly average in yearly mode), annotated `avg $X`. Drawn whenever expenses are shown and there are 2 or more periods, so each bar reads as above/below normal at a glance. The rolling average shows the trend; this flat line shows the baseline.

### Yearly mode

- **Expenses bar**: `yearly_expenses(filtered)` — this mode only triggers when Year and Month are both "All", so `filtered` is source-filtered only and every year appears.
- **Income bar**: `yearly_income(filtered)` — same.
- No rolling average in yearly mode (the average-spend reference line still appears).

All numbers on this tab are **label-based**: expenses are rows with `master_category == "Expense"`, income is rows with `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total — the All Transactions tab shows how many non-Transfer rows are being ignored.

---

## Summary stat cards (`summary-stats`)

Four cards rendered as a 4-column grid below the filter bar.

| Card | Value | Label |
|------|-------|-------|
| Total Expenses | Sum of `monthly_expenses(data_df)["total_expenses"]` | "TOTAL EXPENSES · {period_label}" |
| Net | Total income − total expenses; green when ≥ 0, red when negative. A sub-line shows the savings rate (`net / income`, only when income > 0) | "NET · {period_label}" |
| Total Income | Sum of `monthly_income(data_df)["total_income"]` | "TOTAL INCOME · {period_label}" |
| Average spend | Mean of monthly totals (monthly mode) or mean of yearly totals (yearly mode) | "AVG MONTHLY SPEND" or "AVG YEARLY SPEND" |

Negative values render as `-$1,372.65` (sign before the dollar sign). There is no separate net chart — net lives here as a headline number.

### MoM / YoY delta

When a specific month or year is selected, each card shows a delta line below the dollar value comparing the current period to the prior one:

- **Month selected** → compares to the previous calendar month
- **Year selected** → compares to the previous year
- Format: `+$142 (+8%) vs prior` in green when favourable, red when unfavourable
- Expenses: green = decreased (lower is better); Net and Income: green = increased (higher is better)
- The percentage divides by `abs(prev)` so it stays meaningful when the prior net was negative
- No delta is shown when All Months / All Years is selected (no single prior period to compare)
- Prior-period totals use the same label-based rules, so `Transfer` and unlabeled rows never affect deltas

`period_label` reflects the active filter scope — see [global-filters.md](global-filters.md).

---

## Theme

All Plotly figures use transparent backgrounds and pull colours from `_CHART[theme]`, a dict of hex values for the current dark/light theme. The chart template (`chart_template(theme)`) sets paper/plot background to transparent so the card's CSS background shows through.
