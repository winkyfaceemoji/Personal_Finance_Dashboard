---
paths:
  - Modules/merchants.py
  - Modules/similar.py
  - Test Data/SORTED/merchants.csv
  - Test Data/SORTED/merchant_aliases.csv
---

# Merchants (ADR 0025)

Terms (spelling, merchant, alias, rule, pattern) are defined in `CONTEXT.md`. The build plan is `.scratch/merchants/issues/`, and the spec is `docs/specs/merchants.md`.

## Files
- `SORTED/merchants.csv` holds one row per merchant: name, label, category, patterns. `SORTED/merchant_aliases.csv` holds one row per spelling–merchant pairing, with status `alias` or `dismissed`. Both live beside the master, hold real names, and never enter the repo (ADR 0024). The demo's are made up and tracked.
- A spelling is `merchant_key`, unchanged: grouping pitfalls are in the labeling rule. A spelling with no alias is its own merchant, named after itself, and a row with no spelling has no merchant.

## Writes (`save_merchants`)
- The caller holds `MASTER_LOCK`; the function doesn't take it, so it can run inside a labeling write that already holds it.
- Both temp files are written before either swap. If the second swap is refused (Excel), the first is put back atomically and a `PermissionError` saying "Nothing changed: <file> is open in another program" is raised. If even the put-back fails, an `OSError` says the files may disagree; the forgiving reader then keeps the app safe.
- **Order is the crash guard.** `adding=True` writes `merchants.csv` first (a merchant with no spellings is harmless). `adding=False` writes the aliases first (spellings fall back to their own merchant). Pass the flag that matches the change, or a crash can leave an alias pointing at nothing.

## Reading (`read_merchants`)
- The forgiving reader ignores an alias that points at a missing merchant, or a spelling filed under two merchants. That spelling stays its own merchant, and `problems` says why. Empty rows, a merchant listed twice (first row wins) and an unreadable file are reported the same way; an unreadable `merchants.csv` means no merchants at all, never a crash. `attention_parts` shows the problems in the header's "other" item; never guess which alias was meant.
- Alias spellings are normalized on read (`normalize_description`), so a hand-typed `AMZN  Mktp US` still matches.

## Remember and UNDO
- `remember(merchants, name, spellings, label, category, today)` returns both files with the rule set; a merchant that doesn't exist yet is made, so an unmerged spelling becomes a merchant named after itself, with its alias. Save it with `adding=True`.
- `snapshot_files` keeps both files' exact bytes as latin-1 text (JSON-safe), and `restore_files` writes them back through the same two-file write, aliases first. A file that was missing is removed again.

## Merge, split, rename
- `merge`, `split` and `rename` return the new `(table, aliases)`. Save them with **`save_change(folder, before, table, aliases)`**, never `save_merchants` directly: it works out the crash-safe order from what the change adds and removes. A change that does both (a rename; a merge into a new merchant) goes in two saves, first with the old row still there. A plain `adding=` flag got this wrong for renames: a crash left aliases pointing at the old name.
- `merge` takes a merchant (all its spellings move; its row, and rule, go) or one spelling of a merged merchant (only it moves: the MOVE button). A bare-spelling target becomes a new merchant named after its highest-spend spelling (`spend` is money out *by spelling*).
- Dismissed suggestions follow a rename or merge (`_renamed`), and tying a spelling to a merchant clears any dismissal of that same pairing (`_tie`).
- `split` of a merchant's last spelling ends the merchant, rule and all: otherwise an invisible merchant keeps its name taken.
- A new name may not equal any merchant name or spelling in use, whatever its case (`names_in_use`), including the merchant's own spellings: that would make SPLIT OUT of the spelling impossible. Typed names resolve with `find_merchant`, case-insensitive.
- `merchants_from(table, aliases)` builds Merchants exactly as the reader would, so a preview of a change (`label_changes`) trusts the same aliases loading will. `rule_labels` gives label *and* category per row (the keywords applied too), so the preview shows a category that goes away, as `describe_label` text ("unlabeled · Venmo").
- `_write_pair` says "Nothing changed: <file> is open in another program" whichever of the two swaps is refused. When `save_change`'s *second* save is refused, it restores the first from a snapshot, so "Nothing changed" stays true.
- `merge` resolves a target that is a spelling of another merchant to that merchant: it never pulls a spelling out of its merchant.

