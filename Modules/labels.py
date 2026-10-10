"""
Applying an edited export (IMPORT CSV) back onto the master file.

The round-trip goes through Excel, which re-saves CSVs in its own way:
UTF-8 with a BOM or Windows-1252, dates as 3/15/2024, amounts as
-$1,234.50 or ($1,234.50), and card numbers without their leading zero.
Everything here tolerates that.
"""
import hashlib
import io
import re
from datetime import date
from pathlib import Path

import pandas as pd

from Modules.safety import atomic_write_csv
from Modules.transforms import PREDEFINED_CATEGORIES, normalize_description, read_rules_csv


def read_import_csv(raw: bytes) -> pd.DataFrame:
    """Decode an uploaded CSV; every column as text, blanks as ''."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    raise ValueError("the file isn't UTF-8 or Windows-1252 text")


def _amount(value) -> float | None:
    text = str(value).strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    try:
        number = float(text.strip("()"))
    except ValueError:
        return None
    return round(-number if negative else number, 2)


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", format="mixed").dt.normalize()


def _last4(value) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(4) if text.isdigit() else text


def apply_label_import(master: pd.DataFrame, imp: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Write master_category / sub_category from `imp` onto matching `master`
    rows. A row matches on description + amount + source, plus date when the
    file has a date column, plus card when the row names one.

    Returns (updated master, master rows updated, import rows skipped). An
    import row is skipped when its amount or date can't be read, or when it
    matches nothing — a row with a date column but a blank date is skipped
    rather than applied to every date. Rows with no labels are ignored.
    """
    master = master.copy()
    for col in ("master_category", "sub_category", "card_last4"):
        if col not in master.columns:
            master[col] = ""
        master[col] = master[col].fillna("").astype(str)

    m_desc  = master["description"].astype(str).str.strip()
    m_amt   = pd.to_numeric(master["amount"], errors="coerce").round(2)
    m_src   = master["source"].astype(str)
    m_date  = _dates(master["date"])
    m_last4 = master["card_last4"].map(_last4)

    has_date, has_sub, has_card = ("date" in imp.columns, "sub_category" in imp.columns,
                                   "card_last4" in imp.columns)
    updated = skipped = 0
    for _, row in imp.iterrows():
        cat = str(row.get("master_category", "")).strip()
        sub = str(row.get("sub_category", "")).strip() if has_sub else ""
        if not cat and not sub:
            continue
        amount = _amount(row["amount"])
        if amount is None:
            skipped += 1
            continue
        mask = (m_desc == str(row["description"]).strip()) & (m_amt == amount) & (m_src == str(row["source"]))
        if has_date:
            day = _dates(pd.Series([row["date"]])).iat[0]
            if pd.isna(day):
                skipped += 1
                continue
            mask &= m_date == day
        if has_card and _last4(row["card_last4"]):
            mask &= m_last4 == _last4(row["card_last4"])
        n = int(mask.sum())
        if n == 0:
            skipped += 1
            continue
        if cat:
            master.loc[mask, "master_category"] = cat
        if sub:
            master.loc[mask, "sub_category"] = sub
        updated += n
    return master, updated, skipped


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


_ID_COLUMNS = ["date", "description", "amount", "source", "card_last4"]


def row_ids(df: pd.DataFrame) -> pd.Series:
    # Only the identity columns: to_dict over the full-width frame is the
    # slow part, and the panel calls this on every click
    narrow = df[[c for c in _ID_COLUMNS if c in df.columns]]
    return pd.Series([row_id(r) for r in narrow.to_dict("records")], index=df.index, dtype=str)


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
    # One pass over plain records (narrow columns only): a DataFrame groupby
    # with to_dict per group cost ~1 s on 1.3k rows, paid twice per click
    cols = ["_mk", "_fb", "_rid", "date", "description", "amount", "source", "card_last4"]
    recs = un[[c for c in cols if c in un.columns]].to_dict("records")
    by_key: dict[str, list[dict]] = {}
    for r in recs:                                  # first-appearance order
        by_key.setdefault(r["_mk"], []).append(r)
    groups = []
    for mk, g in by_key.items():
        amounts = [float(r["amount"]) for r in g]
        dates = [r["date"] for r in g]
        rows: dict[str, dict] = {}
        # Identical twins share a row_id and are labeled together: one entry
        for r in sorted(g, key=lambda r: r["date"]):    # stable, like the old sort
            if r["_rid"] in rows:
                rows[r["_rid"]]["count"] += 1
            else:
                rows[r["_rid"]] = {"row_id": r["_rid"], "date": r["date"],
                                   "description": r["description"], "amount": float(r["amount"]),
                                   "source": r["source"], "card_last4": r.get("card_last4", "") or "",
                                   "count": 1}
        sig_src = "|".join(sorted(f"{k}x{v['count']}" for k, v in rows.items()))
        fallback = any(r["_fb"] for r in g)
        groups.append({
            "key": hashlib.sha1(mk.encode()).hexdigest()[:10],
            "mkey": mk,
            "merchant": (str(g[0]["description"]).strip() if fallback else mk).upper(),
            "count": len(g),
            "total": float(sum(amounts)),
            "abs_total": float(sum(abs(a) for a in amounts)),
            "first": min(dates),
            "last": max(dates),
            "example": str(g[0]["description"]).strip(),
            "mixed": any(a > 0 for a in amounts) and any(a < 0 for a in amounts),
            "fallback": fallback,
            "sig": hashlib.sha1(sig_src.encode()).hexdigest()[:10],
            "suggest_transfer": any(looks_like_transfer(r["description"]) for r in g),
            "rows": list(rows.values()),
        })
    return sorted(groups, key=lambda x: x["abs_total"], reverse=True)


