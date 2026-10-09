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
from Modules.transforms import PREDEFINED_CATEGORIES, normalize_description


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
