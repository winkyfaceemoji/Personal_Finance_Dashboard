# 0004. The RAW folder is authoritative for institution identity

Status: Accepted

## Context
Past three sources, header detection plus a Chase-only filename regex can't identify institutions. Two banks can also export the same CSV format, which would collapse them into one account and mis-merge their files.

## Decision
The top-level `RAW/<institution>/` folder is recorded as the `institution` column and is part of the account key `(institution, source, card_last4)`. The CSV format is still detected from headers, independent of the folder. `institution` is deliberately left out of `MATCH_COLUMNS`.

## Consequences
- Two institutions that share a format stay separate accounts.
- Masters built before the column existed still carry their labels forward on the first rebuild.
- Known gap: the folder separates institutions, not cards within one. `card_last4` comes only from Chase filenames, so two non-Chase cards in one folder share an account key and their overlapping dates merge.
- Capital One files are the one exception (see 0005).
