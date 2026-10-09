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


def test_amount_ignores_an_odd_latest_charge():
    # A prorated or fee charge from the same payee must not become "the rent"
    rows = _monthly("RENT CO", -1500.0) + [("2025-07-20", "RENT CO", -200.0)]
    (r,) = recurring_charges(_df(rows))
    assert r["amount"] == 1500.0 and r["yearly"] == 18000.0


def test_same_day_charges_are_not_summed():
    rows = _monthly("HULU 877", -7.99) + [("2025-06-15", "HULU 877", -7.99)]
    (r,) = recurring_charges(_df(rows))
    assert r["amount"] == 7.99


def test_transfers_are_not_charges():
    rows = (_monthly("ONLINE TRANSFER TO SAV XXXX1234", -500.0)        # unlabeled, looks like a transfer
            + _monthly("ACME SAVINGS XFER 1", -250.0))                  # a side of a transfer pair
    from Modules.labels import row_ids
    df = _df(rows)
    df["source"], df["card_last4"] = "Chase Debit", ""
    acme = df["description"].str.startswith("ACME")
    assert {r["merchant"] for r in recurring_charges(df)} == {"ACME SAVINGS XFER"}
    assert recurring_charges(df, exclude_row_ids=set(row_ids(df[acme]))) == []


def test_bimonthly_and_semiannual():
    water = [(d, "CITY WATER 7", -80.0) for d in ("2024-11-05", "2025-01-06", "2025-03-05", "2025-05-06")]
    car = [(d, "GEICO AUTO", -620.0) for d in ("2024-01-10", "2024-07-10", "2025-01-09")]
    found = {r["merchant"]: r for r in recurring_charges(_df(water + car), as_of=pd.Timestamp("2025-05-30"))}
    assert found["CITY WATER"]["cadence"] == "every 2 months" and found["CITY WATER"]["yearly"] == 480.0
    assert found["GEICO AUTO"]["cadence"] == "every 6 months" and found["GEICO AUTO"]["yearly"] == 1240.0


def test_missing_descriptions_are_skipped():
    rows = _monthly("NETFLIX.COM", -15.49)
    df = _df(rows)
    df.loc[0, "description"] = None
    assert [r["merchant"] for r in recurring_charges(df)] == ["NETFLIX.COM"]
