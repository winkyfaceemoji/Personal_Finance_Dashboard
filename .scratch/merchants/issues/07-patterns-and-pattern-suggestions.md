# 07: Patterns and pattern suggestions

**What to build:** A merchant can own patterns, pieces of text such as `zelle payment to`. A spelling that contains a merchant's pattern is suggested as that merchant ("Same as Zelle sent?") on To label and All merchants cards. Confirming adds the alias and the merchant's rule then labels it, after a preview. Dismissing hides that pairing for good. Nothing ever joins on its own.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] Add and remove patterns on a merchant card (two-file save, UNDO)
- [ ] Suggestions appear for spellings without an alias whose text contains a pattern, skipping dismissed pairings and spellings already aliased
- [ ] Confirm = merge the spelling into the merchant, with ticket 05's preview and UNDO
- [ ] Dismiss stores the pairing as dismissed in the alias file; it never comes back
- [ ] The needs-attention sort counts open suggestions
- [ ] Tests (seams 1 and 2): matching, skipping dismissed and aliased spellings, confirm labels the rows, dismiss persists across reloads, a pattern never labels anything on its own; browser tests for the suggestion line
