# In-App Labeling — Design

**Date:** 2026-10-09 · **Status:** implemented; text revised to match the code

## Why

The dashboard is a private, local tool. You download bank and card statements as CSV files, and it answers two questions for any week, month or year: *am I on track?* and *where did the money go?*

A bank file can't say what a transaction *means*, so every transaction needs one of three labels:

- **Expense:** money left you for someone else.
- **Income:** money came to you from someone else.
- **Transfer:** money moved between two of your own accounts, such as paying a credit card from checking.

Only labeled rows are counted. In the demo data, 562 of 1,343 rows ($152,346) are unlabeled and missing from every number. Today the only way to label them is Export → Excel → Import, which is slow enough that it doesn't get done. Weekly tracking makes it worse: each week's statements arrive unlabeled unless a `rules.csv` keyword matches them.

**Success has three parts:**
1. Anyone can clear the backlog inside the app in one sitting, one click per merchant.
2. Later weeks stay mostly labeled automatically.
3. No click or rule can quietly corrupt totals the user never looked at.

## Decisions

| Question | Decision |
|---|---|
| Unit of labeling | **By merchant group**, one click for the whole group. A group expands to label single rows, which is the only safe way to split mixed groups such as Zelle or Venmo. |
| Remember for future statements | A checkbox per group. **It is ticked by default only when the rule is provably safe and the group has at least two transactions** (see *Rule safety*); otherwise it starts unticked, with the reason shown. It is disabled on cards without group buttons. |
| Placement | A full-screen panel opened from the header's unlabeled warning, and from the new post-import line. |
| Labels that are already set | Not editable here. Export and Import still cover that. |
| Unlabeled money in the totals | Still **not** counted, because counting it by sign would double-count card payments. Instead each stat card shows how much is unreviewed. |
| Built-in transfer rules | **Not added.** On the demo data, card-payment phrases cover 1% of unlabeled dollars, and the council rejected unreviewed rules. Instead, groups that look like card payments get a **suggested** Transfer button (highlighted, never auto-applied). |
| Approach | Plain Dash components with pattern-matching callbacks. No new dependency. |

**Out of scope:** relabeling, AI suggestions, a starter ruleset, budgets, search, pagination beyond the top 25 groups.

## Measured on the demo data (2026-10-09)

Measured with the final `merchant_key` on the demo data:
- **286 merchant groups**, with 0 fallback groups and 5 mixed groups.
- The **top 25 groups cover 87.7%** of unlabeled dollars ($133,640 of $152,346).
- **`rule_check` passes for 268 of 286 groups, which is 52.7% of unlabeled dollars.** 20 of the top 25 pass.
- Of the groups that fail, 9 also match another merchant, 4 have a keyword that is too short, and 2 overlap an existing rule. Another 3 are mixed, which is not blocking.

So one sitting of about 25 clicks clears most of the backlog, and "remember" covers most recurring merchants.

## Labeling guide (shown in the panel)

A collapsible **"How to choose"** box at the top of the panel:

> **Ask one question: did money enter or leave *you*, counting all your accounts as one pot?**
> - **Expense:** it left you for someone else (groceries, rent, a Zelle to a friend for dinner).
> - **Income:** it came to you from someone else (paycheck, client payment, tax refund).
> - **Transfer:** it moved between your own accounts (credit-card payment, moving money to savings or investments, Venmo cash-out to your bank). Card purchases were already counted, so the bill payment must not count again.
>
> **Tricky cases:**
> - **Card payment ("AUTOPAY", "PAYMENT THANK YOU"):** Transfer, on both the checking and the card side.
> - **Refund:** Expense. It shows as a positive amount and reduces your spending.
> - **A friend paying you back:** Expense, for the same reason.
> - **Venmo, Zelle, PayPal:** depends on who's on the other end. Expand the group and label row by row.
> - **ATM cash:** Expense, or Transfer if you track cash separately. Pick one and keep to it.
> - **Loan or mortgage payment:** Expense.

## User experience

