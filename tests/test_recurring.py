import pandas as pd

from Modules.recurring import recurring_charges


def _df(rows):
    """rows: (date, description, amount[, master_category])."""
    df = pd.DataFrame([dict(date=r[0], description=r[1], amount=r[2],
                            master_category=r[3] if len(r) > 3 else "") for r in rows],
                      columns=["date", "description", "amount", "master_category"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _monthly(desc, amount, start="2025-01-15", n=6, label=""):
    return [(d.strftime("%Y-%m-%d"), desc, amount, label)
            for d in pd.date_range(start, periods=n, freq="MS") + pd.Timedelta(days=14)]


def test_monthly_subscription_found_with_yearly_cost():
    df = _df(_monthly("NETFLIX.COM 866-579-7172", -15.49))
    (r,) = recurring_charges(df)
    assert r["merchant"] == "NETFLIX.COM" and r["cadence"] == "monthly"
    assert r["amount"] == 15.49 and r["yearly"] == round(15.49 * 12, 2)
    assert r["count"] == 6 and r["active"]


def test_price_change_uses_the_latest_charge():
    rows = _monthly("SPOTIFY USA", -10.99, n=4) + _monthly("SPOTIFY USA", -11.99, start="2025-05-15", n=3)
    (r,) = recurring_charges(_df(rows))
    assert r["amount"] == 11.99


def test_yearly_and_quarterly():
    yearly = [("2023-03-02", "AMAZON PRIME*AB12", -139.0), ("2024-03-01", "AMAZON PRIME*CD34", -139.0),
              ("2025-03-03", "AMAZON PRIME*EF56", -139.0)]
    quarterly = [(d, "WATER UTILITY 99", -60.0) for d in
                 ("2024-06-10", "2024-09-09", "2024-12-10", "2025-03-11")]
    found = {r["merchant"]: r for r in recurring_charges(_df(yearly + quarterly), as_of=pd.Timestamp("2025-04-01"))}
    assert found["AMAZON PRIME"]["cadence"] == "yearly" and found["AMAZON PRIME"]["yearly"] == 139.0
    assert found["WATER UTILITY"]["cadence"] == "quarterly" and found["WATER UTILITY"]["yearly"] == 240.0


def test_irregular_or_variable_spending_is_not_a_subscription():
    groceries = [(d.strftime("%Y-%m-%d"), "KEY FOOD 123", -a) for d, a in
                 zip(pd.date_range("2025-01-01", periods=12, freq="9D"), [40, 85, 12, 60, 33, 90, 25, 70, 15, 55, 80, 20])]
    wild = [("2025-01-05", "GYM", -50.0), ("2025-02-04", "GYM", -50.0), ("2025-03-30", "GYM", -50.0),
            ("2025-04-02", "GYM", -50.0)]
    assert recurring_charges(_df(groceries + wild)) == []


def test_stopped_subscription_is_inactive():
    df = _df(_monthly("HULU 877", -7.99, start="2024-01-15", n=5)
             + [("2025-06-30", "CAFE", -4.0)])          # data runs much later
    (r,) = recurring_charges(df)
    assert not r["active"]


def test_income_transfers_and_two_charges_ignored():
    rows = (_monthly("PAYROLL ACME", 2000.0)                      # money in
            + _monthly("AUTOPAY CHASE CARD", -300.0, label="Transfer")
            + [("2025-01-10", "ADOBE", -20.0), ("2025-02-10", "ADOBE", -20.0)]    # only two
            + [("2023-05-01", "AMTRAK", -156.0), ("2024-05-03", "AMTRAK", -156.0)])  # same trip twice
    assert recurring_charges(_df(rows)) == []


def test_biggest_yearly_cost_first():
    rows = _monthly("NETFLIX.COM", -15.49) + _monthly("RENT CO", -1500.0)
    assert [r["merchant"] for r in recurring_charges(_df(rows))] == ["RENT CO", "NETFLIX.COM"]


def test_empty():
    assert recurring_charges(_df([])) == []
