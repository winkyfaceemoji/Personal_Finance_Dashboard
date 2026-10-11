"""
Replacement cards: one account, two card numbers.

A replaced card (new number after a loss, fraud or expiry) keeps its account,
and the bank's export for the new number repeats the old number's charges for
the dates both cover. The import keys accounts by the card number in the file
name, so each number would be its own account and those charges counted twice.

The import spots two numbers whose overlapping charges are the same and
records them in SORTED/linked_cards.csv as "proposed": nothing changes until
the user answers the dashboard's question ("Did Chase replace your card
ending 6236 with 9956?"). Yes → "same": the newer number's rows are filed
under the older number and the two merge like any re-export of one account.
No → "different": they stay apart and the pair isn't asked about again. Both
answers can be undone from the dashboard for two weeks (back to "proposed"),
and later by editing the file; a status it doesn't recognise counts as
"proposed", so a typo brings the question back rather than settling it.
"""
from pathlib import Path

import pandas as pd

from Modules.safety import atomic_write_csv

LINKS_NAME = "linked_cards.csv"
LINK_COLUMNS = ["source", "institution", "old_card", "new_card", "status", "matched", "out",
                "from", "to", "found_on", "answered_on"]
STATUSES = ("proposed", "same", "different")
ANSWER_DAYS = 14   # how long the dashboard offers to undo an answer

# A replacement repeats every charge of the overlap (116 of 116 on real data);
# two different cards share only the odd coincidence (3 of 342). Under
# MIN_ROWS there's too little to tell, and little to count twice.
MIN_ROWS = 10
MIN_SHARE = 0.95


def links_path(master: Path) -> Path:
    return Path(master).parent / LINKS_NAME


def read_links(master: Path) -> pd.DataFrame | None:
    """The recorded pairs (empty when none). None when the file exists but
    can't be read: the import then neither proposes nor rewrites it, so a
    hand-edit gone wrong never loses the user's answers. A status it doesn't
    recognise reads as "proposed"; those rows are listed in attrs["unknown"]."""
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
        d = d[LINK_COLUMNS].apply(lambda col: col.str.strip())
        d["status"] = d["status"].str.lower()
        odd = ~d["status"].isin(STATUSES)
        unknown = [(r.source, r.old_card, r.new_card, r.status) for r in d[odd].itertuples()]
        d.loc[odd, "status"] = "proposed"
        d.attrs["unknown"] = unknown
        return d
    except Exception as e:
        print(f"  ⚠ Could not read {p} ({e}) — replacement cards aren't checked this run")
        return None


def write_links(master: Path, links: pd.DataFrame) -> None:
    p = links_path(master)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(links[LINK_COLUMNS], p)


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


def recorded(links: pd.DataFrame, source: str, a: str, b: str) -> pd.Series | None:
    """The file's row for two numbers, in either order (None when absent)."""
    hit = links[(links["source"] == source)
                & (((links["old_card"] == a) & (links["new_card"] == b))
                   | ((links["old_card"] == b) & (links["new_card"] == a)))]
    return None if hit.empty else hit.iloc[-1]


def find_replacements(accounts: dict[tuple, pd.DataFrame], links: pd.DataFrame,
                      today=None) -> list[dict]:
    """Card pairs to ask about that linked_cards.csv doesn't mention yet: two
    numbers of one institution and source whose overlapping charges are the
    same. Old = the number whose data starts first. Each dict is a links row
    (status "proposed"), plus the match itself under "match"."""
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today())
    keys = sorted(k for k in accounts if k[2])
    found = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if a[:2] != b[:2] or a[2] == b[2] or recorded(links, a[1], a[2], b[2]) is not None:
                continue
            m = overlap_match(accounts[a], accounts[b])
            if not is_replacement(m):
                continue
            old, new = sorted((a, b), key=lambda k: (accounts[k]["date"].min(), k[2]))
            found.append({"source": a[1], "institution": a[0], "old_card": old[2], "new_card": new[2],
                          "status": "proposed", "matched": f"{m['same']}/{max(m['rows_a'], m['rows_b'])}",
                          "out": f"{m['out']:.2f}", "from": f"{m['from']:%Y-%m-%d}",
                          "to": f"{m['to']:%Y-%m-%d}", "found_on": f"{today:%Y-%m-%d}",
                          "answered_on": "", "match": m})
    return found


