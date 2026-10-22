# 08: Convert the old rules

**What to build:** The user's existing text rules become merchants, through a one-time review list in the panel. Each rule shows the spellings it covers today and a proposed merchant. The user can split spellings out (Zelle to Dad) or drop a pattern that only matched by accident (`sq *the`), then confirm. Afterwards the old rules file is retired, and every row a rule labeled keeps its label unless the user chose otherwise.

**Blocked by:** 05, 07

**Status:** ready-for-agent

- [ ] While the old rules file exists and isn't converted, the attention line says so and links to the review
- [ ] Proposals: one merchant per rule, with the rule's label, category and text as its pattern, named after its highest-spend spelling, owning every spelling the rule matches today. Category-only rules become category-only merchants
- [ ] The review allows splitting spellings out, dropping the pattern, and editing the name and label before confirming
- [ ] Old rules keep applying until the whole review is confirmed
- [ ] Confirming writes both merchant files and moves the old rules file to a dated backup in the backups folder, as one UNDO step
- [ ] A test proves every rule label survives conversion unless the review changed it, with the totals by period identical
- [ ] The demo is converted the same way (its old demo rules file is removed from git once demo merchant files cover it)
- [ ] Browser tests for the review list
