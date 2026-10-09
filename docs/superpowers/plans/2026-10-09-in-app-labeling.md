# In-App Labeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user label unlabeled transactions inside the dashboard, one click per merchant, with rules created only when provably safe, so totals become complete and stay complete week to week.

**Architecture:** Pure, tested functions in `Modules/labels.py` do the work: grouping, rule safety, rule-file I/O, and labeling through the existing `apply_label_import` matcher. `Modules/transforms.py` gains one shared description normalizer used by grouping and by rule matching. `main.py` records which rows the last import added. `app.py` adds a full-screen labeling panel (pattern-matching callbacks), header entry points, and an "unreviewed" line on the stat cards. Every master write reuses `Modules/safety.py`: lock, backup, then atomic write.

**Tech Stack:** Python 3.12+, pandas 3.0.2, Dash 4.1.0 (`dash.html`, `dcc`, pattern-matching `ALL` ids), pytest 8.4.2, Playwright (verification only, not a dependency).

**Spec:** `docs/superpowers/specs/2026-10-09-in-app-labeling-design.md`

**Revision 2 (after the council's plan review):** fixes folded into the tasks below:
- grouping keeps names that start with a number or contain a hyphen, and descriptions with no recognizable name become their own flagged *fallback* group;
- a regression gate on the normalizer;
- no one-click group labels on fallback or mixed-direction groups;
- buttons keyed on `row_id` plus a group signature, and labeling touches only unlabeled master rows and aborts on a count mismatch;
- a no-op Reload no longer clears `last_import.csv`;
- undo state survives JSON (mtimes stored as strings);
- a pre-labeling snapshot is kept outside the backup rotation;
- an acceptance gate;
- `FINANCE_RULES_PATH`, so tests and Playwright never touch the repo's `rules.csv`.

**Checkpoint after Task 3 (controller):** before starting Task 4, re-check the Task 1 regression output, the re-measured grouping numbers, and that a no-op Reload keeps `last_import.csv`.

## Global Constraints

- No new dependencies. Pinned versions stay as in `requirements.txt` / `requirements-dev.txt`.
- Must run on Windows: no `%-d` strftime; temp files in the target's own folder; a `PermissionError` (file open in Excel) gives a plain message and changes nothing.
- Tests never write into the repo: use `tmp_path`, or a temp copy of `Test Data/`.
- Every master write runs under `MASTER_LOCK`: `backup_master` then `atomic_write_csv`. `rules.csv` writes use `atomic_write_csv`, and a rule is written only after the master write succeeded.
- CSS uses theme tokens only (`var(--…)`), never hex. Code style matches the surroundings: `# ── … ──` section comments, comments explain why.
- Labels are exactly `Expense`, `Income`, `Transfer` (`PREDEFINED_CATEGORIES`). The free-text box is called **Subcategory** in the UI and writes `sub_category`.
- "Remember" is ticked by default only when `rule_check` returns `ok`. A blocking reason disables the checkbox. Mixed sign is the only non-blocking reason.
- The panel shows at most the top 25 groups (`LABEL_TOP_N = 25`). There is no search and no pagination.
- z-index: setup overlay 100 > label panel 90 > settings menu 50 > period bar 30.

## Review Focus

1. **Twin rows** (two identical same-day purchases) share a `row_id`. They are merged into one row entry with `count` 2 (shown `×2`), so component ids stay unique and a click labels both. Row buttons are keyed on `row_id`, never a list position, and group buttons carry the group's `sig`, so a click from a stale list is refused instead of labeling the wrong rows. Pinned in Task 5: `test_group_card_row_ids_unique`; Task 6: `test_label_click_refuses_stale_sig`.
2. **The pattern-matching callback fires when the list re-renders** (new buttons with `n_clicks=0`). It must do nothing, and in particular write nothing. Pinned in Task 6: `test_label_click_ignores_rerender` (via `_is_real_click`).
3. **Rules whose keyword contains `*` or `#`** (`mta*nyct paygo`, `sq *the` already exist) must keep labeling the same rows after the normalizer change. Pinned in Task 1: `test_existing_star_rules_still_match`.
4. **A `rules.csv` saved by Excel** (with a BOM, or a keyword containing a comma) must still be read and written correctly. Pinned in Task 2: `test_rules_bom_and_quoting_roundtrip`.
5. **Undo after something else changed the master or `rules.csv`** must refuse and change nothing. Pinned in Task 6: `test_undo_refuses_after_change`.

---

## File Structure

| File | Responsibility |
|---|---|
| `Modules/transforms.py` (modify) | `normalize_description`; `apply_auto_categories` matches normalized text and reads BOM-tolerantly |
| `Modules/labels.py` (modify) | Grouping (`merchant_key`, `rule_keyword`, `row_id(s)`, `looks_like_transfer`, `unlabeled_groups`), rule safety (`rule_check`), rule I/O (`read_rules`, `add_rule`, `delete_rule`), `label_rows`, `last_import_ids` |
| `Modules/safety.py` (modify) | `restore_backup` |
| `main.py` (modify) | `rebuild_master` writes `SORTED/last_import.csv` |
| `app.py` (modify) | Header entry points, unreviewed line, drilldown uses `merchant_key`, label panel layout and callbacks |
| `assets/app.css` (modify) | Panel and notice-row styles |
| `tests/test_grouping.py`, `tests/test_rules.py`, `tests/test_labeling.py`, `tests/test_label_panel.py` (new) | One per unit |
| `docs/features/labeling-panel.md` (new), `docs/decisions.md`, `docs/design.md`, `docs/features/overview-charts.md`, `readme.md` (modify) | Docs |

---

### Task 1: Normalizer and merchant grouping

**Files:**
- Modify: `Modules/transforms.py` (top imports; `apply_auto_categories`)
- Modify: `Modules/labels.py` (append the grouping section)
- Test: `tests/test_grouping.py`

**Interfaces:**
- Produces:
  - `transforms.normalize_description(text) -> str`
  - `labels.merchant_key(description) -> str`
  - `labels.rule_keyword(descriptions) -> str`
  - `labels.row_id(row: dict) -> str`
  - `labels.row_ids(df) -> pd.Series`
  - `labels.looks_like_transfer(description) -> bool`
  - `labels.unlabeled_groups(df, only_row_ids=None) -> list[dict]`. Each group dict has the keys `key, mkey, merchant, count, total, abs_total, first, last, example, mixed, fallback, sig, suggest_transfer, rows`. `rows` has **one entry per distinct `row_id`** (identical twins merged), each with `row_id, date, description, amount, source, card_last4, count`. `sig` is a short hash of the group's `row_id`s and counts. `fallback` is True when the description has no recognizable merchant name.
  - `labels.merchant_key` returns `""` when no name with a letter is left. The group then falls back to the full normalized description.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grouping.py
import pandas as pd

from Modules.labels import (
    looks_like_transfer, merchant_key, row_id, row_ids, rule_keyword, unlabeled_groups,
)
from Modules.transforms import apply_auto_categories, normalize_description


def _df(rows):
    """rows: (date, description, amount, master_category[, card_last4])."""
    recs = [dict(date=r[0], description=r[1], amount=r[2], master_category=r[3],
                 sub_category="", source="Chase Credit",
                 card_last4=r[4] if len(r) > 4 else "") for r in rows]
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_normalize_description():
    assert normalize_description("VENMO            PAYMENT  1234") == "venmo payment 1234"
    assert normalize_description("PAYPAL *NETFLIX") == "paypal netflix"
    assert normalize_description("STARBUCKS #12") == "starbucks 12"


def test_merchant_key():
    assert merchant_key("STARBUCKS STORE 01234 SEATTLE") == "starbucks store"
    assert merchant_key("STARBUCKS STORE 09876 NEW YORK") == "starbucks store"
    assert merchant_key("PAYPAL *NETFLIX 4029357733") == "paypal netflix"
    assert merchant_key("PAYPAL *SPOTIFY 4029357733") == "paypal spotify"
    assert merchant_key("MORGAN STANLEY ACH DEBIT PPD ID: 123") == "morgan stanley"
    assert merchant_key("COINBASE INC. RTL-TPPSGD WEB ID: 1") == "coinbase inc"
    assert merchant_key("COINBASE INC. RTL-QRARKLK WEB ID: 2") == "coinbase inc"
    assert merchant_key("VENMO            PAYMENT 1234") == "venmo payment"
    assert merchant_key("   ") == ""
    assert merchant_key("#1234") == ""


def test_merchant_key_keeps_numeric_and_hyphenated_names():
    # Names that start with a number or contain a hyphen must not collapse
    # into one shared bucket (council round 2)
    assert merchant_key("7-ELEVEN 12345") == "7-eleven"
    assert merchant_key("99 RANCH MARKET #12") == "99 ranch market"
    assert merchant_key("1-800-FLOWERS") == "1-800-flowers"
    assert merchant_key("23ANDME") == "23andme"
    assert merchant_key("76 FUEL 1234") == "76 fuel"
    assert merchant_key("WAL-MART #1234") == "wal-mart"


def test_rule_keyword_is_common_prefix_and_substring():
    descs = ["STARBUCKS STORE 01234 SEATTLE", "STARBUCKS STORE 09876 NY"]
    kw = rule_keyword(descs)
    assert kw == "starbucks store"
    assert all(kw in normalize_description(d) for d in descs)
    assert rule_keyword(["PAYPAL *NETFLIX 1", "PAYPAL *NETFLIX 2"]) == "paypal netflix"
    assert rule_keyword(["AMAZON MKTP US", "AMAZON.COM"]) == ""
    assert rule_keyword([]) == ""
    assert rule_keyword(["7-ELEVEN 123", "7-ELEVEN 456"]) == "7-eleven"
    assert rule_keyword(["MORGAN STANLEY ACH DEBIT PPD ID: 123"]) == "morgan stanley"


def test_row_id_stable_and_twins_equal():
    df = _df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, ""),
              ("2025-03-01", "CAFE", -4.5, "", "0123")])
    ids = row_ids(df)
    assert ids.iloc[0] == ids.iloc[1] != ids.iloc[2]
    assert row_id(df.iloc[0].to_dict()) == ids.iloc[0]
    assert len(ids.iloc[0]) == 12


def test_looks_like_transfer():
    assert looks_like_transfer("PAYMENT THANK YOU - WEB")
    assert looks_like_transfer("Online Transfer to SAV ...1234")
    assert not looks_like_transfer("STARBUCKS STORE 123")


