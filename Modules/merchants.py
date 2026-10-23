"""
Merchants (ADR 0025; terms in CONTEXT.md).

A spelling is a row's bank text with store numbers and prefixes removed
(`merchant_key`). An alias ties one spelling to one merchant. A spelling
with no alias is its own merchant; a row with no spelling has none. Both
files live in the data folder's SORTED/, next to the master, and hold real
names, so they never enter the repo (ADR 0024).
"""
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from Modules.labels import merchant_key
from Modules.safety import _discard, _match_mode
from Modules.transforms import PREDEFINED_CATEGORIES, normalize_description, read_rules_csv

MERCHANTS_NAME = "merchants.csv"
ALIASES_NAME = "merchant_aliases.csv"
MERCHANT_COLUMNS = ["merchant", "master_category", "sub_category", "patterns", "added"]
ALIAS_COLUMNS = ["spelling", "merchant", "status"]


@dataclass
class Merchants:
    table: pd.DataFrame                      # one row per merchant
    aliases: pd.DataFrame                    # one row per spelling–merchant pairing
    alias_of: dict[str, str] = field(default_factory=dict)   # spelling -> merchant, trusted only
    problems: list[str] = field(default_factory=list)        # why an alias was ignored

    @property
    def version(self) -> str:
        """Changes whenever either file's content does ('' with no merchants)."""
        if self.table.empty and self.aliases.empty:
            return ""
        text = self.table.to_csv(index=False) + self.aliases.to_csv(index=False)
        return hashlib.sha1(text.encode()).hexdigest()[:10]


def _read_file(path: Path, columns: list[str]) -> pd.DataFrame | None:
    """One merchant file as stripped text columns; empty when missing, None
    when it can't be read (the caller reports it, the app still loads)."""
    try:
        frame = read_rules_csv(path) if path.exists() else pd.DataFrame()
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    for c in columns:
        if c not in frame.columns:
            frame[c] = ""
    return frame[columns].astype(str).apply(lambda s: s.str.strip())


def read_merchants(folder) -> Merchants:
    """Both merchant files from `folder` (missing files mean no merchants yet).
    The forgiving reader: whatever can't be trusted is ignored and listed in
    `problems`, never guessed at, so a spelling falls back to its own merchant."""
    if folder is None:                          # no data folder: no merchants
        return Merchants(pd.DataFrame(columns=MERCHANT_COLUMNS), pd.DataFrame(columns=ALIAS_COLUMNS))
    folder = Path(folder)
    problems = []
    table = _read_file(folder / MERCHANTS_NAME, MERCHANT_COLUMNS)
    aliases = _read_file(folder / ALIASES_NAME, ALIAS_COLUMNS)
    if table is None:
        problems.append(f"{MERCHANTS_NAME} can't be read, so no merchants are used")
        return Merchants(pd.DataFrame(columns=MERCHANT_COLUMNS), pd.DataFrame(columns=ALIAS_COLUMNS), {}, problems)
    if aliases is None:
        problems.append(f"{ALIASES_NAME} can't be read, so no spellings are merged")
        aliases = pd.DataFrame(columns=ALIAS_COLUMNS)
    return merchants_from(table, aliases, problems)


def merchants_from(table: pd.DataFrame, aliases: pd.DataFrame, problems: list[str] | None = None) -> Merchants:
    """Merchants from the two tables, trusting only what read_merchants would:
    used for files from disk and for the result of a change (its preview)."""
    problems = list(problems or [])
    table = table.astype(str).apply(lambda s: s.str.strip())
    aliases = aliases.astype(str).apply(lambda s: s.str.strip())
    table = table[table["merchant"] != ""]                       # Excel leaves empty rows
    for name in table.loc[table["merchant"].duplicated(), "merchant"].unique():
        problems.append(f"{name} is listed twice in {MERCHANTS_NAME} (the first row is used)")
    table = table.drop_duplicates("merchant").reset_index(drop=True)
    aliases["spelling"] = aliases["spelling"].map(normalize_description)   # a hand-typed spelling still matches
    live = aliases[(aliases["status"] == "alias") & (aliases["spelling"] != "")]
    names, alias_of = set(table["merchant"]), {}
    for spelling, group in live.groupby("spelling", sort=False):
        targets = group["merchant"].unique()
        if len(targets) > 1:
            problems.append(f"{spelling} is filed under {len(targets)} merchants")
        elif targets[0] not in names:
            problems.append(f"{spelling} points at a merchant that doesn't exist ({targets[0]})")
        else:
            alias_of[spelling] = targets[0]
    return Merchants(table, aliases, alias_of, problems)


