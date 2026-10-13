# 0019. Stat cards compare with the same period last year, in dollars

Status: Accepted

## Context
The cards used to compare with the median of the previous 12 periods, as a percentage. Income arrives in a few big months, so its median sat near zero. A normal month then showed `▲564%`, even when last year's income was higher. Medians of income, spending and net also don't add up, so the cards couldn't be reconciled.

## Decision
- The spent, income and net cards each compare with the same period last year: the same month (month view) or the previous year (year view). While a period is in progress, they compare the same number of days.
- The comparison is written in dollars with last year's figure: `$450 more than Oct 2024 ($2,420)`.
- The week view has no comparison: the same week a year ago mostly measures where a payday fell.
- A card shows a reason instead of a number when last year has no data, is only partly covered, or is over 10% unlabeled.
- A card shows nothing while the headline says *Can't say yet*.
- The headline keeps its typical-period comparison (0014).

Rejected (reverted): percentage deltas against a median.

## Consequences
- Figures are checkable and always reconcile: income − spent = net in both years.
- Cards never claim what the headline refuses to.
