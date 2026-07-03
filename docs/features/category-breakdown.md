# Category breakdown & drilldown

---

## Category bar chart (`category-bar-chart`)

A horizontal bar chart at the bottom of the Summary tab. Each bar is one `effective_category`; bar length is total spend for that category under the active filters.

**Data source:** `expenses_by_category(data_df)` where `data_df = filtered` (all three global filters applied). Bars are sorted largest-to-smallest (most expensive category at the top) because `expenses_by_category` returns rows sorted by `total_expenses` descending.

The chart always uses the fully filtered data, so its totals match the stat cards and the drilldown below it.

---

## Click drilldown (`category-drilldown`)

Clicking any bar opens a transaction table directly below the chart, scoped to that category and the active filters.

### Trigger

The `category_drilldown` callback has `clickData` from `category-bar-chart` as its only **Input**. Source, year, and month are also **Inputs** (not States), so:

- Clicking a bar → drilldown renders for that category.
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

`expenses_by_category` renames `effective_category` → `category` in its output. The bar chart's y-axis displays that value. When the user clicks, `clickData["points"][0]["y"]` returns the exact same string. The drilldown filters on `filtered["effective_category"] == category` — an exact string match, so there is no label-transformation gap.

---

## Colours

The bar chart uses `PIE_COLORS`, a fixed 12-colour palette (`#6c8aff`, `#ff6c8a`, `#6cffd4`, …). If there are more than 12 categories, the palette wraps silently (Plotly truncates the list to the number of bars). The drilldown table uses the theme's `accent2` colour for the summary total.