def card_map(links: pd.DataFrame | None) -> dict[tuple[str, str], str]:
    """{(source, card): the card it's filed under} for every number the user
    confirmed as a replacement, the oldest number included (mapped to
    itself). Chains (A→B→C) resolve to A. Proposed pairs map nothing."""
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


def pair_id(r) -> str:
    return f"{r['source']}|{r['old_card']}|{r['new_card']}"


def _info(r) -> dict:
    d = {c: r[c] for c in LINK_COLUMNS}
    d["id"] = pair_id(r)
    n = str(r["matched"]).split("/")[0]
    d["n"] = int(n) if n.isdigit() else 0
    out = pd.to_numeric(r["out"], errors="coerce")
    d["out"] = 0.0 if pd.isna(out) else float(out)
    d["from"] = pd.to_datetime(r["from"], errors="coerce")
    d["to"] = pd.to_datetime(r["to"], errors="coerce")
    d["answered_on"] = pd.to_datetime(r["answered_on"], errors="coerce")
    return d


def pending_links(master: Path) -> list[dict]:
    """Pairs waiting for the user's answer (status "proposed")."""
    links = read_links(master)
    if links is None or links.empty:
        return []
    return [_info(r) for _, r in links[links["status"] == "proposed"].iterrows()]


def recent_answers(master: Path, today=None, days: int = ANSWER_DAYS) -> list[dict]:
    """Pairs the user answered in the last `days` days — still undoable from
    the dashboard."""
    links = read_links(master)
    if links is None or links.empty:
        return []
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today()).normalize()
    out = []
    for _, r in links[links["status"].isin(["same", "different"])].iterrows():
        d = _info(r)
        if pd.notna(d["answered_on"]) and (today - d["answered_on"].normalize()).days <= days:
            out.append(d)
    return out


def answer_link(master: Path, pid: str, expect: str, status: str, today=None) -> bool:
    """Set a pair's status to `status` — only if it is still `expect`, so a
    double tap or a stale page can't answer twice. True when written."""
    links = read_links(master)
    if links is None:
        return False
    hit = [i for i, r in links.iterrows() if pair_id(r) == pid and r["status"] == expect]
    if not hit:
        return False
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today())
    links.loc[hit, "status"] = status
    links.loc[hit, "answered_on"] = "" if status == "proposed" else f"{today:%Y-%m-%d}"
    write_links(master, links)
    return True


def pending_duplicates(frame: pd.DataFrame, pending: list[dict]) -> pd.Series:
    """Rows of `frame` that are a new number's copy of an old number's charge
    in a pair awaiting an answer: kept out of the unlabeled count and the
    LABEL list, so the user isn't asked to label charges that may be
    duplicates. Works on any date-filtered slice (both copies share a date)."""
    mask = pd.Series(False, index=frame.index)
    if frame.empty:
        return mask
    card = frame["card_last4"].fillna("").astype(str)
    for p in pending:
        if pd.isna(p["from"]) or pd.isna(p["to"]):
            continue
        win = (frame["source"] == p["source"]) & frame["date"].between(p["from"], p["to"])
        old, new = frame[win & (card == p["old_card"])], frame[win & (card == p["new_card"])]
        if old.empty or new.empty:
            continue

        def keyed(d):
            k = list(zip(d["date"], d["description"].astype(str).str.strip(), d["amount"].round(2)))
            s = pd.Series(k, index=d.index)
            return s, s.groupby(s).cumcount()

        ok, _ = keyed(old)
        have = ok.value_counts()
        nk, nth = keyed(new)
        dup = [n < have.get(k, 0) for k, n in zip(nk, nth)]
        mask.loc[new.index[dup]] = True
    return mask


def month_span(lo, hi) -> str:
    """'Jan–Mar 2026', 'Dec 2025–Mar 2026' or 'Mar 2026'."""
    if pd.isna(lo) or pd.isna(hi):
        return ""
    if (lo.year, lo.month) == (hi.year, hi.month):
        return f"{hi:%b %Y}"
    return f"{lo:%b}–{hi:%b %Y}" if lo.year == hi.year else f"{lo:%b %Y}–{hi:%b %Y}"
