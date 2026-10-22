# 06: Relabel a merchant's past rows

**What to build:** The user can change a merchant's label (and category) from its card. The merchant's hand-labeled rows that still show the label the user saw are rewritten, and the merchant's rule is updated, so past and future agree. This is ADR 0025's one exception to "only unlabeled rows are touched".

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Relabel previews rows and dollars that change, by label
- [ ] It writes through today's label-writing function with "relabel from" set to the label shown on the card. Rows whose label changed since (Excel, another tab) are left alone and counted in the status
- [ ] The rule is updated after the master write. A failed rule save keeps the labels and UNDO
- [ ] Money-in-and-out merchants: relabel is allowed, because it is an explicit, previewed choice, and the preview lists the refunds separately
- [ ] UNDO restores the previous labels and rule
- [ ] Tests (seam 2): only rows still showing the seen label change; preview equals result; a locked file; UNDO; browser test for the relabel flow
