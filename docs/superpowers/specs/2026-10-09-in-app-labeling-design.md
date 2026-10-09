# In-App Labeling — Design

**Date:** 2026-10-09 · **Status:** revised after council review; awaiting spec review

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
| Remember for future statements | A checkbox per group. **It is ticked by default only when the rule is provably safe** (see *Rule safety*); otherwise it starts unticked, with the reason shown. |
| Placement | A full-screen panel opened from the header's unlabeled warning, and from the new post-import line. |
| Labels that are already set | Not editable here. Export and Import still cover that. |
| Unlabeled money in the totals | Still **not** counted, because counting it by sign would double-count card payments. Instead each stat card shows how much is unreviewed. |
| Built-in transfer rules | **Not added.** On the demo data, card-payment phrases cover 1% of unlabeled dollars, and the council rejected unreviewed rules. Instead, groups that look like card payments get a **suggested** Transfer button (highlighted, never auto-applied). |
| Approach | Plain Dash components with pattern-matching callbacks. No new dependency. |

**Out of scope:** relabeling, AI suggestions, a starter ruleset, budgets, search, pagination beyond the top 25 groups.

## Measured on the demo data (2026-10-09)

Grouping by the merchant **keyword** gives 209 groups, while grouping by the full description minus digits gives 304, because transaction IDs split one merchant into several groups. With keyword grouping:
- the **top 25 groups cover 91%** of unlabeled dollars;
- **175 of 209 groups (67% of dollars) pass the rule-safety check**;
- of the groups that fail, 29 have a keyword that is too short or matches other merchants, 5 mix money in and out (e.g. Coinbase buys and sells), and 2 are shadowed by an existing rule.

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

1. **Header.** The unlabeled note becomes a button: `⚠ 562 unlabeled ($152,346) · LABEL THEM →`. It is hidden when nothing is unlabeled.
2. **After each import or Reload,** a second header line appears: `Last import: 31 new · 27 labeled by rules · 4 need you → REVIEW`. **REVIEW** opens the panel filtered to those 4.
3. **Stat cards** gain one muted line when the period has unlabeled rows: `+ $412 unreviewed`. The numbers are visibly incomplete, not silently incomplete.
4. **The panel** is a full-screen overlay. Its header reads `LABEL TRANSACTIONS · 562 rows · $152,346 · 209 merchants`, followed by the guide, a status line with **UNDO**, a **Rules** tab, and **DONE**.
5. **Groups** are sorted by absolute dollars, largest first. Only the **top 25** are shown, and the rest follow in the next session. Each group shows:
   - the merchant, count, net total, date range, and one example description;
   - **EXPENSE / INCOME / TRANSFER** buttons, with TRANSFER highlighted as *suggested* when the description matches a card-payment or own-account-transfer phrase;
   - a **Subcategory** box (optional, e.g. "Coffee") with suggestions from subcategories already in use;
   - **Remember for future statements**: the checkbox plus `rule "starbucks" · labels 14 rows ($87) now`, or the reason it's off (`also matches PAYPAL *SPOTIFY, PAYPAL *HULU`, `money in and out`, or `an existing rule "venmo" would override it`);
   - a **mixed** badge when the group has both money in and out;
   - **▸** to expand the group into rows (date · description · amount · card), each row with its own three buttons.
6. **A click saves immediately.** The group or row disappears and the status reads `Labeled 14 STARBUCKS rows as Expense · rule "starbucks" added · UNDO`.
7. **UNDO** reverts the last action only, and only while neither the master nor `rules.csv` has changed since.
8. **Rules tab:** the rules this panel added (keyword, label, subcategory, date added, rows it labels now), each with **DELETE**. Hand-written rules are listed read-only.
9. **DONE** closes the panel and refreshes the whole dashboard.

## Rule safety

A rule in `rules.csv` applies to every unlabeled row whose description contains the keyword (case-insensitive), past and future, on every load. The first matching rule wins. Labels saved in the master always win over rules.

"Remember" is **ticked by default only if all of the following hold**. Otherwise it starts unticked and shows the reason. The user can still tick it when only the *mixed sign* condition fails; the others hard-block it.
1. **Long enough:** the keyword is at least 4 characters.
2. **This merchant only:** across **all** rows, labeled or not, every row the keyword matches belongs to this merchant group. Otherwise the reason names the other merchants (up to 3).
3. **One direction:** every row in the group is money out, or every row is money in.
4. **Not overridden:** no existing rule's keyword matches any description in the group (it would win first match), and no existing rule's keyword contains the new keyword or is contained by it.

The keyword is not editable. It is derived; see `rule_keyword` below.

## Components

### `Modules/labels.py` (pure functions, tested)