def merchant_of(descriptions: pd.Series, merchants: Merchants) -> pd.Series:
    """Each row's merchant: its alias's merchant, else its own spelling, else
    '' when the bank text has no recognisable name."""
    spelling = descriptions.map(merchant_key)
    return spelling.map(lambda s: merchants.alias_of.get(s, s) if s else "")


def apply_rules(df: pd.DataFrame, merchants: Merchants) -> pd.DataFrame:
    """Each merchant's rule (its label and category) on every row of that
    merchant, in memory, never written. Same semantics as rules.csv keywords:
    the label goes only on rows with none (a hand label wins), and the
    category only fills a blank one, and only where the row's label agrees
    with the rule's (a category-only merchant fills any of its rows)."""
    rules = merchants.table[merchants.table["merchant"] != ""].drop_duplicates("merchant")
    rules = rules[(rules["master_category"] == "") | rules["master_category"].isin(PREDEFINED_CATEGORIES)]
    if rules.empty:
        return df
    who = merchant_of(df["description"], merchants)
    label = who.map(dict(zip(rules["merchant"], rules["master_category"]))).fillna("")
    sub = who.map(dict(zip(rules["merchant"], rules["sub_category"]))).fillna("")
    take = (label != "") & (df["master_category"] == "")
    df.loc[take, "master_category"] = label[take]
    fill = (sub != "") & (df["sub_category"] == "") & ((label == "") | (df["master_category"] == label))
    df.loc[fill, "sub_category"] = sub[fill]
    return df


def save_merchants(folder, table: pd.DataFrame, aliases: pd.DataFrame, adding: bool) -> None:
    """Write both merchant files as one change. The caller holds MASTER_LOCK.

    Order keeps even a crash between the two swaps valid: a change that adds
    writes merchants.csv first (a merchant with no spellings yet is
    harmless), one that removes writes the aliases first (a spelling falls
    back to being its own merchant)."""
    folder = Path(folder)
    files = [(folder / MERCHANTS_NAME, table[MERCHANT_COLUMNS].to_csv(index=False).encode("utf-8")),
             (folder / ALIASES_NAME, aliases[ALIAS_COLUMNS].to_csv(index=False).encode("utf-8"))]
    _write_pair(folder, files if adding else files[::-1])


def snapshot_files(folder) -> dict[str, str | None]:
    """Both merchant files' exact bytes, for UNDO: latin-1 text so the record
    survives the browser's JSON byte for byte; None for a missing file."""
    folder = Path(folder)
    return {name: (folder / name).read_bytes().decode("latin-1") if (folder / name).exists() else None
            for name in (MERCHANTS_NAME, ALIASES_NAME)}


def restore_files(folder, saved: dict[str, str | None]) -> None:
    """Put both merchant files back exactly as snapshot_files saw them, in the
    removal order (aliases first). The caller holds MASTER_LOCK."""
    folder = Path(folder)
    _write_pair(folder, [(folder / name, None if saved.get(name) is None else saved[name].encode("latin-1"))
                         for name in (ALIASES_NAME, MERCHANTS_NAME)])


def _write_pair(folder: Path, files: list[tuple[Path, bytes | None]]) -> None:
    """Two files as one change (None: the file should not exist). Both temp
    files are written first, so a full disk fails before anything real
    changes. Then the two swaps run back to back; if the second is refused (a
    file open in Excel), the first is put back and the error raised, so
    nothing changed."""
    folder.mkdir(parents=True, exist_ok=True)
    temps = []

    def _put(path, content, tmp):
        if content is None:
            path.unlink(missing_ok=True)
        else:
            os.replace(tmp, path)
    try:
        for path, content in files:
            fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=folder)
            os.close(fd)
            temps.append(tmp)
            if content is not None:
                Path(tmp).write_bytes(content)
                _match_mode(tmp, path)
        (first, first_new), (second, second_new) = files
        old_first = first.read_bytes() if first.exists() else None
        try:
            _put(first, first_new, temps[0])
        except PermissionError as err:
            raise PermissionError(f"Nothing changed: {first.name} is open in another program") from err
        try:
            _put(second, second_new, temps[1])
        except BaseException as err:
            try:
                if old_first is None:
                    first.unlink(missing_ok=True)
                else:                   # put it back atomically, as it was written
                    Path(temps[0]).write_bytes(old_first)
                    os.replace(temps[0], first)
            except OSError as undo_err:
                raise OSError(f"{first.name} was saved but {second.name} wasn't, so the merchant files "
                              f"may disagree ({undo_err})") from err
            if isinstance(err, PermissionError):
                raise PermissionError(f"Nothing changed: {second.name} is open in another program") from err
            raise
    finally:
        for tmp in temps:
            _discard(tmp)


