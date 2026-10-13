# 0015. Comparisons say where the data stops and skip partly covered periods

Status: Accepted

## Context
Two problems prompted this:

- The sub-line said "data ends Oct 8" while the headline said "DAY 8 OF 31 · over your typical pace". That put two statuses on one screen, and it was the only place the wall clock leaked in.
- The user's exports start Feb 16 2023, yet 2023 was used as a confident baseline. Its "last year" was ten and a half months long ("$650 more than Feb 2023 ($64)").

## Decision
- When the newest data falls inside a period, the period line, headline title and stat cards say where it stops (`through Oct 8`, `SPENT THROUGH OCT 8`). This applies whatever today's date is. The truncated like-for-like comparison is kept.
- A period counts toward typical, or as "last year", only if the data starts within 7 days of its start (`is_covered`).
- With one full earlier period, the headline names it (`$1,200 over 2024`). With none, it says so.

Rejected (council review):
- Treating a month whose calendar end has passed as complete. Early each month the data reaches about the 29th, so a 29-day month reads falsely as under typical.
- Aligning windows ("from Feb 16"). The difference wouldn't match the card's total.

## Consequences
- The 7 grace days exist because a first transaction on day 5 doesn't prove days 1–4 are missing.
- Deferred: a lagging account can still make the current period read low (the attention line flags it).
- Deferred: a mostly unlabeled baseline month can pull typical down.
