---
type: Feature Doc
title: Import / export & labeling
description: CSV labeling round-trip, the category system, and transfer handling.
resource: app.py, Modules/transforms.py
updated: 2026-07-06
---

# Import / export & labeling

The app is a single page — there is no transactions tab or table. Labeling happens via a CSV round-trip through Excel, driven by **IMPORT CSV** / **EXPORT CSV** in the settings menu (gear icon). To inspect individual transactions in the app, use the Categories chart's click drilldown.

---

## Import / export (settings menu)

**IMPORT CSV** and **EXPORT CSV** live in the settings menu (gear icon), under the **DATA** section alongside **RELOAD DATA**. An import status message appears at the bottom of the menu after an upload.

### Unlabeled-rows note (`unlabeled-note`)

All totals are label-based: a row only counts as an expense or income if its `master_category` is `Expense` or `Income`. A red note on its own line in the page header shows how many rows in the whole dataset have no valid label (blank or anything outside `Expense` / `Income` / `Transfer`) and are therefore ignored by every number in the app — e.g. `⚠ 40 of 2100 transactions have no valid label…`. Transfer rows are not counted here since ignoring them is intentional. The note hides itself when everything is labeled, and refreshes after imports/reloads.

---

## Import / export workflow

Before reaching for Excel: recurring merchants (paychecks, subscriptions, transfers) are better handled by [auto-labeling rules](../../readme.md#auto-labeling-rules) in `rules.csv`, which label new statements automatically on every load. The Excel round-trip is for everything the rules don't catch.

Note that **exports include rule-applied labels** (the export reads the loaded frame, not the raw master file), so importing an export back writes those labels into the master permanently.

This is the recommended workflow for bulk category assignment:

1. Click **EXPORT CSV** — downloads all transactions with columns: `date`, `description`, `amount`, `institution`, `source`, `card_last4`, `original_category`, `master_category`, `sub_category`. (`institution` is informational — sort by it in Excel; it isn't used to match rows on re-import.)
2. Open in Excel. Fill in `master_category` (`Expense`, `Income`, or `Transfer`) and optionally `sub_category` for each row you want to categorise.
3. Save and click **IMPORT CSV** — upload the edited file. The import callback:
   - Matches rows by `description` + `amount` + `source` + `date` (date matching is used when the import file includes a `date` column; omitting date falls back to the three-field match)
   - Writes `master_category` and `sub_category` to every matched row in the master CSV
   - Skips rows where both fields are blank in the import file
   - Reloads `df` so all charts reflect the new categories immediately
   - Increments `refresh-trigger` to update the unlabeled-rows note

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