def test_unlabeled_groups():
    df = _df([
        ("2025-03-01", "STARBUCKS STORE 1", -5.0, ""),
        ("2025-03-02", "STARBUCKS STORE 2", -6.0, ""),
        ("2025-03-03", "RENT CO 9", -900.0, ""),
        ("2025-03-04", "PAYCHECK ACME", 2000.0, "Income"),      # labeled: excluded
        ("2025-03-05", "PAYMENT THANK YOU", 300.0, "Transfer"),  # labeled: excluded
        ("2025-03-06", "AMAZON MKTP 1", -20.0, ""),
        ("2025-03-07", "AMAZON MKTP 2", 20.0, ""),               # refund: mixed group
    ])
    groups = unlabeled_groups(df)
    assert [g["merchant"] for g in groups] == ["RENT CO", "AMAZON MKTP", "STARBUCKS STORE"]
    sb = groups[2]
    assert sb["count"] == 2 and sb["total"] == -11.0 and sb["abs_total"] == 11.0
    assert not sb["mixed"] and groups[1]["mixed"]
    assert sb["first"] == pd.Timestamp("2025-03-01") and sb["last"] == pd.Timestamp("2025-03-02")
    assert {r["row_id"] for r in sb["rows"]} == set(row_ids(df.iloc[:2]))
    assert all(r["count"] == 1 for r in sb["rows"]) and not sb["fallback"]
    assert sb["sig"] == unlabeled_groups(df)[2]["sig"] and len(sb["sig"]) == 10
    assert sb["key"] == unlabeled_groups(df)[2]["key"]          # stable
    only = unlabeled_groups(df, only_row_ids=[sb["rows"][0]["row_id"]])
    assert len(only) == 1 and only[0]["count"] == 1
    assert unlabeled_groups(df.iloc[3:5]) == []


def test_twins_merged_into_one_row():
    df = _df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, "")])
    g = unlabeled_groups(df)[0]
    assert g["count"] == 2 and len(g["rows"]) == 1 and g["rows"][0]["count"] == 2


def test_nameless_descriptions_are_separate_fallback_groups():
    df = _df([("2025-03-01", "#1234", -4.5, ""), ("2025-03-02", "#5678", -9.0, ""),
              ("2025-03-03", "STARBUCKS 1", -3.0, "")])
    groups = unlabeled_groups(df)
    assert len(groups) == 3
    fb = [g for g in groups if g["fallback"]]
    assert len(fb) == 2 and all(g["count"] == 1 for g in fb)


def test_suggest_transfer_flag():
    df = _df([("2025-03-01", "AUTOPAY PAYMENT", -300.0, "")])
    assert unlabeled_groups(df)[0]["suggest_transfer"]


