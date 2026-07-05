# Overview charts

The dashboard is a single page of three cards; the first two are produced by the `update_overview` callback:

1. **Graph card** — a chart-view dropdown (Net / Trends / Categories), four range chips (1M / YTD / 1Y / 3Y), and a compact source dropdown in the header; one chart body visible at a time.
2. **Performance card** — the range's metrics (expenses, income, net, savings rate) with deltas vs the prior equivalent window.

The third card is the import/export card (see [import-export.md](import-export.md)). The page header row above holds the title and the settings gear. There are no other filters — the range chips and the source dropdown are the entire filtering surface.

## Range chips (`summary-range`)

Calendar-anchored windows computed by `_range_window` in `app.py`:

| Chip | Window | Prior window (for deltas) |
|------|--------|---------------------------|
| 1M | The current calendar month | The previous calendar month |
| YTD (default) | Jan 1 of the current year → now | The previous year's Jan → same month |
| 1Y | Trailing 12 calendar months | The 12 months before those |
| 3Y | Trailing 36 calendar months | The 36 months before those |

Windows are anchored to *today*, not to the newest data — if statements lag the calendar, 1M can legitimately show an empty chart. The `summary-source` dropdown scopes everything on the page to one account.

## Chart selector (`chart-view-toggle`)

A single dropdown swaps which chart body is visible — Net (per-period net bars), Trends (same-month YoY lines), or Categories (share-of-spend trend lines, or snapshot bars on 1M, plus the drilldown). Visibility styles are emitted by `update_overview` itself (the selector is one of its Inputs) so the figure redraw and the unhide land in the same render cycle — a Plotly graph drawn while `display:none` mis-sizes.

---

## Net view (`net-position-chart` / `net-position-header`)

The default chart view: how much you kept (or overspent) per period. Headline numbers live in the performance card below, so the chart carries only a plain title — `MONTHLY NET · TRAILING 1Y` (or `DAILY NET · JUL 2026` on the 1M range).

**Chart:** per-period net bars — green when net ≥ 0, red when negative, with a zero line. Monthly bars for YTD/1Y/3Y; the 1M range switches to **daily** resolution within the current month (days with no transactions render as zero).

There is deliberately no cumulative/net-worth line — the app monitors period cash flow, not account balances.

---

## Trends chart (`overview-main-chart`)

Same-calendar-month year-over-year comparison of one metric at a time — expenses or income, picked by the Expenses/Income radio (`toggle-income-expenses`) in this chart body's header.

**This view deliberately ignores the range chips.** It is inherently an all-years chart: one `Scatter` line per calendar year over a fixed Jan–Dec axis, so every February shares a column and Feb '25 vs Feb '26 is a straight vertical read. The chips keep driving the NET and CATEGORIES views and the performance card; trends always shows the full source-scoped history.

- Each year gets its own colour from `PIE_COLORS`, stable across metric switches, with a year legend.
- The **current year** is drawn heaviest (3.5px, full opacity, larger markers); other years are thin at 0.55 opacity.
- Hover on any point shows the value plus the change vs the same month the prior year (`+$312 (+18%) vs Mar 2025`); blank when the prior year has no data for that month.
- Partial years simply render as shorter lines (missing months are gaps, not zeros).

A cumulative "pace" variant of this chart was tried and reverted — the ahead/behind-last-year aggregate it visualised is already stated numerically by the performance card, while the monthly shape (spike months, seasonality) is information only this chart carries.

All numbers are **label-based**: expenses are rows with `master_category == "Expense"`, income is rows with `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total — the import/export card's note shows how many non-Transfer rows are being ignored.

---

## Performance card (`performance-card` / `performance-title`)

One card below the graphs, titled `PERFORMANCE · {range label}`, holding four metrics in a responsive grid — all computed within the selected range's window:

| Metric | Value | Delta |
|--------|-------|-------|
| Total Expenses | Sum of `monthly_expenses(data_df)` | vs prior window, green when spending fell |
| Total Income | Sum of `monthly_income(data_df)` | vs prior window, green when income rose |
| Net | Income − expenses; green when ≥ 0, red when negative | vs prior window |
| Savings rate | `net / income` (— when the window has no income) | percentage-point change vs the prior window's rate |

Negative values render as `-$1,372.65` (sign before the dollar sign). Dollar deltas read `+$142 (+8%) vs prior`; the percentage divides by `abs(prev)` so it stays meaningful when the prior net was negative. Prior-window totals use the same label-based rules, so `Transfer` and unlabeled rows never affect them.

**Prior-window coverage:** deltas (here and on the category bars) are shown only when the prior window is *fully* covered by data — if it reaches back before the first month in the data, all "vs prior" comparisons are suppressed rather than comparing a full window against a sliver. With ~3.5 years of data, 3Y shows totals only; its deltas appear once 6 years exist.

---

## Theme

All Plotly figures use transparent backgrounds and pull colours from `_CHART[theme]`, a dict of hex values for the current dark/light theme. The chart template (`chart_template(theme)`) sets paper/plot background to transparent so the card's CSS background shows through.
