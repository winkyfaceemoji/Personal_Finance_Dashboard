# Overview charts

All charts live on the Summary tab and are produced by the `update_overview` callback. They re-render together whenever any global filter, the view toggle, or the refresh trigger changes.

---

## View toggle

A radio button in the filter bar (VIEW) switches between two modes:

| Mode | `view_mode` value | Main chart shows |
|------|------------------|-----------------|
| MONTH BY MONTH | `"monthly"` | One bar per calendar month in the filtered data |
| ALL YEARS | `"yearly"` | One bar per calendar year (source-filtered only, so all years appear even when a specific year is selected) |

---

## Main bar chart (`overview-main-chart`)

Grouped bar chart of expenses and/or income, toggled by the **SHOW ON CHARTS** checklist.

### Monthly mode

- **Expenses bar**: `monthly_expenses(filtered, excluded)` → one bar per `month_str`.
- **Income bar**: `monthly_income(filtered, excluded)` → one bar per `month_str`.
- X-axis labels: abbreviated month names (`"Jan"`, `"Feb"`, …) when a specific year is filtered; `"Jan '24"` style when year = All (prevents duplicate labels across years).
- **3-month rolling average** (expenses only): shown as a dashed line overlay whenever there are 2 or more months in view. Computed with `rolling(3, min_periods=1).mean()` so it degrades gracefully to a 1-month window at the start of the series.

### Yearly mode

- **Expenses bar**: `yearly_expenses(source_df, excluded)` — source-filtered but not year/month filtered, so all years appear.
- **Income bar**: `yearly_income(source_df, excluded)` — same.
- No rolling average in yearly mode.

`excluded` is `EXCLUDED_CATEGORIES` (`{"Transfer"}`), applied to all income and expense calculations. Rows tagged `Transfer` in `master_category` are excluded from every number on this tab.

---

## Net chart (`net-chart`)

Shows `income − expenses` per period. Always uses the fully filtered `data_df`.

**Construction:**
1. `monthly_expenses(data_df, excluded)` and `monthly_income(data_df, excluded)`, renamed to `exp` and `inc`.
2. Outer-merged on `month_str`, filled with `0` for months where only one side has data, then sorted by `month_str` so income-only or expense-only months land in chronological position.
3. In **yearly mode**, the month-level rows are grouped into year buckets by summing `net`.

**Colour:** each bar is independently coloured — green (`accent3`) when net ≥ 0, red (`accent2`) when negative. A horizontal zero line marks the break-even point.

---

## Summary stat cards (`summary-stats`)

Three cards rendered as a 3-column grid below the filter bar.

| Card | Value | Label |
|------|-------|-------|
| Total Expenses | Sum of `monthly_expenses(data_df, excluded)["total_expenses"]` | "TOTAL EXPENSES · {period_label}" |
| Total Income | Sum of `monthly_income(data_df, excluded)["total_income"]` | "TOTAL INCOME · {period_label}" |
| Average spend | Mean of monthly totals (monthly mode) or mean of yearly totals (yearly mode) | "AVG MONTHLY SPEND" or "AVG YEARLY SPEND" |

### MoM / YoY delta

When a specific month or year is selected, each card shows a delta line below the dollar value comparing the current period to the prior one:

- **Month selected** → compares to the previous calendar month
- **Year selected** → compares to the previous year
- Format: `+$142 (+8%) vs prior` in green when favourable, red when unfavourable
- Expenses: green = decreased (lower is better); Income: green = increased (higher is better)
- No delta is shown when All Months / All Years is selected (no single prior period to compare)
- Both prior-period expense and income calculations also pass `excluded`, so `Transfer` rows never affect deltas

`period_label` reflects the active filter scope — see [global-filters.md](global-filters.md).

---

## Theme

All Plotly figures use transparent backgrounds and pull colours from `_CHART[theme]`, a dict of hex values for the current dark/light theme. The chart template (`chart_template(theme)`) sets paper/plot background to transparent so the card's CSS background shows through.