def test_padded_rule_keyword_matches(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nvenmo payment,Transfer,\n")
    df = _df([("2025-03-01", "VENMO            PAYMENT 77", -10.0, "")])
    out = apply_auto_categories(df.copy(), rules)
    assert out.loc[0, "master_category"] == "Transfer"


def test_existing_star_rules_still_match(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nmta*nyct paygo,Expense,\nsq *the,Expense,\n")
    df = _df([("2025-03-01", "MTA*NYCT PAYGO NEW YORK", -2.9, ""),
              ("2025-03-02", "SQ *THE COFFEE PLACE", -4.0, ""),
              ("2025-03-03", "SQ *OTHER SHOP", -4.0, "")])
    out = apply_auto_categories(df.copy(), rules)
    assert out["master_category"].tolist() == ["Expense", "Expense", ""]


def _old_apply(df, rules):
    """The matching loop as it was before the normalizer (for the regression gate)."""
    from Modules.transforms import PREDEFINED_CATEGORIES
    desc = df["description"].str.lower()
    unlabeled = df["master_category"] == ""
    for _, rule in rules.iterrows():
        keyword = str(rule["keyword"]).strip().lower()
        mc = str(rule.get("master_category", "")).strip()
        sc = str(rule.get("sub_category", "")).strip()
        if not keyword or (mc and mc not in PREDEFINED_CATEGORIES) or (not mc and not sc):
            continue
        hits = desc.str.contains(keyword, regex=False, na=False)
        if mc:
            take = unlabeled & hits
            df.loc[take, "master_category"] = mc
            unlabeled = unlabeled & ~take
        if sc:
            fill = hits & (df["sub_category"] == "")
            if mc:
                fill = fill & (df["master_category"] == mc)
            df.loc[fill, "sub_category"] = sc
    return df


def test_normalizer_regression_gate(tmp_path, capsys):
    """Every demo row whose rule label changes under the normalizer must be
    explained by it: the normalizer must actually have altered that row's
    description (padding, '*' or '#'). Prints the diff for the report."""
    import shutil
    from pathlib import Path
    from main import main as run_ingest
    repo = Path(__file__).resolve().parent.parent
    data = tmp_path / "data"
    shutil.copytree(repo / "Test Data" / "RAW", data / "RAW")
    run_ingest(data)
    master = pd.read_csv(data / "SORTED" / "edited_combined_transactions.csv",
                         dtype=str, keep_default_na=False)
    base = master[["description", "master_category", "sub_category"]].copy()
    rules = pd.read_csv(repo / "rules.csv", encoding="utf-8-sig").fillna("")
    old = _old_apply(base.copy(), rules)
    new = apply_auto_categories(base.copy(), repo / "rules.csv")
    changed = ((old["master_category"] != new["master_category"])
               | (old["sub_category"] != new["sub_category"]))
    with capsys.disabled():
        print(f"\n[regression gate] {int(changed.sum())} of {len(base)} demo rows change label")
        for i in base.index[changed][:20]:
            print(f"  {base.at[i, 'description']!r}: {old.at[i, 'master_category'] or '-'}"
                  f" -> {new.at[i, 'master_category'] or '-'}")
    for d in base.loc[changed, "description"]:
        assert normalize_description(d) != str(d).lower().strip(), f"unexplained change: {d!r}"


def test_rules_file_with_bom(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_bytes("keyword,master_category,sub_category\npayroll,Income,\n".encode("utf-8-sig"))
    df = _df([("2025-03-01", "ACME PAYROLL", 100.0, "")])
    assert apply_auto_categories(df.copy(), rules).loc[0, "master_category"] == "Income"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_grouping.py -v -p no:cacheprovider`
Expected: collection ERROR, `ImportError: cannot import name 'looks_like_transfer' from 'Modules.labels'`.

- [ ] **Step 3: Implement**

In `Modules/transforms.py`, add `import re` to the imports and this function above `apply_auto_categories`:

```python
def normalize_description(text) -> str:
    """The one form rule keywords and descriptions are compared in: lower-case,
    '*' and '#' as spaces, whitespace collapsed. Bank exports pad descriptions
    ('venmo            payment') and glue processors to merchants
    ('PAYPAL *NETFLIX'), so raw substring matching misses or over-matches."""
    return re.sub(r"\s+", " ", re.sub(r"[*#]", " ", str(text).lower())).strip()
```

In `apply_auto_categories`, change the rules read to `rules = pd.read_csv(rules_path, encoding="utf-8-sig").fillna("")`. Excel saves a BOM, and without this the `keyword` column is never found. Then replace

```python
    desc      = df["description"].str.lower()
```
with
```python
    desc      = df["description"].map(normalize_description)
```
and
```python
        keyword = str(rule["keyword"]).strip().lower()
```
with
```python
        keyword = normalize_description(rule["keyword"])
```
Update the docstring's matching sentence to "Keywords and descriptions are compared after `normalize_description`."

In `Modules/labels.py`, change the imports to:

```python
import hashlib
import io
import re

import pandas as pd

from Modules.transforms import PREDEFINED_CATEGORIES, normalize_description
```

and append:

```python
# ── Merchant grouping (the labeling panel) ────────────────────────────────────

_ID_TAIL  = re.compile(r" (?:web id|ppd id|ccd id|id:|ach )")
# ACH reference codes like "rtl-tppsgd" — narrow on purpose: a generic
# "xx-…" pattern would also eat names like "wal-mart"
_CODE     = re.compile(r"\b(?:rtl|ppd|ccd|web)-\S+")
_TRANSFER = re.compile(r"payment thank|autopay|online transfer|transfer to|transfer from"
                       r"|epay|card payment|directpay|internet payment")


def _leading_words(text: str) -> str:
    """Words up to the first word *after the first* that contains a digit:
    store numbers and dates drop off, but a name that starts with a number
    ('7-eleven', '99 ranch', '1-800-flowers') survives."""
    words = text.split()
    keep = words[:1]
    for w in words[1:]:
        if re.search(r"\d", w):
            break
        keep.append(w)
    return " ".join(keep)


def merchant_key(description) -> str:
    """Who a transaction is with, stripped of store numbers, reference ids and
    ACH codes, so one merchant's rows group together: 'STARBUCKS STORE 01234
    SEATTLE' and '… 09876 NEW YORK' are both 'starbucks store'. Returns ''
    when no name with a letter is left (e.g. '#1234') — the caller must not
    lump those together."""
    s = normalize_description(description)
    s = _ID_TAIL.split(s, maxsplit=1)[0]
    s = _CODE.sub("", s)
    s = _leading_words(s).strip(" -.,/")
    return s if re.search(r"[a-z]", s) else ""


def rule_keyword(descriptions) -> str:
    """The rule keyword for a group: the longest word-aligned prefix all its
    descriptions share (normalized), cut at reference-id tails and before a
    later word with a digit. Always a real substring of every description,
    so the rule matches the whole group."""
    split = [normalize_description(d).split() for d in descriptions]
    common = []
    for words in zip(*split):
        if any(w != words[0] for w in words):
            break
        common.append(words[0])
    prefix = _ID_TAIL.split(" ".join(common), maxsplit=1)[0]
    return _leading_words(prefix).strip(" -.,/")


def row_id(row: dict) -> str:
    """Stable id for a transaction. Identical twin rows share it, the same way
    the import matcher treats them."""
    date = pd.Timestamp(row["date"]).strftime("%Y-%m-%d") if pd.notna(row["date"]) else ""
    card = row.get("card_last4", "")
    card = "" if card is None or (isinstance(card, float) and pd.isna(card)) else str(card)
    raw = "|".join([date, str(row["description"]).strip(), f"{float(row['amount']):.2f}",
                    str(row["source"]), card])
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def row_ids(df: pd.DataFrame) -> pd.Series:
    return pd.Series([row_id(r) for r in df.to_dict("records")], index=df.index, dtype=str)


def looks_like_transfer(description) -> bool:
    """Card-payment / own-account wording — only ever a *suggestion*."""
    return bool(_TRANSFER.search(normalize_description(description)))


def unlabeled_groups(df: pd.DataFrame, only_row_ids=None) -> list[dict]:
    """Rows with no valid label, grouped by merchant, biggest dollar total first.
    only_row_ids restricts to those rows (the last import's)."""
    un = df[~df["master_category"].isin(PREDEFINED_CATEGORIES)].copy()
    if un.empty:
        return []
    un["_rid"] = row_ids(un)
    if only_row_ids is not None:
        un = un[un["_rid"].isin(set(only_row_ids))]
    un["_mk"] = un["description"].map(merchant_key)
    # No recognizable name: each description is its own group, flagged, so
    # unrelated rows are never bulk-labeled together
    un["_fb"] = un["_mk"] == ""
    un.loc[un["_fb"], "_mk"] = un.loc[un["_fb"], "description"].map(normalize_description)
    groups = []
    for mk, g in un.groupby("_mk", sort=False):
        amounts = g["amount"]
        rows: dict[str, dict] = {}
        # Identical twins share a row_id and are labeled together: one entry
        for r in g.sort_values("date", kind="stable").to_dict("records"):
            if r["_rid"] in rows:
                rows[r["_rid"]]["count"] += 1
            else:
                rows[r["_rid"]] = {"row_id": r["_rid"], "date": r["date"],
                                   "description": r["description"], "amount": float(r["amount"]),
                                   "source": r["source"], "card_last4": r.get("card_last4", "") or "",
                                   "count": 1}
        sig_src = "|".join(sorted(f"{k}x{v['count']}" for k, v in rows.items()))
        fallback = bool(g["_fb"].any())
        groups.append({
            "key": hashlib.sha1(mk.encode()).hexdigest()[:10],
            "mkey": mk,
            "merchant": (str(g["description"].iloc[0]).strip() if fallback else mk).upper(),
            "count": int(len(g)),
            "total": float(amounts.sum()),
            "abs_total": float(amounts.abs().sum()),
            "first": g["date"].min(),
            "last": g["date"].max(),
            "example": str(g["description"].iloc[0]).strip(),
            "mixed": bool((amounts > 0).any() and (amounts < 0).any()),
            "fallback": fallback,
            "sig": hashlib.sha1(sig_src.encode()).hexdigest()[:10],
            "suggest_transfer": bool(g["description"].map(looks_like_transfer).any()),
            "rows": list(rows.values()),
        })
    return sorted(groups, key=lambda x: x["abs_total"], reverse=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider -s`
Expected: every test passes. Copy the `[regression gate]` lines into your report: the controller reviews every changed row.

- [ ] **Step 4b: Measure the grouping on the demo data** (for the spec's numbers). Using a temp copy of `Test Data` (ingest it with `main.main(data_dir)`), load it with `load_transactions(..., rules_path=<repo>/rules.csv)` and report:
  - `len(unlabeled_groups(df))`;
  - the share of unlabeled `abs_total` covered by the top 25;
  - how many groups are `fallback` and how many are `mixed`.

- [ ] **Step 5: Commit**

```bash
git add Modules/transforms.py Modules/labels.py tests/test_grouping.py
git commit -m "Group unlabeled rows by merchant; normalize rule matching"
```

---

### Task 2: Rule safety and `rules.csv` I/O

**Files:**
- Modify: `Modules/labels.py` (append)
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: from Task 1, `normalize_description`, `merchant_key`, `rule_keyword` and the group dicts.
- Produces:
  - `RULE_COLUMNS = ["keyword", "master_category", "sub_category", "added"]` and `MIN_KEYWORD = 4`
  - `read_rules(path) -> pd.DataFrame` (all columns `str`; `RULE_COLUMNS` always present)
  - `add_rule(path, keyword, category, sub="") -> bool`
  - `delete_rule(path, keyword) -> bool`
  - `rule_check(df, rules, group, norm=None) -> dict`, with keys `ok, keyword, reason, blocking, rows_now, dollars_now, others, direction` (`"money out"`, `"money in"` or `"mixed"`). Fallback groups are always blocked.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rules.py
import pandas as pd

from Modules.labels import (
    add_rule, delete_rule, read_rules, rule_check, unlabeled_groups,
)
from Modules.transforms import apply_auto_categories


def _df(rows):
    recs = [dict(date=r[0], description=r[1], amount=r[2], master_category=r[3],
                 sub_category="", source="Chase Credit", card_last4="") for r in rows]
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _group(df, merchant):
    return next(g for g in unlabeled_groups(df) if g["merchant"] == merchant)


def test_rule_check_ok():
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, ""),
              ("2025-03-02", "STARBUCKS STORE 2", -6.0, ""),
              ("2025-03-03", "RENT CO 9", -900.0, "")])
    chk = rule_check(df, read_rules("/nonexistent/rules.csv"), _group(df, "STARBUCKS STORE"))
    assert chk["ok"] and not chk["blocking"] and chk["reason"] is None
    assert chk["keyword"] == "starbucks store"
    assert chk["rows_now"] == 2 and chk["dollars_now"] == 11.0
    assert chk["direction"] == "money out"


def test_rule_check_blocks_fallback_groups():
    df = _df([("2025-03-01", "#123456", -5.0, "")])
    g = unlabeled_groups(df)[0]
    assert g["fallback"]
    chk = rule_check(df, read_rules("/nonexistent"), g)
    assert not chk["ok"] and chk["blocking"] and "name" in chk["reason"]


def test_rule_check_too_short():
    df = _df([("2025-03-01", "AB 12", -5.0, "")])
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AB"))
    assert not chk["ok"] and chk["blocking"] and "long enough" in chk["reason"]


def test_rule_check_matches_other_merchant_even_if_labeled():
    df = _df([("2025-03-01", "AMAZON MKTP 1", -20.0, ""),
              ("2025-03-02", "AMAZON MKTP US 99", -30.0, "Expense")])   # labeled, other merchant
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AMAZON MKTP"))
    assert not chk["ok"] and chk["blocking"]
    assert chk["others"] == ["AMAZON MKTP US"] and "AMAZON MKTP US" in chk["reason"]


def test_rule_check_existing_rule_overlap(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nstarbucks,,Coffee\n")   # sub-only rule
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, "")])
    chk = rule_check(df, read_rules(rules), _group(df, "STARBUCKS STORE"))
    assert not chk["ok"] and chk["blocking"] and '"starbucks"' in chk["reason"]


def test_rule_check_mixed_sign_is_not_blocking():
    df = _df([("2025-03-01", "AMAZON MKTP 1", -20.0, ""),
              ("2025-03-02", "AMAZON MKTP 2", 20.0, "")])
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AMAZON MKTP"))
    assert not chk["ok"] and not chk["blocking"] and "in and out" in chk["reason"]
    assert chk["direction"] == "mixed"


def test_add_rule_new_file_and_refusals(tmp_path):
    path = tmp_path / "rules.csv"
    assert add_rule(path, "starbucks store", "Expense", "Coffee")
    r = read_rules(path)
    assert r[["keyword", "master_category", "sub_category"]].values.tolist() == \
        [["starbucks store", "Expense", "Coffee"]]
    assert len(r.loc[0, "added"]) == 10                       # ISO date
    assert not add_rule(path, "Starbucks   Store", "Expense")   # duplicate after normalizing
    assert not add_rule(path, "rent co", "Groceries")          # not a predefined category
    assert not add_rule(path, "ab", "Expense")                 # too short
    assert len(read_rules(path)) == 1


def test_rules_bom_and_quoting_roundtrip(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_bytes("keyword,master_category,sub_category\npayroll,Income,\n".encode("utf-8-sig"))
    assert add_rule(path, "smith, jones & co", "Expense", "Legal, fees")
    r = read_rules(path)
    assert r["keyword"].tolist() == ["payroll", "smith, jones & co"]
    assert r.loc[1, "sub_category"] == "Legal, fees"


def test_added_rule_is_applied_and_extra_column_ignored(tmp_path):
    path = tmp_path / "rules.csv"
    add_rule(path, "starbucks store", "Expense", "Coffee")
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, "")])
    out = apply_auto_categories(df.copy(), path)
    assert (out.loc[0, "master_category"], out.loc[0, "sub_category"]) == ("Expense", "Coffee")


def test_delete_rule(tmp_path):
    path = tmp_path / "rules.csv"
    add_rule(path, "starbucks store", "Expense")
    add_rule(path, "rent co", "Expense")
    assert delete_rule(path, "STARBUCKS STORE")
    assert read_rules(path)["keyword"].tolist() == ["rent co"]
    assert not delete_rule(path, "nothing like this")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_rules.py -v -p no:cacheprovider`
Expected: collection ERROR, `ImportError: cannot import name 'add_rule'`.

- [ ] **Step 3: Implement** (append to `Modules/labels.py`, and add `from datetime import date` and `from pathlib import Path` to its imports, plus `from Modules.safety import atomic_write_csv`)

```python
# ── Rules: safety check and rules.csv I/O ─────────────────────────────────────

RULE_COLUMNS = ["keyword", "master_category", "sub_category", "added"]
MIN_KEYWORD  = 4


def read_rules(path) -> pd.DataFrame:
    """rules.csv as text columns, BOM-tolerant (Excel), RULE_COLUMNS always present."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=RULE_COLUMNS)
    rules = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if "master_category" not in rules.columns:     # legacy single-column files
        rules["master_category"] = rules["category"] if "category" in rules.columns else ""
    for col in RULE_COLUMNS:
        if col not in rules.columns:
            rules[col] = ""
    return rules


def add_rule(path, keyword, category, sub="") -> bool:
    """Append a rule. Refused (False, nothing written) for a short or duplicate
    keyword or a category that isn't Expense / Income / Transfer."""
    keyword = normalize_description(keyword)
    if len(keyword) < MIN_KEYWORD or category not in PREDEFINED_CATEGORIES:
        return False
    rules = read_rules(path)
    if (rules["keyword"].map(normalize_description) == keyword).any():
        return False
    row = {"keyword": keyword, "master_category": category,
           "sub_category": (sub or "").strip(), "added": date.today().isoformat()}
    atomic_write_csv(pd.concat([rules, pd.DataFrame([row])], ignore_index=True), Path(path))
    return True


def delete_rule(path, keyword) -> bool:
    rules = read_rules(path)
    hit = rules["keyword"].map(normalize_description) == normalize_description(keyword)
    if not hit.any():
        return False
    atomic_write_csv(rules[~hit], Path(path))
    return True


def rule_check(df: pd.DataFrame, rules: pd.DataFrame, group: dict, norm=None) -> dict:
    """
    Is remembering this group as a rule safe? A rule applies to every
    unlabeled row containing its keyword, past and future, first match wins —
    so it must provably mean only this merchant. Checks, in order:
    long enough · matches this merchant only (across ALL rows, labeled too)
    · no existing rule overlaps or would win first · one direction of money.
    Mixed direction is the only non-blocking reason (the user may still tick).
    norm: df's descriptions already normalized (saves work across many groups).
    """
    descs = [r["description"] for r in group["rows"]]
    kw = rule_keyword(descs)
    direction = "mixed" if group["mixed"] else ("money in" if group["total"] > 0 else "money out")
    out = {"ok": False, "keyword": kw, "reason": None, "blocking": True,
           "rows_now": 0, "dollars_now": 0.0, "others": [], "direction": direction}
    if group.get("fallback"):
        out["reason"] = "no recognizable merchant name — label these one at a time"
        return out
    if len(kw) < MIN_KEYWORD:
        out["reason"] = "no keyword long enough to be safe"
        return out
    norm = df["description"].map(normalize_description) if norm is None else norm
    hits = norm.str.contains(kw, regex=False)
    # Group keys exactly as unlabeled_groups makes them (nameless rows key on
    # their own description)
    keys = {merchant_key(d) or normalize_description(d) for d in df.loc[hits, "description"]}
    others = sorted(keys - {group["mkey"]})
    if others:
        out["others"] = [o.upper() for o in others[:3]]
        out["reason"] = "also matches " + ", ".join(out["others"])
        return out
    group_norm = [normalize_description(d) for d in descs]
    for k in rules["keyword"]:
        rk = normalize_description(k)
        if rk and (rk in kw or kw in rk or any(rk in d for d in group_norm)):
            out["reason"] = f'existing rule "{rk}" would override it'
            return out
    unl = hits & ~df["master_category"].isin(PREDEFINED_CATEGORIES)
    out["rows_now"] = int(unl.sum())
    out["dollars_now"] = float(df.loc[unl, "amount"].abs().sum())
    if group["mixed"]:
        out.update(reason="money in and out — check the rows first", blocking=False)
        return out
    out.update(ok=True, blocking=False)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 4b: Measure rule safety on the demo data** (for the spec). On the same temp copy as Task 1 Step 4b, report:
  - how many groups `rule_check` passes (`ok`), and their share of unlabeled dollars;
  - how many of the top 25 pass;
  - a count of the blocking reasons.

- [ ] **Step 5: Commit**

```bash
git add Modules/labels.py tests/test_rules.py
git commit -m "Add rule safety check and rules.csv read/add/delete"
```

---

### Task 3: Labeling writes, undo restore, last-import record

**Files:**
- Modify: `Modules/labels.py` (append `label_rows`, `LAST_IMPORT_NAME`, `last_import_ids`)
- Modify: `Modules/safety.py` (add `restore_backup`)
- Modify: `main.py`, `rebuild_master` (record new rows; write `SORTED/last_import.csv`)
- Test: `tests/test_labeling.py`

**Interfaces:**
- Consumes: from Task 1, `row_id`, `row_ids` and `unlabeled_groups`; the existing `apply_label_import`, `atomic_write_csv`, `backup_master` and `_replace_from`.
- Produces:
  - `label_rows(master, rows, category, sub="") -> tuple[pd.DataFrame, int]`. It touches **only master rows with no valid label**, so a hand-labeled twin is never overwritten. Callers compare the returned count with `sum(r["count"] for r in rows)` and write nothing on a mismatch.
  - `safety.snapshot_master(master, name="before-labeling") -> Path | None`: a copy kept **outside** the 10-backup rotation (`SORTED/backups/before-labeling.csv`)
  - `LAST_IMPORT_NAME = "last_import.csv"`
  - `last_import_ids(master_path) -> list[str] | None`
  - `safety.restore_backup(backup, master) -> None`
  - `SORTED/last_import.csv`, a single `row_id` column, written only when an import added rows. A Reload that adds nothing leaves it alone.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_labeling.py
import shutil
from pathlib import Path

import pandas as pd
import pytest

from main import MASTER_COLUMNS, UNIFIED_COLUMNS, rebuild_master
from Modules.labels import (
    LAST_IMPORT_NAME, label_rows, last_import_ids, row_id, row_ids, unlabeled_groups,
)
from Modules.safety import atomic_write_csv, backup_master, restore_backup
from Modules.transforms import load_transactions, period_totals

REPO = Path(__file__).resolve().parent.parent


def _master_df(rows):
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "card_last4"])
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    return df[MASTER_COLUMNS]


def _as_rows(master, idx):
    recs = master.loc[idx].to_dict("records")
    for r in recs:
        r["date"] = pd.Timestamp(r["date"])
        r["amount"] = float(r["amount"])
    return recs


def test_label_rows_twins_once_each():
    master = _master_df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, ""),
                         ("2025-03-02", "OTHER", -9.0, "")])
    out, n = label_rows(master, _as_rows(master, [0, 1]), "Expense", "Coffee")
    assert n == 2
    assert out["master_category"].tolist() == ["Expense", "Expense", ""]
    assert out.loc[0, "sub_category"] == "Coffee"


def test_label_rows_never_overwrites_a_labeled_twin():
    master = _master_df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, "")])
    master.loc[0, "master_category"] = "Income"            # hand-labeled twin
    out, n = label_rows(master, _as_rows(master, [1]), "Expense")
    assert n == 1 and out["master_category"].tolist() == ["Income", "Expense"]


def test_label_rows_card_aware():
    master = _master_df([("2025-03-01", "CAFE", -4.5, "0123"), ("2025-03-01", "CAFE", -4.5, "4567")])
    out, n = label_rows(master, _as_rows(master, [0]), "Expense")
    assert n == 1 and out["master_category"].tolist() == ["Expense", ""]


def test_restore_backup(tmp_path):
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    master.write_text("a\n1\n")
    b = backup_master(master)
    master.write_text("a\n2\n")
    restore_backup(b, master)
    assert master.read_text() == "a\n1\n"


def test_snapshot_survives_backup_rotation(tmp_path):
    from Modules.safety import list_backups, snapshot_master
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    master.write_text("a\n0\n")
    snap = snapshot_master(master)
    for i in range(1, 13):
        master.write_text(f"a\n{i}\n")
        backup_master(master, keep=3)
    assert snap.exists() and snap.read_text() == "a\n0\n"
    assert snap not in list_backups(master)


def _combined(rows):
    df = pd.DataFrame(rows, columns=["date", "description", "amount"])
    for col in UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df["date"] = pd.to_datetime(df["date"])
    return df[UNIFIED_COLUMNS]


def test_last_import_records_only_new_rows(tmp_path):
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    a = ("2025-03-01", "CAFE", -4.5)
    b = ("2025-03-02", "BOOKS", -12.0)
    rebuild_master(_combined([a]), master)                       # first import: no record
    assert last_import_ids(master) is None
    rebuild_master(_combined([a, b]), master)
    ids = last_import_ids(master)
    expected = row_id({"date": pd.Timestamp(b[0]), "description": b[1], "amount": b[2],
                       "source": "Chase Credit", "card_last4": ""})
    assert ids == [expected]
    assert (master.parent / LAST_IMPORT_NAME).exists()
    rebuild_master(_combined([a, b]), master)                    # no-op Reload
    assert last_import_ids(master) == [expected]                 # still remembered


@pytest.fixture
def demo(tmp_path):
    from main import main as run_ingest
    data = tmp_path / "data"
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    run_ingest(data)
    return data / "SORTED" / "edited_combined_transactions.csv"


def test_labeling_a_group_raises_totals_by_exactly_its_amount(demo):
    rules = REPO / "rules.csv"
    df = load_transactions(demo, rules_path=rules)
    group = next(g for g in unlabeled_groups(df) if all(r["amount"] < 0 for r in g["rows"]))
    before = period_totals(df, "year")["exp"].sum()

    master = pd.read_csv(demo, dtype={"card_last4": str, "master_category": str, "sub_category": str})
    master, n = label_rows(master, group["rows"], "Expense")
    atomic_write_csv(master, demo)
    df2 = load_transactions(demo, rules_path=rules)

    assert n >= len({r["row_id"] for r in group["rows"]})
    assert period_totals(df2, "year")["exp"].sum() - before == pytest.approx(
        -sum(r["amount"] for r in group["rows"]))
    ids = {r["row_id"] for r in group["rows"]}
    assert (df2.loc[row_ids(df2).isin(ids), "master_category"] == "Expense").all()


def test_acceptance_label_top_groups_then_new_statement(demo, tmp_path):
    """The goal, end to end: labeling the top groups (remembering safe ones)
    shrinks the unreviewed dollars, loses or duplicates nothing, and the next
    statement's matching row is labeled by the new rule automatically."""
    from main import main as run_ingest
    from Modules.labels import add_rule, read_rules, rule_check
    from Modules.transforms import PREDEFINED_CATEGORIES as CATS
    rules = tmp_path / "rules.csv"
    shutil.copy(REPO / "rules.csv", rules)
    df = load_transactions(demo, rules_path=rules)
    n_rows, total = len(df), df["amount"].sum()
    unrev = lambda d: d.loc[~d["master_category"].isin(CATS), "amount"].abs().sum()
    before = unrev(df)

    groups = [g for g in unlabeled_groups(df) if not g["fallback"] and not g["mixed"]][:25]
    master = pd.read_csv(demo, dtype={"card_last4": str, "master_category": str, "sub_category": str})
    labeled, remembered = 0.0, []
    for g in groups:
        cat = "Expense" if g["total"] < 0 else "Income"
        master, n = label_rows(master, g["rows"], cat)
        assert n == sum(r["count"] for r in g["rows"])
        labeled += g["abs_total"]
        chk = rule_check(df, read_rules(rules), g)
        if chk["ok"] and add_rule(rules, chk["keyword"], cat):
            remembered.append(chk["keyword"])
    atomic_write_csv(master, demo)
    df2 = load_transactions(demo, rules_path=rules)

    assert len(df2) == n_rows and df2["amount"].sum() == pytest.approx(total)   # nothing lost or duplicated
    assert unrev(df2) <= before - labeled + 0.01
    buckets = sum(df2.loc[df2["master_category"] == c, "amount"].sum() for c in CATS)
    unrev_amt = df2.loc[~df2["master_category"].isin(CATS), "amount"].sum()
    assert buckets + unrev_amt == pytest.approx(total)                          # every row in one bucket
    assert remembered, "no top group was safe to remember"

    # Next week's statement: one row from a remembered merchant, two new ones
    kw = remembered[0]
    (demo.parent.parent / "RAW" / "Chase" / "Chase9999_Activity_20260110.CSV").write_text(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        f"01/05/2026,01/06/2026,{kw.upper()} 555,Shopping,Sale,-12.34,\n"
        "01/06/2026,01/07/2026,NEWSHOP ALPHA 1,Shopping,Sale,-20.00,\n"
        "01/07/2026,01/08/2026,NEWSHOP BETA 2,Shopping,Sale,-30.00,\n")
    run_ingest(demo.parent.parent)
    ids = last_import_ids(demo)
    df3 = load_transactions(demo, rules_path=rules)
    new = df3[row_ids(df3).isin(set(ids))]
    assert len(ids) == 3
    assert int(new["master_category"].isin(CATS).sum()) == 1                  # the rule caught it
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_labeling.py -v -p no:cacheprovider`
Expected: collection ERROR, `ImportError: cannot import name 'LAST_IMPORT_NAME'`.

- [ ] **Step 3: Implement**

In `Modules/safety.py`, after `_replace_from`:

```python
def restore_backup(backup: Path, master: Path) -> None:
    """Put a backup back over the master, atomically (used by the panel's Undo)."""
    _replace_from(Path(backup), Path(master))


def snapshot_master(master: Path, name: str = "before-labeling") -> Path | None:
    """A named copy kept OUTSIDE the backup rotation: labeling takes a backup
    per click, so ten clicks would otherwise prune away the state from before
    the labeling session — the recovery point that matters most."""
    master = Path(master)
    if not master.exists():
        return None
    d = _backup_dir(master)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{name}{master.suffix}"          # outside list_backups' glob
    _replace_from(master, dest)
    return dest
```

Append to `Modules/labels.py`:

```python
# ── Writing labels; the last import's rows ────────────────────────────────────

LAST_IMPORT_NAME = "last_import.csv"


def label_rows(master: pd.DataFrame, rows: list[dict], category: str, sub: str = "") -> tuple[pd.DataFrame, int]:
    """Label exactly these rows in the master, through the same matcher Excel
    imports use (date + description + amount + source + card), touching only
    rows that have no valid label yet. Twin rows are sent once so the count
    isn't doubled. Returns (master, rows labeled); the caller checks the count
    against what it expected and writes nothing on a mismatch."""
    imp = pd.DataFrame([{
        "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
        "description": str(r["description"]),
        "amount": f"{float(r['amount']):.2f}",
        "source": str(r["source"]),
        "card_last4": str(r.get("card_last4", "") or ""),
        "master_category": category,
        "sub_category": sub or "",
    } for r in rows]).drop_duplicates()
    # Only rows without a valid label are candidates: a hand-labeled twin of an
    # unlabeled row (same date, description, amount, card) must keep its label
    master = master.copy()
    open_ = ~master["master_category"].fillna("").astype(str).str.strip().isin(PREDEFINED_CATEGORIES)
    part, updated, _ = apply_label_import(master[open_], imp)
    for col in ("master_category", "sub_category"):
        master[col] = master[col].fillna("").astype(str)
        master.loc[part.index, col] = part[col]
    return master, updated


def last_import_ids(master_path) -> list[str] | None:
    """Row ids the last import added, or None when there's no record."""
    if not master_path:
        return None
    p = Path(master_path).parent / LAST_IMPORT_NAME
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, dtype=str, keep_default_na=False)["row_id"].tolist()
    except (pd.errors.ParserError, pd.errors.EmptyDataError, KeyError, OSError):
        return None
```

In `main.py`, add `from Modules.labels import LAST_IMPORT_NAME, row_id` to the imports. Then make four edits in `rebuild_master`. Each code block below is shown at the indentation it has in the function.

**(a)** Next to `orphans = None`:

```python
    new_ids = None   # rows this import added; set only when a prior master existed
```

**(b)** In pass 2, put `rescued = set()` on the line before `rest = combined[...]`. Then change the `if bucket:` block to:

```python
            if bucket:
                _take(idx, bucket.popleft())
                rescued.add(idx)
                result["rescued"] += 1
```

**(c)** Directly after `result["orphaned"] = len(orphans)`:

```python
        # What this import added: rows neither carried nor rescued from the
        # old master. Computed before the sort below renumbers the index.
        fresh = combined.index.difference(list(matched | rescued))
        new_ids = [row_id(r) for r in combined.loc[fresh].to_dict("records")]
```

**(d)** After the orphan block, and before `return result`:

```python
    # Record the import's new rows for the dashboard's "N new · K need you"
    # line — only when this import added any: a Reload that finds nothing new
    # must not wipe the record of the last real import.
    if new_ids:
        try:
            atomic_write_csv(pd.DataFrame({"row_id": new_ids}),
                             master_file.parent / LAST_IMPORT_NAME)
        except OSError as e:
            print(f"  ⚠ Could not record the last import ({e})")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add Modules/labels.py Modules/safety.py main.py tests/test_labeling.py
git commit -m "Label rows via the import matcher; record each import's new rows"
```

---

### Task 4: Header entry points, unreviewed line, rules-path override

**Files:**
- Modify: `app.py`: imports; `RULES_PATH` (env override); the header layout (`unlabeled-note` area); `update_unlabeled_note`; a new `update_last_import_note`; `update_stats`; and a new `_HIDDEN` / `_SHOWN_INLINE` style pair near `_MENU_HIDDEN`. The drilldown's `_merchant` is **not** changed: that would be an unrelated behaviour change.
- Modify: `assets/app.css` (the `.notice-row` and `.unreviewed` rules)
- Test: `tests/test_label_panel.py` (header and stat-card helpers)

**Interfaces:**
- Consumes: from Tasks 1 and 3, `unlabeled_groups`, `row_ids`, `last_import_ids` and `merchant_key`.
- Produces:
  - `RULES_PATH` honours `FINANCE_RULES_PATH`, so tests and Playwright point the app at a temp copy and never write the repo's `rules.csv`
  - layout ids `open-label-panel`, `last-import-note` and `open-label-review`. The two buttons have no callback until Task 5 and stay hidden until data exists, which is acceptable inside this branch.
  - the module helpers `unreviewed_amounts(pdf) -> tuple[float, float]` (money out, money in) and `last_import_text(df, ids) -> tuple[str, int]` (text, need-you count)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_label_panel.py
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def appmod(tmp_path_factory):
    """app.py loaded against a temp copy of Test Data (never the repo's)."""
    import runpy
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    rules = data / "rules.csv"
    shutil.copy(REPO / "rules.csv", rules)          # never write the repo's rules.csv
    saved = {k: os.environ.get(k) for k in ("FINANCE_DATA_DIR", "FINANCE_RULES_PATH")}
    os.environ["FINANCE_DATA_DIR"] = str(data)
    os.environ["FINANCE_RULES_PATH"] = str(rules)
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_app")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_rules_path_override(appmod):
    assert Path(appmod["RULES_PATH"]).parent != REPO


def test_unreviewed_amounts(appmod):
    pdf = pd.DataFrame({"amount": [-10.0, -5.0, 7.0, -100.0],
                        "master_category": ["", "", "", "Expense"]})
    assert appmod["unreviewed_amounts"](pdf) == (15.0, 7.0)


def test_last_import_text(appmod):
    from Modules.labels import row_ids
    df = appmod["df"]
    ids = row_ids(df.head(3)).tolist()
    text, need = appmod["last_import_text"](df, ids)
    assert text.startswith("Last import: 3 new")
    assert need == int((~df.head(3)["master_category"].isin(["Expense", "Income", "Transfer"])).sum())
    assert appmod["last_import_text"](df, None) == ("", 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_label_panel.py -v -p no:cacheprovider`
Expected: FAIL, `KeyError: 'unreviewed_amounts'`.

- [ ] **Step 3: Implement**

`RULES_PATH` in `app.py` becomes:

```python
# FINANCE_RULES_PATH lets tests and scripted checks use a copy, so they never
# rewrite the real rules.csv now that the app can add and delete rules
RULES_PATH  = Path(os.environ.get("FINANCE_RULES_PATH") or BASE_DIR / "rules.csv")
```

Imports in `app.py`: add `ALL` to `from dash import …`. Extend the labels import to `from Modules.labels import apply_label_import, read_import_csv, row_ids, last_import_ids` (later tasks add more names). Add `PREDEFINED_CATEGORIES` to the `Modules.transforms` import.

Near `_MENU_HIDDEN`:

```python
_HIDDEN       = {"display": "none"}
_SHOWN_INLINE = {"display": "inline-block"}
```

Module helpers, placed before `# ── App ──`:

```python
def unreviewed_amounts(pdf: pd.DataFrame) -> tuple[float, float]:
    """Unlabeled money out and money in for a slice of rows — shown on the stat
    cards so incomplete totals look incomplete instead of quietly short."""
    un = pdf[~pdf["master_category"].isin(PREDEFINED_CATEGORIES)]
    return (float(-un.loc[un["amount"] < 0, "amount"].sum()),
            float(un.loc[un["amount"] > 0, "amount"].sum()))


def last_import_text(frame: pd.DataFrame, ids) -> tuple[str, int]:
    """'Last import: 31 new · 27 labeled · 4 need you', and the need-you count."""
    if not ids:
        return "", 0
    rows = frame[row_ids(frame).isin(set(ids))]
    labeled = int(rows["master_category"].isin(PREDEFINED_CATEGORIES).sum())
    need = len(rows) - labeled
    return f"Last import: {len(ids)} new · {labeled} labeled · {need} need you", need
```

Header layout: replace

```python
            # Unlabeled rows are ignored by every total — count and size them
            html.P(id="unlabeled-note", className="notice warn-text"),
```

with

```python
            # Unlabeled rows are ignored by every total — count, size, and the
            # way in to label them
            html.Div(className="notice-row", children=[
                html.Span(id="unlabeled-note", className="notice warn-text"),
                html.Button("LABEL THEM →", id="open-label-panel", n_clicks=0,
                            className="btn-secondary btn-small", style=_HIDDEN),
            ]),
            # What the last import added, and how many still need a label
            html.Div(className="notice-row", children=[
                html.Span(id="last-import-note", className="notice"),
                html.Button("REVIEW →", id="open-label-review", n_clicks=0,
                            className="btn-secondary btn-small", style=_HIDDEN),
            ]),
```

Replace `update_unlabeled_note` with:

```python
@app.callback(
    Output("unlabeled-note",   "children"),
    Output("open-label-panel", "style"),
    Input("refresh-trigger", "data"),
)
def update_unlabeled_note(_refresh):
    # Anything outside Expense / Income / Transfer (including blank) never
    # reaches a total — Transfer is deliberate, the rest deserve a flag.
    u = unlabeled_summary(df)
    if u["count"] == 0:
        return "", _HIDDEN
    return (f"⚠ {u['count']:,} of {u['total']:,} transactions ({_dollar0(u['amount'])}) "
            f"are unlabeled and not counted."), _SHOWN_INLINE


@app.callback(
    Output("last-import-note",  "children"),
    Output("open-label-review", "style"),
    Input("refresh-trigger", "data"),
)
def update_last_import_note(_refresh):
    text, need = last_import_text(df, last_import_ids(MASTER_PATH))
    return text, (_SHOWN_INLINE if need else _HIDDEN)
```

In `update_stats`, before `cards = [`:

```python
    out_unrev, in_unrev = unreviewed_amounts(filter_period(df, p))

    def _unreviewed(amount):
        if amount < 0.5:
            return None
        return html.Div(f"+ {_dollar0(amount)} unreviewed", className="stat-delta unreviewed",
                        title="Unlabeled transactions in this period — not counted above")
```

Then change the SPENT and INCOME cards so they pass `[*_lines("exp", False), _unreviewed(out_unrev)]` and `[*_lines("inc", True), _unreviewed(in_unrev)]` respectively. In `_stat_card`, filter out `None`: `*[l for l in lines if l is not None]`.

CSS (append to `assets/app.css` under the Header section):

```css
.notice-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.notice-row .notice { margin: 4px 0 0; }
.notice-row .btn-small { padding: 3px 10px; font-size: 10px; margin-top: 4px; }
.stat-delta.unreviewed { color: var(--subtext); font-style: italic; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; pyflakes shows only the two existing `main.py` f-string warnings.

- [ ] **Step 5: Commit**

```bash
git add app.py assets/app.css tests/test_label_panel.py
git commit -m "Header entry points, unreviewed totals, rules-path override"
```

---

### Task 5: Label panel: layout, open/close, list rendering

**Files:**
- Modify: `app.py` (constants, stores, overlay layout, `_group_card`, `_rules_view`, `toggle_label_panel`, `render_label_list`)
- Modify: `assets/app.css` (panel section)
- Test: `tests/test_label_panel.py` (append)

**Interfaces:**
- Consumes: from Tasks 1–4, `unlabeled_groups`, `rule_check`, `read_rules`, `last_import_ids`, `normalize_description` and `_HIDDEN`.
- Produces:
  - `LABEL_TOP_N = 25` and `LABEL_GUIDE` (markdown)
  - stores `label-filter` (`"all"`/`"last"`), `label-undo` and `label-version`
  - ids `label-panel`, `label-list`, `label-summary`, `label-tab`, `label-status`, `label-undo-btn` and `close-label-panel`
  - pattern ids:
    - `{"type": "lbl-group", "group", "sig", "cat"}`, where `sig` is the group's signature at render time, checked again at click time
    - `{"type": "lbl-row", "group", "row", "cat"}`, where `row` is a `row_id`, never a list position
    - `{"type": "lbl-sub", "group"}`
    - `{"type": "lbl-remember", "group"}`
    - `{"type": "lbl-rule-del", "keyword"}`
  - `_group_card(group, chk) -> html.Div` and `_rules_view() -> list`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_label_panel.py`)

```python
def _ids(component):
    """Every component id in a Dash tree."""
    out, stack = [], [component]
    while stack:
        c = stack.pop()
        if isinstance(c, (list, tuple)):
            stack.extend(c)
            continue
        if getattr(c, "id", None) is not None:
            out.append(c.id)
        kids = getattr(c, "children", None)
        if kids is not None:
            stack.append(kids)
    return out


def test_mixed_and_fallback_groups_have_no_group_buttons(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-02", "2025-03-03"]),
        "description": ["AMAZON MKTP 1", "AMAZON MKTP 2", "#99999"], "amount": [-20.0, 20.0, -5.0],
        "master_category": ["", "", ""], "sub_category": ["", "", ""],
        "source": ["Chase Credit"] * 3, "card_last4": ["", "", ""],
    })
    for g in unlabeled_groups(df):
        assert g["mixed"] or g["fallback"]
        card = appmod["_group_card"](g, rule_check(df, read_rules("/none"), g))
        ids = _ids(card)
        assert not any(isinstance(i, dict) and i.get("type") == "lbl-group" for i in ids)
        assert any(isinstance(i, dict) and i.get("type") == "lbl-row" for i in ids)


def test_group_card_row_ids_unique(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-01"]),
        "description": ["CAFE", "CAFE"], "amount": [-4.5, -4.5],
        "master_category": ["", ""], "sub_category": ["", ""],
        "source": ["Chase Credit"] * 2, "card_last4": ["", ""],
    })
    g = unlabeled_groups(df)[0]
    card = appmod["_group_card"](g, rule_check(df, read_rules("/none"), g))
    ids = [str(i) for i in _ids(card)]
    assert len(ids) == len(set(ids))            # twins don't collide


def test_group_card_remember_state(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01"]), "description": ["AB 12"], "amount": [-4.5],
        "master_category": [""], "sub_category": [""], "source": ["Chase Credit"], "card_last4": [""],
    })
    g = unlabeled_groups(df)[0]
    chk = rule_check(df, read_rules("/none"), g)
    card = appmod["_group_card"](g, chk)
    remember = next(c for c in _walk(card) if getattr(c, "id", None) == {"type": "lbl-remember", "group": g["key"]})
    assert remember.value == [] and remember.options[0]["disabled"] is True


def _walk(component):
    stack = [component]
    while stack:
        c = stack.pop()
        if isinstance(c, (list, tuple)):
            stack.extend(c)
            continue
        yield c
        kids = getattr(c, "children", None)
        if kids is not None:
            stack.append(kids)


def test_render_label_list_top_n(appmod):
    children, summary = appmod["render_label_list"]({"display": "block"}, 0, "todo", "dark", "all")
    assert 0 < len(children) <= appmod["LABEL_TOP_N"] + 1     # + the subcategory datalist
    assert "merchants" in summary
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_label_panel.py -v -p no:cacheprovider`
Expected: FAIL, `KeyError: '_group_card'`.

- [ ] **Step 3: Implement**

Extend the `Modules.labels` import with `unlabeled_groups, rule_check, read_rules`, add `normalize_description` to the transforms import, and add `snapshot_master` to the `Modules.safety` import.

Constants, after `CHART_PERIODS`:

```python
# The labeling panel shows the biggest merchants only — the top 25 cover ~90%
# of unlabeled dollars on real data; the rest wait for the next session.
LABEL_TOP_N = 25

LABEL_GUIDE = """
**Ask one question: did money enter or leave *you* — all your accounts counted as one pot?**

- **Expense** — it left you for someone else (groceries, rent, a Zelle to a friend for dinner).
- **Income** — it came to you from someone else (paycheck, client payment, tax refund).
- **Transfer** — it moved between your own accounts (credit-card payment, savings or investments, Venmo cash-out). Card purchases were already counted, so the bill payment must not count again.

**Tricky cases** — card payment ("AUTOPAY", "PAYMENT THANK YOU"): Transfer, on both sides ·
refund: Expense (it reduces spending) · friend paying you back: Expense · Venmo / Zelle / PayPal:
depends who's on the other end — expand and label row by row · ATM cash: Expense ·
loan or mortgage payment: Expense.
"""
```

Stores, next to the other `dcc.Store`s:

```python
        # Labeling panel: which list it shows, the last action (for Undo), and a
        # counter bumped after every write so the list re-renders
        dcc.Store(id="label-filter", data="all"),
        dcc.Store(id="label-undo"),
        dcc.Store(id="label-version", data=0),
```

Overlay, placed right after the setup overlay `html.Div(...)`:

```python
        # ── Labeling panel (full-screen; opened from the header) ─────────────
        html.Div(id="label-panel", style=_HIDDEN, children=html.Div(className="label-panel-inner", children=[
            html.Div(className="label-head", children=[
                html.Div([html.Div("LABEL TRANSACTIONS", className="app-label"),
                          html.Div(id="label-summary", className="hint")]),
                dcc.RadioItems(
                    id="label-tab", className="pills", value="todo", inline=True,
                    inputStyle=_PILL_INPUT,
                    options=[{"label": "TO LABEL", "value": "todo"},
                             {"label": "RULES", "value": "rules"}],
                ),
                html.Button("DONE", id="close-label-panel", n_clicks=0, className="btn-primary"),
            ]),
            html.Details(className="label-guide", children=[
                html.Summary("How to choose a label"),
                dcc.Markdown(LABEL_GUIDE),
            ]),
            html.Div(className="label-status-row", children=[
                html.Span(id="label-status", className="settings-status"),
                html.Button("UNDO", id="label-undo-btn", n_clicks=0,
                            className="btn-secondary btn-small", style=_HIDDEN),
            ]),
            html.Div(id="label-list"),
        ])),
```

Card builders, before the callbacks section:

```python
def _span_text(g) -> str:
    a, b = pd.Timestamp(g["first"]), pd.Timestamp(g["last"])
    if a.date() == b.date():
        return f"{a:%b} {a.day}, {a.year}"
    return f"{a:%b} {a.day}, {a.year} – {b:%b} {b.day}, {b.year}"


def _group_card(g: dict, chk: dict):
    """One merchant group: three label buttons, subcategory, remember, rows."""
    key = g["key"]

    # Bulk buttons only when one click is safe: never on a nameless (fallback)
    # group or one with money both in and out — those are labeled row by row
    bulk = not g["fallback"] and not g["mixed"]

    def _btn(cat, row=None):
        id_ = ({"type": "lbl-group", "group": key, "sig": g["sig"], "cat": cat} if row is None
               else {"type": "lbl-row", "group": key, "row": row, "cat": cat})
        cls = "btn-secondary btn-small"
        if cat == "Transfer" and g["suggest_transfer"]:
            cls += " suggested"
        return html.Button(cat.upper(), id=id_, n_clicks=0, className=cls,
                           title="Suggested: looks like a card payment or transfer"
                           if "suggested" in cls else None)

    if chk["ok"]:
        note = (f'rule "{chk["keyword"]}" ({chk["direction"]}) · labels {chk["rows_now"]} row'
                f'{"s" if chk["rows_now"] != 1 else ""} ({_dollar0(chk["dollars_now"])}) now')
    else:
        note = chk["reason"]

    rows = [html.Div(className="lg-row", children=[
                html.Span(f"{pd.Timestamp(r['date']):%b} {pd.Timestamp(r['date']).day}", className="lg-date"),
                html.Span(r["description"] + (f"  ×{r['count']}" if r["count"] > 1 else ""),
                          className="lg-desc", title=r["description"]),
                html.Span(_dollar(r["amount"]), className="lg-amt"),
                html.Div(className="lg-buttons", children=[_btn(c, r["row_id"]) for c in PREDEFINED_CATEGORIES]),
            ]) for r in g["rows"]]

    return html.Div(className="app-card label-group", children=[
        html.Div(className="lg-main", children=[
            html.Div(className="lg-info", children=[
                html.Div([html.Span(g["merchant"], className="lg-name", title=g["example"]),
                          html.Span("MIXED", className="lg-badge",
                                    title="Has money in and out — check the rows")
                          if g["mixed"] else None]),
                html.Div(f'{g["count"]} txn{"s" if g["count"] != 1 else ""} · '
                         f'{_dollar(g["total"])} · {_span_text(g)}', className="hint"),
                html.Div(g["example"], className="lg-example"),
            ]),
            html.Div(className="lg-buttons", children=[_btn(c) for c in PREDEFINED_CATEGORIES]) if bulk
            else html.Div("Label these one at a time below", className="hint"),
        ]),
        html.Div(className="lg-options", children=[
            dcc.Input(id={"type": "lbl-sub", "group": key}, placeholder="Subcategory (optional)",
                      className="setup-input lg-sub", list="lbl-sub-options", debounce=False),
            dcc.Checklist(
                id={"type": "lbl-remember", "group": key}, className="lg-remember",
                options=[{"label": " Remember for future statements", "value": "yes",
                          "disabled": bool(chk["blocking"])}],
                value=["yes"] if chk["ok"] else [],
            ),
            html.Span(note, className="hint"),
        ]),
        # Row-by-row groups stay open so each click doesn't re-collapse them
        html.Details(className="lg-rows", open=not bulk, children=[
            html.Summary(f"Label rows one at a time ({g['count']})"), *rows,
        ]),
    ])


def _rules_view():
    """The Rules tab: rules this panel added (with DELETE), then hand-written ones."""
    rules = read_rules(RULES_PATH)
    norm = df["description"].map(normalize_description)

    def _hits(k):
        k = normalize_description(k)
        return int(norm.str.contains(k, regex=False).sum()) if k else 0

    def _row(r, deletable):
        label = r.master_category or "—"
        if r.sub_category:
            label += f" · {r.sub_category}"
        meta = f"{label} · matches {_hits(r.keyword)} rows" + (f" · added {r.added}" if r.added else "")
        return html.Div(className="rule-row", children=[
            html.Span(r.keyword, className="lg-name"),
            html.Span(meta, className="hint"),
            html.Button("DELETE", id={"type": "lbl-rule-del", "keyword": r.keyword}, n_clicks=0,
                        className="btn-secondary btn-small") if deletable else None,
        ])

    added = rules[rules["added"] != ""]
    manual = rules[rules["added"] == ""]
    return [
        html.Div("ADDED FROM THIS PANEL", className="settings-label"),
        *([_row(r, True) for r in added.itertuples()] or [html.Div("None yet.", className="hint")]),
        html.Div("IN RULES.CSV (EDIT THE FILE TO CHANGE)", className="settings-label",
                 style={"marginTop": "20px"}),
        *[_row(r, False) for r in manual.itertuples()],
    ]
```

Callbacks:

```python
# ── Labeling panel ────────────────────────────────────────────────────────────

@app.callback(
    Output("label-panel",     "style"),
    Output("label-filter",    "data"),
    Output("label-tab",       "value"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("open-label-panel",  "n_clicks"),
    Input("open-label-review", "n_clicks"),
    Input("close-label-panel", "n_clicks"),
    State("refresh-trigger",   "data"),
    prevent_initial_call=True,
)
def toggle_label_panel(_open, _review, _close, trigger):
    # Closing refreshes every card: labels written while the panel was open
    # change totals, the header notes and the period bar
    if ctx.triggered_id == "close-label-panel":
        return _HIDDEN, dash.no_update, dash.no_update, (trigger or 0) + 1
    filt = "last" if ctx.triggered_id == "open-label-review" else "all"
    # Keep the state from before this labeling session outside the backup
    # rotation (each click takes a rotating backup)
    if MASTER_PATH and MASTER_PATH.exists():
        with MASTER_LOCK:
            snapshot_master(MASTER_PATH)
    return {"display": "block"}, filt, "todo", dash.no_update


@app.callback(
    Output("label-list",    "children"),
    Output("label-summary", "children"),
    Input("label-panel",   "style"),
    Input("label-version", "data"),
    Input("label-tab",     "value"),
    Input("theme-store",   "data"),
    State("label-filter",  "data"),
)
def render_label_list(style, _version, tab, _theme, filt):
    if not style or style.get("display") == "none":
        return dash.no_update, dash.no_update
    if tab == "rules":
        return _rules_view(), "Rules label every matching unlabeled row, past and future"
    only = last_import_ids(MASTER_PATH) if filt == "last" else None
    groups = unlabeled_groups(df, only_row_ids=only)
    n_rows = sum(g["count"] for g in groups)
    summary = (f"{n_rows:,} rows · {_dollar0(sum(g['abs_total'] for g in groups))} · "
               f"{len(groups)} merchants" + (" · from the last import" if only is not None else ""))
    if not groups:
        return html.Div("Everything is labeled ✓", className="hint"), summary
    rules = read_rules(RULES_PATH)
    norm = df["description"].map(normalize_description)
    subs = sorted(s for s in df["sub_category"].unique() if s)
    cards = [_group_card(g, rule_check(df, rules, g, norm=norm)) for g in groups[:LABEL_TOP_N]]
    datalist = html.Datalist(id="lbl-sub-options", children=[html.Option(value=s) for s in subs])
    if len(groups) > LABEL_TOP_N:
        summary += f" · showing the top {LABEL_TOP_N}"
    return [datalist, *cards], summary
```

CSS (append a section to `assets/app.css`):

```css
/* ── Labeling panel ─────────────────────────────────────────────────────── */
#label-panel { position: fixed; inset: 0; z-index: 90; background: var(--bg); overflow-y: auto; padding: 32px 40px; }
.label-panel-inner { max-width: 1100px; margin: 0 auto; }
.label-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.label-guide { margin-bottom: 12px; font-size: 12px; color: var(--subtext); line-height: 1.6; }
.label-guide summary { cursor: pointer; color: var(--accent); font-weight: 600; letter-spacing: 1px; }
.label-guide p, .label-guide ul { margin: 8px 0; }
.label-guide ul { padding-left: 18px; }
.label-status-row { display: flex; gap: 10px; align-items: center; min-height: 30px; margin-bottom: 8px; }
.label-group { padding: 16px 18px; margin-bottom: 12px; }
.lg-main { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.lg-info { min-width: 0; flex: 1; }
.lg-name { font-weight: 600; font-size: 14px; }
.lg-badge { margin-left: 8px; font-size: 10px; letter-spacing: 1px; color: var(--accent2); border: 1px solid var(--accent2); border-radius: 4px; padding: 1px 6px; }
.lg-example { font-size: 11px; color: var(--subtext); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lg-buttons { display: flex; gap: 6px; flex-wrap: wrap; align-items: flex-start; }
.btn-secondary.suggested { background: var(--accent-weak); color: var(--text); }
.lg-options { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 10px; }
.lg-sub { flex: 0 0 200px; padding: 6px 10px; font-size: 12px; }
.lg-remember { font-size: 12px; }
.lg-rows summary { cursor: pointer; font-size: 11px; color: var(--subtext); margin-top: 10px; }
.lg-row { display: flex; gap: 10px; align-items: center; padding: 6px 0; border-top: 1px solid var(--border); font-size: 12px; flex-wrap: wrap; }
.lg-date { flex: 0 0 52px; color: var(--subtext); }
.lg-desc { flex: 1; min-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lg-amt { flex: 0 0 90px; text-align: right; }
.rule-row { display: flex; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
@media (max-width: 640px) { #label-panel { padding: 20px 16px; } .lg-sub { flex-basis: 100%; } }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; pyflakes shows only the two existing warnings.

- [ ] **Step 5: Commit**

```bash
git add app.py assets/app.css tests/test_label_panel.py
git commit -m "Labeling panel: layout, guide, merchant groups, rules tab"
```

---

### Task 6: Label panel actions: label, undo, delete rule

**Files:**
- Modify: `app.py` (callbacks `label_click`, `undo_label`, `delete_rule_click`; imports)
- Test: `tests/test_label_panel.py` (append)

**Interfaces:**
- Consumes: from Tasks 1–5, `label_rows`, `rule_check`, `add_rule`, `delete_rule`, `read_rules`, `restore_backup`, `backup_master`, `atomic_write_csv`, `MASTER_LOCK` and the ids from Task 5 (`lbl-group` carries `sig`; `lbl-row` carries `row`, a `row_id`).
- Produces: `_is_real_click`, `_mtime`, `_do_label`, `_do_undo`, and the callbacks. `label-undo` data is `{"backup": str, "master_mtime": str, "rules_mtime": str, "rule": str | None}`. The mtimes are **strings**: `st_mtime_ns` is above 2^53, and the browser's JSON round-trip would round an int, so undo would always refuse.

- [ ] **Step 1: Write the failing tests** (append)

```python
import json


def _live(appmod):
    """The app module's live globals (runpy returns a copy; callbacks rebind df)."""
    return appmod["_do_label"].__globals__


def _bulk_group(g_):
    from Modules.labels import unlabeled_groups
    return next(g for g in unlabeled_groups(g_["df"]) if not g["fallback"] and not g["mixed"])


def _group_trig(grp, cat="Expense", sig=None):
    return {"type": "lbl-group", "group": grp["key"], "sig": sig or grp["sig"], "cat": cat}


def test_label_click_ignores_rerender(appmod):
    real = appmod["_is_real_click"]
    pid = '{"cat":"Expense","group":"x","sig":"s","type":"lbl-group"}.n_clicks'
    assert not real([])
    assert not real([{"prop_id": pid, "value": 0}])
    assert not real([{"prop_id": pid, "value": None}])
    assert real([{"prop_id": pid, "value": 1}])


def test_label_then_undo_roundtrip(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = _bulk_group(g_)
    status, undo, _, version = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    assert status.startswith("Labeled") and undo and version == 1
    assert master.read_bytes() != before
    undo = json.loads(json.dumps(undo))          # what the browser hands back
    status2, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status2 == "Undone." and undo2 is None
    assert master.read_bytes() == before


def test_undo_record_survives_json(appmod):
    g_ = _live(appmod)
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    assert isinstance(undo["master_mtime"], str) and isinstance(undo["rules_mtime"], str)
    assert json.loads(json.dumps(undo)) == undo


def test_undo_refuses_after_change(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    changed = master.read_bytes() + b"\n"
    master.write_bytes(changed)                  # something else wrote the master
    status, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert master.read_bytes() == changed


def test_undo_refuses_after_rules_change(appmod):
    g_ = _live(appmod)
    master, rules = g_["MASTER_PATH"], g_["RULES_PATH"]
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    after = master.read_bytes()
    rules.write_text(rules.read_text() + "zzz unrelated shop,Expense,,2026-01-01\n")
    status, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert master.read_bytes() == after


def test_label_click_refuses_stale_sig(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, undo, _, version = g_["_do_label"](_group_trig(_bulk_group(g_), sig="0000000000"), "", False, 0, "all")
    assert status.startswith("The list changed") and version == 1
    assert master.read_bytes() == before


def test_label_click_refuses_group_label_on_mixed_or_fallback(appmod):
    from Modules.labels import unlabeled_groups
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    risky = [g for g in unlabeled_groups(g_["df"]) if g["fallback"] or g["mixed"]]
    assert risky, "Test Data should contain at least one mixed or fallback group"
    status, _, _, _ = g_["_do_label"](_group_trig(risky[0]), "", False, 0, "all")
    assert status.startswith("Label these one at a time")
    assert master.read_bytes() == before


def test_row_click_labels_by_row_id(appmod):
    from Modules.labels import row_ids
    g_ = _live(appmod)
    grp = _bulk_group(g_)
    row = grp["rows"][-1]
    status, _, _, _ = g_["_do_label"](
        {"type": "lbl-row", "group": grp["key"], "row": row["row_id"], "cat": "Transfer"}, "", False, 0, "all")
    assert status.startswith("Labeled")
    df = g_["df"]
    assert (df.loc[row_ids(df) == row["row_id"], "master_category"] == "Transfer").all()


def test_label_survives_rules_file_locked(appmod, monkeypatch):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()

    def locked(*a, **k):
        raise PermissionError("open in Excel")
    monkeypatch.setitem(g_, "add_rule", locked)
    status, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", True, 0, "all")
    assert status.startswith("Labeled") and "not remembered" in status
    assert undo and undo["rule"] is None          # the label still has an undo
    assert master.read_bytes() != before
```

The callback bodies live in plain functions so the tests can call them without a running Dash server:
- `_is_real_click(triggered)`: is this a real click, or a re-render?
- `_do_label(trig, sub, remember, version, filt)`
- `_do_undo(undo, version)`

The callbacks themselves only read `ctx` and the ALL-states, then delegate.

If `test_label_click_refuses_group_label_on_mixed_or_fallback` finds no risky group in `Test Data/`, build one in the test's temp master instead (append an unlabeled `#99999` row); don't skip the test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_label_panel.py -v -p no:cacheprovider`
Expected: FAIL, `KeyError: '_do_label'`.

- [ ] **Step 3: Implement**

Extend the imports to `from Modules.labels import (…, label_rows, add_rule, delete_rule)` and `from Modules.safety import MASTER_LOCK, atomic_write_csv, backup_master, orphan_count, restore_backup, snapshot_master`.

```python
_LOCKED_MSG = "⚠ The data file is open in another program (Excel?) — close it and try again."


def _is_real_click(triggered) -> bool:
    """Re-rendering the list adds buttons with n_clicks=0 (or None), which fires
    pattern-matching callbacks too — only a real click may write anything."""
    return bool(triggered) and bool(triggered[0].get("value"))


def _mtime(path) -> str:
    """A file's mtime as a string: st_mtime_ns is past 2^53, and the undo record
    goes through the browser's JSON, which would round an int."""
    return str(Path(path).stat().st_mtime_ns) if path and Path(path).exists() else "0"


def _do_label(trig: dict, sub: str, remember: bool, version, filt):
    """Label a group (or one row of it): master write under the lock with a
    backup first, then — only if that succeeded — the rule. Returns
    (status, undo, undo-button style, version)."""
    global df
    bumped = (version or 0) + 1
    stale = ("The list changed — it has been refreshed.", dash.no_update, dash.no_update, bumped)
    only = last_import_ids(MASTER_PATH) if filt == "last" else None
    groups = unlabeled_groups(df, only_row_ids=only)
    group = next((g for g in groups if g["key"] == trig["group"]), None)
    if trig["type"] == "lbl-group":
        if group is None or group["sig"] != trig.get("sig"):
            return stale                           # never label rows the user didn't see
        if group["fallback"] or group["mixed"]:
            return ("Label these one at a time — the rows don't all look alike.",
                    dash.no_update, dash.no_update, bumped)
        rows = group["rows"]
    else:
        # A row is found by its id anywhere in the list, so it still works after
        # another click regrouped things
        row = next((r for g in groups for r in g["rows"] if r["row_id"] == trig.get("row")), None)
        if row is None:
            return stale
        rows, group = [row], group or {"merchant": row["description"]}
    expected = sum(r["count"] for r in rows)
    cat = trig["cat"]
    try:
        with MASTER_LOCK:
            master = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
            master, n = label_rows(master, rows, cat, sub)
            if n != expected:
                # Something relabeled or removed these rows since the list was
                # drawn — write nothing rather than a partial label
                return stale
            backup = backup_master(MASTER_PATH)
            atomic_write_csv(master, MASTER_PATH)
            rule, rule_note = None, ""
            if remember and trig["type"] == "lbl-group":
                chk = rule_check(df, read_rules(RULES_PATH), group)
                try:
                    if not chk["blocking"] and add_rule(RULES_PATH, chk["keyword"], cat, sub):
                        rule = chk["keyword"]
                except PermissionError:
                    rule_note = " · not remembered: rules.csv is open in another program"
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except PermissionError:
        return _LOCKED_MSG, dash.no_update, dash.no_update, dash.no_update
    # The master write happened, so Undo must be offered even if the rule failed
    undo = {"backup": str(backup), "master_mtime": _mtime(MASTER_PATH),
            "rules_mtime": _mtime(RULES_PATH), "rule": rule}
    status = (f"Labeled {n} {group['merchant']} row{'s' if n != 1 else ''} as {cat}"
              + (f' · rule "{rule}" added' if rule else "") + rule_note)
    return status, undo, _SHOWN_INLINE, bumped


def _do_undo(undo: dict, version):
    """Revert the last label action — only if nothing has written the master or
    rules.csv since (otherwise restoring would throw that newer change away)."""
    global df
    if not undo:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if (_mtime(MASTER_PATH) != str(undo["master_mtime"])
            or _mtime(RULES_PATH) != str(undo["rules_mtime"])):
        return "Can't undo — the data changed since.", None, _HIDDEN, dash.no_update
    try:
        with MASTER_LOCK:
            restore_backup(Path(undo["backup"]), MASTER_PATH)
            if undo.get("rule"):
                delete_rule(RULES_PATH, undo["rule"])
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except PermissionError:
        return ("⚠ The data or rules file is open in another program (Excel?) — close it and try again.",
                dash.no_update, dash.no_update, dash.no_update)
    return "Undone.", None, _HIDDEN, (version or 0) + 1


@app.callback(
    Output("label-status",   "children"),
    Output("label-undo",     "data"),
    Output("label-undo-btn", "style"),
    Output("label-version",  "data"),
    Input({"type": "lbl-group", "group": ALL, "sig": ALL, "cat": ALL}, "n_clicks"),
    Input({"type": "lbl-row", "group": ALL, "row": ALL, "cat": ALL}, "n_clicks"),
    State({"type": "lbl-sub", "group": ALL}, "value"),
    State({"type": "lbl-sub", "group": ALL}, "id"),
    State({"type": "lbl-remember", "group": ALL}, "value"),
    State({"type": "lbl-remember", "group": ALL}, "id"),
    State("label-version", "data"),
    State("label-filter",  "data"),
    prevent_initial_call=True,
)
def label_click(_g, _r, subs, sub_ids, rems, rem_ids, version, filt):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return (dash.no_update,) * 4
    trig = dict(ctx.triggered_id)
    key = trig["group"]
    sub = ({i["group"]: v for i, v in zip(sub_ids, subs)}.get(key) or "").strip()
    remember = bool({i["group"]: v for i, v in zip(rem_ids, rems)}.get(key))
    return _do_label(trig, sub, remember, version, filt)


@app.callback(
    Output("label-status",   "children", allow_duplicate=True),
    Output("label-undo",     "data",     allow_duplicate=True),
    Output("label-undo-btn", "style",    allow_duplicate=True),
    Output("label-version",  "data",     allow_duplicate=True),
    Input("label-undo-btn", "n_clicks"),
    State("label-undo",     "data"),
    State("label-version",  "data"),
    prevent_initial_call=True,
)
def undo_label(n_clicks, undo, version):
    if not n_clicks:
        return (dash.no_update,) * 4
    return _do_undo(undo, version)


@app.callback(
    Output("label-status",  "children", allow_duplicate=True),
    Output("label-version", "data",     allow_duplicate=True),
    Input({"type": "lbl-rule-del", "keyword": ALL}, "n_clicks"),
    State("label-version", "data"),
    prevent_initial_call=True,
)
def delete_rule_click(_clicks, version):
    global df
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return dash.no_update, dash.no_update
    keyword = ctx.triggered_id["keyword"]
    try:
        removed = delete_rule(RULES_PATH, keyword)
    except PermissionError:
        return "⚠ rules.csv is open in another program (Excel?) — close it and try again.", dash.no_update
    df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    return (f'Rule "{keyword}" deleted' if removed else "That rule was already gone"), (version or 0) + 1
```

Notes for the implementer:
- `add_rule` is looked up as a module global at call time, which is what lets `test_label_survives_rules_file_locked` patch it. Don't bind it to a local alias.
- `snapshot_master` is already called by `toggle_label_panel` (Task 5); this task only needs it imported if Task 5 didn't already import it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; pyflakes shows only the two existing warnings. `git status` shows the repo's `rules.csv` and `Test Data/` unchanged.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_label_panel.py
git commit -m "Labeling panel actions: label, remember, undo, delete rule"
```

---

### Task 7: Verify in the running app; docs

**Files:**
- Create: `docs/features/labeling-panel.md`
- Modify: `docs/decisions.md`, `docs/design.md`, `docs/features/overview-charts.md`, `docs/features/README.md`, `readme.md`
- No repo test file. The Playwright script lives in the scratchpad.

**Interfaces:**
- Consumes: everything above.
- Produces: docs and screenshots.

- [ ] **Step 1: Run the app on a temp copy of Test Data and drive it.** Copy `Test Data/` and `rules.csv` into the scratchpad and start the app with `FINANCE_DATA_DIR` and `FINANCE_RULES_PATH` pointing at the copies, so nothing in the repo is written. Afterwards, `git status` must show `rules.csv` and `Test Data/` unchanged. Use Playwright with `executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"` at 1440×900 to do the following, recording the browser console errors:
  1. load the page and wait 5 s;
  2. click `#open-label-panel`, then screenshot;
  3. expand `.label-guide`, then screenshot;
  4. click the EXPENSE button of the first `.label-group` that has group buttons; check that `#label-status` starts with `Labeled` and that the group count in `#label-summary` dropped by one;
  5. click `#label-undo-btn`; check that the status reads `Undone.`;
  6. expand the first `.lg-rows` and click one row's EXPENSE;
  7. click the `RULES` pill, then screenshot;
  8. click `#close-label-panel`; check that the panel is hidden;
  9. switch to the light theme, reopen the panel, then screenshot.

  Also check that a mixed or fallback group card shows no group buttons, only "Label these one at a time below" with its rows already expanded, and that `SORTED/backups/before-labeling.csv` exists in the temp copy after the panel was opened.

  Expected: no console errors and every check passes. Look at the screenshots: cards readable in both themes, MIXED badges and suggested-Transfer highlights visible, nothing overflowing.

- [ ] **Step 2: Docs.** The docs must match the code.
  - `docs/features/labeling-panel.md`:
    - purpose;
    - entry points (header button, last-import REVIEW);
    - the labeling guide (copy `LABEL_GUIDE`);
    - grouping (`merchant_key`; names starting with a number or containing a hyphen are kept; descriptions with no recognizable name become one-row *fallback* groups);
    - which groups get one-click group labels (not fallback, not mixed-direction) and why;
    - rule safety (the four conditions, and that mixed sign is the only non-blocking one);
    - writes (lock, backup, atomic, rule after master; only unlabeled rows are touched; a stale list or a count mismatch writes nothing);
    - the `before-labeling.csv` snapshot, outside the rotation, and how to restore it;
    - undo (both mtimes, stored as strings);
    - the Rules tab;
    - `last_import.csv` (written only when an import added rows);
    - `FINANCE_RULES_PATH`;
    - the top-25 limit;
    - frontmatter `resource: app.py, Modules/labels.py`.
  - `docs/decisions.md`: add an ADR, "Label in the app through the import matcher; remember only provably safe rules; show unreviewed money instead of counting it", with the why from the spec's Decisions table.
  - `docs/design.md`: add the label panel row (90) to the z-index table; component notes for `.label-group`, `.suggested` and `.lg-badge`.
  - `docs/features/overview-charts.md`: header bullets for the LABEL THEM button and the last-import line; the stat-card `+ $X unreviewed` line.
  - `docs/features/README.md`: add the labeling-panel row to the feature table.
  - `readme.md`: in the UI tour, one paragraph on the labeling panel, and the Import/export section says to label in the app first, with Excel for bulk edits.
  - `docs/superpowers/specs/2026-10-09-in-app-labeling-design.md`: replace the "Measured on the demo data" numbers with the ones measured at the Task 3 checkpoint.

- [ ] **Step 3: Full check**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; only the two existing warnings.

- [ ] **Step 4: Commit**

```bash
git add docs readme.md
git commit -m "Document the labeling panel"
```