def remember(merchants: Merchants, name: str, spellings: list[str], label: str, category: str,
             today: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Both files with `name`'s rule set to `label` (and `category`, when one
    is given) and each of `spellings` tied to it. A merchant that doesn't
    exist yet is made, so an unmerged spelling becomes a merchant named after
    itself. Save the result with adding=True."""
    table, aliases = merchants.table.copy(), merchants.aliases.copy()
    mine = table["merchant"] == name
    if mine.any():
        table.loc[mine, "master_category"] = label
        if category:
            table.loc[mine, "sub_category"] = category
    else:
        row = {"merchant": name, "master_category": label, "sub_category": category, "patterns": "", "added": today}
        table = pd.concat([table, pd.DataFrame([row])], ignore_index=True)
    # Each spelling gets exactly one alias, to this merchant: one the reader
    # couldn't trust (pointing nowhere, or filed twice) is replaced, not added to
    aliases = aliases[~(aliases["spelling"].isin(spellings) & (aliases["status"] == "alias"))]
    new = pd.DataFrame([{"spelling": s, "merchant": name, "status": "alias"} for s in spellings], columns=ALIAS_COLUMNS)
    return table, pd.concat([aliases, new], ignore_index=True)


def remember_check(df: pd.DataFrame, group: dict, merchants: Merchants) -> dict:
    """What remembering this To label group would do: ok, blocking and reason
    for the Remember tick; rows_now / dollars_now it would label today;
    months the merchant has been seen in; direction. A rule labels *every*
    unlabeled row of the merchant, not just the ones shown (REVIEW → shows
    only the last import), so all of these are measured over the merchant's
    rows. A rule matches the merchant's own spellings only, so nothing else
    can be swept up (ADR 0025). Nameless rows have no merchant to remember."""
    direction = "mixed" if group["mixed"] else ("money in" if group["total"] > 0 else "money out")
    out = {"ok": False, "reason": None, "blocking": True, "rows_now": 0, "dollars_now": 0.0,
           "months": 0, "direction": direction}
    if group.get("fallback"):
        out["reason"] = "no recognizable merchant name — label these one at a time"
        return out
    rows = df[merchant_of(df["description"], merchants) == group["mkey"]]
    open_ = rows[~rows["master_category"].isin(PREDEFINED_CATEGORIES)]
    out["rows_now"] = len(open_)
    out["dollars_now"] = float(open_["amount"].abs().sum())
    out["months"] = rows["date"].dt.to_period("M").nunique()
    if group["mixed"]:
        out.update(reason="money in and out — check the rows first", blocking=False)
        return out
    if (open_["amount"] > 0).any() and (open_["amount"] < 0).any():
        out["reason"] = "money in and out among its unlabeled rows — label them one at a time"
        return out
    out.update(ok=True, blocking=False)
    return out


# ── Merge, split, rename (ticket 05) ──────────────────────────────────────────
# Each returns the new (table, aliases); save them with save_change, which
# works out a crash-safe order from what the change adds and removes.

def _spellings(merchants: Merchants, name: str) -> list[str]:
    """The spellings aliased to `name`, or the bare spelling itself."""
    own = [s for s, m in merchants.alias_of.items() if m == name]
    return own or ([name] if name not in set(merchants.table["merchant"]) else [])


def _tie(aliases: pd.DataFrame, spellings: list[str], name: str) -> pd.DataFrame:
    """Aliases with each of `spellings` tied to `name` and nothing else; a
    dismissed suggestion of one of them for `name` goes, as it's now true."""
    alias = aliases["spelling"].isin(spellings) & (
        (aliases["status"] == "alias") | (aliases["merchant"] == name))
    new = pd.DataFrame([{"spelling": s, "merchant": name, "status": "alias"} for s in spellings], columns=ALIAS_COLUMNS)
    return pd.concat([aliases[~alias], new], ignore_index=True)


def _renamed(aliases: pd.DataFrame, old: str, new: str) -> pd.DataFrame:
    """Dismissed suggestions for `old` now speak of `new`."""
    return aliases.assign(merchant=aliases["merchant"].where(aliases["merchant"] != old, new))


