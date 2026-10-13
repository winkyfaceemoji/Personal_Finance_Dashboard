# 0020. Recurring charges are labeled by what they are, and their price follows the latest charge

Status: Accepted

## Context
The folded card was labeled **MORE**, which said nothing about what it held. A price rise over 25% kept showing the old price and yearly cost. After enough charges at the new price, the subscription dropped off the list entirely.

## Decision
- The closed line states the answer: `RECURRING CHARGES · 7 · $3,149 a year`. The open card says it covers all history.
- "Stopped" reads **No longer charging**.
- The shown price follows a confirmed new price, meaning the last two charges agree.
- Charges near the latest price count as steady.

Rejected (council review):
- Price-change or new-charge alerts on the attention line. That line is for data warnings with a fix, and nothing remembers what was already shown.
- A "fixed vs everything else" split in the headline. It would mix all-history averages with this period.
- Next-due dates.

## Consequences
Known gaps:
- A new charge needs 3 payments to appear.
- Rent or loans paid by transfer or Zelle aren't counted.
- "No longer charging" is measured from the newest transaction, so it can't show while imports lag.
