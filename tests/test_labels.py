import pandas as pd

from Modules.labels import apply_label_import, read_import_csv


def _master():
    return pd.DataFrame({
        "date":            ["2024-03-15", "2024-03-15", "2024-03-16"],
        "description":     ["CAFE", "CAFE", "BOOKSHOP"],
        "amount":          [-1234.5, -1234.5, -12.0],
        "source":          ["Chase Credit"] * 3,
        "card_last4":      ["0123", "4567", "0123"],
        "master_category": ["", "", ""],
        "sub_category":    ["", "", ""],
    })


def _imp(**cols):
    return pd.DataFrame(cols).astype(str)


def test_reads_bom_and_windows_1252():
    assert read_import_csv("﻿description\nCAFÉ\n".encode("utf-8")).columns[0] == "description"
    assert read_import_csv("description\nCAFÉ\n".encode("cp1252")).iloc[0, 0] == "CAFÉ"


def test_excel_reformatted_values_still_match():
    imp = _imp(date=["3/15/2024"], description=["CAFE"], amount=["-$1,234.50"],
               source=["Chase Credit"], card_last4=["123"],
               master_category=["Expense"], sub_category=["Coffee"])
    out, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (1, 0)
    assert out.loc[0, "sub_category"] == "Coffee"      # card 0123 only
    assert out.loc[1, "sub_category"] == ""            # same purchase, other card


def test_parenthesised_negative_amount():
    imp = _imp(date=["2024-03-16"], description=["BOOKSHOP"], amount=["($12.00)"],
               source=["Chase Credit"], master_category=["Expense"])
    _, updated, _ = apply_label_import(_master(), imp)
    assert updated == 1


def test_blank_date_is_skipped_not_mass_applied():
    imp = _imp(date=[""], description=["CAFE"], amount=["-1234.5"],
               source=["Chase Credit"], master_category=["Transfer"])
    out, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (0, 1)
    assert (out["master_category"] == "").all()


def test_rows_without_labels_are_ignored_and_unmatched_counted():
    imp = _imp(date=["2024-03-15", "2024-01-01"], description=["CAFE", "NOWHERE"],
               amount=["-1234.5", "-1"], source=["Chase Credit"] * 2,
               master_category=["", "Expense"])
    _, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (0, 1)


def test_without_card_column_matches_every_card():
    imp = _imp(date=["2024-03-15"], description=["CAFE"], amount=["-1234.5"],
               source=["Chase Credit"], master_category=["Expense"])
    out, updated, _ = apply_label_import(_master(), imp)
    assert updated == 2 and (out.loc[:1, "master_category"] == "Expense").all()
