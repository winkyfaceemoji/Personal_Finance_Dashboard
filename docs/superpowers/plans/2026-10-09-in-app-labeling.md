# In-App Labeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user label unlabeled transactions inside the dashboard, one click per merchant, with rules created only when provably safe, so totals become complete and stay complete week to week.

**Architecture:** Pure, tested functions in `Modules/labels.py` do the work: grouping, rule safety, rule-file I/O, and labeling through the existing `apply_label_import` matcher. `Modules/transforms.py` gains one shared description normalizer used by grouping and by rule matching. `main.py` records which rows the last import added. `app.py` adds a full-screen labeling panel (pattern-matching callbacks), header entry points, and an "unreviewed" line on the stat cards. Every master write reuses `Modules/safety.py`: lock, backup, then atomic write.

**Tech Stack:** Python 3.12+, pandas 3.0.2, Dash 4.1.0 (`dash.html`, `dcc`, pattern-matching `ALL` ids), pytest 8.4.2, Playwright (verification only, not a dependency).

**Spec:** `docs/superpowers/specs/2026-10-09-in-app-labeling-design.md`

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

1. **Twin rows** (two identical same-day purchases) produce duplicate component ids in the expanded row list, and Dash rejects duplicate ids. Row button ids must carry a position `n`. Pinned in Task 5: `test_group_card_row_ids_unique`.
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
  - `labels.unlabeled_groups(df, only_row_ids=None) -> list[dict]`. Each group dict has the keys `key, mkey, merchant, count, total, abs_total, first, last, example, mixed, suggest_transfer, rows`. Each row dict has `row_id, date, description, amount, source, card_last4`.

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
    assert merchant_key("   ") == "unknown"
    assert merchant_key("#1234") == "unknown"


def test_rule_keyword_is_common_prefix_and_substring():
    descs = ["STARBUCKS STORE 01234 SEATTLE", "STARBUCKS STORE 09876 NY"]
    kw = rule_keyword(descs)
    assert kw == "starbucks store"
    assert all(kw in normalize_description(d) for d in descs)
    assert rule_keyword(["PAYPAL *NETFLIX 1", "PAYPAL *NETFLIX 2"]) == "paypal netflix"
    assert rule_keyword(["AMAZON MKTP US", "AMAZON.COM"]) == ""
    assert rule_keyword([]) == ""


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
    assert sb["key"] == unlabeled_groups(df)[2]["key"]          # stable
    only = unlabeled_groups(df, only_row_ids=[sb["rows"][0]["row_id"]])
    assert len(only) == 1 and only[0]["count"] == 1
    assert unlabeled_groups(df.iloc[3:5]) == []


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
_CODE     = re.compile(r"\b[a-z]{2,4}-\S+")
_TRANSFER = re.compile(r"payment thank|autopay|online transfer|transfer to|transfer from"
                       r"|epay|card payment|directpay|internet payment")


def merchant_key(description) -> str:
    """Who a transaction is with, stripped of store numbers, reference ids and
    ACH codes, so one merchant's rows group together: 'STARBUCKS STORE 01234
    SEATTLE' and '… 09876 NEW YORK' are both 'starbucks store'."""
    s = normalize_description(description)
    s = _ID_TAIL.split(s, maxsplit=1)[0]
    s = re.split(r"\d", s, maxsplit=1)[0]
    s = _CODE.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" -.,/") or "unknown"


