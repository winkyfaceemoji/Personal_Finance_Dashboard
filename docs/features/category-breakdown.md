# Category breakdown & drilldown

---

## Category bar chart (`category-bar-chart`)

A horizontal bar chart directly below the main chart on the Summary tab. Each bar is one `category_display` value; bar length is total spend for that category under the active filters. Only rows labeled `Expense` in `master_category` are counted, matching the Summary totals.

**Data source:** `expenses_by_category(data_df)` where `data_df = filtered` (all three global filters applied). Bars are sorted largest-to-smallest (most expensive category at the top) because `expenses_by_category` returns rows sorted by `total_expenses` descending.

**Top 10 + Other:** only the 10 largest categories get their own bar. Anything beyond that is collapsed into a single `Other · {n} categories` bar so the card height stays stable regardless of how many categories exist.

**Bar labels and vs-prior deltas:** each bar is annotated with its total (`$432`). When a specific month or year is selected — i.e. whenever the stat cards show a MoM/YoY delta — the label also shows the change against the same prior period: `$432 · +$120`. The prior-period totals come from `expenses_by_category(_prev_df)`; a category absent from the prior period counts as $0, and the `Other` bar's delta compares against the prior spend of all non-top-10 categories. Hovering a bar shows its share of total spend (`% of total`).

The chart always uses the fully filtered data, so its totals match the stat cards and the drilldown below it.

---

## Click drilldown (`category-drilldown`)

Clicking any bar opens a transaction table directly below the chart, scoped to that category and the active filters.

### Trigger

The `category_drilldown` callback has `clickData` from `category-bar-chart` as its only **Input**. Source, year, and month are also **Inputs** (not States), so:

- Clicking a bar → drilldown renders for that category.
- Clicking the `Other · {n} categories` bar → no drilldown (it's an aggregate, not a real category).
- Changing any filter → drilldown clears immediately (returns an empty div). The user must click a bar again to re-open it for the new filter context. This prevents stale data from being visible while the main charts have already updated.

### What it shows

| Element | Detail |
|---------|--------|
| Header line | Category name (all-caps) |
| Summary line | Total spend and transaction count for the category under the active filters |
| DataTable | Up to 100 most-recent transactions, paginated at 15 rows; natively sortable |
| Columns | Date, Description, Amount (formatted `$x,xxx.xx`), Source |

The `total` in the summary line is computed from all matching transactions (not capped at 100), so the dollar figure is always accurate even when the table is truncated.

### How the category label is matched

`expenses_by_category` renames `category_display` → `category` in its output. The bar chart's y-axis displays that value. When the user clicks, `clickData["points"][0]["y"]` returns the exact same string. The drilldown filters on `category_display == category` (blank mapped to "Uncategorized") and keeps only rows labeled `Expense` — the same rule as the bars, so drilldown totals always match the clicked bar.

---

## Colours

The bar chart uses `PIE_COLORS`, a fixed 12-colour palette (`#6c8aff`, `#ff6c8a`, `#6cffd4`, …). If there are more than 12 categories, the palette wraps silently (Plotly truncates the list to the number of bars). The drilldown table uses the theme's `accent2` colour for the summary total.
