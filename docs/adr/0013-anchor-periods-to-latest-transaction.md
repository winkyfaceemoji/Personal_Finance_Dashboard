# 0013. Periods are anchored to the latest transaction, not today

Status: Accepted

## Context
Exports are manual and always lag behind. Anchored to today, a dataset ending Dec 26 showed `$0.00 ▼100%` on every card in October, plus an empty current-period chart. The first screen was wrong whenever the data was stale.

## Decision
"Latest" is the period containing the newest transaction, and ranges and comparisons are measured from it. Staleness is surfaced explicitly instead:
- the header names the data's end date;
- the attention line flags data over 14 days old;
- the attention line flags any source lagging by more than a week.

Rejected: anchoring to the wall clock.

## Consequences
- Numbers stay meaningful on stale data.
- Staleness is visible instead of hidden in zeros.
- Period maths must never read today's date (see also 0015).
