"""
Replacement cards: one account, two card numbers.

A replaced card (new number after a loss, fraud or expiry) keeps its account,
and the bank's export for the new number repeats the old number's charges for
the dates both cover. The import keys accounts by the card number in the file
name, so each number would be its own account and those charges counted twice.

The import links two numbers when their overlapping charges are the same
(detection proposes) and records the link in SORTED/linked_cards.csv (the file
decides, so a later import can't quietly undo it). From then on the newer
number's rows are filed under the older number and the two merge like any
re-export of one account. Changing a line's status to "different" unlinks two
numbers, and keeps them from being linked again.
"""
from pathlib import Path

import pandas as pd

from Modules.safety import atomic_write_csv

LINKS_NAME = "linked_cards.csv"
LINK_COLUMNS = ["source", "old_card", "new_card", "status", "matched", "linked_on"]

# A replacement repeats every charge of the overlap (116 of 116 on real data);
# two different cards share only the odd coincidence (3 of 342). Under
# MIN_ROWS there's too little to tell, and little to count twice.
MIN_ROWS = 10
MIN_SHARE = 0.95


def links_path(master: Path) -> Path:
    return Path(master).parent / LINKS_NAME


def read_links(master: Path) -> pd.DataFrame | None:
    """The recorded links (empty when none). None when the file exists but
    can't be read: the import then neither links nor rewrites it, so a
    hand-edit gone wrong never loses the user's "different" lines."""
    p = links_path(master)
    if not p.exists():
        return pd.DataFrame(columns=LINK_COLUMNS)
    try:
        d = pd.read_csv(p, dtype=str, keep_default_na=False)
        if not {"source", "old_card", "new_card", "status"} <= set(d.columns):
            raise ValueError("missing columns")
        for c in LINK_COLUMNS:
            if c not in d.columns:
                d[c] = ""
        for c in ("source", "old_card", "new_card", "status"):
            d[c] = d[c].str.strip()
        d["status"] = d["status"].str.lower()
        return d[LINK_COLUMNS]
    except Exception as e:
        print(f"  ⚠ Could not read {p} ({e}) — replacement cards aren't linked this run")
        return None


def write_links(master: Path, links: pd.DataFrame) -> None:
    p = links_path(master)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(links[LINK_COLUMNS], p)
    except OSError as e:
        print(f"  ⚠ Could not update {p} ({e})")


def overlap_match(da: pd.DataFrame, db: pd.DataFrame) -> dict | None:
    """Charges on both of two accounts (same date, amount and description)
    over the dates both cover; None when their dates don't overlap."""
    lo = max(da["date"].min(), db["date"].min())
    hi = min(da["date"].max(), db["date"].max())
    if pd.isna(lo) or pd.isna(hi) or lo > hi:
        return None

    def counts(d):
        w = d[d["date"].between(lo, hi)]
        return w.groupby([w["date"], w["amount"].round(2), w["description"].astype(str).str.strip()]).size()

    ca, cb = counts(da), counts(db)
    both = pd.concat([ca, cb], axis=1, join="inner").min(axis=1)
    amounts = pd.Series(both.index.get_level_values(1), index=both.index)
    return {"from": lo, "to": hi, "rows_a": int(ca.sum()), "rows_b": int(cb.sum()),
            "same": int(both.sum()), "out": float((-amounts[amounts < 0] * both[amounts < 0]).sum())}


def is_replacement(m: dict | None) -> bool:
    return (m is not None and min(m["rows_a"], m["rows_b"]) >= MIN_ROWS
            and m["same"] >= MIN_SHARE * max(m["rows_a"], m["rows_b"]))


def _recorded(links: pd.DataFrame, source: str, a: str, b: str) -> pd.Series | None:
    hit = links[(links["source"] == source)
                & (((links["old_card"] == a) & (links["new_card"] == b))
                   | ((links["old_card"] == b) & (links["new_card"] == a)))]
    return None if hit.empty else hit.iloc[-1]


def find_replacements(accounts: dict[tuple, pd.DataFrame], links: pd.DataFrame,
                      today=None) -> list[dict]:
    """Card pairs to link that linked_cards.csv doesn't mention yet: two
    numbers of one institution and source whose overlapping charges are the
    same. Old = the number whose data starts first. Each dict is a links
    row, plus the match itself under "match"."""
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today())
    keys = sorted(k for k in accounts if k[2])
    found = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if a[:2] != b[:2] or a[2] == b[2] or _recorded(links, a[1], a[2], b[2]) is not None:
                continue
            m = overlap_match(accounts[a], accounts[b])
            if not is_replacement(m):
                continue
            old, new = sorted((a, b), key=lambda k: (accounts[k]["date"].min(), k[2]))
            found.append({"source": a[1], "old_card": old[2], "new_card": new[2], "status": "same",
                          "matched": f"{m['same']}/{max(m['rows_a'], m['rows_b'])}",
                          "linked_on": f"{today:%Y-%m-%d}", "match": m})
    return found


def card_map(links: pd.DataFrame | None) -> dict[tuple[str, str], str]:
    """{(source, card): the card it's filed under} for every linked number,
    the oldest number included (mapped to itself). Chains (A→B→C) resolve
    to A."""
    if links is None or links.empty:
        return {}
    parent = {}
    for r in links[links["status"] == "same"].itertuples():
        if r.old_card and r.new_card and r.old_card != r.new_card:
            parent[(r.source, r.new_card)] = r.old_card
    out = {}
    for (source, card) in parent:
        root, seen = card, set()
        while (source, root) in parent and root not in seen:
            seen.add(root)
            root = parent[(source, root)]
        out[(source, card)] = root
        out[(source, root)] = root
    return out


def recent_links(master: Path, today=None, days: int = 14) -> list[str]:
    """Plain-words notes for links the import made in the last `days` days,
    so a change to past totals is explained where the user looks."""
    links = read_links(master)
    if links is None or links.empty:
        return []
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today()).normalize()
    made = pd.to_datetime(links["linked_on"], errors="coerce")
    fresh = links[(links["status"] == "same") & made.notna() & ((today - made).dt.days <= days)]
    return [f"{r.source} {r.new_card} is a new number for {r.old_card} — charges on both now count once"
            for r in fresh.itertuples()]
