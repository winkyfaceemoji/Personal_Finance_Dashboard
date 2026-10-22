# 03: To label groups by merchant; Remember saves a merchant rule

**What to build:** The labeling panel's list becomes the To label view. Unlabeled rows are grouped by merchant, across all its spellings, so one click labels a merchant everywhere. Remember now saves the label as the merchant's rule: unaliased spellings get a merchant of their own plus its alias. Every safeguard from ADR 0008, now restated in ADR 0025, holds and is proven by a test.

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] Groups are merchants: biggest unlabeled dollars first, top 25; REVIEW → still limits to the last import's rows
- [ ] Rows with no spelling sit in their own "No merchant name" section, labeled one at a time
- [ ] No group buttons on a merchant with money in and out; it is labeled row by row
- [ ] Remember writes a merchant rule (through the two-file save). It starts ticked only for a merchant seen in 3+ months, and unticked for a single transaction
- [ ] The stale-list signature includes the merchant files' version: an alias change makes an open list stale, and a click then writes nothing
- [ ] Write order: master, then the UNDO record, then the merchant files. A merchant-file failure keeps the labels and UNDO and says "not remembered: …"
- [ ] UNDO tracks the merchant files too (through ticket 01's list)
- [ ] Tests (seam 2), one per safeguard:
  - [ ] shared matcher;
  - [ ] only unlabeled rows touched;
  - [ ] stale list and count mismatch write nothing;
  - [ ] write order;
  - [ ] no group buttons on nameless or money-in-and-out merchants;
  - [ ] Remember defaults;
  - [ ] TRANSFER only suggested;
  - [ ] unlabeled money counted nowhere;
  - [ ] daily snapshot;
  - [ ] UNDO, and UNDO refused after another write;
  - [ ] file open in Excel
- [ ] The end-to-end acceptance test in its merchant form: label and remember the top merchants, import a new statement, and only the remembered merchant's new row gets labeled
- [ ] Browser tests cover the To label cards in both themes
