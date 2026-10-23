---
paths:
  - Modules/labels.py
  - config.py
  - Test Data/SORTED/rules.csv
  - app.py
---

# Labeling panel, rules & transfer pairs

The pure functions live in `Modules/labels.py` and `Modules/merchants.py`. The panel callbacks (`_do_label`, `_write_labels`, undo, conversion) live in `app.py`. Background: ADR 0025 (which replaces 0008) and 0017.

## Where rules live
- The real rules are `SORTED/rules.csv` in the data folder (`get_rules_path`), never the repo: they name real merchants (ADR 0024). `RULES_PATH` must follow the data folder when setup changes it.
- `Test Data/SORTED/rules.csv` is made up and tracked. Never copy real rules into it; tests copy it to a temp folder before writing.

## Writes
- The panel never edits an existing label. **RELABEL AS TRANSFER** is the only exception: an explicit click, and only if the label on disk is still the one on the card (`relabel_from`).
- All writes go through `label_rows` → `apply_label_import`, the Excel import's matcher, so the two paths can't disagree. Only rows with no valid label are touched, and a hand-labeled twin keeps its label.
- Stale-list guard:
  - A group click must match the group's `sig`.
  - If the labeled-row count differs from what was shown, write nothing.
  - Rows the user didn't see are never labeled. LABEL ALL covers only the pairs on screen (max 25).
- Order in `_do_label`:
  1. Master write: lock, backup, atomic.
  2. Build the undo record.
  3. Remember: snapshot the merchant files into the undo record, then save the merchant's rule (`remember` + `save_merchants`).

  Remember comes strictly after the master. A merchant-file failure (open in Excel, unwritable) keeps the labels and UNDO, and only appends `· not remembered: …` to the status. The snapshot goes into the record only once the save succeeded.
- `rules.csv` writes (`add_rule`, `delete_rule`) are atomic and run under `MASTER_LOCK`. `add_rule` refuses a keyword under 4 characters, a duplicate, or an invalid category.
- Excel import (`apply_label_import`):
  - A row with a blank or unreadable date is *skipped*. It must never be applied to every date.
  - Unmatched rows are counted and reported.
  - Export writes UTF-8 *with BOM*, so Excel keeps non-ASCII descriptions and they still match on re-import.
- An unreadable `not_transfers.csv` is never overwritten. The click reports the problem instead.

## Dash quirks
- Re-rendering the list adds buttons with `n_clicks` 0, which fires pattern-matching callbacks. Gate every handler with `_is_real_click`.
- Card state survives re-render: `render_label_list` reads back the typed subcategory, the Remember tick and the open row list, then re-applies them. Dash doesn't report a `<details>` toggle, so each summary counts its clicks and the parity flips the last-rendered `open`.
- The undo record stores `st_mtime_ns` as **strings**. Nanosecond times exceed 2^53, and the browser's JSON round-trip would round them, making every undo look stale.
- Undo works only while none of the files in `_undo_files()` (the master, `rules.csv`, both merchant files) has changed since the click. Add a file there when a label action starts writing it.
- Undo refuses up front if any tracked file is open in another program (`_first_locked`), so the user can close it and retry. Then it puts the merchant files back (`restore_files`, byte for byte from the snapshot) and then the master; if the master is still refused, the merchant files go back to their labeled state, so an Undo is never half done.

## Grouping (`merchant_key`, then merchants)
- The To label list groups by **merchant**: `unlabeled_groups(..., merchants=)` puts all of a merchant's spellings in one group. The list and the click must both build groups through `_todo_groups`, or a click can't find its group.
- Every group's `sig` includes the merchant files' `version`, so any merchant change makes an open list stale.
- A merged merchant's name shows as typed; a bare spelling (all lower case) shows in capitals.
- The ACH code-token pattern (`rtl-`, `ppd-`, `ccd-`, `web-`) is narrow on purpose. A generic `xx-…` pattern eats names like `wal-mart`.
- Names that start with a number or contain a hyphen must survive (`7-eleven`, `99 ranch market`).
- After a processor prefix (`tst`, `sq`, `sp`, `paypal`), keep the next word if it has a letter. A bare number there is a phone number.
- These descriptions become their own one-row *fallback* group, never a shared catch-all:
  - descriptions with no recognisable name;
  - real-time payments (`REAL TIME PAYMENT …`): the text names the network, not the payer.
- Group buttons appear only for groups that are neither fallback nor mixed-direction. One click must label one kind of thing. Row clicks label identical twins too, and never create a rule.

## Remember (`remember_check`, ADR 0025)
- Remember saves the merchant's rule. It matches whole spellings, so the old keyword checks (length, other merchants, overlapping rules) don't apply: a short name like `AB` can be remembered.
- Still applied: nameless rows can't be remembered; money in and out has no group buttons; a single transaction, or one seen in fewer than `REMEMBER_MONTHS` months, starts unticked.
- **Measured over every row of the merchant, not just those shown.** A rule labels all of them, and REVIEW → shows only the last import. So the month count, and the money-in-and-out check (on the unlabeled rows), use the whole merchant: a merchant whose older refunds are unlabeled can't be remembered from a view that only shows its purchases.
- Nameless rows sit in their own NO MERCHANT NAME section after the merchants, each labeled one at a time.

