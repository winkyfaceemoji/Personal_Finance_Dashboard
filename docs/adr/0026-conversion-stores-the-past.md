# 0026. Converting rules.csv stores the keywords' past labels on the rows

Status: Accepted

## Context

ADR 0025 replaces the `rules.csv` keywords with merchants' rules, converted once through a review. The obvious conversion turns each keyword into a merchant whose rule gives the same label. Measured on hard keyword sets it moves past labels, and so totals, in ways the review can't see or fix:

- A keyword can match part of a spelling's rows (`maple street grocery 0142` labels one store's rows; the spelling `maple street grocery` covers every store).
- Keywords stack: one gives the label, a later one the category, and they can disagree across a merchant's spellings.
- A typo'd label is skipped on load, and a spelling may already belong to a merchant.

A merchant's rule matches whole spellings, so for these no choice of rules reproduces the past.

## Decision

At CONFIRM, every label and category the keywords give a row today is stored on that row in the master (backup plus atomic swap, ADR 0003), except where the review chose otherwise: an unticked spelling's keyword labels are dropped, and a changed label or category is stored instead. The new merchants' rules then apply to new rows only. A proposal whose rule would still move a past row keeps its spellings and pattern but gets no rule, so its new rows wait for a person. The preview names every row that moves, the rows that get a stored label, and the merchants left without a rule.

Rejected: converting into rules alone (it moves the past, above); keeping the keywords forever under the merchants (two kinds of rule, which ADR 0025 set out to end).

## Consequences

- No past label moves unless the review moved it, by construction rather than by checking each case.
- Keyword-given labels become stored labels and look like hand labels from then on. A later relabel of the merchant treats them as hand labels.
- The master is written, so one UNDO restores the master, both merchant files and `rules.csv`. `rules.csv` is kept as `SORTED/backups/rules-converted-<date>.csv`.
- Loading still applies an unconverted `rules.csv`, so a data folder that hasn't converted shows what it always did.
