import pandas as pd

from Modules.labels import TRANSFER_PAIR_DAYS, label_rows, row_ids, suspect_transfers, transfer_pairs


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


# ── Likely transfers labeled Expense / Income ─────────────────────────────────


def test_card_payment_labeled_expense_is_suspect():
    # The payment out of checking labeled Expense counts the card's purchases twice
    df = _df([PAY_OUT[:5] + ("Expense",), PAY_IN[:5] + ("Transfer",)])
    assert transfer_pairs(df) == []
    s = suspect_transfers(df)
    assert len(s) == 1
    p = s[0]
    assert p["out"]["label"] == "Expense" and p["in"]["label"] == "Transfer"
    assert [r["row_id"] for r in p["to_fix"]] == [row_ids(df).iloc[0]]
    assert p["counted"] == 500.0                     # dollars wrongly in totals


def test_suspect_fixes_every_non_transfer_side():
    df = _df([PAY_OUT[:5] + ("Expense",), PAY_IN[:5] + ("Income",)])
    p = suspect_transfers(df)[0]
    assert len(p["to_fix"]) == 2 and p["counted"] == 1000.0


def test_suspects_need_a_labeled_side_and_a_certain_match():
    assert suspect_transfers(_df([PAY_OUT, PAY_IN])) == []                     # plain pair, not suspect
    assert suspect_transfers(_df([PAY_OUT[:5] + ("Transfer",), PAY_IN[:5] + ("Transfer",)])) == []
    other_in = ("2025-03-05", "PAYMENT THANK YOU", 500.00, "Discover Credit", "", "")
    assert suspect_transfers(_df([PAY_OUT[:5] + ("Expense",), PAY_IN, other_in])) == []   # ambiguous


def test_label_rows_relabel_overwrites_only_the_named_row():
    master = pd.DataFrame({
        "date": ["2025-03-03", "2025-03-04"], "description": [PAY_OUT[1], "CAFE"],
        "amount": [-500.0, -4.5], "source": ["Chase Debit", "Chase Debit"],
        "card_last4": ["4823", "4823"], "master_category": ["Expense", "Expense"],
        "sub_category": ["", ""],
    })
    row = {"date": pd.Timestamp("2025-03-03"), "description": PAY_OUT[1], "amount": -500.0,
           "source": "Chase Debit", "card_last4": "4823", "count": 1}
    _, n = label_rows(master, [row], "Transfer")                  # default: labeled rows are safe
    assert n == 0
    _, n = label_rows(master, [row], "Transfer", relabel_from={"Income"})   # label changed since
    assert n == 0
    out, n = label_rows(master, [row], "Transfer", relabel_from={"Expense"})
    assert n == 1 and out["master_category"].tolist() == ["Transfer", "Expense"]


def test_pair_lists_matches_the_separate_calls():
    from Modules.labels import pair_lists
    df = _df([PAY_OUT[:5] + ("Expense",), PAY_IN,
              ("2025-04-01", "Payment to card", -20.0, "Chase Debit", "4823", ""),
              ("2025-04-02", "PAYMENT THANK YOU", 20.0, "Discover Credit", "", "")])
    assert pair_lists(df) == (transfer_pairs(df), suspect_transfers(df))


def test_unreadable_dismissals_are_never_overwritten(tmp_path):
    import pytest
    from Modules.labels import add_not_transfer, not_transfer_keys
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    bad = master.parent / "not_transfers.csv"
    bad.write_text("Pair Key\nabc\n")                  # header changed by hand
    assert not_transfer_keys(master) == set()
    with pytest.raises(KeyError):
        add_not_transfer(master, "new0000000")
    assert bad.read_text() == "Pair Key\nabc\n"


def test_not_a_transfer_is_remembered(tmp_path):
    from Modules.labels import add_not_transfer, not_transfer_keys
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    assert not_transfer_keys(master) == set()
    add_not_transfer(master, "abc123def0")
    add_not_transfer(master, "abc123def0")             # idempotent
    add_not_transfer(master, "ffff000011")
    assert not_transfer_keys(master) == {"abc123def0", "ffff000011"}
