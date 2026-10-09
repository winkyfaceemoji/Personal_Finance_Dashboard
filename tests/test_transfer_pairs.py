import pandas as pd

from Modules.labels import TRANSFER_PAIR_DAYS, row_ids, transfer_pairs


def _df(rows):
    """rows: (date, description, amount, source, card_last4, master_category)."""
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "source",
                                     "card_last4", "master_category"])
    df["date"] = pd.to_datetime(df["date"])
    df["sub_category"] = ""
    return df


PAY_OUT = ("2025-03-03", "Payment to Chase card ending in 3094", -500.00, "Chase Debit", "4823", "")
PAY_IN = ("2025-03-04", "AUTOMATIC PAYMENT - THANK", 500.00, "Chase Credit", "3094", "")


def test_card_payment_pair_found():
    df = _df([PAY_OUT, PAY_IN, ("2025-03-05", "CAFE", -4.5, "Chase Credit", "3094", "")])
    pairs = transfer_pairs(df)
    assert len(pairs) == 1
    p = pairs[0]
    ids = row_ids(df)
    assert p["out"]["row_id"] == ids.iloc[0] and p["in"]["row_id"] == ids.iloc[1]
    assert p["amount"] == 500.0 and p["gap"] == 1
    assert [r["row_id"] for r in p["to_label"]] == [ids.iloc[0], ids.iloc[1]]
    assert len(p["key"]) == 10 and p["key"] == transfer_pairs(df)[0]["key"]   # stable


def test_same_account_is_not_a_transfer():
    # A refund on the same card is money back, not a move between accounts
    df = _df([("2025-03-03", "SHOP", -50.0, "Chase Credit", "3094", ""),
              ("2025-03-04", "SHOP REFUND", 50.0, "Chase Credit", "3094", "")])
    assert transfer_pairs(df) == []


def test_window_and_exact_amount():
    late = (pd.Timestamp(PAY_OUT[0]) + pd.Timedelta(days=TRANSFER_PAIR_DAYS + 1)).strftime("%Y-%m-%d")
    assert transfer_pairs(_df([PAY_OUT, (late,) + PAY_IN[1:]])) == []
    off_by_a_cent = PAY_IN[:2] + (500.01,) + PAY_IN[3:]
    assert transfer_pairs(_df([PAY_OUT, off_by_a_cent])) == []


def test_ambiguous_matches_are_skipped():
    # Two equal payments in: which one pairs with the payment out is a guess
    other_in = ("2025-03-05", "PAYMENT THANK YOU", 500.00, "Discover Credit", "", "")
    assert transfer_pairs(_df([PAY_OUT, PAY_IN, other_in])) == []
    # ...even when the competing candidate is already labeled
    labeled_in = other_in[:5] + ("Expense",)
    assert transfer_pairs(_df([PAY_OUT, PAY_IN, labeled_in])) == []


def test_identical_twins_are_ambiguous():
    assert transfer_pairs(_df([PAY_OUT, PAY_IN, PAY_IN])) == []


def test_labeled_sides():
    # One side already Transfer: only the other needs a label
    df = _df([PAY_OUT[:5] + ("Transfer",), PAY_IN])
    p = transfer_pairs(df)[0]
    assert [r["row_id"] for r in p["to_label"]] == [row_ids(df).iloc[1]]
    # Both Transfer: nothing to do
    assert transfer_pairs(_df([PAY_OUT[:5] + ("Transfer",), PAY_IN[:5] + ("Transfer",)])) == []
    # A side labeled Expense or Income is the user's call — left alone
    assert transfer_pairs(_df([PAY_OUT[:5] + ("Expense",), PAY_IN])) == []


def test_biggest_first():
    small_out = ("2025-04-01", "Payment to card", -20.0, "Chase Debit", "4823", "")
    small_in = ("2025-04-02", "PAYMENT THANK YOU", 20.0, "Discover Credit", "", "")
    pairs = transfer_pairs(_df([small_out, small_in, PAY_OUT, PAY_IN]))
    assert [p["amount"] for p in pairs] == [500.0, 20.0]


def test_empty():
    assert transfer_pairs(_df([])) == []
