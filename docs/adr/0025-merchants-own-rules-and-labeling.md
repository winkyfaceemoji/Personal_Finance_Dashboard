# 0025. Merchants own the rules; one panel labels and reviews them, with every 0008 safeguard

Status: Accepted (supersedes 0008)

## Context
One merchant shows up under many spellings (`AMZN MKTP US`, `AMAZON PRIME`), so it was labeled and remembered once per spelling. Substring rules had grown to cover several merchants at once (`sq *the` hit five shops, `zelle payment to` every person), and a past label could only be fixed through Excel. ADR 0008's safeguards made one-click labeling safe; they must survive the change. Terms are defined in `CONTEXT.md`.

## Decision
- **Merchants.** A merchant is the spellings you would always label the same way. An alias ties one spelling to one merchant by exact match, in `SORTED/merchant_aliases.csv`. A merchant's name, label, category and patterns are in `SORTED/merchants.csv`. Both are read on every load. A spelling with no alias is its own merchant. A row with no spelling has none.
- **Rules belong to merchants.** A rule is a merchant's saved label; a hand label always wins. Substring rules are retired: the old `rules.csv` is converted once, through a review list, and kept as a backup. Its text survives as merchant **patterns**, which only *suggest* a new spelling, never join it.
- **Suggestions are never applied on their own.** They come from patterns, and from the nearest name by EmbeddingGemma 2 above a cutoff, through the app's embedding server. With the server down, only patterns suggest.
- **One panel.** A *To label* view and an *All merchants* view (all-time spend) replace the labeling groups and the RULES tab. TRANSFER PAIRS stays.
- **0008's safeguards carry over:**
  - every label goes through `label_rows` → `apply_label_import`, under the lock, with a backup and an atomic swap;
  - only rows with no valid label are touched;
  - a stale list or a count mismatch writes nothing;
  - the master is written first, then the undo record, then merchant files;
  - group buttons never appear on nameless rows or on merchants with money in and out (labeled row by row);
  - Remember starts ticked only for a merchant seen in 3+ months;
  - TRANSFER is only ever suggested;
  - unlabeled money is shown, never counted;
  - daily snapshot, rotating backups, UNDO.
- **One new exception to "only unlabeled rows":** relabelling a merchant rewrites its hand labels, but only rows still showing the label you saw, after a preview of rows and dollars. It also updates the merchant's rule.
- **Every merchant action previews its effect,** and UNDO reverses the last one.
- **Two-file writes:** both temp files are prepared, then swapped back to back. If the second swap fails, the first is rolled back. Adding writes `merchants.csv` first and removing writes the aliases first, so a crash leaves a valid state. A reader that finds the two files disagreeing falls back to the spelling and says so.

Rejected:
- Grouping by fuzzy string score: it missed abbreviations (`amzn`/`amazon`) and chained unrelated names through shared words. Measured: 20–24 of 39 merchants whole.
- Grouping by an embedding score cutoff: scores bunch together, so a cutoff that merges `amzn`/`amazon` also merges two different "King's" restaurants. The closest match is good (96%), so it is used for suggestions, not merges.
- Keeping substring rules beside merchant rules: two kinds overlap, and the broad one blocks the specific one.
- Patterns that join new spellings automatically: they label a stray match before anyone sees it.
- One storage file with a row per spelling: merchant details repeat, and pattern-only merchants need placeholder rows.
- A local LLM naming merchants: only works while the chat model runs. A merged merchant is named after its highest-spend spelling, and you can rename it.

## Consequences
- One click labels a merchant across all its spellings, and a past call can be fixed in the app.
- A new payee waits for your confirm, even one a pattern recognises.
- Big merchants with a refund lose their one-click buttons; their existing rules still label refunds.
- The AI chat groups by merchant through one pure function and lists merchants with their spellings.
- Merchant files hold real names, so they live in the data folder (ADR 0024).