1. **Header.** The unlabeled note (`⚠ 562 of 1,343 transactions ($152,346) are unlabeled and not counted.`) gets a **LABEL THEM →** button beside it. The button is hidden when nothing is unlabeled.
2. **After an import or Reload that added rows,** a second header line appears: `Last import: 31 new · 27 labeled · 4 need you`. **REVIEW →** appears beside it while any of those rows are still unlabeled, and opens the panel filtered to them. A Reload that adds nothing leaves the line as it was.
3. **Stat cards:** Spent and Income each gain one muted italic line when the period has unlabeled money out or in (at least $0.50): `+ $412 unreviewed`. Net and Savings rate don't. The numbers are visibly incomplete, not silently incomplete.
4. **The panel** is a full-screen overlay. Its header reads `LABEL TRANSACTIONS` with the summary `562 rows · $152,346 · 286 merchants · showing the top 25`, next to the **TO LABEL / RULES** tabs and **DONE**. The guide and a status line with **UNDO** follow.
5. **Groups** are sorted by absolute dollars, largest first. Only the **top 25** are shown, and the rest follow in the next session. Each group shows:
   - the merchant, count, net total, date range, and one example description;
   - **EXPENSE / INCOME / TRANSFER** buttons, with TRANSFER highlighted as *suggested* when the description matches a card-payment or own-account-transfer phrase. Fallback and mixed groups show `Label these one at a time below` instead of the buttons;
   - a **Subcategory** box (optional, e.g. "Coffee") with suggestions from subcategories already in use;
   - **Remember for future statements**: the checkbox plus `rule "starbucks" (money out) · labels 14 rows ($87) now`, or the reason it's off (`also matches PAYPAL SPOTIFY, PAYPAL HULU`, `money in and out — check the rows first`, or `existing rule "venmo" would override it`);
   - a **MIXED** badge when the group has both money in and out;
   - a **Label rows one at a time (N)** expander listing the rows (date · description · amount), each with its own three buttons. It is open by default on fallback and mixed groups.
6. **A click saves immediately.** The group or row disappears and the status reads `Labeled 14 STARBUCKS rows as Expense · rule "starbucks" added`, with **UNDO** beside it.
7. **UNDO** reverts the last action only, and only while neither the master nor `rules.csv` has changed since.
8. **Rules tab:** the rules this panel added (keyword, label, subcategory, `matches N rows`, date added), each with **DELETE**. Hand-written rules are listed read-only.
9. **DONE** closes the panel and refreshes the whole dashboard.
10. **Snapshot.** The first time the panel opens each day, the master is copied to `SORTED/backups/before-labeling-YYYY-MM-DD.csv` (local date), outside the ten-file backup rotation, so the state from before a long session can't be pruned away. Reopening the same day keeps that first copy.

## Rule safety

A rule in `rules.csv` applies to every unlabeled row whose description contains the keyword (case-insensitive), past and future, on every load. The first matching rule wins. Labels saved in the master always win over rules.

"Remember" is **ticked by default only if all of the following hold AND the group has at least two transactions**, checked in this order (a fallback group fails first, with `no recognizable merchant name`). Otherwise it starts unticked and shows the reason; a one-transaction group that passes stays enabled with the note `only one transaction — tick to remember anyway`. The first three conditions hard-block it (the checkbox is disabled).
1. **Long enough:** the keyword is at least 4 characters.
2. **This merchant only:** across **all** rows, labeled or not, every row the keyword matches belongs to this merchant group. Otherwise the reason names the other merchants (up to 3).
3. **Not overridden:** no existing rule's keyword matches any description in the group (it would win first match), and no existing rule's keyword contains the new keyword or is contained by it.
4. **One direction:** every row in the group is money out, or every row is money in.

Mixed groups only offer row buttons, and a row click never creates a rule, so the checkbox is disabled and unticked on every card without group buttons (fallback or mixed).

The keyword is not editable. It is derived; see `rule_keyword` below.

## Components

### `Modules/labels.py` (pure functions, tested)