def _new_row(name: str) -> pd.DataFrame:
    return pd.DataFrame([{"merchant": name, "master_category": "", "sub_category": "", "patterns": "", "added": ""}],
                        columns=MERCHANT_COLUMNS)


def merge(merchants: Merchants, source: str, target: str, spend: dict[str, float]):
    """`source` moves into `target`. `source` is a merchant (all its
    spellings move, and its own row, its rule, goes) or one spelling of a
    merged merchant (only it moves). A target that is a bare spelling becomes
    a new merchant, named after its highest-spend spelling (`spend`: money out
    by spelling)."""
    table, named = merchants.table, set(merchants.table["merchant"])
    target = merchants.alias_of.get(target, target)        # a spelling of a merchant means that merchant
    one_spelling = merchants.alias_of.get(source, source) != source
    carried = "" if one_spelling or source not in named else table.set_index("merchant").loc[source, "patterns"]
    moving = [source] if one_spelling else _spellings(merchants, source)
    aliases = merchants.aliases
    if not one_spelling and source in named:
        table = table[table["merchant"] != source]
    everything = moving + _spellings(merchants, target)
    if target not in named:
        target = max(everything, key=lambda s: (spend.get(s, 0.0), s == target))
        table = pd.concat([table, _new_row(target)], ignore_index=True)
    if not one_spelling:
        aliases = _renamed(aliases, source, target)
    if carried:                                             # its patterns follow it, like its dismissals
        mine = table["merchant"] == target
        own = table.loc[mine, "patterns"].iloc[0]
        joined = list(dict.fromkeys(p.strip() for p in f"{own}{PATTERN_SEP}{carried}".split(PATTERN_SEP) if p.strip()))
        table = table.assign(patterns=table["patterns"].where(~mine, f" {PATTERN_SEP} ".join(joined)))
    return table.reset_index(drop=True), _tie(aliases, everything, target)


def split(merchants: Merchants, spelling: str):
    """`spelling` leaves its merchant and becomes its own (no rule yet). A
    merchant left with no spelling ends, rule and all."""
    owner = merchants.alias_of.get(spelling)
    aliases = merchants.aliases
    aliases = aliases[~((aliases["spelling"] == spelling) & (aliases["status"] == "alias"))].reset_index(drop=True)
    table = merchants.table
    if owner and _spellings(merchants, owner) == [spelling]:
        table = table[table["merchant"] != owner].reset_index(drop=True)
    return table, aliases


def names_in_use(merchants: Merchants, spellings) -> set[str]:
    """Every merchant name and spelling, case-folded: what a rename may not
    collide with (a spelling, even the merchant's own, would make SPLIT OUT
    of it impossible)."""
    names = set(merchants.table["merchant"]) | set(merchants.alias_of) | set(spellings)
    return {n.casefold() for n in names} | {display_name(n).casefold() for n in names}


def rename(merchants: Merchants, old: str, new: str, in_use: set[str]):
    """`old` is called `new`, keeping its rule, spellings and dismissed
    suggestions. A bare spelling gets a merchant row of its own. `in_use`:
    names_in_use(), which `new` may not collide with, whatever its case."""
    new = new.strip()
    if not new:
        raise ValueError("A merchant needs a name")
    if new.casefold() in (old.casefold(), display_name(old).casefold()):
        raise ValueError("That's already its name")
    if new.casefold() in in_use:
        raise ValueError(f"Another merchant or spelling is already called {new}")
    table = merchants.table
    if old in set(table["merchant"]):
        table = table.assign(merchant=table["merchant"].where(table["merchant"] != old, new))
    else:
        table = pd.concat([table, _new_row(new)], ignore_index=True)
    aliases = _renamed(merchants.aliases, old, new)
    return table, _tie(aliases, _spellings(merchants, old), new)


def find_merchant(text: str, names: dict[str, str]) -> str | None:
    """The merchant a typed name means, whatever its case: `names` maps each
    name as shown (and as stored) to the merchant."""
    folded = {n.casefold(): m for n, m in names.items()}
    return folded.get((text or "").strip().casefold())


