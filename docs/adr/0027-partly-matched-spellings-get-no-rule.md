# 0027. A spelling a keyword matched by its store number gets no rule at conversion

Status: Accepted

## Context

ADR 0026 keeps every past label when `rules.csv` keywords become merchants, and takes the rule off a merchant whose rule would move a past row. Future rows are a separate risk. Spellings drop store numbers, so with keywords `maple street grocery 0142 → Expense · Groceries` and `grocery → Food`, every past row is Groceries and no past row moves, yet a rule of Expense · Groceries would label a new store's rows Groceries where the keywords gave Food, or labeled nothing.

## Decision

At conversion, a spelling whose past rows got something other than what the keywords give the bare spelling is proposed on its own with no rule. Its card says why, and the review can still pick a rule (then ADR 0026's past check applies). Its new rows wait for a person.

Rejected: relying on the past-row check alone. It can't see this case, because nothing in the past moves.

## Consequences

- New rows of such spellings are labeled by hand, once, through Remember.
- Only rows that don't exist yet can still differ: a stacked keyword that hit no past row, or an ACH code that splits a keyword inside the bank text. Neither moves a past label.
- The demo's keywords have no such spelling, so the demo converts with every rule.
