---
paths:
  - Modules/transforms.py
  - Modules/recurring.py
---

# Transforms, periods & recurring charges

## Totals
- Totals are label-based. Only `master_category` decides whether a row counts, never the amount's sign (ADR 0007). `Transfer` is excluded deliberately. Unlabeled rows are excluded because they're unclassified.
- Expense totals are *negated sums*, not absolute values. A refund labeled Expense nets against spending instead of inflating it.

## Auto-labeling rules (`apply_auto_categories`)
- Rules are applied **in memory on every load and never written to the master**:
  - Editing `rules.csv` relabels all history.
  - Deleting a rule un-labels rows on the next load.
  - EXPORT CSV reads the loaded frame, so an exported-then-imported file makes rule labels permanent.
- Precedence:
  - A hand label always wins, and the first matching rule wins.
  - A rule whose master isn't Expense/Income/Transfer is skipped. A typo would otherwise create rows that every total ignores.
- A rule's `sub_category` fills only a blank sub, and only when the rule's master (if it has one) agrees with the row's label.
- Sub-only rules (blank master) exist for ambiguous descriptions like `venmo`.
- Matching is a substring test, not a regex, after `normalize_description` on *both* sides. That is what lets `venmo payment` match column-padded bank text.
- `read_rules_csv` is shared with the labeling panel. It must accept UTF-8 with or without BOM, Windows-1252 (Excel's plain CSV save), and a zero-byte file (no rules). An unreadable file leaves `df` unchanged. A legacy single `category` column reads as `master_category`. The extra `added` column is ignored.

## Periods
- Weeks run Monday→Sunday (`W-SUN`). The user chose this: it keeps a weekend inside one week. Don't change it.
- "Latest" and `as_of` are the newest transaction date, never today (ADR 0013). Nothing here may read the wall clock. `filename_date` in `main.py` is the only exception.
- Typical (ADR 0014, 0015):
  - It is the **median**, not the mean, of up to 12 previous weeks or months, or of every earlier year.
  - It uses only periods `is_covered`: the data starts within `COVERAGE_GRACE_DAYS` (7) of the period start.
  - For an in-progress period it is truncated to the same number of days.
  - A period with over `UNLABELED_BLOCK` (10%) of its money out unlabeled is left out: it would read short and pull the median down. `left_out_unlabeled` counts them and the legend says `N earlier months not fully labeled, left out`.
- `period_totals` includes gap periods as zeros, and they count toward typical. Don't drop them.
- Last-year comparison: none for weeks. A partly covered last-year period returns `None` and is flagged as partial, never a partial total.
- `period_label` builds days from `.day`, because `%-d` doesn't exist on Windows.

## Recurring charges (`Modules/recurring.py`)
- They are judged over **all history** and ignore the period bar. A subscription is a standing commitment.
- Excluded:
  - rows labeled Transfer or Income;
  - unlabeled rows with transfer wording;
  - either side of a likely transfer pair. A fixed monthly move to savings isn't a subscription.
- "Steady" means 75% of charges are within 25% of the median *or of the latest charge*. The shown price follows the latest charge once the last two agree. Without both, a re-priced subscription drops off the list (ADR 0020).
- Yearly cadence needs 3 charges. Two similar charges a year apart are too often coincidence.
- "Active" is measured from the newest transaction, not today.
- Known misses:
  - several subscriptions under one merchant (Apple, Google, PayPal);
  - a price jump over 25% for half the history (an intro price ending).

## Don't delete
- `available_months/years/sources/categories` and `get_uncategorized` are unused by the dashboard. They're kept for scripting against the master.
