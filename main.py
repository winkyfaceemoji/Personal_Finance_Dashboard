import re
from collections import defaultdict, deque
import pandas as pd
from pathlib import Path
from config import get_data_dir, get_master_path
from Modules.labels import LAST_IMPORT_NAME, row_id
from Modules.linked_cards import card_map, find_replacements, read_links, write_links
from Modules.safety import (
    atomic_write_csv, backup_master, orphans_path, restore_if_missing, write_exported_through,
    write_overlap_only, write_skipped,
)

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# Unified output schema
UNIFIED_COLUMNS = [
    "date", "post_date", "description", "amount", "original_category",
    "type", "balance", "memo", "check_or_slip", "institution", "source", "card_last4"
]

# Master file schema — unified + user-assigned columns
MASTER_COLUMNS = UNIFIED_COLUMNS + ["master_category", "sub_category"]

# Columns used to match a rebuilt row back to its prior categorization.
# card_last4 excluded: old rows lack it and would never match otherwise.
# institution excluded: it's folder-derived identity (redundant with source
# for matching) and predates existing master files, so keying on it would
# drop every prior label on the first rebuild.
# User-assigned columns (master_category, sub_category) also excluded.
MATCH_COLUMNS = [c for c in UNIFIED_COLUMNS if c not in ("card_last4", "institution")]

# Looser key tried for labels the exact key couldn't place: a re-export that
# changes a secondary field (bank category, memo, running balance) still
# lands its label. Labels neither key places go to orphaned_labels.csv.
FALLBACK_COLUMNS = ["date", "description", "amount", "source"]

# ── Header signatures used to detect which bank format a file is ─────────────
CHASE_DEBIT_HEADERS     = {"Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"}
CHASE_CREDIT_HEADERS    = {"Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"}
DISCOVER_CREDIT_HEADERS = {"Trans. Date", "Post Date", "Description", "Amount", "Category"}
CAPITAL_ONE_CREDIT_HEADERS = {"Transaction Date", "Posted Date", "Card No.", "Description",
                              "Category", "Debit", "Credit"}

# Capital One took over the Discover card: its exports are that account,
# whichever RAW/ folder they sit in (RAW/CapitalOne/ keeps them apart on disk)
CAPITAL_ONE_ACCOUNT = "Discover"

# Within one account, files of a higher-priority format own their dates
# before any span comparison. The Discover-format history is a closed
# archive — labeled, and never growing again — so a wide Capital One export
# reaching back into it can't take its dates (and orphan its labels).
FORMAT_PRIORITY = {"discover_credit": 1}


def detect_format(df: pd.DataFrame) -> str | None:
    """Detect which bank format a dataframe belongs to based on its columns."""
    cols = set(df.columns.str.strip())
    if CHASE_DEBIT_HEADERS.issubset(cols):
        return "chase_debit"
    elif CHASE_CREDIT_HEADERS.issubset(cols):
        return "chase_credit"
    elif DISCOVER_CREDIT_HEADERS.issubset(cols):
        return "discover_credit"
    elif CAPITAL_ONE_CREDIT_HEADERS.issubset(cols):
        return "capital_one_credit"
    return None


def _text(col: pd.Series) -> pd.Series:
    """A text column, stripped. A column that is empty in every row (e.g. a
    statement holding only payments has no Category) is read as float NaN,
    which the .str accessor rejects — and one such file used to abort the
    whole import."""
    # str(v): a column of digits only (e.g. a numeric Memo) is read as numbers;
    # blanks stay NaN, as .str.strip() left them
    return col.map(lambda v: v if pd.isna(v) else str(v).strip())


def normalize_chase_debit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chase Debit columns:
    Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #
    """
    out = pd.DataFrame(columns=UNIFIED_COLUMNS)
    out["date"]          = pd.to_datetime(df["Posting Date"], errors="coerce")
    out["post_date"]     = pd.to_datetime(df["Posting Date"], errors="coerce")
    out["description"]   = _text(df["Description"])
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce")
    out["original_category"] = None
    out["type"]          = _text(df["Type"])
    out["balance"]       = pd.to_numeric(df["Balance"], errors="coerce")
    out["memo"]          = None
    out["check_or_slip"] = df["Check or Slip #"]
    out["source"]        = "Chase Debit"
    return out


def normalize_chase_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chase Credit columns:
    Transaction Date, Post Date, Description, Category, Type, Amount, Memo
    """
    out = pd.DataFrame(columns=UNIFIED_COLUMNS)
    out["date"]          = pd.to_datetime(df["Transaction Date"], errors="coerce")
    out["post_date"]     = pd.to_datetime(df["Post Date"], errors="coerce")
    out["description"]   = _text(df["Description"])
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce")
    out["original_category"] = _text(df["Category"])
    out["type"]          = _text(df["Type"])
    out["balance"]       = None
    out["memo"]          = _text(df["Memo"])
    out["check_or_slip"] = None
    out["source"]        = "Chase Credit"
    return out


