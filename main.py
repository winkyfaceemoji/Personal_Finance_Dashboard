import re
from collections import defaultdict, deque
import pandas as pd
from pathlib import Path
from config import get_data_dir, get_master_path

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# Unified output schema
UNIFIED_COLUMNS = [
    "date", "post_date", "description", "amount", "original_category",
    "type", "balance", "memo", "check_or_slip", "source", "card_last4"
]

# Master file schema — unified + user-assigned columns
MASTER_COLUMNS = UNIFIED_COLUMNS + ["master_category", "sub_category"]

# Columns used to match a rebuilt row back to its prior categorization.
# card_last4 excluded: old rows lack it and would never match otherwise.
# User-assigned columns (master_category, sub_category) also excluded.
MATCH_COLUMNS = [c for c in UNIFIED_COLUMNS if c != "card_last4"]

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


def load_and_normalize(filepath: Path) -> pd.DataFrame | None:
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

    # Extract card last-4 from Chase filenames: Chase_XXXX_Activity...
    last4 = None
    m = re.search(r"Chase(\d{4})_", filepath.name, re.IGNORECASE)
    if m:
        last4 = m.group(1)
    result["card_last4"] = last4 if last4 else ""

    print(f"  [OK]   {filepath.name} -> {fmt}" + (f" (card ...{last4})" if last4 else ""))
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


def rebuild_master(combined: pd.DataFrame, master_file: Path) -> None:
    """
    Rebuild edited_combined_transactions.csv from the freshly-merged combined
    data, carrying forward existing master_category / sub_category
    assignments by matching each row's MATCH_COLUMNS key against the prior
    master file.

    Every unified-schema column is regenerated from RAW on every run — only
    the user-assigned categorization is preserved. A match key that occurs
    more times in the new combined data than in the prior master (e.g. a
    same-day repeat transaction an older, buggy ingest had collapsed away)
    inherits the category of an existing occurrence of that key, in order;
    any occurrence beyond what the prior master had is genuinely new and
    starts uncategorized.
    """
    combined = combined.copy()
    for col in ["date", "post_date"]:
        combined[col] = pd.to_datetime(combined[col], errors="coerce").dt.strftime("%Y-%m-%d")
    combined["master_category"] = None
    combined["sub_category"]    = None

    def row_key(d: pd.DataFrame) -> pd.Series:
        return d[MATCH_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    if master_file.exists():
        # Keep a rolling backup — this rebuild replaces the whole file.
        master_file.replace(master_file.with_suffix(".csv.bak"))
        old_master = pd.read_csv(master_file.with_suffix(".csv.bak"), dtype={"card_last4": str})
        if "category" in old_master.columns and "original_category" not in old_master.columns:
            old_master = old_master.rename(columns={"category": "original_category"})
        for col in ("master_category", "sub_category"):
            if col not in old_master.columns:
                old_master[col] = None
        for col in ["date", "post_date"]:
            if col in old_master.columns:
                old_master[col] = pd.to_datetime(old_master[col], errors="coerce").dt.strftime("%Y-%m-%d")

        categorization = defaultdict(deque)
        for key, mc, sc in zip(row_key(old_master), old_master["master_category"], old_master["sub_category"]):
            categorization[key].append((mc, sc))

        carried = 0
        for idx, key in zip(combined.index, row_key(combined)):
            bucket = categorization.get(key)
            if bucket:
                mc, sc = bucket.popleft()
                combined.at[idx, "master_category"] = mc
                combined.at[idx, "sub_category"]    = sc
                carried += 1
        print(f"  Categorization carried over for {carried}/{len(combined)} row(s)")

    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined.sort_values("date", inplace=True, ignore_index=True)
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    combined[MASTER_COLUMNS].to_csv(master_file, index=False)
    print(f"  Master file rebuilt with {len(combined)} rows -> {master_file}")


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
        normalized = load_and_normalize(f)
        if normalized is None or normalized.empty:
            continue
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        key = (normalized["source"].iat[0], normalized["card_last4"].iat[0])
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
