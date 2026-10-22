"""
Merchants (ADR 0025; terms in CONTEXT.md).

A spelling is a row's bank text with store numbers and prefixes removed
(`merchant_key`). An alias ties one spelling to one merchant. A spelling
with no alias is its own merchant; a row with no spelling has none. Both
files live in the data folder's SORTED/, next to the master, and hold real
names, so they never enter the repo (ADR 0024).
"""
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from Modules.labels import merchant_key
from Modules.safety import _discard, _match_mode
from Modules.transforms import PREDEFINED_CATEGORIES, read_rules_csv

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


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    frame = read_rules_csv(path) if path.exists() else pd.DataFrame()
    for c in columns:
        if c not in frame.columns:
            frame[c] = ""
    return frame[columns].astype(str).apply(lambda s: s.str.strip())


def read_merchants(folder) -> Merchants:
    """Both merchant files from `folder` (missing files mean no merchants yet)."""
    folder = Path(folder)
    table = _read(folder / MERCHANTS_NAME, MERCHANT_COLUMNS)
    aliases = _read(folder / ALIASES_NAME, ALIAS_COLUMNS)
    # The forgiving reader: an alias that can't be trusted is ignored (its
    # spelling stays its own merchant) and reported, never guessed at
    live = aliases[(aliases["status"] == "alias") & (aliases["spelling"] != "")]
    names, problems, alias_of = set(table["merchant"]), [], {}
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


def apply_merchant_rules(df: pd.DataFrame, merchants: Merchants) -> pd.DataFrame:
    """A merchant's rule (its label and category) on every row of that
    merchant, in memory, never written. Same semantics as the old text rules:
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

    Both temp files are written first, so bad data or a full disk fails
    before anything real changes. Then the two swaps run back to back; if the
    second is refused (a file open in Excel), the first is put back and the
    error raised, so nothing changed. Order keeps even a crash between the
    swaps valid: a change that adds writes merchants.csv first (a merchant
    with no spellings yet is harmless), one that removes writes the aliases
    first (a spelling falls back to being its own merchant)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = [(folder / MERCHANTS_NAME, table[MERCHANT_COLUMNS]), (folder / ALIASES_NAME, aliases[ALIAS_COLUMNS])]
    if not adding:
        files.reverse()
    temps = []
    try:
        for path, frame in files:
            fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=folder)
            os.close(fd)
            temps.append(tmp)
            frame.to_csv(tmp, index=False)
            _match_mode(tmp, path)
        (first, _), (second, _) = files
        old_first = first.read_bytes() if first.exists() else None
        os.replace(temps[0], first)
        try:
            os.replace(temps[1], second)
        except BaseException:
            if old_first is None:
                first.unlink(missing_ok=True)
            else:                       # put it back atomically, as it was written
                Path(temps[0]).write_bytes(old_first)
                os.replace(temps[0], first)
            raise
    finally:
        for tmp in temps:
            _discard(tmp)


def merchant_list(descriptions: pd.Series, merchants: Merchants) -> dict[str, list[str]]:
    """Every merchant, from the rows and the alias file, with the spellings it
    covers (sorted). Rows with no spelling belong to no merchant."""
    spellings = set(descriptions.map(merchant_key)) | set(merchants.alias_of)
    out: dict[str, list[str]] = {}
    for s in sorted(spellings - {""}):
        out.setdefault(merchants.alias_of.get(s, s), []).append(s)
    return out