def normalize_discover_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Discover Credit columns:
    Trans. Date, Post Date, Description, Amount, Category
    """
    out = pd.DataFrame(columns=UNIFIED_COLUMNS)
    out["date"]          = pd.to_datetime(df["Trans. Date"], errors="coerce")
    out["post_date"]     = pd.to_datetime(df["Post Date"], errors="coerce")
    out["description"]   = _text(df["Description"])
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce") * -1
    out["original_category"] = _text(df["Category"])
    out["type"]          = None
    out["balance"]       = None
    out["memo"]          = None
    out["check_or_slip"] = None
    out["source"]        = "Discover Credit"
    return out


def _money(col: pd.Series) -> pd.Series:
    """Dollar amounts that may carry "$" or thousands commas; blank is NaN."""
    return pd.to_numeric(col.astype(str).str.replace(r"[$,\s]", "", regex=True),
                         errors="coerce")


def normalize_capital_one_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Capital One credit columns:
    Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit

    Capital One took over the Discover card, and its exports are the same
    account in a new format — so the rows keep source "Discover Credit" and
    a blank card_last4 (Card No. is ignored), and load_and_normalize files
    them under the Discover institution (CAPITAL_ONE_ACCOUNT) whatever their
    folder: an export overlapping the Discover history is merged by coverage
    instead of counted twice. Charges are in Debit and payments / refunds in
    Credit, both positive.
    """
    debit, credit = _money(df["Debit"]), _money(df["Credit"])
    out = pd.DataFrame(columns=UNIFIED_COLUMNS)
    out["date"]          = pd.to_datetime(df["Transaction Date"], errors="coerce")
    out["post_date"]     = pd.to_datetime(df["Posted Date"], errors="coerce")
    out["description"]   = _text(df["Description"])
    out["amount"]        = (credit.fillna(0) - debit.fillna(0)).where(credit.notna() | debit.notna())
    out["original_category"] = _text(df["Category"])
    out["type"]          = None
    out["balance"]       = None
    out["memo"]          = None
    out["check_or_slip"] = None
    out["source"]        = "Discover Credit"
    return out


NORMALIZERS = {
    "chase_debit":        normalize_chase_debit,
    "chase_credit":       normalize_chase_credit,
    "discover_credit":    normalize_discover_credit,
    "capital_one_credit": normalize_capital_one_credit,
}


def load_and_normalize(filepath: Path, input_folder: Path, skipped: list | None = None) -> pd.DataFrame | None:
    """Load a CSV, detect its format, and normalize it to the unified schema.
    A file that can't be used is skipped — appended to `skipped` as (path under
    RAW, reason) so the dashboard can say so — never aborting the import."""
    rel_name = str(filepath.relative_to(input_folder))

    def _skip(reason: str) -> None:
        print(f"  [SKIP] {filepath.name}: {reason}")
        if skipped is not None:
            skipped.append((rel_name, reason))

    try:
        df = pd.read_csv(filepath, index_col=False)
        df.columns = df.columns.str.strip()
    except Exception as e:
        _skip(f"couldn't be read ({e})")
        return None

    fmt = detect_format(df)
    if fmt is None:
        _skip("unrecognized format")
        return None

    try:
        result = NORMALIZERS[fmt](df)
    except Exception as e:
        # One malformed statement used to take the whole import down with it
        _skip(f"couldn't be parsed as {fmt} ({e})")
        return None

    # Institution = the top-level folder under RAW (folder-authoritative
    # identity). Files dropped directly in RAW get a blank institution.
    rel = filepath.relative_to(input_folder).parts
    institution = rel[0] if len(rel) > 1 else ""
    if fmt == "capital_one_credit":
        institution = CAPITAL_ONE_ACCOUNT
    result["institution"] = institution
    # For the coverage merge: format priority, and naming what it leaves out
    result.attrs.update(format=fmt, file=rel_name)

    # Extract card last-4 from Chase filenames: ChaseXXXX_Activity... (no
    # separator between "Chase" and the digits — the regex requires that)
    last4 = None
    m = re.search(r"Chase(\d{4})_", filepath.name, re.IGNORECASE)
    if m:
        last4 = m.group(1)
    result["card_last4"] = last4 if last4 else ""
    # The number in the file name, kept when a replacement card's rows are
    # re-filed under the old number (the coverage merge's overlap check)
    result.attrs["card"] = result["card_last4"].iat[0] if len(result) else ""

    tag = f" [{institution}]" if institution else ""
    print(f"  [OK]   {filepath.name} -> {fmt}{tag}" + (f" (card ...{last4})" if last4 else ""))
    return result


