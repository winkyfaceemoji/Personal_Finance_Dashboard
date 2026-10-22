# Spec: merchants

Status: ready-for-agent. Agreed in a grilling session on 2026-10-22. Decisions: ADR 0025 (replaces 0008) and ADR 0024. Terms: `CONTEXT.md`. Not built yet.

## Problem Statement

One merchant reaches the app under many spellings: `AMZN MKTP US` and `AMAZON PRIME`, three Steam spellings, a store number per Whole Foods. Each spelling is its own group in the labeling panel and needs its own remembered rule. Rules are pieces of text matched anywhere in the bank text. Some quietly cover several unrelated merchants (`sq *the` hits five shops), and a broad rule can't be overridden for one merchant. Once everything is labeled the panel is empty, so there's nowhere to see your merchants, check a past call, or fix one. The only fix is the Excel round-trip. The upcoming AI chat also needs to group spending by merchant, and today there's no such thing as a merchant.

## Solution

A **merchant** is the set of spellings you'd always label the same way. You confirm which spellings belong together; the app only *suggests*, from the merchant's patterns and from names that look alike. Every rule now belongs to one merchant: the merchant's saved label applies to all its spellings, past and future, and a hand label still wins.

The labeling panel becomes one merchant panel with two views:
- **To label:** what needs you, as today.
- **All merchants:** everything, all time, sorted by spend or by what needs attention.

From a merchant card you can:
- label;
- confirm or dismiss a suggestion;
- merge, split and rename;
- relabel a merchant's past rows.

Every action shows its effect before saving and can be undone. Your 46 existing rules are converted once, through a review list. Every safeguard the labeling panel had carries over.

## User Stories

### Seeing merchants
1. As the user, I want every transaction with a spelling to belong to exactly one merchant, so that spending can be read per merchant instead of per bank wording.
2. As the user, I want a spelling I never merged to count as its own merchant, named after itself, so that nothing has to be set up before the app works.
3. As the user, I want rows with no recognisable name (real-time payments, bare reference numbers) to belong to no merchant, so that unrelated payments are never lumped together.
4. As the user, I want an All merchants view listing every merchant with its all-time money out and money in, so that I can see where my money goes across the whole history.
5. As the user, I want each merchant card to show its spellings, label, category, patterns, row count and first and last dates, so that I can judge a past decision at a glance.
6. As the user, I want to sort All merchants by spend, so that the merchants that matter most come first.
7. As the user, I want to sort All merchants by needs attention (open suggestions first, then merchants whose rows carry different labels, then merchants with no rule, then by spend), so that I can work through what needs fixing.
8. As the user, I want small merchants folded into an `Other · N merchants` line, so that hundreds of one-off merchants don't bury the rest.
9. As the user, I want All merchants to ignore the page's period control, so that the figures I review past decisions against don't change as I browse periods.

### Labeling
10. As the user, I want the panel to open on To label when anything is unlabeled, and on All merchants otherwise, so that it opens where my work is.
11. As the user, I want To label to group unlabeled rows by merchant (all its spellings together), biggest unlabeled dollars first, top 25, so that one click clears a merchant across all its spellings.
12. As the user, I want REVIEW → to show only the last import's rows, as today, so that a weekly check stays quick.
13. As the user, I want EXPENSE / INCOME / TRANSFER on a merchant card to label every unlabeled row of that merchant I can see, so that labeling stays one click.
14. As the user, I want a merchant with money both in and out to be labeled row by row, so that a refund or payout never gets a label meant for purchases.
15. As the user, I want rows with no merchant in their own section, labeled one at a time, so that they're never bulk-labeled.
16. As the user, I want a row click to label that row and its identical twins and never create a rule, so that a one-off fix stays a one-off.
17. As the user, I want card-payment-looking merchants to show a starred, suggested TRANSFER button that is never applied by itself, so that transfers are easy but never automatic.
18. As the user, I want an optional category when I label, as today, so that the category breakdown stays meaningful.

