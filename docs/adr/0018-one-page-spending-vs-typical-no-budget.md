# 0018. One high-level page: spending vs typical, no budget

Status: Accepted

## Context
Two strips disagreed on the same page: a red "over your typical pace" and a green "on track for budget". The page said two things at once. The user tracks budgets elsewhere and wants total spending against one reference.

## Decision
The page answers one question at the top: this period's spending against a typical one. Below that come spent / income / net, the spending-over-time and category charts, and folded recurring charges. Warnings collapse into one red attention line that appears only when something fires.

The headline says *Can't say yet* instead of giving a verdict when either:
- the period's data is over 14 days old, or
- over 10% of its money out is unlabeled.

Removed (reverted): budget tracking, the savings-rate card, the vs-previous comparisons and the seasonality chart.

Rejected: flagging verdicts on stale or unlabeled data instead of blocking them. A confident verdict over missing data is wrong.

## Consequences
- A messy ledger shows *Can't say yet* often until it is labeled.
- Without seasonality, December reads as over typical.
- *Can't say yet* is shown in ink, not red: missing data isn't overspending.