_NAME_DATE = re.compile(r"(?<!\d)(\d{4})-?(\d{2})-?(\d{2})(?!\d)")


def filename_date(name: str, today=None) -> pd.Timestamp | None:
    """The latest date written in an export's file name — the download date
    (2026-10-10_transaction_download.csv, Chase…_20260411.CSV) or statement
    date (Discover-Statement-20230527.csv). None without one; dates after
    today are ignored as not dates at all."""
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today()).normalize()
    found = []
    for y, m, d in _NAME_DATE.findall(name):
        try:
            t = pd.Timestamp(int(y), int(m), int(d))
        except ValueError:
            continue
        if 2000 <= t.year and t <= today:
            found.append(t)
    return max(found) if found else None


def _merge_by_coverage(file_dfs: list[pd.DataFrame], overlap_only: list | None = None,
                       check_all: bool = False) -> pd.DataFrame:
    """
    Merge multiple raw exports of the same physical account into one
    timeline, using each file's actual transaction-date coverage to decide
    which file owns a given date — rather than comparing row values.

    Banks get re-exported periodically with overlapping date ranges; the
    overlapping segment between two exports covers the same real
    transactions. Deduplicating by row value (date, description, amount, ...)
    breaks on genuine same-day repeat purchases (e.g. two subway swipes),
    since they're indistinguishable by value alone. Deciding ownership by
    date range instead means rows are never compared against each other —
    whichever file owns a date contributes all of its rows for that date,
    duplicates included.

    File modification time is deliberately NOT used to pick a winner: bulk
    copies, git checkouts, and drive migrations all rewrite mtimes without
    any relation to when a statement was actually downloaded. Instead, the
    file with the widest verified date span (derived from its own parsed
    transactions) wins any date it covers; ties broken by row count. A file of
    a higher FORMAT_PRIORITY outranks any span (the Discover archive over
    Capital One exports of the same card).

    The rule assumes the winning file is complete for its dates. Where it
    isn't — a charge still pending when the last Discover export was taken
    shows up only in a Capital One export, dated inside Discover's range —
    the losing file's row is dropped. Where a file of another format than the
    winning one loses dates (Capital One under the Discover archive), its
    dropped rows with no transaction of the same date and amount in the
    merged result are appended to `overlap_only` (with their file), so they
    are reported rather than silently lost. They aren't added back: a changed
    amount (a tip on a pending charge) would then count one charge twice.
    Re-downloads of one format (the usual overlapping statements) aren't
    checked — the same export always carries the same rows, and a pending
    charge that posted with a tip would read as left out. `check_all` (a
    linked replacement card's account) adds the rows a file loses on dates
    another card number's export owns: a charge still pending when the old
    number's last export was taken may only be in the new number's.
    """
    def span(d: pd.DataFrame) -> pd.Timedelta:
        valid = d["date"].dropna()
        return valid.max() - valid.min() if not valid.empty else pd.Timedelta(0)

    ordered = sorted(file_dfs, key=lambda d: (FORMAT_PRIORITY.get(d.attrs.get("format"), 0),
                                              span(d), len(d)), reverse=True)

    covered: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []   # (from, to, owner's card)
    kept, dropped = [], []
    for d in ordered:
        card = d.attrs.get("card", "")
        already_covered = pd.Series(False, index=d.index)
        other_card = pd.Series(False, index=d.index)
        for lo, hi, owner in covered:
            inside = d["date"].between(lo, hi)
            already_covered |= inside
            if owner != card:
                other_card |= inside
        new_rows = d[~already_covered]
        if already_covered.any():
            if d.attrs.get("format") != ordered[0].attrs.get("format"):
                dropped.append(d[already_covered].assign(file=d.attrs.get("file", "")))
            elif check_all and other_card.any():
                dropped.append(d[other_card].assign(file=d.attrs.get("file", "")))
        if not new_rows.empty:
            kept.append(new_rows)
            dated = new_rows["date"].dropna()
            if not dated.empty:
                covered.append((dated.min(), dated.max(), card))

    merged = pd.concat(kept, ignore_index=True) if kept else ordered[0].iloc[0:0]
    if overlap_only is not None and dropped:
        missing = _only_in_dropped(merged, dropped)
        if not missing.empty:
            overlap_only.append(missing)
    return merged