## All merchants (`_merchants_view`, ticket 04)
- All time: it never reads the period bar. The `LABEL_TOP_N` biggest by spend get cards, shown in the chosen sort; the rest, always the smallest, fold into one `Other · N merchants` line (the user's choice: no sort may fold a big merchant away), then a `No merchant name` line.
- Cards show the merchant's own rule *and* the labels its rows carry: until `rules.csv` keywords are converted (ticket 08), a row can be labeled by a keyword while its merchant says "No rule".
- Merge, split and rename (ticket 05) never apply on the click. `_merchant_preview` stores the pending change (with the merchant files' `version`) in `merchant-pending` and shows what it would relabel; CONFIRM (`_do_merchant_change`) applies it only if the files are still that version, else writes nothing. Both go through `_merchant_change`, so the preview and the result can't disagree. A refusal (name in use, no merge target) goes to the status line, never next to a CONFIRM.
- A merchant change writes only the merchant files: its undo record has no `backup`, and `_do_undo` restores the master only when one is there. It refuses up front (`_first_locked`) when a merchant file is open elsewhere.
- **Relabel (ticket 06)** is ADR 0025's one exception to "only unlabeled rows". The preview stores in `pending["rows"]` the hand-labeled rows it showed, each with the label seen; CONFIRM (`_do_relabel`) rewrites exactly those through `label_rows(relabel_from={seen})`, one at a time, and leaves (and counts) any whose label changed since. Never re-read the rows at CONFIRM: a row changed in Excel in between would be relabeled. A row's expected count includes identical unlabeled twins, because `label_rows` takes them too; without that, the row was always "left as it was". Master first, then the rule (`save_change`); a rule that can't be saved keeps the labels and UNDO. The preview calls out refunds when a merchant has money in and out.
- "Same as …?" (`_suggestion_line`) shows on To label and All merchants cards. YES and NO both go through the preview and CONFIRM like every merchant change (YES is a merge, NO a dismissal), and both re-check the suggestion still stands.
- The sort switch (`merchant-sort`) lives in the static layout, hidden off this tab; a change bumps `label-version` to re-render.
- The settings menu's LABELS & MERCHANTS is the way in when nothing is unlabeled (the header's LABEL → only shows while something is). `_opening_tab` opens it on To label while anything is unlabeled, otherwise on All merchants.

## Converting rules.csv (ticket 08)
- While `rules.csv` holds keywords loading applies (`valid_keywords`), the header shows CONVERT →, which opens the CONVERT RULES tab: one editable proposal per keyword (`_convert_view`). CONVERT ALL (`cv-go`, in the static layout because every callback id must be) previews the whole result.
- **No past label moves, by construction.** A keyword can label part of a spelling's rows (`… 0142` and `… 0377` share a spelling), or stack with others, so a merchant rule can't always reproduce it. `_conversion` therefore stores every label and category the keywords give a row today on that row (`freeze_keyword_labels`), then `keep_past` takes the rule off any proposal that would still move a past row: its new rows wait for a person. The preview names the rows that get a stored label and the merchants left without a rule; "no labels change" unless the review changed one.
- CONFIRM (`_do_convert`) refuses if the merchant files or `rules.csv` changed since the preview (a hash of its bytes rides in the pending change), or if any of the four files is open elsewhere. Order: back up and write the master (only when a label gets stored), save the merchants, copy `rules.csv` to `SORTED/backups/rules-converted-<date>[-n].csv`, delete it. An `OSError` on any step restores all of them. One UNDO restores the master backup, both merchant files and `rules.csv` byte for byte.
- Until then the keywords keep applying on load, under the merchants' rules.

## `rules.csv` keywords (until ticket 10)
- No tab lists or deletes them any more; CONVERT RULES replaces it. The app no longer calls `rule_check`; it stays, with `add_rule`, until ticket 10 removes the keyword machinery. Its checks, in order:
  1. Keyword is at least `MIN_KEYWORD` (4) characters.
  2. It matches this merchant only, across **all** rows, labeled ones included.
  3. No existing rule equals, contains or is contained by it, or matches the group.
  4. The group is one direction of money.
- Failing 1–3 is blocking: the checkbox is disabled and unticked. Failing 4 only adds a note.
- A single-transaction group passes but starts unticked, because one row is thin evidence.
- Remember starts ticked only for a regular: the merchant has charged in at least `REMEMBER_MONTHS` (3) different months. A few charges close together (a trip) are thin evidence for a rule that labels every future match, so 1–2 months start unticked with a `seen in N months` note.
- The checkbox is disabled wherever it can't act: fallback or mixed cards have no group buttons.
- There are no built-in transfer rules. `looks_like_transfer` only stars a *suggested* button, which must never look selected.

## Transfer pairs
- A pair needs an exact opposite amount, on a different account (source + card), within `TRANSFER_PAIR_DAYS` (5). It is shown only when neither row has another candidate, labeled rows included.
- Unlabeled sides of certain pairs, and copies waiting on a replacement-card question, are left out of every unlabeled count: the attention line, `_blocking_rows`, and the unreviewed lines. That keeps the header and headline in agreement.

## Recovery files
- `before-labeling-YYYY-MM-DD.csv` must stay outside the backup rotation's glob. It must never be pruned or picked by auto-restore. Write it once per day. If the copy fails, the panel still opens.
- To restore a snapshot:
  1. Stop the app.
  2. Copy the snapshot over the master.
  3. Restart the app, or use RELOAD DATA.

  Restoring doesn't touch the merchant files or `rules.csv`. A snapshot taken before a conversion has the keyword labels unstored; restore the matching `rules-converted-*.csv` too, or UNDO the conversion instead.
