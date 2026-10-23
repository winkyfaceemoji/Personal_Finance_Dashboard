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

## Overview (`merchant_overview`, `sort_merchants`)
- One item per merchant over **all** its rows. `out`/`inn` are positive sums of money out and in. `labels` are the valid labels its rows carry; `has_rule` is the merchant's own rule only.
- Needs attention: open suggestions (always 0 until ticket 07 fills `suggestions`), then rows whose labels differ, then no rule, each by spend.
- `display_name` is the one rule for showing a name: as typed when you gave it, capitals for a bare spelling. Groups and cards both use it.

## Rules on load
- `load_transactions` applies merchants' rules (`apply_rules`) **before** the `rules.csv` keywords, so a merchant's rule wins and the keywords only fill what's left (until ticket 10 removes them). Same semantics as the keywords: the label goes only on rows with none (a hand label wins), and the category only fills a blank one where the labels agree. A category-only merchant fills any of its rows.

## Name-similarity suggestions (`Modules/similar.py`)
- `PREFIX` and `CUTOFF` were measured together on EmbeddingGemma 2. A different prefix or model moves every score, so re-run `merchant_eval.py` against the answer key before changing either. The research embedded spellings further cleaned (punctuation, `sq`/`tst` prefixes and `inc`/`llc` suffixes stripped); the module sends the bare spelling, so `merchant_eval.py` is the number to trust.
- Raw cosines bunch high (most pairs 0.75–0.95), so a score alone doesn't mean "alike". Only the closest merchant counts, and only at or above the cutoff.
- `embed` returns None, never raises, when the server is down, slow or answers badly; `similar_merchants` then returns `{}`. The feature must stay silent then, with pattern suggestions unaffected. Each call to a down server still waits for the refusal (about 2 s on Windows) or the timeout.
- Vectors are cached in memory per `http_embedder`, by text, for the life of the process. Make one embedder and reuse it, or every call re-sends every spelling.
