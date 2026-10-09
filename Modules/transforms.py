import re

import pandas as pd
from pathlib import Path


# ── Predefined categories ─────────────────────────────────────────────────────
PREDEFINED_CATEGORIES = [
    "Expense",
    "Income",
    "Transfer",
]


def normalize_description(text) -> str:
    """The one form rule keywords and descriptions are compared in: lower-case,
    '*' and '#' as spaces, whitespace collapsed. Bank exports pad descriptions
    ('venmo            payment') and glue processors to merchants
    ('PAYPAL *NETFLIX'), so raw substring matching misses or over-matches."""
    return re.sub(r"\s+", " ", re.sub(r"[*#]", " ", str(text).lower())).strip()


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

    Keywords and descriptions are compared after `normalize_description`.

    Everything is applied in-memory on every load and never written to the
    master file, so editing rules.csv retroactively re-labels all history.
    """
    if not rules_path or not Path(rules_path).exists():
        return df
    try:
        # utf-8-sig: Excel saves a BOM, which would otherwise hide the keyword column
        rules = pd.read_csv(rules_path, encoding="utf-8-sig").fillna("")
    except Exception:
        return df
    if rules.empty or "keyword" not in rules.columns:
        return df
    if "master_category" not in rules.columns:
        rules["master_category"] = rules["category"] if "category" in rules.columns else ""
    if "sub_category" not in rules.columns:
        rules["sub_category"] = ""

    desc      = df["description"].map(normalize_description)
    unlabeled = df["master_category"] == ""
    for _, rule in rules.iterrows():
        keyword = normalize_description(rule["keyword"])
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
    # institution predates older master files — backfill blank so callers can
    # rely on the column existing regardless of when the master was built
    if "institution" not in df.columns:
        df["institution"] = ""

    # Clean original_category and master_category
    df["original_category"] = df["original_category"].fillna("").str.strip()
    df["master_category"]   = df["master_category"].fillna("").str.strip()
    df["sub_category"]      = df["sub_category"].fillna("").str.strip()
    df["card_last4"]        = df["card_last4"].fillna("")

    # Auto-labeling rules run before the derived columns below so that
    # effective_category and category_display pick up rule-assigned labels
    apply_auto_categories(df, rules_path)

    # effective_category: master overrides bank, fallback to Uncategorized
    df["effective_category"] = (
        df["master_category"]
        .where(df["master_category"] != "", df["original_category"])
        .replace("", "Uncategorized")
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


# ── Periods (week / month / year) ─────────────────────────────────────────────
# Weeks run Monday → Sunday (ISO). Every period helper below takes one of
# these names; pandas does the calendar arithmetic via Period objects.
PERIOD_FREQS = {"week": "W-SUN", "month": "M", "year": "Y"}

# How many earlier periods make up "typical" (their median). Years use every
# earlier year in the data — there are rarely more than a handful.
TYPICAL_LOOKBACK = {"week": 12, "month": 12, "year": None}


def to_period(ts, freq: str) -> pd.Period:
    """The week / month / year period containing a timestamp."""
    return pd.Timestamp(ts).to_period(PERIOD_FREQS[freq])


def period_label(p: pd.Period, freq: str) -> str:
    """Human label for a period: 'Dec 22 – 28, 2025', 'Dec 2025', '2025'."""
    if freq == "year":
        return str(p.year)
    if freq == "month":
        return p.start_time.strftime("%b %Y")
    # Day numbers via .day, not %-d — that strftime flag doesn't exist on Windows
    s, e = p.start_time, p.end_time
    if s.year != e.year:
        return f"{s:%b} {s.day}, {s.year} – {e:%b} {e.day}, {e.year}"
    if s.month != e.month:
        return f"{s:%b} {s.day} – {e:%b} {e.day}, {e.year}"
    return f"{s:%b} {s.day} – {e.day}, {e.year}"


def period_short_label(p: pd.Period, freq: str) -> str:
    """Compact axis label: 'Dec 22' (week start), "Dec '25", '2025'."""
    if freq == "year":
        return str(p.year)
    if freq == "month":
        return p.start_time.strftime("%b '%y")
    return f"{p.start_time:%b} {p.start_time.day}"


def filter_window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    """Rows whose date falls in [start, end], both days inclusive."""
    start = pd.Timestamp(start).normalize()
    end   = pd.Timestamp(end).normalize()
    return df[(df["date"] >= start) & (df["date"] < end + pd.Timedelta(days=1))]


def filter_period(df: pd.DataFrame, p: pd.Period) -> pd.DataFrame:
    """Rows dated inside a period."""
    return filter_window(df, p.start_time, p.end_time)


def window_totals(df: pd.DataFrame) -> dict:
    """Label-based income / expenses / net for a slice of rows. Expenses are
    positive (refunds labeled Expense net against them), like monthly_expenses."""
    exp = -get_expenses(df)["amount"].sum()
    inc = get_income(df)["amount"].sum()
    return {"exp": float(exp), "inc": float(inc), "net": float(inc - exp)}


def period_totals(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Income / expenses / net for every period from the first to the last
    transaction date — gap periods included as zeros, so a week with no
    spending counts toward "typical" instead of silently disappearing.
    Index: Period. Columns: exp (positive), inc, net.
    """
    dates = df["date"].dropna()
    if dates.empty:
        return pd.DataFrame(columns=["exp", "inc", "net"],
                            index=pd.PeriodIndex([], freq=PERIOD_FREQS[freq]))
    alias = PERIOD_FREQS[freq]
    idx = pd.period_range(dates.min().to_period(alias), dates.max().to_period(alias), freq=alias)

    def _sum(rows: pd.DataFrame) -> pd.Series:
        return rows.groupby(rows["date"].dt.to_period(alias))["amount"].sum()

    out = pd.DataFrame(index=idx)
    out["exp"] = -_sum(get_expenses(df)).reindex(idx, fill_value=0.0)
    out["inc"] = _sum(get_income(df)).reindex(idx, fill_value=0.0)
    out = out.fillna(0.0)
    out["net"] = out["inc"] - out["exp"]
    return out


