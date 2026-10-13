# 0007. Totals are label-based; merges are coverage-based

Status: Accepted

## Context
Earlier versions removed duplicates from overlapping re-exports by comparing row values across all of RAW. That collapsed genuine same-day repeat purchases, such as two identical coffees or two subway swipes, into one row. Counting rows by the sign of the amount would also double-count transfers such as card payments.

## Decision
- Only rows labeled `Expense` or `Income` count. `Transfer` and unlabeled rows are left out of every total.
- Overlapping exports of one account are merged by date-range ownership (`_merge_by_coverage`), never by comparing rows. The file that owns a date contributes all of its rows for that date.

Rejected: value-based deduplication (reverted).

## Consequences
- Repeat same-day purchases survive.
- Transfers can't double-count.
- Unlabeled money is invisible to totals, so the UI must surface it through the attention line, the `+ $X unreviewed` lines and the headline's *Can't say yet* (see 0008).
- The coverage rule assumes the winning file is complete for its dates, which is why rows dropped from a losing file of another format are checked (0005).
