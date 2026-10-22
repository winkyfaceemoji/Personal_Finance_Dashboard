# 02: Merchant files, each row's merchant, and merchant rules on load

**What to build:** Merchants exist. The data folder can hold the two merchant files. Every row gets its merchant: the merged merchant's name, the spelling itself when it isn't merged, or blank when the row has no spelling. Merchant rules label rows on load, and a hand label still wins. The AI chat can group by merchant and list merchants with their spellings. Today's rules keep working; where both match, the merchant rule wins.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A pure merchants module (no Dash) reads the merchant file (one row per merchant: name, label, category, patterns, added) and the alias file (one row per spelling–merchant pairing, with status alias or dismissed), tolerating a UTF-8 BOM and Windows-1252
- [ ] "Merchant of each row" returns the merchant name, the spelling for an unmerged spelling, and blank for a row with no spelling. Spelling is today's merchant-grouping function, unchanged
- [ ] "Merchant list" returns each merchant with its spellings
- [ ] On every load, merchant rules label rows with no hand label and fill categories only where the row has none and the labels agree. Category-only merchants are supported. Nothing is written to the master
- [ ] Where an old text rule and a merchant rule both match a row, the merchant rule wins
- [ ] Saving both files: both temp files are written first, then swapped back to back. A refused second swap restores the first and reports "nothing changed". Adds write the merchant file first and removals write the aliases first. All under the master lock
- [ ] The forgiving reader: an alias pointing at a missing merchant, or a spelling aliased twice, falls back to the spelling as its own merchant, and the header's attention line says the merchant files disagree
- [ ] Made-up demo merchant files in the demo's sorted folder, matching the demo generator's merchants, with at least one merged merchant, one pattern, one dismissed pairing and one category-only merchant. Tracked in git
- [ ] Tests (seam 1): each function above; rollback on a simulated locked file; the safe order under a simulated crash between swaps; the forgiving reader; demo totals unchanged except where demo merchant rules intend it
