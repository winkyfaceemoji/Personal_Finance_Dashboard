import re
from collections import defaultdict, deque
import pandas as pd
from pathlib import Path
from config import get_data_dir, get_master_path
from Modules.safety import atomic_write_csv, backup_master, orphans_path, restore_if_missing

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


def detect_format(df: pd.DataFrame) -> str | None:
    """Detect which bank format a dataframe belongs to based on its columns."""
    cols = set(df.columns.str.strip())
    if CHASE_DEBIT_HEADERS.issubset(cols):
        return "chase_debit"
    elif CHASE_CREDIT_HEADERS.issubset(cols):
        return "chase_credit"
    elif DISCOVER_CREDIT_HEADERS.issubset(cols):
        return "discover_credit"
    return None


def normalize_chase_debit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chase Debit columns:
    Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #
    """
    out = pd.DataFrame(columns=UNIFIED_COLUMNS)
    out["date"]          = pd.to_datetime(df["Posting Date"], errors="coerce")
    out["post_date"]     = pd.to_datetime(df["Posting Date"], errors="coerce")
    out["description"]   = df["Description"].str.strip()
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce")
    out["original_category"] = None
    out["type"]          = df["Type"].str.strip()
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
    out["description"]   = df["Description"].str.strip()
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce")
    out["original_category"] = df["Category"].str.strip()
    out["type"]          = df["Type"].str.strip()
    out["balance"]       = None
    out["memo"]          = df["Memo"].astype(str).str.strip().replace("nan", None)
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
    out["description"]   = df["Description"].str.strip()
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce") * -1
    out["original_category"] = df["Category"].str.strip()
    out["type"]          = None
    out["balance"]       = None
    out["memo"]          = None
    out["check_or_slip"] = None
    out["source"]        = "Discover Credit"
    return out


NORMALIZERS = {
    "chase_debit":     normalize_chase_debit,
    "chase_credit":    normalize_chase_credit,
    "discover_credit": normalize_discover_credit,
}


def load_and_normalize(filepath: Path, input_folder: Path) -> pd.DataFrame | None:
    """Load a CSV, detect its format, and normalize it to the unified schema."""
    try:
        df = pd.read_csv(filepath, index_col=False)
        df.columns = df.columns.str.strip()
    except Exception as e:
        print(f"  [SKIP] Could not read {filepath.name}: {e}")
        return None

    fmt = detect_format(df)
    if fmt is None:
        print(f"  [SKIP] Unrecognized format: {filepath.name}")
        return None

    result = NORMALIZERS[fmt](df)

    # Institution = the top-level folder under RAW (folder-authoritative
    # identity). Files dropped directly in RAW get a blank institution.
    rel = filepath.relative_to(input_folder).parts
    institution = rel[0] if len(rel) > 1 else ""
    result["institution"] = institution

    # Extract card last-4 from Chase filenames: ChaseXXXX_Activity... (no
    # separator between "Chase" and the digits — the regex requires that)
    last4 = None
    m = re.search(r"Chase(\d{4})_", filepath.name, re.IGNORECASE)
    if m:
        last4 = m.group(1)
    result["card_last4"] = last4 if last4 else ""

    tag = f" [{institution}]" if institution else ""
    print(f"  [OK]   {filepath.name} -> {fmt}{tag}" + (f" (card ...{last4})" if last4 else ""))
    return result


def _merge_by_coverage(file_dfs: list[pd.DataFrame]) -> pd.DataFrame:
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
    transactions) wins any date it covers; ties broken by row count.
    """
    def span(d: pd.DataFrame) -> pd.Timedelta:
        valid = d["date"].dropna()
        return valid.max() - valid.min() if not valid.empty else pd.Timedelta(0)

    ordered = sorted(file_dfs, key=lambda d: (span(d), len(d)), reverse=True)

    covered: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    kept = []
    for d in ordered:
        already_covered = pd.Series(False, index=d.index)
        for lo, hi in covered:
            already_covered |= d["date"].between(lo, hi)
        new_rows = d[~already_covered]
        if not new_rows.empty:
            kept.append(new_rows)
            dated = new_rows["date"].dropna()
            if not dated.empty:
                covered.append((dated.min(), dated.max()))

    return pd.concat(kept, ignore_index=True) if kept else ordered[0].iloc[0:0]