def save_change(folder, before: Merchants, table: pd.DataFrame, aliases: pd.DataFrame) -> None:
    """Save a change from `before`, so a crash at any point leaves files that
    agree. A change that only adds a merchant writes merchants.csv first; one
    that only removes, the aliases first. One that does both (a rename, a
    merge into a new merchant) goes in two saves: first with the old row
    still there, then without it. The caller holds MASTER_LOCK."""
    old = set(before.table["merchant"])
    new = set(table["merchant"])
    added, removed = new - old, old - new
    if added and removed:
        both = pd.concat([table, before.table[before.table["merchant"].isin(removed)]], ignore_index=True)
        saved = snapshot_files(folder)
        save_merchants(folder, both, aliases, adding=True)
        try:
            save_merchants(folder, table, aliases, adding=False)
        except PermissionError:
            restore_files(folder, saved)              # the first save goes too: nothing changed
            raise
    else:
        save_merchants(folder, table, aliases, adding=bool(added))


# ── Patterns and pattern suggestions (ticket 07) ──────────────────────────────

PATTERN_SEP = "|"
MIN_PATTERN = 3     # "e" suggested 22 spellings in review


def _patterns(cell: str) -> list[str]:
    """One merchant's patterns, from its "a | b" cell, in matching form."""
    return [normalize_description(p) for p in str(cell).split(PATTERN_SEP) if p.strip()]


def pattern_suggestions(spellings, merchants: Merchants) -> dict[str, str]:
    """{spelling: merchant} for each spelling with no alias that contains one
    of a merchant's patterns — a suggestion only, never a join. A dismissed
    pairing is never suggested again; the longest matching pattern wins."""
    aliases = merchants.aliases
    dismissed = set(zip(aliases.loc[aliases["status"] == "dismissed", "spelling"],
                        aliases.loc[aliases["status"] == "dismissed", "merchant"]))
    pats = sorted(((p, name) for name, cell in zip(merchants.table["merchant"], merchants.table["patterns"])
                   for p in _patterns(cell)), key=lambda x: (-len(x[0]), x[1]))
    out = {}
    for s in sorted(set(spellings) - {""} - set(merchants.alias_of)):
        hit = next((name for p, name in pats if p in s and name != s and (s, name) not in dismissed), None)
        if hit:
            out[s] = hit
    return out


def dismiss(merchants: Merchants, spelling: str, name: str):
    """Never suggest `spelling` for `name` again (it joins nothing)."""
    row = pd.DataFrame([{"spelling": spelling, "merchant": name, "status": "dismissed"}], columns=ALIAS_COLUMNS)
    return merchants.table, pd.concat([merchants.aliases, row], ignore_index=True)


def set_patterns(merchants: Merchants, name: str, text: str):
    """`name`'s patterns become those in `text` ("a | b"). A bare spelling
    gets a merchant row of its own to hold them."""
    pats = [p.strip() for p in str(text or "").split(PATTERN_SEP) if p.strip()]
    short = [p for p in pats if len(normalize_description(p)) < MIN_PATTERN]
    if short:
        raise ValueError(f"A pattern needs at least {MIN_PATTERN} letters: {short[0]}")
    cell = f" {PATTERN_SEP} ".join(pats)
    table, aliases = merchants.table, merchants.aliases
    if not cell and name not in set(table["merchant"]):
        raise ValueError("No patterns to save")
    if name in set(table["merchant"]):
        return table.assign(patterns=table["patterns"].where(table["merchant"] != name, cell)), aliases
    row = _new_row(name).assign(patterns=cell)
    return pd.concat([table, row], ignore_index=True), _tie(aliases, [name], name)


# ── Converting the old rules (ticket 08) ──────────────────────────────────────

def valid_keywords(rules: pd.DataFrame) -> list[dict]:
    """The rules.csv keywords loading applies, in order: a keyword with a
    valid label or a category (a typo'd label alone is skipped on load)."""
    out = []
    for r in rules.itertuples():
        kw = normalize_description(getattr(r, "keyword", ""))
        mc, sc = str(r.master_category).strip(), str(r.sub_category).strip()
        if kw and mc in PREDEFINED_CATEGORIES + [""] and (mc or sc):
            out.append({"keyword": r.keyword, "kw": kw, "label": mc, "category": sc})
    return out


def spend_by_spelling(rows: pd.DataFrame) -> dict[str, float]:
    """Money out by spelling: what names a merchant made from several."""
    out = rows[rows["amount"] < 0]
    return (-out["amount"]).groupby(out["description"].map(merchant_key)).sum().to_dict()