| Function | Contract |
|---|---|
| `merchant_key(description) -> str` | The group key and rule keyword source, in this order: lowercase; collapse whitespace; cut at the first ` web id`, ` ppd id`, ` ccd id`, ` id:` or ` ach `; cut at the first digit, `#` or `*`; drop `xx-…` code tokens (e.g. `rtl-tppsgd`); trim ` -.,/`. Empty → `"unknown"`. The drilldown's private `_merchant` in `app.py` is replaced by a display form of this (upper-case), so grouping is the same everywhere. |
| `rule_keyword(group_descriptions) -> str` | The longest common **word-aligned prefix** of the group's descriptions, lowercased with whitespace collapsed, trimmed of ` -.,/`. It is therefore a real substring of every description in the group, which `merchant_key` isn't always (it drops code tokens). It may be `""`, in which case remember is blocked as too short. Descriptions are compared with whitespace collapsed throughout, and rules match against collapsed descriptions; see the transforms change below. |
| `rule_check(df, rules, group) -> dict` | Applies the four *Rule safety* conditions. Returns `{"ok": bool, "keyword": str, "reason": str \| None, "blocking": bool, "rows_now": int, "dollars_now": float, "others": [merchant, …]}`. |
| `unlabeled_groups(df, only_row_ids=None) -> list[dict]` | Unlabeled rows (`master_category` not in `PREDEFINED_CATEGORIES`), grouped by `merchant_key`. Each dict has `key` (a short stable hash), `merchant` (display form), `count`, `total`, `abs_total`, `first`, `last`, `example`, `mixed`, `suggest_transfer` and `rows` (records with `row_id`, `date`, `description`, `amount`, `source`, `card_last4`). Sorted by `abs_total`, descending. `only_row_ids` restricts it to the last import's rows. |
| `row_id(row) -> str` | Stable id from `date \| description \| amount \| source \| card_last4`. Identical twin rows share an id, consistent with the import matcher. |
| `looks_like_transfer(description) -> bool` | Matches `payment thank`, `autopay`, `online transfer`, `transfer to`, `transfer from`, `epay`, `card payment`, `directpay` and `internet payment`. Used only to highlight the suggestion. |
| `label_rows(master, rows, category, sub) -> tuple[DataFrame, int]` | Builds an import frame from `rows` and runs `apply_label_import`. This is the single matching path for Excel and in-app labeling. |
| `read_rules(path) -> DataFrame` / `add_rule(path, keyword, category, sub) -> bool` / `delete_rule(path, keyword) -> bool` | `rules.csv` I/O. Reads tolerate a BOM. Writes are atomic and correctly quoted. `add_rule` appends the columns `keyword, master_category, sub_category, added`, where `added` is an ISO date; `apply_auto_categories` ignores extra columns. It refuses, returning `False`, when the keyword already exists or the category isn't predefined. `delete_rule` removes exactly the matching keyword row. |

### `Modules/transforms.py`

- `apply_auto_categories` matches keywords against descriptions **with whitespace collapsed**. Bank files pad descriptions (`venmo            payment`), so a keyword derived from collapsed text would otherwise never match. This is a small behaviour change; existing single-word rules are unaffected.

### `main.py` / `Modules/safety.py`

- `rebuild_master` records the last import in `SORTED/last_import.json` (atomic): `{when, new_row_ids: [...]}`. The new rows are those not carried or rescued from the old master. The header line computes "labeled by rules" and "need you" from the loaded frame.
- `safety.restore_backup(backup, master)`: public atomic restore, used by Undo.

### `app.py`

- **Header:** the `open-label-panel` button, plus a `last-import-note` line with a **REVIEW** button.
- **Stat cards:** the `+ $X unreviewed` line, computed from unlabeled rows in the period.
- **Overlay `label-panel`:** layout as above.
  - Stores: `label-filter` (all, or last import), `label-undo` (`{backup, master_mtime_ns, rules_mtime_ns, rule_keyword}`).
  - Pattern-matching ids: `{"type": "lbl-group", "group", "cat"}`, `{"type": "lbl-row", "row", "group", "cat"}`, `{"type": "lbl-sub", "group"}`, `{"type": "lbl-remember", "group"}`, `{"type": "lbl-expand", "group"}`, `{"type": "lbl-rule-del", "keyword"}`.
- **`label_click`** (group and row buttons):
  1. Ignore re-render triggers whose `n_clicks` is falsy.
  2. Resolve the rows from the current `df`.
  3. Under `MASTER_LOCK`: read the master, run `label_rows`, `backup_master` (keep the path), then `atomic_write_csv`.
  4. If remember is on and `rule_check` passes, or fails only on a non-blocking condition, run `add_rule`. The rule is written only after the master succeeds.
  5. Reload `df` and set the status and `label-undo`.
- **`undo_label`:** only when both mtimes are unchanged. Restore the backup, delete the added rule, then reload.
- **`delete_rule_click`:** delete the rule, reload, re-render.
- A `PermissionError` on the master or on `rules.csv` gets the same plain message as Import, and nothing is half-written.

### `assets/app.css`

The panel uses theme tokens only and reuses `.app-card`, `.btn-secondary`, `.btn-small`, `.setup-input` and `.pills`. The *suggested* button uses the accent tint, and the *mixed* badge uses `accent2`. z-index: setup 100 > label panel 90 > settings menu 50.

## Error handling

| Condition | Behaviour |
|---|---|
| Master or `rules.csv` locked (Excel) | A plain message in the status line. Nothing changes. |
| Rows gone, e.g. a Reload elsewhere | `Nothing to label — the list was out of date`, then the list re-renders. |
| The rule fails the safety check | Remember is off, with the reason. If the user ticks it on a non-blocking reason, the rule is added; a blocking reason stops that. |
| Undo after another write | Undo is hidden and the status says `can't undo — the data changed since`. |
| No data, or nothing unlabeled | The header button is hidden. The panel shows `Everything is labeled`. |

## Testing

- **Unit tests:**
  - `merchant_key`: the ID and code stripping that turns the five Coinbase variants into one key, whitespace collapse, and `unknown`;
  - `rule_check`: each of the four conditions, and that it checks labeled rows too;
  - `unlabeled_groups`: grouping, sort order, the `mixed` flag, `only_row_ids`, and stable ids;
  - `looks_like_transfer`;
  - `label_rows`: exactly the group's rows, twins together, card-aware;
  - `add_rule` / `delete_rule`: append, BOM, quoting, duplicate refused, invalid category refused, extra column ignored by `apply_auto_categories`;
  - the whitespace-collapsing rule match;
  - `last_import.json` written by `rebuild_master`;
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