## Patterns and pattern suggestions (ticket 07)
- Patterns live in `merchants.csv`'s `patterns` cell, `"a | b"` (`PATTERN_SEP`), and match normalized spellings by substring. They only ever **suggest** (`pattern_suggestions`): a spelling joins on CONFIRM (a merge), never on its own (ADR 0025).
- Only spellings with no alias get suggestions; a dismissed pairing (`dismiss` writes a `dismissed` alias row) never comes back. The longest matching pattern wins.
- `merchant_overview` fills `suggested` / `suggestions` (pattern suggestions by default; pass `suggested=` to add others), which the needs-attention sort ranks first.
- `set_patterns` gives a bare spelling a merchant row (and its alias) to hold them, so it refuses empty patterns there (the alias would stop it ever being suggested elsewhere), and any pattern under `MIN_PATTERN` (3) letters.
- Patterns match the *spelling*, which has already lost words with digits and ID tails: a pattern like "store 123" never matches.
- A merge carries the source's patterns over to the target, as it does its dismissals.

## Converting the old rules (ticket 08)
- `convert_proposals` must reproduce what the keywords give each spelling on load (`_keyword_rule` is `apply_auto_categories` for one row): keywords **stack** (`cashout` labels a row, a later `venmo` adds its category), so a spelling's merchant carries both. A keyword whose spellings end up labeled differently makes one proposal each. A first version gave each spelling only its first keyword and dropped 71 demo rows' category.
- Spellings already a merchant's are never proposed again. A keyword matching nothing today becomes a merchant holding only its pattern.
- `apply_conversion` refuses two proposals with one name, or a name already a merchant's. The review's edits (name, label, category, ticked spellings, keep pattern) arrive as the edited proposals.

## Overview (`merchant_overview`, `sort_merchants`)
- One item per merchant over **all** its rows. `out`/`inn` are positive sums of money out and in. `labels` are the valid labels its rows carry; `has_rule` is the merchant's own rule only.
- Needs attention: open suggestions (`suggestions`, filled from pattern suggestions), then rows whose labels differ, then no rule, each by spend.
- `display_name` is the one rule for showing a name: as typed when you gave it, capitals for a bare spelling. Groups and cards both use it.

## Rules on load
- `load_transactions` applies merchants' rules (`apply_rules`) **before** the `rules.csv` keywords, so a merchant's rule wins and the keywords only fill what's left (until ticket 10 removes them). Same semantics as the keywords: the label goes only on rows with none (a hand label wins), and the category only fills a blank one where the labels agree. A category-only merchant fills any of its rows.

## Name-similarity suggestions (`Modules/similar.py`)
- `PREFIX` and `CUTOFF` were measured together on EmbeddingGemma 2. A different prefix or model moves every score, so re-run `merchant_eval.py` against the answer key before changing either. The research embedded spellings further cleaned (punctuation, `sq`/`tst` prefixes and `inc`/`llc` suffixes stripped); the module sends the bare spelling, so `merchant_eval.py` is the number to trust.
- Raw cosines bunch high (most pairs 0.75–0.95), so a score alone doesn't mean "alike". Only the closest merchant counts, and only at or above the cutoff.
- `embed` returns None, never raises, when the server is down, slow or answers badly; `similar_merchants` then returns `{}`. The feature must stay silent then, with pattern suggestions unaffected. Each call to a down server still waits for the refusal (about 2 s on Windows) or the timeout.
- Vectors are cached in memory per `http_embedder`, by text, for the life of the process. Make one embedder and reuse it, or every call re-sends every spelling.
- In the app, `_suggestions` is the one place both kinds meet: pattern matches first, similarity only for spellings no pattern names. YES and NO re-check through it. The first `None` from the server sets `_EMBED_DOWN`, and it isn't asked again until restart (ADR 0023), so a down server costs one wait, not one per page.
- Until the embedding session's server lands (ADR 0023), `FINANCE_EMBED_URL` names a server; unset, similarity suggestions stay off.