def _keyword_rule(text: str, keywords: list[dict]) -> tuple[str, str]:
    """The (label, category) the keywords give one unlabeled bank text on
    load: the first with a label labels it, and each with a category fills a
    blank one where its label (if any) agrees (apply_auto_categories, one row)."""
    label = sub = ""
    for k in keywords:
        if k["kw"] in text:
            if k["label"] and not label:
                label = k["label"]
            if k["category"] and not sub and (not k["label"] or label == k["label"]):
                sub = k["category"]
    return label, sub


def convert_proposals(rows: pd.DataFrame, rules: pd.DataFrame, merchants: Merchants) -> list[dict]:
    """Proposed merchants for the rules.csv keywords, in rule order: each
    spelling not already a merchant's goes to the first keyword that matches
    it, with the label and category the keywords give it (several can stack);
    a keyword whose spellings end up labeled differently makes one proposal
    each. Named after the spelling with the most money out, unless that name
    is taken; the keyword is the first proposal's pattern. A keyword that
    matches nothing today keeps only its pattern. These are the merchants'
    rules for *new* rows: the past is kept by freeze_keyword_labels, and
    keep_past drops any rule that would still move it. A spelling whose
    past rows got something other than the keywords give the bare spelling
    (a keyword needed its store number) is proposed on its own with no rule
    (`partial`): a rule would label a new store's rows as the keywords never
    did. Each: {keyword, name, label, category, pattern, spellings, rows,
    partial}."""
    keywords = valid_keywords(rules)
    spelling = rows["description"].map(merchant_key)
    text = rows["description"].map(normalize_description)
    spend = spend_by_spelling(rows)
    taken = {n.casefold() for n in set(merchants.table["merchant"]) | set(merchants.alias_of.values())}
    every_spelling = set(spelling) | set(merchants.alias_of)
    claimed = set(merchants.alias_of) | (set(spelling) & set(merchants.table["merchant"]))
    props = []
    for k in keywords:
        hit = text.str.contains(k["kw"], regex=False)
        mine = sorted(set(spelling[hit]) - {""} - claimed)
        claimed |= set(mine)
        first_hit = dict(zip(spelling[hit][::-1], text[hit][::-1]))   # each spelling's first matching row
        groups: dict[tuple[str, str, bool], list[str]] = {}
        for s in mine:
            past = _keyword_rule(first_hit[s], keywords)
            groups.setdefault((*past, _keyword_rule(s, keywords) != past), []).append(s)
        for n, ((label, sub, part), spellings) in enumerate(groups.items()
                                                            or [((k["label"], k["category"], False), [])]):
            name = _free_name([min(spellings, key=lambda x: (-spend.get(x, 0.0), x))] if spellings else [],
                              k["kw"], spellings, taken, every_spelling)
            taken.add(name.casefold())
            props.append({"keyword": k["keyword"], "name": name, "label": "" if part else label,
                          "category": "" if part else sub, "pattern": k["kw"] if n == 0 else "",
                          "spellings": spellings, "rows": int(hit.sum()), "partial": part})
    return props


def _free_name(preferred: list[str], kw: str, own: list[str], taken: set[str], spellings: set[str]) -> str:
    """The first of `preferred`, the keyword, "keyword 2", … that no other
    merchant uses and that isn't someone else's spelling."""
    candidates = preferred + [kw] + [f"{kw} {i}" for i in range(2, 100)]
    return next(c for c in candidates
                if c.casefold() not in taken and (c not in spellings or c in own))


def apply_conversion(merchants: Merchants, props: list[dict]):
    """Both files with each (reviewed) proposal as a merchant: its name,
    rule, pattern and the spellings left ticked. Save with save_change."""
    names = [p["name"].strip() for p in props]
    folded = [n.casefold() for n in names]
    existing = {n.casefold() for n in merchants.table["merchant"]}
    for name, f in zip(names, folded):
        if not name:
            raise ValueError("A merchant needs a name")
        if folded.count(f) > 1:
            raise ValueError(f"Two merchants would be called {name}")
        if f in existing:
            raise ValueError(f"A merchant called {name} already exists")
    rows = pd.DataFrame([{"merchant": n, "master_category": p["label"], "sub_category": p["category"],
                          "patterns": p["pattern"], "added": ""} for n, p in zip(names, props)], columns=MERCHANT_COLUMNS)
    aliases = merchants.aliases
    for name, p in zip(names, props):
        aliases = _tie(aliases, p["spellings"], name)
    return pd.concat([merchants.table, rows], ignore_index=True), aliases


