import pandas as pd
from pathlib import Path


# ── Predefined categories ─────────────────────────────────────────────────────
PREDEFINED_CATEGORIES = [
    "Expense",
    "Income",
    "Transfer",
]


def apply_auto_categories(df: pd.DataFrame, rules_path: Path | str | None) -> pd.DataFrame:
    """
    Apply keyword-based auto-categorization to rows that have no master_category.
    Rules are loaded from a CSV with 'keyword' and 'category' columns.
    First matching rule wins. master_category always takes precedence over rules.
    """
    if not rules_path or not Path(rules_path).exists():
        return df
    try:
        rules = pd.read_csv(rules_path)
    except Exception:
        return df
    if rules.empty or not {"keyword", "category"}.issubset(rules.columns):
        return df

    no_override = df["master_category"] == ""
    for _, rule in rules.iterrows():
        keyword  = str(rule["keyword"]).strip().lower()
        category = str(rule["category"]).strip()
        if not keyword or not category:
            continue
        matches = no_override & df["description"].str.lower().str.contains(keyword, regex=False, na=False)
        df.loc[matches, "effective_category"] = category
    return df


def load_transactions(path: Path | str, rules_path: Path | str | None = None) -> pd.DataFrame:
    """
    Load edited_combined_transactions.csv and return a cleaned dataframe.

    - Parses dates
    - Computes effective_category: master_category if set, else bank category,
      else 'Uncategorized'
    - Ensures amount is numeric
    - Adds convenience columns: month, month_str, year
    """
    df = pd.read_csv(path, parse_dates=["date", "post_date"], dtype={"card_last4": str})

    # Ensure master_category column exists (safety for first run)
    if "master_category" not in df.columns:
        df["master_category"] = None

    # Normalize amount
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # Drop rows where amount couldn't be parsed
    df = df.dropna(subset=["amount"])

    # Backward-compat: rename old column name if present
    if "category" in df.columns and "original_category" not in df.columns:
        df = df.rename(columns={"category": "original_category"})
    if "sub_category" not in df.columns:
        df["sub_category"] = None
    if "card_last4" not in df.columns:
        df["card_last4"] = ""

    # Clean original_category and master_category
    df["original_category"] = df["original_category"].fillna("").str.strip()
    df["master_category"]   = df["master_category"].fillna("").str.strip()
    df["sub_category"]      = df["sub_category"].fillna("")
    df["card_last4"]        = df["card_last4"].fillna("")

    # effective_category: master overrides bank, fallback to Uncategorized
    df["effective_category"] = df.apply(
        lambda r: r["master_category"] if r["master_category"] != ""
                  else (r["original_category"] if r["original_category"] != "" else "Uncategorized"),
        axis=1,
    )

    # Convenience columns
    df["month"]     = df["date"].dt.to_period("M")
    df["month_str"] = df["date"].dt.strftime("%Y-%m")
    df["year"]      = df["date"].dt.year

    apply_auto_categories(df, rules_path)
    return df


def get_expenses(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """Return only expense rows (negative amounts), skipping excluded categories."""
    mask = df["amount"] < 0
    if excluded:
        mask = mask & ~df["effective_category"].isin(excluded)
    return df[mask].copy()


def get_income(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """Return only income rows (positive amounts), skipping excluded categories."""
    mask = df["amount"] > 0
    if excluded:
        mask = mask & ~df["effective_category"].isin(excluded)
    return df[mask].copy()


def monthly_expenses(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """
    Total expenses grouped by month.
    Returns: month_str, total_expenses (positive values).
    """
    expenses = get_expenses(df, excluded)
    grouped = (
        expenses
        .groupby("month_str", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = grouped["total_expenses"].abs()
    return grouped  # already sorted by groupby(sort=True)


def monthly_income(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """
    Total income grouped by month.
    Returns: month_str, total_income.
    """
    income = get_income(df, excluded)
    grouped = (
        income
        .groupby("month_str", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped  # already sorted by groupby(sort=True)


def yearly_expenses(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """
    Total expenses grouped by year.
    Returns: year, total_expenses (positive values).
    """
    expenses = get_expenses(df, excluded)
    grouped = (
        expenses
        .groupby("year", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = grouped["total_expenses"].abs()
    return grouped  # already sorted by groupby(sort=True)


def yearly_income(df: pd.DataFrame, excluded: set | None = None) -> pd.DataFrame:
    """
    Total income grouped by year.
    Returns: year, total_income.
    """
    income = get_income(df, excluded)
    grouped = (
        income
        .groupby("year", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped  # already sorted by groupby(sort=True)


def expenses_by_category(df: pd.DataFrame, month_str: str = None, excluded: set | None = None) -> pd.DataFrame:
    """
    Total expenses grouped by effective_category.
    Optionally filter to a specific month (e.g. '2024-01').
    Returns: category, total_expenses (positive values).
    """
    expenses = get_expenses(df, excluded)
    if month_str:
        expenses = expenses[expenses["month_str"] == month_str]

    grouped = (
        expenses
        .groupby("effective_category")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"effective_category": "category", "amount": "total_expenses"})
    )
    grouped["total_expenses"] = grouped["total_expenses"].abs()
    return grouped.sort_values("total_expenses", ascending=False)


def get_uncategorized(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return all transactions where master_category is blank.
    Includes both expenses and income since either may need categorization.
    """
    return df[df["master_category"] == ""].copy()


def available_months(df: pd.DataFrame) -> list[str]:
    """Return a sorted list of all months present in the data."""
    return sorted(df["month_str"].dropna().unique().tolist())


def available_years(df: pd.DataFrame) -> list[int]:
    """Return a sorted list of all years present in the data."""
    return sorted(df["year"].dropna().astype(int).unique().tolist())


def available_categories(df: pd.DataFrame) -> list[str]:
    """
    Return a merged sorted list of predefined categories plus any
    custom categories already present in master_category.
    """
    custom = df["master_category"].dropna().unique().tolist()
    custom = [c for c in custom if c != ""]
    combined = sorted(set(PREDEFINED_CATEGORIES) | set(custom))
    return combined


def available_sources(df: pd.DataFrame) -> list[str]:
    """Return a sorted list of all sources present in the data."""
    return sorted(df["source"].dropna().unique().tolist())
