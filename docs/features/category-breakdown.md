---
type: Feature Doc
title: Category breakdown & drilldown
description: Spend-by-category bars for the selected period, with click-to-merchants drilldown.
resource: app.py
updated: 2026-10-09
---

# Category breakdown & drilldown

The categories card (`category-chart`) shows **spending by category for the selected period** — the week, month, or year picked in the period bar (see [overview-charts.md](overview-charts.md#period-bar)). It's titled `SPEND BY CATEGORY · DEC 2025`; there is no separate control.

- **Sorted horizontal bars** — largest category on top, each labeled `$843 · 41%` (share of the period's spend). Bars rank and compare more accurately than pie slices, and need no per-category colours: every bar is the accent, so there's no palette to tell apart.
- **Top 9 + Other** — the nine largest categories get their own bar; the rest collapse into a muted `Other · {n} categories` bar. The cut is the shared `CAT_TOP_N` constant.
- The category is `category_display` (your `sub_category`, else the bank's category). Only rows labeled `Expense` count, matching every other total. Categories that net to zero or below (refunds only) get no bar.
- A muted hint under the title advertises the drilldown. With no labeled expenses in the period, the chart says so instead of rendering empty.

---

## Click drilldown (`category-drilldown`)

Clicking a bar **highlights it** (the others dim) and opens a compact panel below the chart, scoped to that category and the selected period — a merchant summary, not a transaction table:

| Element | Detail |
|---------|--------|
| Header | Category (all caps) + period (`TAXES · 2025`); total spend, transaction count, and average |
| Top merchants | Up to 5 merchants by spend, each with a proportion bar and `$amount · % · N txns`; the rest roll into a muted `OTHER · N merchants` row. Long names are truncated, with the full name on hover. |
| Largest | The single biggest transaction in scope (`$amount · description · date`) — the audit escape hatch |

- Clicking `Other · {n} categories` pools the small categories it aggregates and shows *their* combined top merchants (`OTHER CATEGORIES · DEC 2025`).
- Clicking the selected bar again deselects it. **Changing the period clears the selection**, so a stale panel never lingers under a chart that has moved on.
- The panel follows theme changes while open (theme is an `Input` of the drilldown callback).

**Merchant grouping:** bank descriptions embed store numbers and ids, so `_merchant` strips digits/`#`/`*` and collapses whitespace before grouping — `STARBUCKS #1234` and `STARBUCKS #98` roll up together.

**Totals always match the bar:** the chart and the drilldown both use `_category_split(rows)`, which returns the top-N frame and the names that roll into Other — so a category's drilldown total equals its bar, and the Other panel equals the Other bar.

### Selection plumbing

The clicked bar is held in a `selected-category` `dcc.Store`, not read from `clickData` directly:

- `select_category` writes the bar's label to the store and resets `clickData` to `None`, so re-clicking the same bar registers as a change. A `period-store` change clears it.
- `highlight_category` `Patch`es only the bars' opacities — a click doesn't rebuild the chart.
- `update_category_chart` reads the store as `State` to keep the highlight across theme changes, but ignores it when the *period* triggered the rebuild — the selection is being cleared in parallel, and reading the stale value would dim the new period's bars.
