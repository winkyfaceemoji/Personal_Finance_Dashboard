# 10: Remove the old rule machinery

**What to build:** Once conversion is done, the old text-rule path goes away. Rules are only ever a merchant's label, the RULES tab is gone (rules show on merchant cards), and the docs describe the merchant world.

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] The RULES tab, substring rule application, the old rule-safety check and the `FINANCE_RULES_PATH` override are removed, along with code only they used
- [ ] Tests that copied the demo rules file use the demo merchant files
- [ ] The labeling path rule is rewritten for merchants: the two merchant files, two-file writes, conversion pitfalls, and the money-in-and-out rule
- [ ] The readme and CLAUDE.md describe the merchant files instead of `rules.csv`
- [ ] All tests pass, browser tests included
