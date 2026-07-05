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
    Keyword-based auto-labeling driven by rules.csv
    (columns: keyword, master_category, sub_category — both labels optional,
    but a rule needs at least one; legacy files with a single 'category'
    column are read as master_category).

    Master labels:
    - Only rows with a blank master_category are labeled — a hand-assigned
      label always wins, and the first matching rule wins for a given row.
    - Rules whose master_category isn't one of PREDEFINED_CATEGORIES are
      skipped (a typo would otherwise create rows that every total ignores).

    Sub-categories:
    - A rule's sub_category fills any matching row whose own sub_category is
      blank, provided the rule's master_category (when it has one) agrees
      with the row's label — so a rule never puts its sub on a row the user
      labeled as something else. Sub-only rules (blank master) apply to any
      matching row; they exist for descriptions like "venmo payment" that are
      too ambiguous to master-label but still deserve a display category.

    Everything is applied in-memory on every load and never written to the
    master file, so editing rules.csv retroactively re-labels all history.
    """
    if not rules_path or not Path(rules_path).exists():
        return df
    try:
        rules = pd.read_csv(rules_path).fillna("")
    except Exception:
        return df
    if rules.empty or "keyword" not in rules.columns:
        return df
    if "master_category" not in rules.columns:
        rules["master_category"] = rules["category"] if "category" in rules.columns else ""
    if "sub_category" not in rules.columns:
        rules["sub_category"] = ""

    desc      = df["description"].str.lower()
    unlabeled = df["master_category"] == ""
    for _, rule in rules.iterrows():
        keyword = str(rule["keyword"]).strip().lower()
        mc      = str(rule["master_category"]).strip()
        sc      = str(rule["sub_category"]).strip()
        if not keyword or (mc and mc not in PREDEFINED_CATEGORIES) or (not mc and not sc):
            continue
        hits = desc.str.contains(keyword, regex=False, na=False)
        if mc:
            take = unlabeled & hits
            df.loc[take, "master_category"] = mc
            unlabeled = unlabeled & ~take
        if sc:
            fill = hits & (df["sub_category"] == "")
            if mc:
                fill = fill & (df["master_category"] == mc)
            df.loc[fill, "sub_category"] = sc
    return df


def load_transactions(path: Path | str, rules_path: Path | str | None = None) -> pd.DataFrame:
    """
    Load edited_combined_transactions.csv and return a cleaned dataframe.

    - Parses dates
    - Applies keyword auto-labeling rules to rows with no master_category
      (in-memory only; the master file keeps its blanks)
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
    df["sub_category"]      = df["sub_category"].fillna("").str.strip()
    df["card_last4"]        = df["card_last4"].fillna("")

    # Auto-labeling rules run before the derived columns below so that
    # effective_category and category_display pick up rule-assigned labels
    apply_auto_categories(df, rules_path)

    # effective_category: master overrides bank, fallback to Uncategorized
    df["effective_category"] = df.apply(
        lambda r: r["master_category"] if r["master_category"] != ""
                  else (r["original_category"] if r["original_category"] != "" else "Uncategorized"),
        axis=1,
    )

    # category_display: the transaction-level category shown in the Transactions
    # tab and used for the Spend by Category chart. Sub-category overrides the
    # bank's original category; master_category is not involved here since it
    # represents the broader "type of transaction" grouping, shown separately.
    df["category_display"] = df["sub_category"].where(
        df["sub_category"] != "", df["original_category"]
    )

    # Convenience columns
    df["month"]     = df["date"].dt.to_period("M")
    df["month_str"] = df["date"].dt.strftime("%Y-%m")
    df["year"]      = df["date"].dt.year
    return df


def get_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows labeled Expense in master_category.
    Unlabeled and Transfer rows are ignored — totals are label-based."""
    return df[df["master_category"] == "Expense"].copy()


def get_income(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows labeled Income in master_category.
    Unlabeled and Transfer rows are ignored — totals are label-based."""
    return df[df["master_category"] == "Income"].copy()


def monthly_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total expenses grouped by month.
    Returns: month_str, total_expenses (positive values; refund rows labeled
    Expense net against the total).
    """
    expenses = get_expenses(df)
    grouped = (
        expenses
        .groupby("month_str", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = -grouped["total_expenses"]
    return grouped  # already sorted by groupby(sort=True)


def monthly_income(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total income grouped by month.
    Returns: month_str, total_income.
    """
    income = get_income(df)
    grouped = (
        income
        .groupby("month_str", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped  # already sorted by groupby(sort=True)


def yearly_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total expenses grouped by year.
    Returns: year, total_expenses (positive values; refund rows labeled
    Expense net against the total).
    """
    expenses = get_expenses(df)
    grouped = (
        expenses
        .groupby("year", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_expenses"})
    )
    grouped["total_expenses"] = -grouped["total_expenses"]
    return grouped  # already sorted by groupby(sort=True)


def yearly_income(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total income grouped by year.
    Returns: year, total_income.
    """
    income = get_income(df)
    grouped = (
        income
        .groupby("year", sort=True)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_income"})
    )
    return grouped  # already sorted by groupby(sort=True)


def expenses_by_category(df: pd.DataFrame, month_str: str = None) -> pd.DataFrame:
    """
    Total expenses grouped by category_display (the same category shown in the
    Transactions tab: sub_category if set, else the bank's original category).
    Optionally filter to a specific month (e.g. '2024-01').
    Returns: category, total_expenses (positive values).
    """
    expenses = get_expenses(df)
    if month_str:
        expenses = expenses[expenses["month_str"] == month_str]
    expenses = expenses.copy()
    expenses["category_display"] = expenses["category_display"].where(
        expenses["category_display"] != "", "Uncategorized"
    )

    grouped = (
        expenses
        .groupby("category_display")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"category_display": "category", "amount": "total_expenses"})
    )
    grouped["total_expenses"] = -grouped["total_expenses"]
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
