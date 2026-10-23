# 0006. A replacement card is asked about, then counted once

Status: Accepted

## Context
On real data, a replaced card's new-number export repeated all 116 of the old number's charges in their overlap, so $883 counted twice. Two genuinely different cards shared only 3 of 342 charges. A first version linked such pairs automatically and was reverted: the user wanted to confirm it, since it changes past totals.

## Decision
A pair is proposed when two card numbers of one institution and source share at least 10 overlapping rows, with at least 95% matching on both sides. The import records it in `SORTED/linked_cards.csv` as `proposed` and merges nothing. The attention line asks about the real event: "Did Chase replace your card ending 4417 with 8823?"

- **YES** files the new number's rows under the oldest number. Keeping the oldest number keeps row ids stable, along with transfer-pair dismissals and last-import ids.
- **NO** takes a second tap. On a pair this alike, NO is almost certainly a mis-tap that would keep the charges doubled.
- Both answers can be undone and switched later in Settings → CARDS.
- While a pair waits for an answer, any headline whose period or typical window covers the overlap says *Can't say yet*.

Rejected:
- Auto-linking.
- Asking "same or different cards?" — the numbers literally are different cards.
- Leaving numbers ungated while the question waits — the overlap feeds the 12-month typical.
- A label-conflict preview, label timestamps, and a generic proposals framework.

## Consequences
- An unreadable `linked_cards.csv` stops the import before anything is written. Falling back to no links would split a confirmed card again.
- A linked account's dropped rows are checked like a format switch, but only for dates that another number's export owns.
- A leftover label is absorbed as a duplicate only up to the number of second-number copies the prior master held.
- Known gaps:
  - Replacements that share fewer than 10 charges aren't detected.
  - UNDO of a YES can leave the carried label on the hidden copy.
  - A waiting pair isn't refreshed by a longer export.
  - Transfer pairs still see a waiting pair's copies.
  - Excel can strip a card number's leading zero.
