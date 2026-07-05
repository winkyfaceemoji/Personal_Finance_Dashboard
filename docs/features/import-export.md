# Import / export & labeling

The app is a single page — there is no transactions tab or table. The import/export card at the bottom of the page is where labeling happens, via a CSV round-trip through Excel. To inspect individual transactions in the app, use the Categories chart's click drilldown.

---

## Import / export card

A slim card below the performance card: **IMPORT CSV**, **EXPORT CSV**, an import status message, and the unlabeled-rows note on the right.

### Unlabeled-rows note (`unlabeled-note`)

All totals are label-based: a row only counts as an expense or income if its `master_category` is `Expense` or `Income`. The note shows how many rows in the whole dataset have no valid label (blank or anything outside `Expense` / `Income` / `Transfer`) and are therefore ignored by every number in the app — e.g. `⚠ 40 of 2100 transactions have no valid label…`. Transfer rows are not counted here since ignoring them is intentional. The note hides itself when everything is labeled, and refreshes after imports/reloads.

---

## Import / export workflow

This is the recommended workflow for bulk category assignment:

1. Click **EXPORT CSV** — downloads all transactions with columns: `date`, `description`, `amount`, `source`, `card_last4`, `original_category`, `master_category`, `sub_category`.
2. Open in Excel. Fill in `master_category` (`Expense`, `Income`, or `Transfer`) and optionally `sub_category` for each row you want to categorise.
3. Save and click **IMPORT CSV** — upload the edited file. The import callback:
   - Matches rows by `description` + `amount` + `source` + `date` (date matching is used when the import file includes a `date` column; omitting date falls back to the three-field match)
   - Writes `master_category` and `sub_category` to every matched row in the master CSV
   - Skips rows where both fields are blank in the import file
   - Reloads `df` so all charts reflect the new categories immediately
   - Increments `refresh-trigger` to update the uncategorized badge and the unlabeled-rows note

The import file must contain at minimum: `description`, `amount`, `source`, `master_category`. Extra columns are ignored.

---

## Category system

Three fields drive how a transaction is labelled:

| Field | Set by | Purpose |
|-------|--------|---------|
| `original_category` | Bank (on import) | Raw label from the bank CSV export |
| `master_category` | You (via Excel import) | High-level type: `Expense`, `Income`, or `Transfer` |
| `sub_category` | You (optional, via Excel import) | Detail label within the type — e.g. "Rent", "Paycheck", "Fidelity" |

Charts and the drilldown display `category_display`: `sub_category` when set, falling back to `original_category` when blank.

---

## Handling transfers

Rows tagged `Transfer` in `master_category` are excluded from all income and expense calculations — charts, headline numbers, and vs-prior deltas. (So are unlabeled rows — see the note above — but Transfers are excluded deliberately and don't appear in the ignored count.)

**Recommended workflow:**
1. Export CSV
2. In Excel, find brokerage transfers, savings moves, and the monthly credit card payment from your checking account
3. Set their `master_category` to `Transfer`
4. Optionally set `sub_category` to something descriptive (e.g. "Fidelity", "Credit Card Payment")
5. Import back

Once tagged, those rows are invisible to all financial calculations.
