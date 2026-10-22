# 04: All merchants view (read-only)

**What to build:** The panel gains an All merchants view beside To label. It lists every merchant, all time, so the user can see where their money goes and spot a wrong past call. The panel opens on To label when anything is unlabeled, otherwise on All merchants.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] A switch between To label and All merchants; the panel opens on the right one
- [ ] Each card shows the merchant's name, its spellings, label and category (its rule), patterns, all-time money out and money in, row count, and first and last dates
- [ ] Sort by spend, or by needs attention: open suggestions, then merchants whose rows carry different labels, then merchants with no rule, then by spend
- [ ] Small merchants fold into an `Other · N merchants` line
- [ ] The view ignores the page's period control
- [ ] Rows with no spelling are counted in a "No merchant name" line
- [ ] Tests (seam 2): ordering for both sorts, the folding, opening on the right view; browser tests for the switch and sort in both themes