### Rules (a merchant's saved label)
19. As the user, I want a Remember tick on a merchant card that saves the label as that merchant's rule, so that its future rows label themselves.
20. As the user, I want Remember to start ticked only for a merchant seen in 3 or more different months, so that a trip's worth of charges doesn't become a permanent rule by default.
21. As the user, I want a single-transaction merchant to start unticked, so that one row is never enough evidence by default.
22. As the user, I want a merchant's rule to label all its rows without a hand label, past and future, in every spelling, so that I decide once per merchant.
23. As the user, I want a hand label to always beat a merchant's rule, so that a deliberate exception is never overridden.
24. As the user, I want a rule's category to fill only rows with no category of their own, and only where the row's label agrees with the rule, so that a rule never paints over my own categories.
25. As the user, I want a merchant to be able to carry a category without a label (like today's `venmo` rule), so that ambiguous merchants still get a display category.
26. As the user, I want rule labels worked out on every load and never stored in the master, so that changing a rule changes all its rows consistently.
27. As the user, I want the rule to be saved only after the labels are safely written, and a failed rule save to keep the labels and UNDO, so that a locked file never costs me labels.

### Suggestions
28. As the user, I want a new spelling that contains one of a merchant's patterns to be suggested as that merchant ("Same as Zelle sent?"), so that recurring kinds of payment are recognised.
29. As the user, I want a spelling to be suggested as the merchant with the most similar name, when the similarity clears a cutoff, so that `AMZN MKTP` is offered as Amazon.
30. As the user, I want suggestions on To label cards and on All merchants cards, so that I can confirm them wherever I meet them.
31. As the user, I want confirming a suggestion to add the alias, and the merchant's rule then to label the spelling's rows, after a preview, so that one click files and labels a new spelling.
32. As the user, I want to dismiss a suggestion and never see that pairing again, so that wrong guesses don't keep coming back.
33. As the user, I want nothing ever joined to a merchant without my confirm, so that no stray match is labeled behind my back.
34. As the user, I want pattern suggestions to keep working when the embedding server is down, and name-similarity suggestions to simply not appear, so that the panel never breaks because a model isn't running.

### Merging, splitting, renaming
35. As the user, I want to merge a spelling or a whole merchant into another merchant, so that one merchant's spellings live together.
36. As the user, I want a merge to preview which rows change label and by how many dollars, so that I see the effect before it happens.
37. As the user, I want a merchant made by a merge named after its highest-spend spelling, so that I don't have to type a name.
38. As the user, I want to rename a merchant, so that `AMZN MKTP US` can read "Amazon".
39. As the user, I want to split a spelling out of a merchant into its own merchant, so that "Zelle to Dad" can be labeled differently from other Zelle payments.
40. As the user, I want to add or remove a merchant's patterns, so that I control what gets suggested to it.

### Fixing past decisions
41. As the user, I want to relabel a merchant (label and category), so that a past call I now think is wrong is fixed everywhere at once.
42. As the user, I want relabelling to rewrite the merchant's hand labels and update its rule, so that past and future rows agree.
43. As the user, I want relabelling to change only rows still showing the label I saw, so that a label changed since (in Excel or another tab) is never overwritten.
44. As the user, I want relabelling to preview the rows and dollars it will change, so that I don't shift a year's totals by accident.

### Safety
45. As the user, I want every label written through the same matcher, lock, backup and atomic swap as the Excel import, so that the two paths can't disagree and a crash never truncates the master.
46. As the user, I want any action to write nothing if the list changed since I saw it or the row count differs from what was shown, so that I never label rows I didn't see.
47. As the user, I want UNDO to reverse my last action of any kind (label, merge, split, rename, relabel, rule change, conversion step) while nothing else has written since, so that a mistake is one click to take back.
48. As the user, I want the daily before-labeling snapshot and rotating backups to keep working, so that I can always get back to where I started.
49. As the user, I want a file open in Excel to produce a plain message and change nothing, so that a lock never leaves a half-done change.
50. As the user, I want the two merchant files to be written so that a crash between them leaves a valid state, so that nothing is ever mislabeled after a failure.
51. As the user, I want the app to tell me in the header if the merchant files disagree, and fall back to treating spellings as their own merchants, so that a damaged file is visible and harmless.
52. As the user, I want unlabeled money shown and never counted, including for merchants, so that an incomplete total still looks incomplete.

### Converting my rules
53. As the user, I want my 46 existing rules shown once as a review list, each with the spellings it covers today and a proposed merchant, so that I see exactly what each becomes.
54. As the user, I want each proposal to default to one merchant per rule, with the rule's label, category and text as its pattern, named after its highest-spend spelling, so that most rules convert with one confirm.
55. As the user, I want to split spellings out of a proposal (Zelle to Dad) and drop a pattern that only matched by accident (`sq *the`), so that conversion fixes old mistakes instead of copying them.
56. As the user, I want my old rules to keep applying until the conversion is finished, so that nothing goes unlabeled halfway through.
57. As the user, I want every row a rule labels today to keep its label after conversion, unless I chose otherwise in the review, so that converting doesn't move my totals by surprise.
58. As the user, I want the old rules file kept as a backup after conversion, so that I can always see what I had.

### For the AI chat
59. As the AI chat, I want one function that gives every row's merchant (the merchant's name, the spelling for an unmerged spelling, blank for no spelling), so that I can group spending by merchant.
60. As the AI chat, I want one function listing every merchant with the spellings it covers, so that a name search can report which merchants and spellings it matched.

