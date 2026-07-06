# Overview charts

The dashboard is a single page of four cards, top to bottom:

1. **Summary card** — four YTD stat cards (income, expenses, net, savings rate), each with a same-period-last-year delta
2. **Cash Flow card** — monthly bars with YTD/1Y/3Y range chips and a Net/Expenses/Income dropdown
3. **Trends card** — same-month year-over-year lines (always all data)
4. **Categories card** — spend pie per year, with click drilldown (see [category-breakdown.md](category-breakdown.md))

Cards 1–4 are produced by the single `update_overview` callback. The page header holds the title, a subtitle listing the sources and the latest transaction date (`3 sources: Chase Credit, Chase Debit, Discover Credit · latest transaction Jun 27, 2026` — the newest `date` in the data, refreshed after imports/reloads via the `data-updated` callback), a red note on its own line counting unlabeled rows, and the settings gear (which holds import/export, reload, change-folder, and theme — see [import-export.md](import-export.md)). There is no source filter and no chart selector — each graph carries only its own controls.

---

## Summary card (`performance-card`)

First thing on the page: four stat cards in a responsive grid (`repeat(auto-fit, minmax(190px, 1fr))`), one per metric. Every card is **year-to-date** — January 1 through the current month of this year — with a delta against the same months last year (apples-to-apples, so a partial current year isn't compared against a full prior year):

| Card | Value | Higher is… |
|------|-------|-----------|
| YTD Income | Sum of `monthly_income` over Jan → current month | good |
| YTD Expenses | Sum of `monthly_expenses` over Jan → current month | bad |
| YTD Net | Income − expenses | good |
| YTD Savings rate | `net / income` (— when there is no income) | good |

The big number is neutral (white/black per theme). Beneath it sits the delta: a coloured, bold change figure followed by a muted `vs last year`.

**Delta direction & colour.** Income/expenses/net compare as a percentage change; savings rate compares in **percentage points** (`▲26pt`), since it is already a percentage. The arrow and colour signal *good vs bad for that metric*, not merely up/down — an increase in income is green, an increase in expenses is red, and so on (`higher_is_good` per card). The percentage is `(cur − prior) / |prior|`, dividing by the *absolute* prior so the arrow stays correct even when last year's figure was negative (e.g. a negative net). A delta is blank when there is no prior-year figure to compare against.

---

## Cash Flow card (`net-position-chart`)

Monthly bars of one metric within a calendar-anchored window. The card has no separate title — the metric dropdown on the left doubles as the title (styled like the other card headers), with the range chips on the right:

- **Metric dropdown** (`cashflow-metric`, left): Net Cash Flow (green/red bars by sign, with a zero line), Expenses (red bars), or Income (green bars). Not searchable — it reads as a heading.
- **Range chips** (`summary-range`, right): YTD (default, Jan 1 → now), 1Y (trailing 12 calendar months), 3Y (trailing 36). Computed by `_range_window`; anchored to *today*, not the newest data. These chips affect only this chart. The selected chip is highlighted (accent tint + border).

There is deliberately no cumulative/net-worth line — the app monitors period cash flow, not account balances.

---

## Trends chart (`overview-main-chart`)

Titled `{metric} BY CALENDAR MONTH`. Same-calendar-month year-over-year comparison of one metric at a time — expenses or income, picked by the Expenses/Income pill toggle (`toggle-income-expenses`, selected pill highlighted) in the card header.

**This chart has no range control** — it is inherently an all-years chart: one `Scatter` line per calendar year over a fixed Jan–Dec axis, so every February shares a column and Feb '25 vs Feb '26 is a straight vertical read.

- Each year gets its own colour from `PIE_COLORS`, stable across metric switches, with a year legend.
- The **current year** is drawn heaviest (3.5px, full opacity, larger markers); other years are thin at 0.55 opacity.
- Hover on any point shows the value plus the change vs the same month the prior year (`+$312 (+18%) vs Mar 2025`); blank when the prior year has no data for that month.
- Partial years simply render as shorter lines (missing months are gaps, not zeros).

A cumulative "pace" variant of this chart was tried and reverted — the monthly shape (spike months, seasonality) is information only this chart carries.

---

All numbers everywhere are **label-based**: expenses are rows with `master_category == "Expense"`, income is rows with `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total — a red note in the page header shows how many non-Transfer rows are being ignored.

---

## Theme

All Plotly figures use transparent backgrounds and pull colours from `_CHART[theme]`, a dict of hex values for the current dark/light theme. The chart template (`chart_template(theme)`) sets paper/plot background to transparent so the card's CSS background shows through.
