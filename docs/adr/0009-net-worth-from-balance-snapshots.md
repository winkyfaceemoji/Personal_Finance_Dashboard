# 0009. Net worth needs balance snapshots, not transactions

Status: Accepted (direction only; not yet built)

## Context
Net worth is a likely future feature. The obvious shortcut is to sum transactions.

## Decision
Net worth should come from periodic account-balance snapshots, kept as a separate, parallel input. It should not be inferred from transactions: transactions drive cash flow, and balances drive net worth.

Rejected: deriving balances from transaction streams. Market moves produce no transaction, and a complete, gap-free history rarely exists.

## Consequences
- Nothing is built yet.
- This is recorded so the transaction pipeline doesn't get bent into the wrong shape when net worth is added.