# ── Transfer pairs ────────────────────────────────────────────────────────────

# Card payments and own-account moves post on both sides within a few days
# (weekends and holidays included); longer gaps start pairing coincidences
TRANSFER_PAIR_DAYS = 5


def _certain_pairs(df: pd.DataFrame, max_days: int) -> list[dict]:
    """
    Likely transfers between your own accounts: one row out and one row in of
    exactly the same amount, on different accounts (source + card), within
    max_days of each other — e.g. "Payment to Chase card ending in 3094" on
    checking and "AUTOMATIC PAYMENT - THANK" on that card.

    Only certain matches are returned: if either row has more than one
    candidate (two equal payments, identical twins) the pair is a guess and is
    skipped. Each dict: key, out, in (row dicts like unlabeled_groups', plus
    their current label), amount, gap (days). Biggest first.
    """
    if df.empty:
        return []
    d = df[_ID_COLUMNS + ["master_category"]].copy()
    d["card_last4"] = d["card_last4"].fillna("").astype(str)
    # Anything that isn't a valid label counts as unlabeled, as everywhere else
    d["master_category"] = d["master_category"].where(d["master_category"].isin(PREDEFINED_CATEGORIES), "")
    d["_acct"] = d["source"].astype(str) + "|" + d["card_last4"]
    d["_cents"] = (d["amount"].astype(float) * 100).round().astype("int64")
    d["_pos"] = range(len(d))
    out = d[d["_cents"] < 0].assign(_key=lambda x: -x["_cents"])
    inn = d[d["_cents"] > 0].assign(_key=lambda x: x["_cents"])
    m = out.merge(inn, on="_key", suffixes=("_o", "_i"))
    m = m[(m["_acct_o"] != m["_acct_i"])
          & ((m["date_i"] - m["date_o"]).abs() <= pd.Timedelta(days=max_days))]
    if m.empty:
        return []
    # Ambiguity counts every candidate, labeled or not: a pairing that might
    # belong to another row is not certain
    unique = (m.groupby("_pos_o")["_pos_i"].transform("size").eq(1)
              & m.groupby("_pos_i")["_pos_o"].transform("size").eq(1))
    m = m[unique]   # identical twins land here too: each gives the other side two candidates

    def _side(r, sfx) -> dict:
        # row ids only for the few rows that pair, not the whole frame
        rid = row_id({c: r[f"{c}{sfx}"] for c in _ID_COLUMNS})
        return {"row_id": rid, "date": r[f"date{sfx}"],
                "description": r[f"description{sfx}"], "amount": float(r[f"amount{sfx}"]),
                "source": r[f"source{sfx}"], "card_last4": r[f"card_last4{sfx}"],
                "count": 1, "label": r[f"master_category{sfx}"]}

    pairs = []
    for r in m.to_dict("records"):
        sides = [_side(r, "_o"), _side(r, "_i")]
        pairs.append({
            "key": hashlib.sha1((sides[0]["row_id"] + sides[1]["row_id"]).encode()).hexdigest()[:10],
            "out": sides[0], "in": sides[1],
            "amount": abs(sides[0]["amount"]),
            "gap": int(abs((sides[1]["date"] - sides[0]["date"]).days)),
        })
    return sorted(pairs, key=lambda p: (p["amount"], p["out"]["date"]), reverse=True)