def _only_in_dropped(merged: pd.DataFrame, dropped: list[pd.DataFrame]) -> pd.DataFrame:
    """Dropped rows with no transaction of the same date and amount in the
    merged result. Counted per (date, amount): if two losing files both hold
    a charge the winner lacks, it's reported once."""
    def keys(d: pd.DataFrame) -> pd.Series:
        return pd.Series(list(zip(d["date"].dt.normalize(), d["amount"].round(2))), index=d.index)

    have = keys(merged).value_counts()
    need: dict = {}
    for d in dropped:
        d = d[d["amount"].notna()]
        k = keys(d)
        for key, n in k.value_counts().items():
            if n > need.get(key, (0, None))[0]:
                need[key] = (n, d[k == key])
    out = [rows.head(n - have.get(key, 0)) for key, (n, rows) in need.items() if n > have.get(key, 0)]
    return pd.concat(out, ignore_index=True) if out else merged.iloc[0:0]


def _link_replacement_cards(groups: dict[tuple, list[pd.DataFrame]], master_file: Path,
                            links: pd.DataFrame
                            ) -> tuple[dict[tuple, list[pd.DataFrame]], dict[tuple[str, str], str]]:
    """Regroup a confirmed replacement card's exports under the number it
    replaced (Modules/linked_cards), so the coverage merge counts the charges
    both exports carry once. A newly spotted pair is only recorded, as
    "proposed", for the dashboard to ask about; returns the regrouped files
    and the card map in force. `links`: read_links' result (never None —
    main stops when the file can't be read)."""
    accounts = {k: _merge_by_coverage(v) for k, v in groups.items()}
    found = find_replacements(accounts, links)
    if found:
        links = pd.concat([links, pd.DataFrame([{k: f[k] for k in links.columns} for f in found])],
                          ignore_index=True)
        try:
            write_links(master_file, links)
        except OSError as e:
            print(f"  ⚠ Could not update SORTED/linked_cards.csv ({e})")
        for f in found:
            print(f"  {f['source']} {f['new_card']} looks like a replacement for {f['old_card']} "
                  f"({f['matched']} charges where both overlap are the same) — answer the question "
                  f"on the dashboard; until then they count twice")
    cards = card_map(links)
    if not cards:
        return groups, cards
    regrouped: dict[tuple, list[pd.DataFrame]] = defaultdict(list)
    for (institution, source, card), file_dfs in groups.items():
        canon = cards.get((source, card), card)
        if canon != card:
            for d in file_dfs:
                d["card_last4"] = canon
        regrouped[(institution, source, canon)].extend(file_dfs)
    return dict(regrouped), cards