def review_choices(defaults: list[dict], reviewed: list[dict]) -> dict:
    """{spelling: (label, category) or None}: what the review chose for the
    past rows a keyword labeled. An unticked spelling is None (its keyword
    labels go, so an accidental match is fixed, not copied); a proposal whose
    label or category was changed gives its spellings the reviewed pair, with
    None for a field left as shown (a no-rule card shows blanks, which must
    not wipe what the keyword gave)."""
    if len(defaults) != len(reviewed):
        raise ValueError("The list changed — reopen CONVERT RULES to see it again.")
    out = {}
    for d, r in zip(defaults, reviewed):
        for s in set(d["spellings"]) - set(r["spellings"]):
            out[s] = None
        pair = (r["label"] if r["label"] != d["label"] else None,
                r["category"] if r["category"] != d["category"] else None)
        if pair != (None, None):
            for s in r["spellings"]:
                out[s] = pair
    return out


def freeze_keyword_labels(hand: pd.DataFrame, merchants: Merchants, rules_path, choices=None):
    """(frozen, kept, stored): `hand` with the label and category the
    rules.csv keywords give each row today stored on that row, so retiring
    them moves nothing in the past, except where the review chose otherwise
    (`choices`, from review_choices). `kept` is each row's label after the
    conversion; `stored` marks the rows that got one. Merchants' own rules
    aren't frozen."""
    shown = rule_labels(hand, merchants, rules_path)
    base = rule_labels(hand, merchants, None)
    kept = shown.copy()
    keyword_given = (shown != base).any(axis=1)
    spelling = hand["description"].map(merchant_key)
    gave_label = shown["master_category"] != base["master_category"]
    gave_sub = shown["sub_category"] != base["sub_category"]
    for s, pair in (choices or {}).items():
        rows = keyword_given & (spelling == s)
        if pair is None:
            kept.loc[rows] = base.loc[rows]
            continue
        label, cat = pair
        if label is not None:
            lab = rows & gave_label
            kept.loc[lab, "master_category"] = label if label else base.loc[lab, "master_category"]
        if cat is not None:
            # where the row's label agrees with the reviewed one (as a rule's would)
            fits = rows & gave_sub & ((kept["master_category"] == label) if label else True)
            kept.loc[fits, "sub_category"] = cat if cat else base.loc[fits, "sub_category"]
    stored = (kept != base).any(axis=1)
    frozen = hand.copy()
    for c in ("master_category", "sub_category"):
        frozen[c] = frozen[c].fillna("").astype(str).str.strip()
        frozen.loc[stored, c] = kept.loc[stored, c]
    return frozen, kept, stored


def keep_past(frozen: pd.DataFrame, kept: pd.DataFrame, merchants: Merchants, props: list[dict]):
    """(props, dropped): a proposal whose rule would still move a past row
    (one a keyword didn't label, but its broader merchant would) keeps its
    spellings and pattern but no rule, so every past label stays as `kept`.
    Repeats until nothing moves (each round drops at least one rule)."""
    out = list(props)
    while True:
        after = merchants_from(*apply_conversion(merchants, out))
        moved = (rule_labels(frozen, after, None) != kept).any(axis=1)
        bad = set(merchant_of(frozen.loc[moved, "description"], after))
        new = [dict(p, label="", category="") if p["name"] in bad and (p["label"] or p["category"]) else p
               for p in out]
        if all(a is b for a, b in zip(new, out)):
            return out, sum(1 for p, q in zip(props, out) if p is not q)
        out = new


def rule_labels(hand: pd.DataFrame, merchants: Merchants, rules_path) -> pd.DataFrame:
    """Each row's label and category as loading would show them: the hand
    labels in `hand`, then the merchants' rules, then the rules.csv keywords."""
    from Modules.transforms import apply_auto_categories   # transforms imports this module
    frame = hand[["description", "amount", "master_category", "sub_category"]].copy()
    for c in ("master_category", "sub_category"):
        frame[c] = frame[c].fillna("").astype(str).str.strip()
    apply_rules(frame, merchants)
    apply_auto_categories(frame, rules_path)
    return frame[["master_category", "sub_category"]]


def describe_label(label: str, category: str) -> str:
    """"Expense · Groceries", "Expense", or "unlabeled · Venmo"."""
    return (label or "unlabeled") + (f" · {category}" if category else "")