def transfer_pairs(df: pd.DataFrame, max_days: int = TRANSFER_PAIR_DAYS,
                   _certain: list[dict] | None = None) -> list[dict]:
    """Certain pairs (see _certain_pairs) with something to label: no side
    labeled Expense or Income (that's suspect_transfers' list), not Transfer on
    both sides already. Adds to_label: the sides without a valid label."""
    out = []
    for p in (_certain if _certain is not None else _certain_pairs(df, max_days)):
        labels = {p["out"]["label"], p["in"]["label"]}
        if labels & {"Expense", "Income"} or labels == {"Transfer"}:
            continue
        out.append({**p, "to_label": [s for s in (p["out"], p["in"]) if not s["label"]]})
    return out


def pair_lists(df: pd.DataFrame, max_days: int = TRANSFER_PAIR_DAYS) -> tuple[list[dict], list[dict]]:
    """(transfer_pairs, suspect_transfers) from a single matching pass."""
    certain = _certain_pairs(df, max_days)
    return transfer_pairs(df, max_days, certain), suspect_transfers(df, max_days, certain)


def suspect_transfers(df: pd.DataFrame, max_days: int = TRANSFER_PAIR_DAYS,
                      _certain: list[dict] | None = None) -> list[dict]:
    """
    Certain pairs with a side labeled Expense or Income — most likely a card
    payment or a move between your own accounts that is being counted as
    spending or income (a card payment labeled Expense counts every purchase
    on that card twice). Adds to_fix (every side not already Transfer) and
    counted (the dollars those sides put into totals).
    """
    out = []
    for p in (_certain if _certain is not None else _certain_pairs(df, max_days)):
        if not {p["out"]["label"], p["in"]["label"]} & {"Expense", "Income"}:
            continue
        fix = [s for s in (p["out"], p["in"]) if s["label"] != "Transfer"]
        counted = sum(abs(s["amount"]) for s in fix if s["label"] in ("Expense", "Income"))
        out.append({**p, "to_fix": fix, "counted": counted})
    return out


# ── Rules: safety check and rules.csv I/O ─────────────────────────────────────

RULE_COLUMNS = ["keyword", "master_category", "sub_category", "added"]
MIN_KEYWORD  = 4


def read_rules(path) -> pd.DataFrame:
    """rules.csv as text columns, RULE_COLUMNS always present. Tolerates what
    Excel saves (BOM, Windows-1252) and an empty file (see read_rules_csv)."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=RULE_COLUMNS)
    rules = read_rules_csv(path)
    if rules.columns.empty:                         # zero-byte / headerless file
        return pd.DataFrame(columns=RULE_COLUMNS)
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


# ── Writing labels; the last import's rows ────────────────────────────────────

LAST_IMPORT_NAME = "last_import.csv"


def label_rows(master: pd.DataFrame, rows: list[dict], category: str, sub: str = "",
               relabel_from: set[str] | None = None) -> tuple[pd.DataFrame, int]:
    """Label exactly these rows in the master, through the same matcher Excel
    imports use (date + description + amount + source + card), touching only
    rows that have no valid label yet — plus, for an explicit fix the user
    clicked, rows currently labeled one of relabel_from (the label they saw, so
    a label changed on disk since is never overwritten). Twin rows are sent
    once so the count isn't doubled. Returns (master, rows labeled); the caller
    checks the count against what it expected and writes nothing on a mismatch."""
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
    current = master["master_category"].fillna("").astype(str).str.strip()
    open_ = ~current.isin(PREDEFINED_CATEGORIES)
    if relabel_from:
        open_ |= current.isin(relabel_from)
    part, updated, _ = apply_label_import(master[open_], imp)
    for col in ("master_category", "sub_category"):
        master[col] = master[col].fillna("").astype(str)
        master.loc[part.index, col] = part[col]
    return master, updated


NOT_TRANSFERS_NAME = "not_transfers.csv"


def _read_not_transfers(p: Path) -> set[str]:
    if not p.exists():
        return set()
    return set(pd.read_csv(p, dtype=str, keep_default_na=False)["pair"])


def not_transfer_keys(master_path) -> set[str]:
    """Pair keys the user marked "not a transfer" — never flagged again."""
    try:
        return _read_not_transfers(Path(master_path).parent / NOT_TRANSFERS_NAME)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, KeyError, OSError, ValueError):
        return set()


def add_not_transfer(master_path, key: str) -> None:
    """Remember one more dismissed pair. An existing file that can't be read
    (hand-edited, saved by Excel) raises instead of being replaced by just
    this key, which would silently bring back every earlier dismissal."""
    keys = _read_not_transfers(Path(master_path).parent / NOT_TRANSFERS_NAME) | {key}
    atomic_write_csv(pd.DataFrame({"pair": sorted(keys)}),
                     Path(master_path).parent / NOT_TRANSFERS_NAME)


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