def rebuild_master(combined: pd.DataFrame, master_file: Path) -> dict:
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

    def row_key(d: pd.DataFrame) -> pd.Series:
        return d[MATCH_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    def fallback_key(d: pd.DataFrame) -> pd.Series:
        amount = pd.to_numeric(d["amount"], errors="coerce").round(2).astype(str)
        parts = d[["date", "description", "source"]].fillna("").astype(str)
        parts["description"] = parts["description"].str.strip()
        return pd.Series(list(zip(parts["date"], parts["description"], amount, parts["source"])),
                         index=d.index)

    result = {"carried": 0, "rescued": 0, "orphaned": 0, "restored_from": None}
    orphans = None   # set once a prior master is read; written only after the master is

    restored = restore_if_missing(master_file)
    if restored:
        result["restored_from"] = restored
        print(f"  Master file was missing — restored labels from backup {restored.name}")

    if master_file.exists():
        backup_master(master_file)
        old_master = pd.read_csv(master_file, dtype={"card_last4": str})
        if "category" in old_master.columns and "original_category" not in old_master.columns:
            old_master = old_master.rename(columns={"category": "original_category"})
        # Masters written by older versions lack newer columns; a missing
        # column reads as blank rather than aborting the rebuild
        for col in MASTER_COLUMNS:
            if col not in old_master.columns:
                old_master[col] = None
        for col in ["date", "post_date"]:
            old_master[col] = pd.to_datetime(old_master[col], errors="coerce").dt.strftime("%Y-%m-%d")

        # Labels orphaned by earlier rebuilds get another chance every run —
        # appended after the master's own rows so those take precedence
        prior_orphans = orphans_path(master_file)
        if prior_orphans.exists():
            extra = pd.read_csv(prior_orphans, dtype={"card_last4": str})
            for col in MASTER_COLUMNS:
                if col not in extra.columns:
                    extra[col] = None
            old_master = pd.concat([old_master[MASTER_COLUMNS], extra[MASTER_COLUMNS]],
                                   ignore_index=True)

        old_master["master_category"] = old_master["master_category"].fillna("")
        old_master["sub_category"]    = old_master["sub_category"].fillna("")
        labeled = (old_master["master_category"] != "") | (old_master["sub_category"] != "")

        def _take(idx, i):
            combined.at[idx, "master_category"] = old_master.at[i, "master_category"] or None
            combined.at[idx, "sub_category"]    = old_master.at[i, "sub_category"] or None
            used.add(i)

        # Pass 1: exact key, in order (same-day repeats inherit in sequence)
        exact = defaultdict(deque)
        for i, key in zip(old_master.index, row_key(old_master)):
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
        rest = combined[~combined.index.isin(matched)]
        for idx, key in zip(rest.index, fallback_key(rest)):
            bucket = fallback.get(key)
            if bucket:
                _take(idx, bucket.popleft())
                result["rescued"] += 1

        # Whatever's still unplaced is kept and reported, never silently dropped
        orphans = old_master[labeled & ~old_master.index.isin(used)]
        result["orphaned"] = len(orphans)
        print(f"  Categorization carried over for {result['carried']}/{len(combined)} row(s)"
              f"; {result['rescued']} rescued by the fallback match")

    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined.sort_values("date", inplace=True, ignore_index=True, kind="stable")
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    atomic_write_csv(combined[MASTER_COLUMNS], master_file)
    print(f"  Master file rebuilt with {len(combined)} rows -> {master_file}")

    # Only now that the new master is safely on disk may the orphan file change:
    # a failed master write must leave every not-yet-placed label where it was
    if orphans is not None:
        if orphans.empty:
            orphans_path(master_file).unlink(missing_ok=True)
        else:
            atomic_write_csv(orphans[MASTER_COLUMNS], orphans_path(master_file))
            print(f"  ⚠ {result['orphaned']} label(s) matched no transaction — saved to "
                  f"{orphans_path(master_file)}")
    return result


def main(data_dir: Path | None = None):
    data_dir = data_dir or get_data_dir()
    if not data_dir:
        print("No data directory configured. Launch the dashboard to set one up.")
        return

    input_folder = data_dir / "RAW"
    output_file  = data_dir / "SORTED" / "combined_transactions.csv"
    master_file  = get_master_path(data_dir)

    csv_files = [f for f in input_folder.rglob("*") if f.suffix.lower() == ".csv"]
    if not csv_files:
        print(f"No CSV files found in {input_folder}")
        return

    print(f"Found {len(csv_files)} CSV file(s) in {input_folder}\n")

    groups: dict[tuple, list[pd.DataFrame]] = defaultdict(list)
    for f in csv_files:
        normalized = load_and_normalize(f, input_folder)
        if normalized is None or normalized.empty:
            continue
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        # Account key includes institution so two institutions that export the
        # same CSV format (same source, blank card_last4) don't collapse into
        # one account and get merged as if they were re-exports of each other.
        key = (normalized["institution"].iat[0],
               normalized["source"].iat[0],
               normalized["card_last4"].iat[0])
        groups[key].append(normalized)

    if not groups:
        print("No valid files were processed. Exiting.")
        return

    before = sum(len(d) for file_dfs in groups.values() for d in file_dfs)

    # Merge each account's exports by date-range ownership, so re-downloaded
    # overlapping statements don't collapse genuine same-day repeat transactions.
    combined = pd.concat(
        [_merge_by_coverage(file_dfs) for file_dfs in groups.values()],
        ignore_index=True,
    )
    after = len(combined)

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
    rebuild_master(combined, master_file)


if __name__ == "__main__":
    main()
    import subprocess, sys
    subprocess.run([sys.executable, BASE_DIR / "app.py"])