def label_changes(hand: pd.DataFrame, before: Merchants, after: Merchants, rules_path,
                  rules_path_after) -> list[dict]:
    """What a change would relabel: rows whose label or category (after
    rules, on top of the hand labels in `hand`) differs, as [{from, to, rows,
    dollars}]. The rules.csv keywords are applied too, so the preview is what
    loading shows. `rules_path_after`: the keywords after the change (the
    same file, or None once they're retired)."""
    was, now = rule_labels(hand, before, rules_path), rule_labels(hand, after, rules_path_after)
    moved = (was != now).any(axis=1)
    frame = pd.DataFrame({"from": [describe_label(*x) for x in was[moved].itertuples(index=False)],
                          "to": [describe_label(*x) for x in now[moved].itertuples(index=False)],
                          "dollars": hand.loc[moved, "amount"].abs().to_numpy()})
    out = frame.groupby(["from", "to"], sort=True).agg(rows=("dollars", "size"), dollars=("dollars", "sum"))
    return [{"from": f, "to": t, "rows": int(r.rows), "dollars": round(float(r.dollars), 2)}
            for (f, t), r in out.iterrows()]


def display_name(name: str) -> str:
    """A name you gave a merchant shows as typed; a bare spelling (all lower
    case) in capitals, like the bank text it came from."""
    return name if name != name.lower() else name.upper()


def _money(rows: pd.DataFrame) -> tuple[float, float]:
    """(money out, money in), both positive."""
    return (round(float(-rows.loc[rows["amount"] < 0, "amount"].sum()), 2),
            round(float(rows.loc[rows["amount"] > 0, "amount"].sum()), 2))


def merchant_overview(df: pd.DataFrame, merchants: Merchants, suggested: dict[str, str] | None = None
                      ) -> tuple[list[dict], dict]:
    """Every merchant over all its rows, all time (the All merchants view
    ignores the period). Each item: name (as shown), mkey, spellings, label,
    category, patterns (its rule), out / inn (money out and in, positive),
    rows, first, last, labels (the valid labels its rows carry), has_rule,
    suggested (the merchant a bare spelling is suggested as, or "") and
    suggestions (1 when it has one). `suggested`: {spelling: merchant}, by
    default the pattern suggestions. Also the rows with no spelling, which
    belong to no merchant: {"rows", "out", "inn"}."""
    who = merchant_of(df["description"], merchants)
    spelling = df["description"].map(merchant_key)
    if suggested is None:
        suggested = pattern_suggestions(spelling, merchants)
    rules = merchants.table.set_index("merchant")
    items = []
    for mk, rows in df[who != ""].groupby(who[who != ""], sort=False):
        rule = rules.loc[mk] if mk in rules.index else None
        label, category = (rule["master_category"], rule["sub_category"]) if rule is not None else ("", "")
        items.append({
            "name": display_name(mk), "mkey": mk,
            "spellings": sorted(set(spelling[rows.index])),
            "label": label, "category": category,
            "patterns": rule["patterns"] if rule is not None else "",
            **dict(zip(("out", "inn"), _money(rows))),
            "rows": len(rows), "first": rows["date"].min(), "last": rows["date"].max(),
            "labels": sorted(set(rows["master_category"]) & set(PREDEFINED_CATEGORIES)),
            "has_rule": bool(label or category),
            "suggested": suggested.get(mk, ""), "suggestions": int(mk in suggested),
        })
    none = df[who == ""]
    nameless = {"rows": len(none), **dict(zip(("out", "inn"), _money(none)))}
    return items, nameless


def sort_merchants(items: list[dict], by: str) -> list[dict]:
    """By "spend" (money out, then money in), or by "attention": open
    suggestions first, then merchants whose rows carry different labels, then
    those with no rule, each by spend."""
    def spend(i):
        return -i["out"], -i["inn"], i["name"]
    if by == "attention":
        return sorted(items, key=lambda i: (not i["suggestions"], len(i["labels"]) < 2, i["has_rule"], *spend(i)))
    return sorted(items, key=spend)


def merchant_list(descriptions: pd.Series, merchants: Merchants) -> dict[str, list[str]]:
    """Every merchant, from the rows and the alias file, with the spellings it
    covers (sorted). Rows with no spelling belong to no merchant."""
    spellings = set(descriptions.map(merchant_key)) | set(merchants.alias_of)
    out: dict[str, list[str]] = {name: [] for name in merchants.table["merchant"]}   # none seen yet
    for s in sorted(spellings - {""}):
        out.setdefault(merchants.alias_of.get(s, s), []).append(s)
    return out
