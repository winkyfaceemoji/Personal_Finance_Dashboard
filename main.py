import pandas as pd
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
INPUT_FOLDER = BASE_DIR / "Data" / "RAW"
OUTPUT_FILE  = BASE_DIR / "Data" / "SORTED" / "combined_transactions.csv"
MASTER_FILE  = BASE_DIR / "Data" / "SORTED" / "edited_combined_transactions.csv"

# Unified output schema
UNIFIED_COLUMNS = [
    "date", "post_date", "description", "amount", "category",
    "type", "balance", "memo", "check_or_slip", "source"
]

# Master file schema — same as unified + master_category
MASTER_COLUMNS = UNIFIED_COLUMNS + ["master_category"]

# Columns used to match existing rows when merging into the master file.
# All non-master_category columns must match exactly for a row to be
# considered already present (and have its master_category preserved).
MATCH_COLUMNS = UNIFIED_COLUMNS

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
    out["category"]      = None
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
    out["category"]      = df["Category"].str.strip()
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
    out["amount"]        = pd.to_numeric(df["Amount"], errors="coerce")
    out["category"]      = df["Category"].str.strip()
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

    print(f"  [OK]   {filepath.name} → {fmt}")
    return NORMALIZERS[fmt](df)


def merge_into_master(combined: pd.DataFrame) -> None:
    """
    Merge newly ingested transactions into edited_combined_transactions.csv.

    Rules:
    - If the master file doesn't exist yet, create it from combined with
      a blank master_category column.
    - For each row in combined, check if it already exists in the master
      file by matching ALL columns in MATCH_COLUMNS exactly.
    - Rows that already exist are left untouched (master_category preserved).
    - Rows that are genuinely new are appended with a blank master_category.
    """
    combined = combined.copy()

    # Normalise date columns to plain date strings for consistent comparison
    for col in ["date", "post_date"]:
        if col in combined.columns:
            combined[col] = pd.to_datetime(combined[col], errors="coerce").dt.strftime("%Y-%m-%d")

    if not MASTER_FILE.exists():
        # First run — create master file from scratch
        combined["master_category"] = None
        combined[MASTER_COLUMNS].to_csv(MASTER_FILE, index=False)
        print(f"  Master file created with {len(combined)} rows → {MASTER_FILE}")
        return

    # Load existing master file
    master = pd.read_csv(MASTER_FILE)

    # Normalise date columns in master for comparison
    for col in ["date", "post_date"]:
        if col in master.columns:
            master[col] = pd.to_datetime(master[col], errors="coerce").dt.strftime("%Y-%m-%d")

    # Build a set of tuples from the master for fast exact-match lookup
    # Use MATCH_COLUMNS only — master_category is intentionally excluded
    def row_key(df: pd.DataFrame) -> pd.Series:
        """Return a series of tuples representing each row's match key."""
        return df[MATCH_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    existing_keys = set(row_key(master))
    combined_keys = row_key(combined)

    new_mask    = ~combined_keys.isin(existing_keys)
    new_rows    = combined[new_mask].copy()
    new_rows["master_category"] = None

    if new_rows.empty:
        print(f"  No new transactions found. Master file unchanged.")
    else:
        master = pd.concat([master, new_rows[MASTER_COLUMNS]], ignore_index=True)

        # Re-sort by date ascending
        master["date"] = pd.to_datetime(master["date"], errors="coerce")
        master.sort_values("date", inplace=True, ignore_index=True)
        master["date"] = master["date"].dt.strftime("%Y-%m-%d")

        master.to_csv(MASTER_FILE, index=False)
        print(f"  {len(new_rows)} new transaction(s) added to master file → {MASTER_FILE}")


def main():
    csv_files = [f for f in INPUT_FOLDER.rglob("*") if f.suffix.lower() == ".csv"]
    if not csv_files:
        print(f"No CSV files found in {INPUT_FOLDER}")
        return

    print(f"Found {len(csv_files)} CSV file(s) in {INPUT_FOLDER}\n")

    frames = []
    for f in csv_files:
        normalized = load_and_normalize(f)
        if normalized is not None:
            frames.append(normalized)

    if not frames:
        print("No valid files were processed. Exiting.")
        return

    combined = pd.concat(frames, ignore_index=True)
    before   = len(combined)

    # Deduplicate across all unified columns
    dedup_cols = [c for c in UNIFIED_COLUMNS if c != "source"]
    combined.drop_duplicates(subset=dedup_cols, keep="first", inplace=True)
    after = len(combined)

    # Sort by date ascending
    combined.sort_values("date", inplace=True, ignore_index=True)

    # Write combined_transactions.csv (clean pipeline output)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_FILE, index=False)

    print(f"\nPipeline complete.")
    print(f"  Rows before dedup : {before}")
    print(f"  Rows after dedup  : {after}")
    print(f"  Duplicates removed: {before - after}")
    print(f"  Output saved to   : {OUTPUT_FILE}")

    # Merge into master file, preserving existing master_category assignments
    print(f"\nMerging into master file...")
    merge_into_master(combined)


if __name__ == "__main__":
    main()