| Function | Contract |
|---|---|
| `merchant_key(description) -> str` | The group key and rule keyword source, in this order: `normalize_description` (lowercase, `*` and `#` become spaces, whitespace collapsed); cut at the first ` web id`, ` ppd id`, ` ccd id`, ` id:` or ` ach `; drop ACH code tokens (`rtl-…`, `ppd-…`, `ccd-…`, `web-…`, e.g. `rtl-tppsgd`; a generic `xx-…` pattern would also eat names like `wal-mart`); keep the first word, then each following word until one contains a digit (so `7-eleven`, `99 ranch market` and `1-800-flowers` survive); trim ` -.,/`. No letters left → `""`, and the row becomes its own *fallback* group keyed on its full normalized description, never a shared catch-all. The drilldown's `_merchant` is left as is (changing it is out of scope). |
| `rule_keyword(group_descriptions) -> str` | The longest common **word-aligned prefix** of the group's descriptions, lowercased with whitespace collapsed, trimmed of ` -.,/`. It is therefore a real substring of every description in the group, which `merchant_key` isn't always (it drops code tokens). It may be `""`, in which case remember is blocked as too short. Descriptions are compared with whitespace collapsed throughout, and rules match against collapsed descriptions; see the transforms change below. |
| `rule_check(df, rules, group, norm=None) -> dict` | Applies the four *Rule safety* conditions in order. Returns `{"ok": bool, "keyword": str, "reason": str \| None, "blocking": bool, "rows_now": int, "dollars_now": float, "others": [merchant, …], "direction": "money in" \| "money out" \| "mixed"}`. A fallback group, or a keyword under 4 characters, fails before any row is searched. An optional `norm` argument takes the frame's descriptions already normalized, which saves work across many groups. |
| `unlabeled_groups(df, only_row_ids=None) -> list[dict]` | Unlabeled rows (`master_category` not in `PREDEFINED_CATEGORIES`), grouped by `merchant_key`. Each dict has `key` (a short stable hash), `mkey` (the normalized group key), `merchant` (display form), `count`, `total`, `abs_total`, `first`, `last`, `example`, `mixed`, `fallback`, `sig` (a hash of the group's row ids and counts, re-checked at click time), `suggest_transfer` and `rows` (one record per distinct `row_id`, identical twins merged with a `count`: `row_id`, `date`, `description`, `amount`, `source`, `card_last4`, `count`). Fallback and mixed groups get no one-click group label; their rows are labeled one at a time. Sorted by `abs_total`, descending. `only_row_ids` restricts it to the last import's rows. |
| `row_id(row) -> str` | Stable id from `date \| description \| amount \| source \| card_last4`. Identical twin rows share an id, consistent with the import matcher. |
| `looks_like_transfer(description) -> bool` | Matches `payment thank`, `autopay`, `online transfer`, `transfer to`, `transfer from`, `epay`, `card payment`, `directpay` and `internet payment`. Used only to highlight the suggestion. |
| `label_rows(master, rows, category, sub) -> tuple[DataFrame, int]` | Builds an import frame from `rows` and runs `apply_label_import`. It sends each twin once so the count isn't doubled, and only rows with no valid label are candidates, so a hand-labeled twin of an unlabeled row keeps its label. This is the single matching path for Excel and in-app labeling. |
| `last_import_ids(master_path) -> list[str] \| None` | The row ids in `SORTED/last_import.csv`, or `None` when the file is missing or unreadable. |
| `read_rules(path) -> DataFrame` / `add_rule(path, keyword, category, sub) -> bool` / `delete_rule(path, keyword) -> bool` | `rules.csv` I/O. Reads tolerate a BOM, Windows-1252 and a zero-byte file (through `transforms.read_rules_csv`, shared with the loader). Writes are atomic and correctly quoted. `add_rule` appends the columns `keyword, master_category, sub_category, added`, where `added` is an ISO date; `apply_auto_categories` ignores extra columns. It refuses, returning `False`, when the keyword already exists or the category isn't predefined. `delete_rule` removes exactly the matching keyword row. |

### `Modules/transforms.py`

- New `normalize_description(text)`: lowercase, `*` and `#` become spaces, whitespace collapsed. `apply_auto_categories` compares **normalized keywords against normalized descriptions** and reads `rules.csv` BOM-tolerantly. Bank files pad descriptions (`venmo            payment`) and glue processors to merchants (`PAYPAL *NETFLIX`), so this keeps `PAYPAL *NETFLIX` and `PAYPAL *SPOTIFY` apart. Existing keywords such as `mta*nyct paygo` keep matching, because both sides are normalized the same way.

### `main.py` / `Modules/safety.py`

- `rebuild_master` records the last import in `SORTED/last_import.csv` (one `row_id` column, written atomically; its file time is the import time). The new rows are those not carried or rescued from the old master. Nothing is written on the very first import, when every row is new. The header line computes "labeled by rules" and "need you" from the loaded frame.
- `safety.restore_backup(backup, master)`: public atomic restore, used by Undo.
- `safety.snapshot_master(master, name="before-labeling")`: copies the master to `SORTED/backups/before-labeling-YYYY-MM-DD.csv` (local date) unless that file already exists, a name outside the rotation's glob so it is never pruned or auto-restored. The panel calls it each time it opens, under `MASTER_LOCK`; an `OSError` is logged and the panel opens anyway.
- `last_import.csv` is rewritten only when the run added rows, so a Reload that finds nothing new keeps the record of the last real import.

### `app.py`

- **Header:** the `open-label-panel` button, plus a `last-import-note` line with a **REVIEW →** button (`open-label-review`).
- **Rules path:** `RULES_PATH` comes from the `FINANCE_RULES_PATH` environment variable when set, otherwise `rules.csv` in the project folder, so tests and scripted checks never rewrite the real file.
- **Top N:** `LABEL_TOP_N = 25` groups are rendered.
- **Stat cards:** the `+ $X unreviewed` line on Spent (unlabeled money out) and Income (unlabeled money in), computed by `unreviewed_amounts` from the unlabeled rows in the period.
- **Overlay `label-panel`:** layout as above.
  - Stores: `label-filter` (all, or last import), `label-version` (bumped to re-render the list), `label-undo` (`{backup, master_mtime, rules_mtime, rule}`, the mtimes stored as strings of `st_mtime_ns` because the record goes through the browser's JSON, which would round a nanosecond integer).
  - Pattern-matching ids: `{"type": "lbl-group", "group", "sig", "cat"}`, `{"type": "lbl-row", "group", "row", "cat"}`, `{"type": "lbl-sub", "group"}`, `{"type": "lbl-remember", "group"}`, `{"type": "lbl-rule-del", "keyword"}`. The row expander is a plain `<details>`, not a callback.
- **`label_click`** (group and row buttons):
  1. Ignore re-render triggers whose `n_clicks` is falsy.
  2. Resolve the rows from the current `df`. A group click compares the group's `sig` with the one on the button; a missing group or a different `sig` writes nothing (`The list changed — it has been refreshed.`). Fallback and mixed groups refuse a group click.
  3. Under `MASTER_LOCK`: read the master, run `label_rows`, and compare the count with what the list showed. A mismatch writes nothing and reloads `df`. Otherwise `backup_master` (keep the path), then `atomic_write_csv`.
  4. Build the undo record. Only for a group click with remember ticked and a non-blocking `rule_check`, run `add_rule`. The rule is written only after the master succeeds; any failure in this step keeps the labels and the undo, and the status says the rule wasn't remembered. A row click never adds a rule.
  5. Reload `df` (a failure is noted in the status, the undo still offered) and set the status and `label-undo`.
  A category outside `PREDEFINED_CATEGORIES` is refused before step 2.
- **`undo_label`:** only when both mtimes are unchanged. Restore the backup, delete the added rule, then reload.
- **`delete_rule_click`:** delete the rule under `MASTER_LOCK`, reload, re-render. Rows saved into the master by a group click keep their labels; rows that only the rule was labeling in memory go back to unlabeled.
- A `PermissionError` on the master before its write gets the same plain message as Import, and nothing is written. After the master write, a `rules.csv` problem only drops the rule.

### `assets/app.css`

The panel uses theme tokens only and reuses `.app-card`, `.btn-secondary`, `.btn-small`, `.setup-input` and `.pills`. The *suggested* button (`.btn-secondary.suggested`) uses the accent tint, and the *mixed* badge (`.lg-badge`) uses `accent2`. z-index: setup 100 > label panel 90 > settings menu 50.

## Error handling

| Condition | Behaviour |
|---|---|
| Master or `rules.csv` locked (Excel) | A plain message in the status line. Nothing changes, except that a locked or unreadable `rules.csv` after a successful master write leaves the labels (and Undo) in place and the status says the rule wasn't remembered. |
| Rows gone or changed, e.g. a Reload elsewhere or a count mismatch | `The list changed — it has been refreshed.` Nothing is written, and the list re-renders. |
| The rule fails the safety check | Remember is off, with the reason. A blocking reason also disables the checkbox. The non-blocking reason (mixed sign) can be ticked, but mixed groups only offer row buttons, which never add rules. |
| Undo after another write | Undo is hidden and the status says `Can't undo — the data changed since.` |
| No data, or nothing unlabeled | The header button is hidden. The panel shows `Everything is labeled ✓`. |

## Testing

- **Unit tests:**
  - `merchant_key`: the ID and code stripping that turns the five Coinbase variants into one key, whitespace collapse, names that start with a number or contain a hyphen, and nameless descriptions returning `""`;
  - `rule_check`: each of the four conditions, and that it checks labeled rows too;
  - `unlabeled_groups`: grouping, sort order, the `mixed` flag, `only_row_ids`, and stable ids;
  - `looks_like_transfer`;
  - `label_rows`: exactly the group's rows, twins together, card-aware;
  - `add_rule` / `delete_rule`: append, BOM, quoting, duplicate refused, invalid category refused, extra column ignored by `apply_auto_categories`;
  - the whitespace-collapsing rule match;
  - `last_import.csv` written by `rebuild_master`;
  - `restore_backup`.
- **End-to-end** on a temp copy of Test Data:
  - Label a group with remember on. Check that the master changed, a backup exists, and the rule was added. After reload, the group is gone, and **every period's expense total rose by exactly the group's labeled amount** (the reconciliation check).
  - Undo, then check that the master is byte-identical and the rule is gone.
  - Delete a rule from the Rules tab and check that its rows return to unlabeled unless their labels were saved in the master.
- **UI:** Playwright at 1440 px in both themes (open, guide, click, expand, suggested Transfer, undo, Rules tab, done), with no console errors.

## Docs

- New `docs/features/labeling-panel.md`, including the labeling guide.
- An ADR in `decisions.md`: in-app labeling shares the import matcher; rules are created only when provably safe; unlabeled money is shown as "unreviewed", not counted.
- One line each in `overview-charts.md` (the header lines and the unreviewed figure) and in the readme UI tour.
