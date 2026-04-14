import pandas as pd
from pathlib import Path


# ── Predefined categories ─────────────────────────────────────────────────────
PREDEFINED_CATEGORIES = [
    # Expenses
    "Food & Dining",
    "Transport",
    "Utilities",
    "Rent/Mortgage",
    "Shopping",
    "Healthcare",
    "Entertainment",
    "Subscriptions",
    "Personal Care",
    # Income
    "Paycheck",
    "Transfer In",
    "Venmo/Zelle In",
    "Reimbursement",
    # Debit-specific
    "Transfer Out",
    "Credit Card Payment",
    "ATM Withdrawal",
]


def load_transactions(path: Path | str) -> pd.DataFrame:
    """
    Load edited_combined_transactions.csv and return a cleaned dataframe.

    - Parses dates
    - Computes effective_category: master_category if set, else bank category,
      else 'Uncategorized'
    - Ensures amount is numeric
    - Adds convenience columns: month, month_str, year
    """
    df = pd.read_csv(path, parse_dates=["date", "post_date"])

    # Ensure master_category column exists (safety for first run)
    if "master_category" not in df.columns:
        df["master_category"] = None

    # Normalize amount
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # Drop rows where amount couldn't be parsed
    df = df.dropna(subset=["amount"])

    # Clean category and master_category
    df["category"] = df["category"].fillna("").str.strip()
    df["master_category"] = df["master_category"].fillna("").str.strip()

    # effective_category: master overrides bank, fallback to Uncategorized
    df["effective_category"] = df.apply(
        lambda r: r["master_category"] if r["master_category"] != ""
                  else (r["category"] if r["category"] != "" else "Uncategorized"),
        axis=1,
    )

    # Convenience columns
    df["month"]     = df["date"].dt.to_period("M")
    df["month_str"] = df["date"].dt.strftime("%Y-%m")
    df["year"]      = df["date"].dt.year

    return df


def get_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Return only expense rows (negative amounts)."""
    return df[df["amount"] < 0].copy()


def get_income(df: pd.DataFrame) -> pd.DataFrame:
    """Return only income rows (positive amounts)."""
    return df[df["amount"] > 0].copy()


def monthly_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total expenses grouped by month.
    Returns: month_str, total_expenses (positive values).
    """
    expenses = get_expenses(df)
    grouped = (
        expenses
        .groupby("month_str")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = grouped["total_expenses"].abs()
    return grouped.sort_values("month_str")


def monthly_income(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total income grouped by month.
    Returns: month_str, total_income.
    """
    income = get_income(df)
    grouped = (
        income
        .groupby("month_str")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped.sort_values("month_str")


def yearly_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total expenses grouped by year.
    Returns: year, total_expenses (positive values).
    """
    expenses = get_expenses(df)
    grouped = (
        expenses
        .groupby("year")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = grouped["total_expenses"].abs()
    return grouped.sort_values("year")


def yearly_income(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total income grouped by year.
    Returns: year, total_income.
    """
    income = get_income(df)
    grouped = (
        income
        .groupby("year")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped.sort_values("year")


def expenses_by_category(df: pd.DataFrame, month_str: str = None) -> pd.DataFrame:
    """
    Total expenses grouped by effective_category.
    Optionally filter to a specific month (e.g. '2024-01').
    Returns: category, total_expenses (positive values).
    """
    expenses = get_expenses(df)
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
