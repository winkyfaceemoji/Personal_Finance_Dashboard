# Category breakdown & drilldown

The Categories card (`category-bar-chart` — the id predates the pie) shows a **pie of spending by category for one calendar year**, titled `SPEND BY CATEGORY · {year}`.

- **Year chips** (`category-year`): one pill per year in the data, defaulting to the latest year. This is the card's only control.
- **Top 9 + Other:** the nine largest categories get their own slice; the rest collapse into `Other · {n} categories` so the pie stays readable. Slice colours come from `PIE_COLORS` in spend-rank order (slices are unsorted so colours match rank).
- Slices show their percent; hover adds the dollar total (`$4,005.15 · 32%`).
- Only rows labeled `Expense` in `master_category` are counted, matching every other total in the app.

---

## Click drilldown (`category-drilldown`)

Clicking a slice opens a transaction table directly below the pie, scoped to that category and the selected year:

- The category comes from the pie point's `label`; the header reads `TRANSACTIONS — FOOD & DRINK · 2026`.
- Clicking the `Other · {n} categories` slice does nothing (it's an aggregate, not a real category).
- Changing the year clears the drilldown immediately (returns an empty div); click again for the new year. This prevents stale data from being visible while the pie has already updated.

### What it shows

| Element | Detail |
|---------|--------|
| Header line | Category name (all-caps) + the year |
| Summary line | Total spend and transaction count in scope |
| DataTable | Up to 100 most-recent transactions, paginated at 15 rows; natively sortable |
| Columns | Date, Description, Amount (formatted `$x,xxx.xx`), Source |

The `total` in the summary line is computed from all matching transactions (not capped at 100), so the dollar figure is always accurate even when the table is truncated. The drilldown filters on `category_display == category` (blank mapped to "Uncategorized") and keeps only rows labeled `Expense` — the same rule as the pie, so drilldown totals always match the clicked slice.