## Implementation Decisions

- **New pure module for merchants** (in `Modules/`, no Dash imports), the chat's and the panel's single source. Its interface:
  - **Read** both merchant files, tolerating Excel's encodings like every reader in the project. Report disagreements: an alias pointing at a missing merchant, or a spelling aliased twice.
  - **Merchant of each row:** returns the merchant name per row; an unmerged spelling is its own merchant, and a row with no spelling is blank.
  - **Merchant list:** each merchant with its spellings.
  - **Apply rules:** labels and categories from merchant rules onto rows with no hand label. Same semantics as today's rule application, with "matches a substring" replaced by "the row's spelling belongs to the merchant".
  - **Pattern suggestions:** for given spellings, the merchant whose pattern each contains, skipping pairings already dismissed.
  - **Change merchants:** add or remove aliases, merge, split, rename, relabel the rule, edit patterns, dismiss a suggestion. Each returns the new state of both files plus a preview of which rows change label.
  - **Save both files** with the two-file safeguards below.
  - **Convert old rules:** from `rules.csv` plus the master, build the review list of proposals, then apply the confirmed review.
- **Spelling** stays exactly today's merchant-grouping function: one definition, already tested, and its pitfalls are in the labeling rule.
- **Storage** (ADR 0025), both in the data folder's `SORTED/`:
  - `merchants.csv`: one row per merchant, with merchant name (unique), label (Expense / Income / Transfer or blank), category (optional), patterns (zero or more pieces of text) and when it was added.
  - `merchant_aliases.csv`: one row per spelling–merchant pairing, with spelling, merchant and a status, which is either an alias or a dismissed suggestion. A spelling has at most one alias.
- **Two-file writes:**
  1. Write both temp files first.
  2. Swap them in back to back.
  3. If the second swap fails, restore the first from the copy held in memory and report "nothing changed".
  4. Order: changes that add write `merchants.csv` first; changes that remove write the aliases first.
  5. All writes run under the master lock.
- **Rule application** replaces today's substring rules in the loader, with the same in-memory, never-stored semantics. Until conversion is done, the old rules file keeps applying as today, and merchant rules apply on top (a merchant rule wins over an old text rule).
- **Retire `FINANCE_RULES_PATH`** after conversion. Merchant files always live in the data folder; tests point `FINANCE_DATA_DIR` at a temp copy.
- **Conversion:**
  - It runs from the panel, which shows a one-line attention item until it's done.
  - Proposals group each rule's matched spellings. A rule whose text matches several spellings proposes one merchant owning all of them; the review can split spellings out or drop the pattern.
  - Confirming the whole list writes both merchant files and renames `rules.csv` to a dated backup in `SORTED/backups/`. The conversion is one UNDO step.
- **Panel:**
  - The labeling panel keeps its overlay, its LABEL THEM → / REVIEW → entry points and the TRANSFER PAIRS tab.
  - The merchant-group list and the RULES tab are replaced by To label and All merchants.
  - Card-state preservation across re-render, real-click gating and the stale-list signature keep today's mechanisms. The signature now also covers the merchant files' version, so an alias change makes an open list stale.
- **Previews:** every change shows rows and dollars by label before and after, computed with the same rule application the loader uses, so a preview can't disagree with the result.
- **Relabel** writes through today's label-writing function, with "relabel from" set to the label shown on the card. That's the mechanism RELABEL AS TRANSFER already uses.
- **UNDO** extends today's record: master and both merchant files, each with its modification time stored as a string. It restores only while none of them has changed since.
- **Name-similarity suggestions:**
  - They come through a small client to the app's embedding server (ADR 0022; set up in its own session). Model: EmbeddingGemma 2 with the `task: search result | query: ` prefix on spellings, closest merchant by cosine, shown only at or above 0.84.
  - The cutoff is a named constant. Measured on the answer key it gives about 87 of 109 right suggestions and 65 wrong ones on 428 unrelated spellings.
  - Vectors are cached by text, as the embedding setup already does. With the server down the client returns nothing and the panel shows pattern suggestions only.