def previous_periods(p: pd.Period, freq: str, first: pd.Period) -> list[pd.Period]:
    """The periods "typical" is measured over: up to TYPICAL_LOOKBACK periods
    immediately before p, never earlier than the first period with data."""
    n = TYPICAL_LOOKBACK[freq]
    out, q = [], p - 1
    while q >= first and (n is None or len(out) < n):
        out.append(q)
        q -= 1
    return out


def to_date_totals(df: pd.DataFrame, p: pd.Period, days_elapsed: int) -> dict:
    """Totals for the first `days_elapsed` days of a period (capped at its end)
    — the like-for-like comparison for a period that is still in progress."""
    start = p.start_time.normalize()
    end   = min(start + pd.Timedelta(days=days_elapsed - 1), p.end_time.normalize())
    return window_totals(filter_window(df, start, end))


def period_summary(df: pd.DataFrame, freq: str, p: pd.Period, as_of) -> dict:
    """
    Everything the stat cards need for one period:

    - cur: totals for p (to date, if p is still in progress)
    - partial / days_elapsed / days_total: whether p ends after `as_of`, the
      latest transaction date, and how far into it the data reaches
    - prev: the previous period — truncated to the same number of days when
      p is partial, so a half-finished month isn't compared to a full one
    - typical: medians over previous_periods(), truncated the same way
    - typical_full: typical *full*-period totals (the pace target)
    - rate / prev_rate / typical_rate: savings rate (net ÷ income, %) — None
      when there's no income to divide by

    prev / typical are None when there is no earlier period in the data.
    """
    as_of      = pd.Timestamp(as_of).normalize()
    start      = p.start_time.normalize()
    days_total = (p.end_time.normalize() - start).days + 1
    partial    = start <= as_of < p.end_time.normalize()
    days       = (as_of - start).days + 1 if partial else days_total

    dates = df["date"].dropna()
    first = to_period(dates.min(), freq) if not dates.empty else p
    prevs = previous_periods(p, freq, first)

    def _totals(q: pd.Period) -> dict:
        return to_date_totals(df, q, days) if partial else window_totals(filter_period(df, q))

    def _rate(t: dict | None):
        return t["net"] / t["inc"] * 100 if t and t["inc"] > 0 else None

    cur  = _totals(p)
    prev = _totals(prevs[0]) if prevs else None

    typical = typical_full = typical_rate = None
    if prevs:
        hist = pd.DataFrame([_totals(q) for q in prevs])
        typical = hist.median().to_dict()
        rates = [r for r in (_rate(t) for t in hist.to_dict("records")) if r is not None]
        typical_rate = float(pd.Series(rates).median()) if rates else None
        full = pd.DataFrame([window_totals(filter_period(df, q)) for q in prevs])
        typical_full = full.median().to_dict()

    return {
        "cur": cur, "prev": prev, "typical": typical, "typical_full": typical_full,
        "rate": _rate(cur), "prev_rate": _rate(prev), "typical_rate": typical_rate,
        "partial": partial, "days_elapsed": days, "days_total": days_total,
        "prev_period": prevs[0] if prevs else None, "n_typical": len(prevs),
    }


def unlabeled_summary(df: pd.DataFrame) -> dict:
    """Rows with no valid label (not Expense / Income / Transfer): these are
    left out of every total, so the header reports their count and size."""
    rows = df[~df["master_category"].isin(PREDEFINED_CATEGORIES)]
    return {"count": int(len(rows)), "total": int(len(df)),
            "amount": float(rows["amount"].abs().sum())}


def source_freshness(df: pd.DataFrame) -> pd.Series:
    """Latest transaction date per source, newest first."""
    if df.empty:
        return pd.Series(dtype="datetime64[ns]")
    return df.groupby("source")["date"].max().sort_values(ascending=False)


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
