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
        _put(first, first_new, temps[0])
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


def merchant_list(descriptions: pd.Series, merchants: Merchants) -> dict[str, list[str]]:
    """Every merchant, from the rows and the alias file, with the spellings it
    covers (sorted). Rows with no spelling belong to no merchant."""
    spellings = set(descriptions.map(merchant_key)) | set(merchants.alias_of)
    out: dict[str, list[str]] = {name: [] for name in merchants.table["merchant"]}   # none seen yet
    for s in sorted(spellings - {""}):
        out.setdefault(merchants.alias_of.get(s, s), []).append(s)
    return out
