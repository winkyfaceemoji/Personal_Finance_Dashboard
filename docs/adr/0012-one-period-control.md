# 0012. One period control drives the whole page

Status: Accepted

## Context
Each card used to have its own time control: YTD/1Y/3Y chips on one chart and year chips on the pie. They answered different questions about different spans on one screen. The YTD cards, a trailing-3Y chart and a 2023 pie could all show at once.

## Decision
A single period bar drives the whole page: WEEK / MONTH / YEAR, a ‹ › stepper and LATEST. It sets the stat cards, the headline, the spending chart's highlight and the category breakdown. The per-card controls were removed.

## Consequences
- Every number on the page is about the same span.
- Exception: recurring charges are judged over all history and ignore the period bar. The card says so.
