# Category breakdown & drilldown

The Categories view of the graph card (`category-bar-chart`). It has two modes, following the range chips:

- **1M** — a snapshot of the current month: horizontal spend bars.
- **YTD / 1Y / 3Y** — share trend lines: each category's % of that month's spending over the months in the range.

Only rows labeled `Expense` in `master_category` are counted in either mode, matching the Summary totals, and both modes respect the summary source dropdown.

---

## Share trend lines (YTD / 1Y / 3Y)

One `Scatter` line per category, y = the category's percentage of that month's total spending — so a rising line is a category eating a growing share, regardless of whether overall spending grew.

- **Top 5 + Other:** the five largest categories (by total spend within the range) get their own line; the rest collapse into `Other · {n} categories`. Line colours come from `PIE_COLORS` in rank order.
- **Hover:** `18% of spend · $432` plus the percentage-point change vs the prior month (`+3pp vs prior month`; blank on each line's first point).
- Months where nothing was spent at all render as gaps; a category with no spending in a month sits at 0%.
- Each point's `customdata` carries `(amount, pp-delta, category name)` — the name is what lets the drilldown identify the clicked line.

## Snapshot bars (1M)

Horizontal bars for the current month, sorted largest-to-smallest via `expenses_by_category(data_df)`.

- **Top 10 + Other:** only the 10 largest categories get their own bar; the rest collapse into `Other · {n} categories` so the card height stays stable.
- **Bar labels:** each bar shows its total (`$432`) and, when the prior month is fully covered by data, the change against it (`$432 · +$120`). A category absent from the prior month counts as $0; the `Other` bar's delta compares against the prior spend of all non-top-10 categories. Hover shows share of total (`% of total`).

Both modes use the same range window as the performance card, so totals always agree with it and with the drilldown.

---

## Click drilldown (`category-drilldown`)

Clicking opens a transaction table directly below the chart:

- **Snapshot bar click** → that category's transactions for the current month; the category comes from `clickData["points"][0]["y"]`.
- **Share-line point click** → that category's transactions for that specific month; the category comes from the point's `customdata[2]` and the month from parsing the x label (`"Mar '26"` → `2026-03`). The drilldown header appends the month: `TRANSACTIONS — FOOD & DRINK · MAR '26`.
- Clicking the `Other · {n} categories` bar/line → no drilldown (it's an aggregate, not a real category).
- Changing the range or summary source → drilldown clears immediately (returns an empty div); click again for the new context. This prevents stale data from being visible while the charts have already updated.

### What it shows

| Element | Detail |
|---------|--------|
| Header line | Category name (all-caps), plus the month for line clicks |
| Summary line | Total spend and transaction count in scope |
| DataTable | Up to 100 most-recent transactions, paginated at 15 rows; natively sortable |
| Columns | Date, Description, Amount (formatted `$x,xxx.xx`), Source |

The `total` in the summary line is computed from all matching transactions (not capped at 100), so the dollar figure is always accurate even when the table is truncated. The drilldown filters on `category_display == category` (blank mapped to "Uncategorized") and keeps only rows labeled `Expense` — the same rule as the chart, so drilldown totals always match the clicked bar or point.

---

## Colours

Both modes use `PIE_COLORS`, a fixed 12-colour palette (`#6c8aff`, `#ff6c8a`, `#6cffd4`, …), assigned in spend-rank order. The drilldown table uses the theme's `accent2` colour for the summary total.
