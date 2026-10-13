# 0017. Transfer pairs are suggested only when the match is certain

Status: Accepted

## Context
A card payment appears twice: once leaving checking and once arriving on the card. Labeling either side as Expense counts the same money twice.

A wrong pair is worse, though. It mislabels real spending as Transfer, which silently removes it from every total. An unlabeled row is at least shown as unreviewed.

## Decision
- A pair is an exact opposite amount on a different account within `TRANSFER_PAIR_DAYS` (5) days.
- A pair is shown only when neither row has any other candidate. Every row counts as a candidate, labeled or not.
- Nothing is labeled without a click, and LABEL ALL covers only the pairs on screen.
- Pairs with a side labeled Expense or Income are flagged (CHECK →) and never changed automatically.
- RELABEL AS TRANSFER is the only place the panel overwrites a label.
- NOT A TRANSFER silences a pair for good by recording it in `SORTED/not_transfers.csv`.

Rejected:
- Suggesting ambiguous matches.
- Same-account pairs: a refund on the same card is money back, not a move.

## Consequences
- Coincidental pairs are rare.
- Some real transfers, such as two equal payments in one week, are left for the merchant list.
- If a `rules.csv` rule produced the Expense label, relabeling fixes only that row. The rule will mislabel the next statement's payment again.