- **Attention line** gains: rules not yet converted; merchant files disagree; open suggestions count (shown in the panel, not the header).
- **Demo data:** `Test Data/SORTED/` gets made-up `merchants.csv` and `merchant_aliases.csv` matching `make_demo_data.py`'s merchants, with at least one merged merchant, one pattern, one dismissed suggestion and one category-only merchant. They're tracked like the demo `rules.csv`, which is removed once the demo is converted.
- **ADR 0025** is the authority for anything above. The labeling path rule is rewritten in the same change (merchant files, two-file writes, conversion pitfalls).

## Testing Decisions

- **A good test** drives behaviour from outside and checks what the user would see or what lands on disk: labels in the master, contents of the merchant files, status text, UNDO results. Never private helpers or call order. Every test runs on temp copies of the demo data; none touches real data.
- **Seam 1, the pure merchants module.** Tested like `tests/test_labels.py` and `tests/test_rules.py`:
  - merchant of each row (unmerged, merged, nameless);
  - the merchant list;
  - rule application, including hand-label-wins, category-only merchants, category agreement, and merchant rule winning over an old text rule during conversion;
  - pattern suggestions and dismissals;
  - each change and its preview;
  - two-file saves: rollback when the second swap fails (simulated lock), safe order (simulated crash between swaps), and the forgiving reader on disagreeing files;
  - conversion proposals on the demo data, and that conversion preserves every rule label unless the review changed it.
- **Seam 2, the app's callbacks against a temp demo copy.** Prior art: `tests/test_label_panel.py`, which loads the app with temp `FINANCE_DATA_DIR` and calls handlers directly. One test per carried-over safeguard:
  - the shared matcher;
  - only unlabeled rows touched;
  - stale list and count mismatch write nothing, including after an alias change;
  - write order and a failed merchant-file save keeping the labels;
  - no group buttons on nameless or money-in-and-out merchants;
  - the Remember default (3 months, single row);
  - TRANSFER only suggested;
  - unlabeled money counted nowhere;
  - the daily snapshot;
  - UNDO for each action kind, and UNDO refused after another write;
  - relabel only changing rows still showing the seen label;
  - a file open in Excel leaving everything unchanged;
  - plus the acceptance test's merchant version: label the top merchants, remember them, import a new statement, and only the remembered merchant's new row is labeled.
- **Seam 3, embedding suggestions.** The client is tested against a fake server returning known vectors (cutoff, closest merchant, server down, cache), like the AI chat's fake-server tests. A hand-run script, outside CI, re-measures quality against the local answer key in `.claude/research/merchant-aliasing/` and reports right and wrong suggestions at the cutoff.
- **Seam 4, browser.** `tests/test_ui_states.py` gains the new views, sort switch, card actions and preview, in both themes.
- Existing suites must keep passing. Tests that today copy the demo `rules.csv` move to the demo merchant files.

## Out of Scope

- The AI chat itself (its own spec), and any chart or drilldown grouped by merchant. The chat only consumes the two functions.
- Setting up or owning the embedding server: that's the embedding session's work, and this spec only uses its endpoint.
- Patterns that join spellings automatically, and grouping by any similarity score.
- Naming merchants with a language model.
- Editing transfer-pair logic (ADR 0017) or the replacement-card flow (ADR 0006).
- Excel export and import of merchants. Excel import of labels stays as it is.
- Rows with no spelling getting merchants or rules.
- Net worth and budgets.

## Further Notes

- Real-data measurements behind the cutoff and the rejected options are in the local, git-ignored `.claude/research/merchant-aliasing/`. They hold real merchant names and must never be committed (ADR 0024).
- In the user's data, 14 of 537 spellings have money in and out. They hold 52% of spending, mostly card payments and brokerage moves, so row-by-row labeling for them is expected and fine.
- Only 108 of 2,152 rows get their label from a rule today. Conversion mainly protects future rows, so the review can be thorough without risking much.
- ADR numbering: 0023 is held by the embedding session's draft. This work uses 0024 and 0025.
