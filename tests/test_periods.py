import shutil
from pathlib import Path

import pandas as pd
import pytest

from Modules.transforms import (
    filter_period,
    load_transactions,
    period_label,
    period_short_label,
    period_summary,
    period_totals,
    to_period,
    unlabeled_summary,
    window_totals,
)

REPO = Path(__file__).resolve().parent.parent


def _df(rows):
    """Minimal frame shaped like load_transactions output."""
    df = pd.DataFrame(rows, columns=["date", "amount", "master_category"])
    df["date"] = pd.to_datetime(df["date"])
    df["source"] = "Test"
    return df


# ── Calendar ──────────────────────────────────────────────────────────────────

def test_weeks_run_monday_to_sunday():
    sun, mon = pd.Timestamp("2025-12-28"), pd.Timestamp("2025-12-29")
    assert sun.day_name() == "Sunday" and mon.day_name() == "Monday"
    assert to_period(sun, "week") != to_period(mon, "week")
    w = to_period("2025-12-24", "week")
    assert w.start_time == pd.Timestamp("2025-12-22")          # Monday
    assert w.end_time.normalize() == pd.Timestamp("2025-12-28")  # Sunday


def test_labels():
    assert period_label(to_period("2025-12-24", "week"), "week") == "Dec 22 – 28, 2025"
    assert period_label(to_period("2025-12-31", "week"), "week") == "Dec 29, 2025 – Jan 4, 2026"
    assert period_label(to_period("2025-09-30", "week"), "week") == "Sep 29 – Oct 5, 2025"
    assert period_label(to_period("2025-12-24", "month"), "month") == "Dec 2025"
    assert period_label(to_period("2025-12-24", "year"), "year") == "2025"
    assert period_short_label(to_period("2025-12-24", "week"), "week") == "Dec 22"
    assert period_short_label(to_period("2025-12-24", "month"), "month") == "Dec '25"


# ── Totals ────────────────────────────────────────────────────────────────────

def test_totals_are_label_based_and_refunds_net():
    df = _df([
        ("2025-03-03", -100.0, "Expense"),
        ("2025-03-04",   20.0, "Expense"),   # refund reduces spending
        ("2025-03-05", 1000.0, "Income"),
        ("2025-03-06", -500.0, "Transfer"),  # ignored
        ("2025-03-07",  -70.0, ""),          # unlabeled: ignored
    ])
    assert window_totals(df) == {"exp": 80.0, "inc": 1000.0, "net": 920.0}
    u = unlabeled_summary(df)
    assert (u["count"], u["total"], u["amount"]) == (1, 5, 70.0)


def test_gap_periods_are_zero_filled():
    df = _df([("2025-01-06", -10.0, "Expense"), ("2025-01-27", -30.0, "Expense")])
    weeks = period_totals(df, "week")
    assert len(weeks) == 4                      # Jan 6, 13, 20, 27
    assert weeks["exp"].tolist() == [10.0, 0.0, 0.0, 30.0]


def test_week_month_year_totals_agree():
    df = _df([
        ("2024-12-30",  -5.0, "Expense"),   # week spans the year boundary
        ("2025-01-02", -15.0, "Expense"),
        ("2025-01-31", 200.0, "Income"),
        ("2025-02-01", -40.0, "Expense"),
    ])
    for col in ("exp", "inc", "net"):
        totals = {f: period_totals(df, f)[col].sum() for f in ("week", "month", "year")}
        assert totals["week"] == pytest.approx(totals["month"]) == pytest.approx(totals["year"])
    # The Dec 30 – Jan 5 week holds spending from both years
    assert period_totals(df, "week").loc[to_period("2025-01-01", "week"), "exp"] == 20.0


# ── Summary (stat cards) ──────────────────────────────────────────────────────

def test_partial_period_compares_like_for_like():
    df = _df([
        ("2025-11-03", -100.0, "Expense"),
        ("2025-11-20", -900.0, "Expense"),   # after day 10: outside the to-date window
        ("2025-12-02", -150.0, "Expense"),
    ])
    s = period_summary(df, "month", to_period("2025-12-10", "month"), as_of="2025-12-10")
    assert s["partial"] and s["days_elapsed"] == 10 and s["days_total"] == 31
    assert s["cur"]["exp"] == 150.0
    assert s["prev"]["exp"] == 100.0             # Nov 1–10 only
    assert s["typical_full"]["exp"] == 1000.0    # the whole of November


def test_complete_period_and_typical_median():
    rows = [(f"2025-{m:02d}-15", -float(v), "Expense")
            for m, v in zip(range(1, 6), [100, 300, 200, 1000, 50])]
    df = _df(rows)
    may = to_period("2025-05-15", "month")
    s = period_summary(df, "month", may, as_of="2025-05-31")
    assert not s["partial"]
    assert s["cur"]["exp"] == 50.0
    assert s["prev"]["exp"] == 1000.0
    assert s["typical"]["exp"] == 250.0          # median of 100, 300, 200, 1000
    assert s["n_typical"] == 4


def test_first_period_has_no_comparison():
    df = _df([("2025-01-15", -10.0, "Expense")])
    s = period_summary(df, "month", to_period("2025-01-15", "month"), as_of="2025-01-31")
    assert s["prev"] is None and s["typical"] is None


def test_savings_rate():
    df = _df([("2025-01-10", 1000.0, "Income"), ("2025-01-11", -250.0, "Expense")])
    s = period_summary(df, "month", to_period("2025-01-10", "month"), as_of="2025-01-31")
    assert s["rate"] == pytest.approx(75.0)


# ── Bundled demo data, end to end ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def demo_df(tmp_path_factory):
    """Ingest a copy of Test Data/RAW and load it, without touching the repo."""
    from main import main as run_ingest
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    run_ingest(data)
    return load_transactions(data / "SORTED" / "edited_combined_transactions.csv",
                             rules_path=REPO / "rules.csv")


def test_demo_totals_agree_across_granularities(demo_df):
    expected = window_totals(demo_df)
    for freq in ("week", "month", "year"):
        t = period_totals(demo_df, freq)
        assert t["exp"].sum() == pytest.approx(expected["exp"])
        assert t["inc"].sum() == pytest.approx(expected["inc"])


def test_demo_period_filter_matches_totals(demo_df):
    t = period_totals(demo_df, "month")
    p = t.index[-1]
    assert window_totals(filter_period(demo_df, p))["exp"] == pytest.approx(t.loc[p, "exp"])


def test_demo_effective_category_never_blank(demo_df):
    assert (demo_df["effective_category"] != "").all()
