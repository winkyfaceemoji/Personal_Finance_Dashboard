# Overview charts

The dashboard is a single page of five cards, top to bottom:

1. **Performance card** — all-years totals, independent of every filter
2. **Cash Flow card** — monthly bars with YTD/1Y/3Y range chips and a Net/Expenses/Income dropdown
3. **Trends card** — same-month year-over-year lines (always all data)
4. **Categories card** — spend pie per year, with click drilldown (see [category-breakdown.md](category-breakdown.md))
5. **Import/export card** (see [import-export.md](import-export.md))

Cards 1–4 are produced by the single `update_overview` callback. The page header holds the title, a subtitle listing the sources and when the data was last updated (`3 sources: Chase Credit, Chase Debit, Discover Credit · updated Jul 05, 2026` — the master file's mtime, refreshed after imports/reloads via the `data-updated` callback), and the settings gear. There is no source filter and no chart selector — each graph carries only its own controls.

---

## Performance card (`performance-card` / `performance-title`)

Titled `PERFORMANCE · ALL YEARS`, first thing on the page. Four metrics over the entire dataset — deliberately unaffected by any control, so it always answers "where do I stand overall":

| Metric | Value |
|--------|-------|
| Total Expenses | Sum of `monthly_expenses(df)` |
| Total Income | Sum of `monthly_income(df)` |
| Net | Income − expenses; green when ≥ 0, red when negative |
| Savings rate | `net / income` (— when there is no income) |

Negative values render as `-$1,372.65` (sign before the dollar sign). No deltas — all-years has no prior window to compare against.

---

## Cash Flow card (`net-position-chart` / `net-position-header`)

Titled `CASH FLOW · {range label}`. Monthly bars of one metric within a calendar-anchored window:

- **Range chips** (`summary-range`): YTD (default, Jan 1 → now), 1Y (trailing 12 calendar months), 3Y (trailing 36). Computed by `_range_window`; anchored to *today*, not the newest data. These chips affect only this chart.
- **Metric dropdown** (`cashflow-metric`): Net (green/red bars by sign, with a zero line), Expenses (red bars), or Income (green bars).

There is deliberately no cumulative/net-worth line — the app monitors period cash flow, not account balances.

---

## Trends chart (`overview-main-chart`)

Titled `TRENDS · {metric} BY CALENDAR MONTH`. Same-calendar-month year-over-year comparison of one metric at a time — expenses or income, picked by the Expenses/Income radio (`toggle-income-expenses`) in the card header.

**This chart has no range control** — it is inherently an all-years chart: one `Scatter` line per calendar year over a fixed Jan–Dec axis, so every February shares a column and Feb '25 vs Feb '26 is a straight vertical read.

- Each year gets its own colour from `PIE_COLORS`, stable across metric switches, with a year legend.
- The **current year** is drawn heaviest (3.5px, full opacity, larger markers); other years are thin at 0.55 opacity.
- Hover on any point shows the value plus the change vs the same month the prior year (`+$312 (+18%) vs Mar 2025`); blank when the prior year has no data for that month.
- Partial years simply render as shorter lines (missing months are gaps, not zeros).

A cumulative "pace" variant of this chart was tried and reverted — the monthly shape (spike months, seasonality) is information only this chart carries.

---

All numbers everywhere are **label-based**: expenses are rows with `master_category == "Expense"`, income is rows with `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total — the import/export card's note shows how many non-Transfer rows are being ignored.

---

## Theme

All Plotly figures use transparent backgrounds and pull colours from `_CHART[theme]`, a dict of hex values for the current dark/light theme. The chart template (`chart_template(theme)`) sets paper/plot background to transparent so the card's CSS background shows through.