def rule_keyword(descriptions) -> str:
    """The rule keyword for a group: the longest word-aligned prefix all its
    descriptions share (normalized), cut before any digit. Always a real
    substring of every description, so the rule matches the whole group."""
    split = [normalize_description(d).split(" ") for d in descriptions]
    common = []
    for words in zip(*split):
        if any(w != words[0] for w in words):
            break
        common.append(words[0])
    return re.split(r"\d", " ".join(common), maxsplit=1)[0].strip(" -.,/")


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
    groups = []
    for mk, g in un.groupby("_mk", sort=False):
        amounts = g["amount"]
        groups.append({
            "key": hashlib.sha1(mk.encode()).hexdigest()[:10],
            "mkey": mk,
            "merchant": mk.upper(),
            "count": int(len(g)),
            "total": float(amounts.sum()),
            "abs_total": float(amounts.abs().sum()),
            "first": g["date"].min(),
            "last": g["date"].max(),
            "example": str(g["description"].iloc[0]).strip(),
            "mixed": bool((amounts > 0).any() and (amounts < 0).any()),
            "suggest_transfer": bool(g["description"].map(looks_like_transfer).any()),
            "rows": [{"row_id": r["_rid"], "date": r["date"], "description": r["description"],
                      "amount": float(r["amount"]), "source": r["source"],
                      "card_last4": r.get("card_last4", "") or ""}
                     for r in g.sort_values("date", kind="stable").to_dict("records")],
        })
    return sorted(groups, key=lambda x: x["abs_total"], reverse=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider`
Expected: every test passes (`tests/test_grouping.py` adds 11; the 49 existing still pass).

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
  - `rule_check(df, rules, group, norm=None) -> dict`, with keys `ok, keyword, reason, blocking, rows_now, dollars_now, others`

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
    out = {"ok": False, "keyword": kw, "reason": None, "blocking": True,
           "rows_now": 0, "dollars_now": 0.0, "others": []}
    if len(kw) < MIN_KEYWORD:
        out["reason"] = "no keyword long enough to be safe"
        return out
    norm = df["description"].map(normalize_description) if norm is None else norm
    hits = norm.str.contains(kw, regex=False)
    others = sorted(set(df.loc[hits, "description"].map(merchant_key)) - {group["mkey"]})
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
  - `label_rows(master, rows, category, sub="") -> tuple[pd.DataFrame, int]`
  - `LAST_IMPORT_NAME = "last_import.csv"`
  - `last_import_ids(master_path) -> list[str] | None`
  - `safety.restore_backup(backup, master) -> None`
  - `SORTED/last_import.csv`, a single `row_id` column

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
```

Append to `Modules/labels.py`:

```python
# ── Writing labels; the last import's rows ────────────────────────────────────

LAST_IMPORT_NAME = "last_import.csv"


def label_rows(master: pd.DataFrame, rows: list[dict], category: str, sub: str = "") -> tuple[pd.DataFrame, int]:
    """Label exactly these rows in the master, through the same matcher Excel
    imports use (date + description + amount + source + card). Twin rows are
    sent once so the count isn't doubled. Returns (master, rows labeled)."""
    imp = pd.DataFrame([{
        "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
        "description": str(r["description"]),
        "amount": f"{float(r['amount']):.2f}",
        "source": str(r["source"]),
        "card_last4": str(r.get("card_last4", "") or ""),
        "master_category": category,
        "sub_category": sub or "",
    } for r in rows]).drop_duplicates()
    master, updated, _ = apply_label_import(master, imp)
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

In `main.py`, add `from Modules.labels import LAST_IMPORT_NAME, row_id` to the imports. In `rebuild_master`:

1. Next to `orphans = None`, add `new_ids = None   # rows this import added; set only when a prior master existed`.
2. In pass 2, track rescued rows. Change
   ```python
               if bucket:
                   _take(idx, bucket.popleft())
                   result["rescued"] += 1
   ```
   to
   ```python
               if bucket:
                   _take(idx, bucket.popleft())
                   rescued.add(idx)
                   result["rescued"] += 1
   ```
   and initialise `rescued = set()` on the line before `rest = combined[...]`.
3. Directly after `result["orphaned"] = len(orphans)`, add:
   ```python
           # What this import added: rows neither carried nor rescued from the
           # old master. Computed before the sort below renumbers the index.
           fresh = combined.index.difference(list(matched | rescued))
           new_ids = [row_id(r) for r in combined.loc[fresh].to_dict("records")]
   ```
4. After the orphan block, and before `return result`:
   ```python
       # Record the import's new rows for the dashboard's "N new · K need you"
       # line. Skipped on the very first import, when every row is new.
       if new_ids is not None:
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

### Task 4: Header entry points, unreviewed line, drilldown grouping

**Files:**
- Modify: `app.py`: imports; the header layout (`unlabeled-note` area); `update_unlabeled_note`; a new `update_last_import_note`; `update_stats`; the drilldown's `_merchant`; and a new `_HIDDEN` / `_SHOWN_INLINE` style pair near `_MENU_HIDDEN`
- Modify: `assets/app.css` (the `.notice-row` and `.unreviewed` rules)
- Test: `tests/test_label_panel.py` (header and stat-card helpers)

**Interfaces:**
- Consumes: from Tasks 1 and 3, `unlabeled_groups`, `row_ids`, `last_import_ids` and `merchant_key`.
- Produces:
  - layout ids `open-label-panel`, `last-import-note` and `open-label-review`
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
    old = os.environ.get("FINANCE_DATA_DIR")
    os.environ["FINANCE_DATA_DIR"] = str(data)
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_app")
    finally:
        if old is None:
            os.environ.pop("FINANCE_DATA_DIR", None)
        else:
            os.environ["FINANCE_DATA_DIR"] = old


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

Imports in `app.py`: add `ALL` to `from dash import …`. Extend the labels import to `from Modules.labels import apply_label_import, read_import_csv, merchant_key, row_ids, last_import_ids` (later tasks add more names). Add `PREDEFINED_CATEGORIES` to the `Modules.transforms` import.

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

Drilldown: delete the inner `_merchant` function and its comment, and change `txns["description"].map(_merchant)` to `txns["description"].map(lambda d: merchant_key(d).upper())`. Merchant grouping is now shared with the labeling panel.

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
git commit -m "Header entry points, unreviewed totals, shared merchant grouping"
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
    - `{"type": "lbl-group", "group", "cat"}`
    - `{"type": "lbl-row", "group", "n", "cat"}`
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

Extend the `Modules.labels` import with `unlabeled_groups, rule_check, read_rules`, and add `normalize_description` to the transforms import.

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

    def _btn(cat, n=None):
        id_ = ({"type": "lbl-group", "group": key, "cat": cat} if n is None
               else {"type": "lbl-row", "group": key, "n": n, "cat": cat})
        cls = "btn-secondary btn-small"
        if cat == "Transfer" and g["suggest_transfer"]:
            cls += " suggested"
        return html.Button(cat.upper(), id=id_, n_clicks=0, className=cls,
                           title="Suggested: looks like a card payment or transfer"
                           if "suggested" in cls else None)

    if chk["ok"]:
        note = (f'rule "{chk["keyword"]}" · labels {chk["rows_now"]} row'
                f'{"s" if chk["rows_now"] != 1 else ""} ({_dollar0(chk["dollars_now"])}) now')
    else:
        note = chk["reason"]

    rows = [html.Div(className="lg-row", children=[
                html.Span(f"{pd.Timestamp(r['date']):%b} {pd.Timestamp(r['date']).day}", className="lg-date"),
                html.Span(r["description"], className="lg-desc", title=r["description"]),
                html.Span(_dollar(r["amount"]), className="lg-amt"),
                html.Div(className="lg-buttons", children=[_btn(c, i) for c in PREDEFINED_CATEGORIES]),
            ]) for i, r in enumerate(g["rows"])]

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
            html.Div(className="lg-buttons", children=[_btn(c) for c in PREDEFINED_CATEGORIES]),
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
        html.Details(className="lg-rows", children=[
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
- Consumes: from Tasks 1–5, `label_rows`, `rule_check`, `add_rule`, `delete_rule`, `read_rules`, `restore_backup`, `backup_master`, `atomic_write_csv`, `MASTER_LOCK` and the ids from Task 5.
- Produces: `_is_real_click`, `_do_label`, `_do_undo`, and the callbacks. `label-undo` data is `{"backup": str, "master_mtime": int, "rules_mtime": int, "rule": str | None}`.

- [ ] **Step 1: Write the failing tests** (append)

```python
def _live(appmod):
    """The app module's live globals (runpy returns a copy; callbacks rebind df)."""
    return appmod["_do_label"].__globals__


def test_label_click_ignores_rerender(appmod):
    real = appmod["_is_real_click"]
    assert not real([])
    assert not real([{"prop_id": '{"cat":"Expense","group":"x","type":"lbl-group"}.n_clicks', "value": 0}])
    assert not real([{"prop_id": '{"cat":"Expense","group":"x","type":"lbl-group"}.n_clicks', "value": None}])
    assert real([{"prop_id": '{"cat":"Expense","group":"x","type":"lbl-group"}.n_clicks', "value": 1}])


def test_label_then_undo_roundtrip(appmod):
    from Modules.labels import unlabeled_groups
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = unlabeled_groups(g_["df"])[0]
    status, undo, _, version = g_["_do_label"](
        {"type": "lbl-group", "group": grp["key"], "cat": "Expense"}, "", False, 0, "all")
    assert status.startswith("Labeled") and undo and version == 1
    assert master.read_bytes() != before
    status2, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status2 == "Undone." and undo2 is None
    assert master.read_bytes() == before


def test_undo_refuses_after_change(appmod):
    from Modules.labels import unlabeled_groups
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    grp = unlabeled_groups(g_["df"])[0]
    _, undo, _, _ = g_["_do_label"](
        {"type": "lbl-group", "group": grp["key"], "cat": "Expense"}, "", False, 0, "all")
    changed = master.read_bytes() + b"\n"
    master.write_bytes(changed)                  # something else wrote the master
    status, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert master.read_bytes() == changed
```

The callback bodies live in plain functions so the tests can call them without a running Dash server:
- `_is_real_click(triggered)`: is this a real click, or a re-render?
- `_do_label(trig, sub, remember, version, filt)`
- `_do_undo(undo, version)`

The callbacks themselves only read `ctx` and the ALL-states, then delegate.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_label_panel.py -v -p no:cacheprovider`
Expected: FAIL, `KeyError: 'label_click'`.

- [ ] **Step 3: Implement**

Extend the imports to `from Modules.labels import (…, label_rows, add_rule, delete_rule)` and `from Modules.safety import MASTER_LOCK, atomic_write_csv, backup_master, orphan_count, restore_backup`.

```python
def _is_real_click(triggered) -> bool:
    """Re-rendering the list adds buttons with n_clicks=0 (or None), which fires
    pattern-matching callbacks too — only a real click may write anything."""
    return bool(triggered) and bool(triggered[0].get("value"))


def _mtime(path) -> int:
    return path.stat().st_mtime_ns if path and Path(path).exists() else 0


def _do_label(trig: dict, sub: str, remember: bool, version, filt):
    """Label a group (or one row of it): master write under the lock with a
    backup first, then — only if that succeeded — the rule. Returns
    (status, undo, undo-button style, version)."""
    global df
    only = last_import_ids(MASTER_PATH) if filt == "last" else None
    group = next((g for g in unlabeled_groups(df, only_row_ids=only) if g["key"] == trig["group"]), None)
    if group is None:
        return "Nothing to label — the list was out of date.", dash.no_update, dash.no_update, (version or 0) + 1
    rows = group["rows"] if trig["type"] == "lbl-group" else [group["rows"][trig["n"]]]
    cat = trig["cat"]
    try:
        with MASTER_LOCK:
            master = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
            master, n = label_rows(master, rows, cat, sub)
            if n == 0:
                return "Nothing to label — the list was out of date.", dash.no_update, dash.no_update, (version or 0) + 1
            backup = backup_master(MASTER_PATH)
            atomic_write_csv(master, MASTER_PATH)
            rule = None
            if remember and trig["type"] == "lbl-group":
                chk = rule_check(df, read_rules(RULES_PATH), group)
                if not chk["blocking"] and add_rule(RULES_PATH, chk["keyword"], cat, sub):
                    rule = chk["keyword"]
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except PermissionError:
        return ("⚠ The data or rules file is open in another program (Excel?) — close it and try again.",
                dash.no_update, dash.no_update, dash.no_update)
    undo = {"backup": str(backup), "master_mtime": _mtime(MASTER_PATH),
            "rules_mtime": _mtime(RULES_PATH), "rule": rule}
    status = (f"Labeled {n} {group['merchant']} row{'s' if n != 1 else ''} as {cat}"
              + (f' · rule "{rule}" added' if rule else ""))
    return status, undo, _SHOWN_INLINE, (version or 0) + 1


def _do_undo(undo: dict, version):
    """Revert the last label action — only if nothing has written the master or
    rules.csv since (otherwise restoring would throw that newer change away)."""
    global df
    if not undo:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if _mtime(MASTER_PATH) != undo["master_mtime"] or _mtime(RULES_PATH) != undo["rules_mtime"]:
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
    Input({"type": "lbl-group", "group": ALL, "cat": ALL}, "n_clicks"),
    Input({"type": "lbl-row", "group": ALL, "n": ALL, "cat": ALL}, "n_clicks"),
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; pyflakes shows only the two existing warnings.

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

- [ ] **Step 1: Run the app on a temp copy of Test Data and drive it.** Use Playwright with `executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"` at 1440×900 to do the following, recording the browser console errors:
  1. load the page and wait 5 s;
  2. click `#open-label-panel`, then screenshot;
  3. expand `.label-guide`, then screenshot;
  4. click the first `.label-group` EXPENSE button; check that `#label-status` starts with `Labeled` and that the group count in `#label-summary` dropped by one;
  5. click `#label-undo-btn`; check that the status reads `Undone.`;
  6. expand the first `.lg-rows` and click one row's EXPENSE;
  7. click the `RULES` pill, then screenshot;
  8. click `#close-label-panel`; check that the panel is hidden;
  9. switch to the light theme, reopen the panel, then screenshot.

  Expected: no console errors and every check passes. Look at the screenshots: cards readable in both themes, MIXED badges and suggested-Transfer highlights visible, nothing overflowing.

- [ ] **Step 2: Docs.** The docs must match the code.
  - `docs/features/labeling-panel.md`:
    - purpose;
    - entry points (header button, last-import REVIEW);
    - the labeling guide (copy `LABEL_GUIDE`);
    - grouping (`merchant_key`);
    - rule safety (the four conditions, and that mixed sign is the only non-blocking one);
    - writes (lock, backup, atomic, rule after master);
    - undo (both mtimes);
    - the Rules tab;
    - `last_import.csv`;
    - the top-25 limit;
    - frontmatter `resource: app.py, Modules/labels.py`.
  - `docs/decisions.md`: add an ADR, "Label in the app through the import matcher; remember only provably safe rules; show unreviewed money instead of counting it", with the why from the spec's Decisions table.
  - `docs/design.md`: add the label panel row (90) to the z-index table; component notes for `.label-group`, `.suggested` and `.lg-badge`.
  - `docs/features/overview-charts.md`: header bullets for the LABEL THEM button and the last-import line; the stat-card `+ $X unreviewed` line.
  - `docs/features/README.md`: add the labeling-panel row to the feature table.
  - `readme.md`: in the UI tour, one paragraph on the labeling panel, and the Import/export section says to label in the app first, with Excel for bulk edits.

- [ ] **Step 3: Full check**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m pyflakes app.py main.py Modules tests`
Expected: all pass; only the two existing warnings.

- [ ] **Step 4: Commit**

```bash
git add docs readme.md
git commit -m "Document the labeling panel"
```
