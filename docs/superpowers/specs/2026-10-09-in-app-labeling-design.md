# In-App Labeling — Design

**Date:** 2026-10-09 · **Status:** approved in conversation, awaiting spec review

## Why

Every total in the dashboard counts only rows labeled `Expense` / `Income` / `Transfer`. Unlabeled rows are left out of everything — in the demo data 562 of 1,343 rows ($152,346). Today the only way to label is Export → Excel → Import, which is slow enough that it doesn't get done, and weekly tracking makes it worse: every week's new statements arrive unlabeled unless a `rules.csv` keyword happens to match.

**Success:** a user can clear the unlabeled backlog inside the app in a few minutes, one click per merchant, and — by letting the app remember merchants as rules — keep later weeks mostly labeled automatically.

## Decisions (from the conversation)

| Question | Decision |
|---|---|
| Unit of labeling | **By merchant**: unlabeled rows grouped by merchant, one click labels the whole group; a group can be expanded to label single rows |
| Remember for future statements | **Checkbox per merchant, on by default** — adds a keyword rule to `rules.csv` |
| Placement | **Full-screen panel opened from the header's unlabeled warning**; closing it refreshes the dashboard |
| Approach | Plain Dash components with pattern-matching callbacks — no new dependency (`dash_table`'s in-cell dropdowns are clunky to theme; AG Grid is a new dependency for ~100 rows) |

**Out of scope:** editing labels that are already set (Export/Import still covers that), suggested/AI labels, multi-step undo.

## User experience

1. The header's red unlabeled note becomes a button: `⚠ 562 unlabeled ($152,346) · LABEL THEM →`. Hidden when nothing is unlabeled.
2. It opens the **Label transactions** panel (full-screen overlay, theme tokens, above the dashboard and settings menu, below the setup overlay). Header: `LABEL TRANSACTIONS · 562 rows · $152,346 · 98 merchants`, a search box (filters by merchant or description, case-insensitive), a status line with **UNDO**, and **DONE** to close.
3. Groups are sorted by absolute dollar total, largest first, **25 at a time** with a **SHOW MORE** button.
4. Each group row shows:
   - merchant name (full name on hover), transaction count, net total (`-$87.40`), date range (`Jan 3 – Dec 20, 2025`), one example raw description;
   - **EXPENSE / INCOME / TRANSFER** buttons;
   - an optional **category** box (becomes `sub_category`, e.g. "Coffee") with suggestions from categories already in use;
   - **Remember for future statements** checkbox, on by default, with an editable **keyword** and a hint of how many *other* unlabeled rows it would also label (`also matches 6 other unlabeled rows`);
   - **▸** to expand the group into its rows (date · description · amount · card), each with its own three buttons. Row clicks use the group's category box.
5. A click saves immediately. The group (or row) disappears and the status line reads `Labeled 14 STARBUCKS rows as Expense · rule "starbucks" added · UNDO`.
6. **UNDO** reverts the last action only. It is offered only while nothing else has written the master since.
7. **DONE** closes the panel and bumps `refresh-trigger`, so every card, the header notes and the period bar recompute.

## Components

### `Modules/labels.py` (pure functions, tested)

| Function | Contract |
|---|---|
| `merchant_key(description) -> str` | Uppercase, strip digits / `#` / `*`, collapse whitespace, trim `-.,/`. Empty → `"UNKNOWN"`. Moved here from the drilldown's private `_merchant` in `app.py`, which then calls this, so grouping is identical in both places. |
| `rule_keyword(descriptions) -> str` | Suggested rule keyword: the text before the first digit / `#` / `*` of each description, lower-cased and stripped, then the **longest common prefix** of those, trimmed back to a whole word. Guaranteed to be a substring of every description in the group. May be `""`. |
| `valid_keyword(keyword, descriptions) -> bool` | True when the keyword is ≥ 4 characters after stripping and is a case-insensitive substring of every description in the group. Remember is disabled, with a hint, when the keyword is not valid. |
| `unlabeled_groups(df) -> list[dict]` | Rows of the loaded frame whose `master_category` is not one of `PREDEFINED_CATEGORIES`, grouped by `merchant_key`. Each dict has `key` (a stable id: short hash of the merchant), `merchant`, `count`, `total` (net), `abs_total`, `first`, `last` (dates), `example`, `keyword` (from `rule_keyword`) and `rows` (records with `row_id`, `date`, `description`, `amount`, `source`, `card_last4`). Sorted by `abs_total`, descending. |
| `row_id(row) -> str` | Stable id from `date \| description \| amount \| source \| card_last4`. Identical twin rows share an id, matching how the import matcher treats them. |
| `label_rows(master, rows, category, sub) -> tuple[DataFrame, int]` | Builds an import frame from `rows` (with `date`, `card_last4`) and runs `apply_label_import`. Returns the updated master and the number of master rows labeled. There is one matching path for Excel imports and in-app labeling. |
| `rule_match_count(df, keyword, exclude_keys) -> int` | How many unlabeled rows *outside* the given group the keyword would also label. Used for the hint. |
| `add_rule(rules_path, keyword, category, sub) -> bool` | Appends `keyword,category,sub` to `rules.csv` with an atomic write. Returns `False` without writing when the keyword already exists (case-insensitive) or `category` is not a predefined category. A missing file gets the header row. |

### `Modules/safety.py`

- `restore_backup(backup, master) -> None`: public, atomic copy of a backup over the master (wraps the existing `_replace_from`). Used by Undo.

### `app.py`

- **Header:** `unlabeled-note` becomes a button (`open-label-panel`); the text adds `· LABEL THEM →`.
- **Overlay `label-panel`:** layout as above.
  - Stores: `label-limit` (25, +25 per SHOW MORE, reset on open), `label-search`, `label-undo` (`{backup, master_mtime_ns, rule}` or None).
  - Pattern-matching ids: `{"type": "lbl-group", "group": key, "cat": "Expense"|…}`, `{"type": "lbl-row", "row": row_id, "group": key, "cat": …}`, `{"type": "lbl-sub", "group": key}`, `{"type": "lbl-remember", "group": key}`, `{"type": "lbl-keyword", "group": key}`, `{"type": "lbl-expand", "group": key}`.
- **Callbacks:**
  - `open/close` panel: closing bumps `refresh-trigger`.
  - `render_label_list` (groups from the current `df`, search, limit).
  - `label_click`: one callback for group and row buttons. It ignores re-render triggers whose `n_clicks` is falsy and resolves rows from the current `df` by `group` / `row_id`. It then does the following under `MASTER_LOCK`:
    1. read the master;
    2. `label_rows`;
    3. `backup_master`, keeping the returned path for undo;
    4. `atomic_write_csv`;
    5. if remember is on and the keyword is valid, `add_rule`.

    After that it reloads `df`, sets the status line and `label-undo`, and re-renders the list.
  - `undo_label`: only if the master's `mtime_ns` still equals the recorded value. It restores the backup, removes the rule it added (rewrites `rules.csv` atomically without that line), reloads `df`, and clears `label-undo`.
- `PermissionError` (master or `rules.csv` open in Excel) gets the same friendly message as Import. The panel stays open, and nothing is half-written: the master write and the rule write are each atomic, and the rule is written only after the master succeeds.

### `assets/app.css`

The panel uses theme tokens only. It reuses `.app-card`, `.btn-secondary`, `.btn-small`, `.setup-input` and `.pills`. On narrow screens the group rows stack: name and stats, then buttons, then category/remember. z-index: setup 100 > label panel 90 > settings menu 50.

## Data flow

```
click → resolve rows from df → [MASTER_LOCK: read master → label_rows → backup_master → atomic_write_csv] → add_rule? → reload df → re-render list + status
DONE  → hide panel → refresh-trigger + 1 → every card recomputes
UNDO  → mtime check → restore_backup → remove rule → reload df → re-render
```

## Error handling

| Condition | Behaviour |
|---|---|
| Master or rules file locked (Excel) | Friendly message in the status line; nothing is changed |
| Rows no longer present (e.g. a Reload happened elsewhere) | `label_rows` reports 0 labeled → status `Nothing to label — the list was out of date`, and the list re-renders |
| Keyword invalid / duplicate | Remember is disabled with a hint, or the status notes `rule already exists`; the labels are still saved |
| Undo after another write | The Undo button is hidden; status explains `can't undo — the data changed since` |
| No data loaded | The header button is hidden and the panel can't open |

## Testing

- **Unit (`tests/test_labels.py`, `tests/test_safety.py`):**
  - `merchant_key` (store numbers stripped, empty → UNKNOWN)
  - `rule_keyword` (common prefix, word boundary, a substring of all descriptions, `""` when there's nothing in common)
  - `valid_keyword` (length, substring)
  - `unlabeled_groups` (grouping, sorting, excludes labeled and Transfer rows, stable `key` / `row_id`)
  - `label_rows` (labels exactly the group's rows, twins together, card-aware)
  - `rule_match_count`
  - `add_rule` (append, header on a new file, duplicate keyword refused, invalid category refused, atomic)
  - `restore_backup`
- **End-to-end (temp copy of Test Data):** label a group, then confirm the master changed, a backup exists, the rule was added, and after reload the group is gone and totals rose by the group's amount. Then undo and confirm the master is byte-identical to before and the rule is removed.
- **UI:** Playwright screenshots of the panel in both themes at 1440 and 390 px. Exercise click, expand, search, show more, undo and close. No console errors.

## Docs

- New `docs/features/labeling-panel.md`.
- Update `import-export.md` (in-app labeling first, Excel for bulk edits), `overview-charts.md` (header button), `design.md` (panel component, z-index table), `decisions.md` (ADR: in-app labeling shares the import matcher; labels can become rules), and the readme UI tour.
