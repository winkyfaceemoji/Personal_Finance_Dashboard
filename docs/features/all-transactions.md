# All Transactions tab

The second tab shows every transaction in the active filter scope. It is a read-only view — the global filters (Source, Year, Month) drive what rows appear, keeping it consistent with the Summary tab at all times.

---

## Transaction table (`editor-table`)

Displays rows from `edited_combined_transactions.csv` after the global filters are applied.

| Column | Source field | Notes |
|--------|-------------|-------|
| DATE | `date` | Transaction date |
| DESCRIPTION | `description` | Merchant / memo text |
| AMOUNT | `amount` | Negative = expense, positive = income/credit |
| SOURCE | `source` | Chase Debit / Chase Credit / Discover Credit |
| CARD | `card_last4` | Last 4 digits of the card; Chase only (extracted from filename); blank for Discover |
| TYPE OF TRANSACTION | `master_category` | User-assigned: `Expense`, `Income`, or `Transfer` |
| CATEGORY | computed | `sub_category` if set, otherwise `original_category` (bank-provided label) |

The table is paginated at 25 rows and supports native column sorting. The `refresh-trigger` store fires the table reload automatically after any import or data reload so the view stays current without a manual page interaction.

---

## Import / export workflow

This is the recommended workflow for bulk category assignment:

1. Click **EXPORT CSV** — downloads all transactions (regardless of active filters) with columns: `date`, `description`, `amount`, `source`, `card_last4`, `original_category`, `master_category`, `sub_category`.
2. Open in Excel. Fill in `master_category` (`Expense`, `Income`, or `Transfer`) and optionally `sub_category` for each row you want to categorise.
3. Save and click **IMPORT CSV** — upload the edited file. The import callback:
   - Matches rows by `description` + `amount` + `source` + `date` (date matching is used when the import file includes a `date` column; omitting date falls back to the three-field match)
   - Writes `master_category` and `sub_category` to every matched row in the master CSV
   - Skips rows where both fields are blank in the import file
   - Reloads `df` so charts and the table reflect the new categories immediately
   - Increments `refresh-trigger` to update the uncategorized badge

The import file must contain at minimum: `description`, `amount`, `source`, `master_category`. Extra columns are ignored.

---

## Category system

Three fields drive how a transaction is labelled:

| Field | Set by | Purpose |
|-------|--------|---------|
| `original_category` | Bank (on import) | Raw label from the bank CSV export |
| `master_category` | You (via Excel import) | High-level type: `Expense`, `Income`, or `Transfer` |
| `sub_category` | You (optional, via Excel import) | Detail label within the type — e.g. "Rent", "Paycheck", "Fidelity" |

The **CATEGORY** column in the table shows `sub_category` when set, and falls back to `original_category` when blank.

---

## Handling transfers

Rows tagged `Transfer` in `master_category` are automatically excluded from all income and expense calculations — charts, stat cards, net chart, and MoM/YoY deltas. They still appear in this table so you can see them.

**Recommended workflow:**
1. Export CSV
2. In Excel, find brokerage transfers, savings moves, and the monthly credit card payment from your checking account
3. Set their `master_category` to `Transfer`
4. Optionally set `sub_category` to something descriptive (e.g. "Fidelity", "Credit Card Payment")
5. Import back

Once tagged, those rows are invisible to all financial calculations.
