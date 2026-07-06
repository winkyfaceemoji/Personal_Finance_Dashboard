# Category breakdown & drilldown

The Categories card (`category-bar-chart` — the id predates the pie) shows a **pie of spending by category for one calendar year**, titled `SPEND BY CATEGORY` (the year lives in the chips, not the title).

- **Year chips** (`category-year`): one pill per year in the data, defaulting to the latest year. This is the card's only control; the selected chip is highlighted. The chip options regenerate after reloads/imports (`update_year_options`), so a new year's data gets a chip without restarting the app.
- **Top 9 + Other:** the nine largest categories get their own slice; the rest collapse into `Other · {n} categories` so the pie stays readable.
- **Stable colours:** a category's colour follows its *all-time* spend rank, not its rank within the selected year — so Food & Drink keeps one colour while you flip between year chips. The Other slice is always grey. The top-9 cut is the shared `CAT_PIE_TOP_N` constant.
- A muted "click a slice to see its top merchants" hint under the title advertises the drilldown.
- Slices show their percent in a fixed dark colour on every slice (not Plotly's per-slice auto black/white); hover adds the dollar total (`$4,005.15 · 32%`).
- Only rows labeled `Expense` in `master_category` are counted, matching every other total in the app.

---

## Click drilldown (`category-drilldown`)

Clicking a slice **pops it out** of the ring and opens a compact panel directly below the pie, scoped to that category and the selected year — a merchant summary, not a transaction table:

- The category comes from the pie point's `label`; the header reads `FOOD & DRINK · 2026` on the left, with `$total · N txns · $avg avg` on the right.
- Clicking the `Other · {n} categories` slice pools all the small categories it aggregates and shows *their* combined top merchants, headed `OTHER CATEGORIES · 2026`.
- Clicking the already-selected slice again deselects it (retracts and closes the panel); changing the year also clears the selection. Both prevent stale data from lingering while the pie has updated.

### Selection plumbing

The clicked slice is held in a `selected-category` `dcc.Store`, not read from `clickData` directly. This decouples the selection from the pie figure: `select_category` writes the label to the store (and resets `clickData` to `None` so re-clicking the same slice registers as a change), `pop_slice` `Patch`es only the slice's `pull` so a click doesn't rebuild the whole dashboard, and `update_overview` reads the store as `State` to keep the pop-out correct across theme/year rebuilds.

### What it shows

| Element | Detail |
|---------|--------|
| Header | Category (all-caps) + year; total spend, transaction count, and average |
| Top merchants | Up to 5 merchants by spend, each with a proportion bar and `$amount · % · N txns`; the rest roll into a muted `OTHER · N merchants` row |
| Largest | The single biggest transaction in scope (`$amount · description · date`) — the audit escape hatch |

**Merchant grouping:** bank descriptions embed store numbers and ids, so `_merchant` strips digits/`#`/`*` and collapses whitespace before grouping — `STARBUCKS #1234` and `STARBUCKS #98` roll up together. The drilldown filters on `category_display == category` (blank mapped to "Uncategorized") and keeps only rows labeled `Expense` — the same rule as the pie, so drilldown totals always match the clicked slice. The `Other` panel reconstructs that slice via the shared `CAT_PIE_TOP_N` constant (categories ranked beyond it), so its total matches the grey slice too.
