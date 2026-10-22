# 0008. Label in the app through the import matcher; remember only provably safe rules; show unreviewed money

Status: Superseded by 0025

## Context
The Excel round-trip was slow enough that the backlog never got labeled: 562 of 1,343 demo rows ($152,346) were missing from every number. Weekly tracking makes this worse. A one-click, merchant-level panel clears most of it, since the top 25 groups cover about 88% of unlabeled dollars. But one click labels many rows, and a remembered rule labels rows nobody has seen. Every failure here is silent.

## Decision
- **Shared matcher.** The labeling panel writes through `label_rows` → `apply_label_import`, with the same matcher, lock, backup and atomic swap as the Excel import. It touches only rows with no valid label. A stale list or a count mismatch writes nothing.
- **Safe rules only.** A `rules.csv` rule is remembered only when `rule_check` proves it safe:
  - the keyword is at least 4 characters;
  - it matches no other merchant across all rows;
  - it doesn't overlap an existing rule;
  - the group is one direction of money.

  The checkbox starts ticked only then, and never for a single transaction.
- **Unlabeled money is shown, not counted** (`+ $X unreviewed`).
- **No built-in transfer rules.** Groups that look like card payments get a *suggested* TRANSFER button, which is never applied automatically.

Rejected:
- Grouping by raw description: transaction ids split one merchant into several groups.
- Starter rules: they are unreviewed, wrong ones fail silently, and card-payment phrases cover only about 1% of unlabeled dollars.
- Counting unlabeled money by sign: it double-counts card payments.

## Consequences
- The two labeling paths can't disagree.
- A short keyword like `pay` can't sweep up other merchants.
- An incomplete total looks incomplete.
- Recovery: every click takes a rotating backup, and UNDO reverts the last action while nothing else has written. Opening the panel also saves `SORTED/backups/before-labeling-YYYY-MM-DD.csv` once a day, outside the rotation.