def rebuild_master(combined: pd.DataFrame, master_file: Path,
                   linked: set[tuple[str, str]] | None = None) -> dict:
    """
    Rebuild edited_combined_transactions.csv from the freshly-merged combined
    data, carrying forward existing master_category / sub_category
    assignments by matching each row's MATCH_COLUMNS key against the prior
    master file.

    Every unified-schema column is regenerated from RAW on every run — only
    the user-assigned categorization is preserved. A match key that occurs
    more times in the new combined data than in the prior master inherits
    the categorization of existing occurrences, in order; any occurrence
    beyond what the prior master had is genuinely new and starts blank.
    Labeled prior rows are offered first, so an unlabeled twin never takes a
    match ahead of a labeled one.

    linked: (source, card) of every linked replacement-card number. Before
    the link, a charge on both numbers' exports was in the master twice; now
    it's once. A leftover prior copy whose label the remaining row already
    carries is that duplicate, not a lost label — it isn't orphaned. A copy
    with a different label is: the user sees it and decides.

    Label safety: the prior master is *copied* to SORTED/backups/ (never
    renamed away), a master missing after a failed run is restored from the
    newest backup first, older master schemas are tolerated, and the new
    master is written atomically — so a crash at any point leaves either
    the old master or the complete new one.
    """
    combined = combined.copy()
    for col in ["date", "post_date"]:
        combined[col] = pd.to_datetime(combined[col], errors="coerce").dt.strftime("%Y-%m-%d")
    combined["master_category"] = None
    combined["sub_category"]    = None

    def iso_dates(d: pd.DataFrame) -> None:
        for col in ["date", "post_date"]:
            d[col] = pd.to_datetime(d[col], errors="coerce").dt.strftime("%Y-%m-%d")

    def row_key(d: pd.DataFrame) -> pd.Series:
        return d[MATCH_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    def full_key(d: pd.DataFrame) -> pd.Series:
        return d[MASTER_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    def fallback_key(d: pd.DataFrame) -> pd.Series:
        amount = pd.to_numeric(d["amount"], errors="coerce").round(2).astype(str)
        parts = d[["date", "description", "source"]].fillna("").astype(str)
        parts["description"] = parts["description"].str.strip()
        return pd.Series(list(zip(parts["date"], parts["description"], amount, parts["source"])),
                         index=d.index)

    result = {"carried": 0, "rescued": 0, "orphaned": 0, "merged": 0, "restored_from": None}
    orphans = None   # set once a prior master is read; written only after the master is
    new_ids = None   # rows this import added; set only when a prior master existed

    restored = restore_if_missing(master_file)
    if restored:
        result["restored_from"] = restored
        print(f"  Master file was missing or empty — restored labels from backup {restored.name}")

    if master_file.exists():
        old_master = pd.read_csv(master_file, dtype={"card_last4": str})
        if "category" in old_master.columns and "original_category" not in old_master.columns:
            old_master = old_master.rename(columns={"category": "original_category"})
        # Masters written by older versions lack newer columns; a missing
        # column reads as blank rather than aborting the rebuild
        for col in MASTER_COLUMNS:
            if col not in old_master.columns:
                old_master[col] = None
        # Back up only a master that parsed: backing up a torn one on every
        # failed run would rotate the good, labelled backups out
        backup_master(master_file)
        iso_dates(old_master)

        # Labels orphaned by earlier rebuilds get another chance every run —
        # appended after the master's own rows so those take precedence
        prior_orphans = orphans_path(master_file)
        if prior_orphans.exists():
            extra = pd.read_csv(prior_orphans, dtype={"card_last4": str})
            for col in MASTER_COLUMNS:
                if col not in extra.columns:
                    extra[col] = None
            # Its own pass: dates parse by the format of their first row, and
            # an orphan file saved from Excel has M/D/YYYY, not the master's ISO
            iso_dates(extra)
            # An orphan identical to a master row, label included, is one that
            # was placed but whose file couldn't then be updated (open in
            # Excel). Kept, it would be re-reported forever and hand its label
            # to the next same-day repeat; the master row already carries it.
            in_master = set(full_key(old_master))
            extra = extra[[k not in in_master for k in full_key(extra)]]
            old_master = pd.concat([old_master[MASTER_COLUMNS], extra[MASTER_COLUMNS]],
                                   ignore_index=True)

        old_master["master_category"] = old_master["master_category"].fillna("")
        old_master["sub_category"]    = old_master["sub_category"].fillna("")
        labeled = (old_master["master_category"] != "") | (old_master["sub_category"] != "")

        def _take(idx, i):
            combined.at[idx, "master_category"] = old_master.at[i, "master_category"] or None
            combined.at[idx, "sub_category"]    = old_master.at[i, "sub_category"] or None
            used.add(i)

        # Pass 1: exact key, in order (same-day repeats inherit in sequence),
        # labeled rows first: rows sharing a key are indistinguishable, so
        # which one inherits is free — and a label is never lost to a blank
        exact = defaultdict(deque)
        first = old_master.index[labeled.to_numpy()].append(old_master.index[~labeled.to_numpy()])
        for i, key in zip(first, row_key(old_master.loc[first])):
            exact[key].append(i)
        used, matched = set(), set()
        for idx, key in zip(combined.index, row_key(combined)):
            bucket = exact.get(key)
            if bucket:
                _take(idx, bucket.popleft())
                matched.add(idx)
                result["carried"] += 1

        # Pass 2: labeled rows pass 1 couldn't place, by the looser key
        spare = old_master[labeled & ~old_master.index.isin(used)]
        fallback = defaultdict(deque)
        for i, key in zip(spare.index, fallback_key(spare)):
            fallback[key].append(i)
        rescued = set()
        rest = combined[~combined.index.isin(matched)]
        for idx, key in zip(rest.index, fallback_key(rest)):
            bucket = fallback.get(key)
            if bucket:
                _take(idx, bucket.popleft())
                rescued.add(idx)
                result["rescued"] += 1

        # A replacement card's repeat of a charge, now counted once: its
        # label is already on the remaining row
        if linked:
            have = defaultdict(set)
            for key, mc, sc in zip(fallback_key(combined), combined["master_category"], combined["sub_category"]):
                have[key].add((mc or "", sc or ""))
            # How many prior rows of a charge were a second number's copy: all
            # its linked prior rows less the most any one number had. Only that
            # many leftovers are duplicates; the rest are labels to keep.
            cards_all = old_master["card_last4"].fillna("").astype(str).str.strip()
            on_link = [(str(src), c) in linked for src, c in zip(old_master["source"], cards_all)]
            per_card = (pd.DataFrame({"key": fallback_key(old_master)[on_link], "card": cards_all[on_link]})
                        .groupby(["key", "card"]).size())
            spare_copies = (per_card.groupby(level="key").sum() - per_card.groupby(level="key").max()).to_dict()
            leftover = old_master[labeled & ~old_master.index.isin(used)]
            cards = cards_all[leftover.index]
            for i, key, src, card in zip(leftover.index, fallback_key(leftover), leftover["source"], cards):
                label = (old_master.at[i, "master_category"], old_master.at[i, "sub_category"])
                if ((str(src), card) in linked and label in have.get(key, ())
                        and spare_copies.get(key, 0) > 0):
                    spare_copies[key] -= 1
                    used.add(i)
                    result["merged"] += 1

        # Whatever's still unplaced is kept and reported, never silently dropped
        orphans = old_master[labeled & ~old_master.index.isin(used)]
        result["orphaned"] = len(orphans)
        # What this import added: rows neither carried nor rescued from the
        # old master. Computed before the sort below renumbers the index.
        fresh = combined.index.difference(list(matched | rescued))
        new_ids = [row_id(r) for r in combined.loc[fresh].to_dict("records")]
        print(f"  Categorization carried over for {result['carried']}/{len(combined)} row(s)"
              f"; {result['rescued']} rescued by the fallback match")
        if result["merged"]:
            print(f"  {result['merged']} label(s) were on a replacement card's repeat of a charge "
                  f"— the remaining copy carries them")

    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined.sort_values("date", inplace=True, ignore_index=True, kind="stable")
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    atomic_write_csv(combined[MASTER_COLUMNS], master_file)
    print(f"  Master file rebuilt with {len(combined)} rows -> {master_file}")

    # Only now that the new master is safely on disk may the orphan file change:
    # a failed master write must leave every not-yet-placed label where it was.
    # Best effort: the master — the part that matters — is already written, so
    # a locked orphan file (open in Excel) is a warning, not a failed rebuild;
    # the old file's labels are still offered to the next one.
    if orphans is not None:
        try:
            if orphans.empty:
                orphans_path(master_file).unlink(missing_ok=True)
            else:
                atomic_write_csv(orphans[MASTER_COLUMNS], orphans_path(master_file))
                print(f"  ⚠ {result['orphaned']} label(s) matched no transaction — saved to "
                      f"{orphans_path(master_file)}")
        except OSError as e:
            print(f"  ⚠ Could not update {orphans_path(master_file)} ({e}) — "
                  f"close it (Excel?) and Reload")

    # Record the import's new rows for the dashboard's "N new · K need you"
    # line — only when this import added any: a Reload that finds nothing new
    # must not wipe the record of the last real import.
    if new_ids:
        try:
            atomic_write_csv(pd.DataFrame({"row_id": new_ids}),
                             master_file.parent / LAST_IMPORT_NAME)
        except OSError as e:
            print(f"  ⚠ Could not record the last import ({e})")
    return result


def main(data_dir: Path | None = None):
    data_dir = data_dir or get_data_dir()
    if not data_dir:
        print("No data directory configured. Launch the dashboard to set one up.")
        return

    input_folder = data_dir / "RAW"
    output_file  = data_dir / "SORTED" / "combined_transactions.csv"
    master_file  = get_master_path(data_dir)

    # Restore a lost master before anything can return early: with RAW empty
    # the rebuild (which also restores) never runs
    restored = restore_if_missing(master_file)
    if restored:
        print(f"Master file was missing or empty — restored labels from backup {restored.name}")

    # A replacement card the user confirmed lives in linked_cards.csv. If that
    # file can't be read, importing would split the card again and count its
    # repeated charges twice — so stop before anything is written; the
    # dashboard says why (links_unreadable)
    links = read_links(master_file)
    if links is None:
        print("Import stopped: SORTED/linked_cards.csv can't be read — fix or close it, then reload.")
        return

    csv_files = [f for f in input_folder.rglob("*") if f.suffix.lower() == ".csv"]
    skipped: list[tuple[str, str]] = []
    if not csv_files:
        print(f"No CSV files found in {input_folder}")
        write_skipped(master_file, skipped)
        write_overlap_only(master_file, None)
        return

    print(f"Found {len(csv_files)} CSV file(s) in {input_folder}\n")

    groups: dict[tuple, list[pd.DataFrame]] = defaultdict(list)
    exported: dict[str, pd.Timestamp] = {}
    for f in csv_files:
        normalized = load_and_normalize(f, input_folder, skipped)
        if normalized is None or normalized.empty:
            continue
        # A card with no recent charges isn't behind if its export is recent
        named = filename_date(f.name)
        src = normalized["source"].iat[0]
        if named is not None and (src not in exported or named > exported[src]):
            exported[src] = named
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        # Account key includes institution so two institutions that export the
        # same CSV format (same source, blank card_last4) don't collapse into
        # one account and get merged as if they were re-exports of each other.
        key = (normalized["institution"].iat[0],
               normalized["source"].iat[0],
               normalized["card_last4"].iat[0])
        groups[key].append(normalized)

    # Recorded before anything below can return or fail: the header warning
    # must describe this run, not a stale one
    write_skipped(master_file, skipped)
    write_exported_through(master_file, exported)

    if not groups:
        print("No valid files were processed. Exiting.")
        write_overlap_only(master_file, None)
        return

    groups, linked = _link_replacement_cards(groups, master_file, links)

    before = sum(len(d) for file_dfs in groups.values() for d in file_dfs)

    # Merge each account's exports by date-range ownership, so re-downloaded
    # overlapping statements don't collapse genuine same-day repeat transactions.
    overlap_only: list[pd.DataFrame] = []
    combined = pd.concat(
        [_merge_by_coverage(file_dfs, overlap_only, check_all=(key[1], key[2]) in linked)
         for key, file_dfs in groups.items()],
        ignore_index=True,
    )
    after = len(combined)
    left_out = pd.concat(overlap_only, ignore_index=True) if overlap_only else None
    if left_out is not None:
        left_out = left_out.assign(date=left_out["date"].dt.strftime("%Y-%m-%d"))
        print(f"  ⚠ {len(left_out)} transaction(s) left out where two exports overlap, on dates "
              f"another export owns — listed in SORTED/overlap_only.csv")
    write_overlap_only(master_file, left_out)

    # Sort by date ascending
    combined.sort_values("date", inplace=True, ignore_index=True)

    # Write combined_transactions.csv (clean pipeline output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_file, index=False)

    print(f"\nPipeline complete.")
    print(f"  Rows before merge      : {before}")
    print(f"  Rows after merge       : {after}")
    print(f"  Collapsed as re-exported overlap: {before - after}")
    print(f"  Output saved to        : {output_file}")

    # Rebuild the master file, carrying forward existing categorization
    print(f"\nRebuilding master file...")
    rebuild_master(combined, master_file, linked=set(linked))


if __name__ == "__main__":
    main()
    import subprocess, sys
    subprocess.run([sys.executable, BASE_DIR / "app.py"])
