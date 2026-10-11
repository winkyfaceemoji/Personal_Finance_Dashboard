# tests/test_capital_one.py — the Discover card's exports since Capital One took it over
from pathlib import Path

import pandas as pd

from main import detect_format, normalize_capital_one_credit
from main import main as run_pipeline

HEADER = "Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit\n"
SAMPLE = HEADER + (
    "2026-09-08,2026-09-09,8255,ANTHROPIC* CLAUDE SUB,Merchandise,103.33,\n"
    "2026-09-02,2026-09-02,8255,CAPITAL ONE AUTOPAY PYMT,Payment/Credit,,21.78\n"
    "2026-08-16,2026-08-17,8255,ANTHROPIC* CLAUDE SUB,Merchandise,21.78,\n"
    "2026-08-14,2026-08-15,8255,OBSIDIAN,Internet,52.26,\n"
)


def _raw(tmp_path: Path, rel: str, text: str) -> None:
    f = tmp_path / "RAW" / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def _read(text: str) -> pd.DataFrame:
    from io import StringIO
    return pd.read_csv(StringIO(text), index_col=False)


def test_format_is_detected():
    assert detect_format(_read(SAMPLE)) == "capital_one_credit"
    chase = _read("Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
                  "01/06/2026,01/06/2026,CAFE,Food,Sale,-4.50,\n")
    assert detect_format(chase) == "chase_credit"


def test_charges_are_negative_and_payments_positive():
    out = normalize_capital_one_credit(_read(SAMPLE))
    assert out["amount"].tolist() == [-103.33, 21.78, -21.78, -52.26]
    assert out["date"].tolist()[0] == pd.Timestamp("2026-09-08")
    assert out["post_date"].tolist()[0] == pd.Timestamp("2026-09-09")
    assert out["original_category"].tolist()[1] == "Payment/Credit"
    # Same account as the Discover card it replaced
    assert set(out["source"]) == {"Discover Credit"}


def test_dollar_signs_commas_and_blank_rows():
    out = normalize_capital_one_credit(_read(
        HEADER + '2026-09-01,2026-09-02,8255,RENT,Other,"$1,250.00",\n'
                 "2026-09-03,2026-09-03,8255,NOTHING,Other,,\n"))
    assert out["amount"].iloc[0] == -1250.0
    assert pd.isna(out["amount"].iloc[1])


DISCOVER = ("Trans. Date,Post Date,Description,Amount,Category\n"
            "08/01/2026,08/02/2026,GROCER,40.00,Supermarkets\n"
            "08/16/2026,08/17/2026,ANTHROPIC CLAUDE SUB,21.78,Services\n"
            "08/20/2026,08/21/2026,GROCER,35.00,Supermarkets\n")


def test_overlap_with_discover_history_is_not_counted_twice(tmp_path):
    # Both exports hold Aug 14–20 (worded differently); the wider one owns
    # the dates they share, and each date's rows come from one file only
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "Discover/CapitalOne_2026-09.csv",
         SAMPLE + "2026-08-20,2026-08-21,8255,GROCER #12,Groceries,35.00,\n")
    run_pipeline(tmp_path)
    master = pd.read_csv(tmp_path / "SORTED" / "edited_combined_transactions.csv")
    assert set(master["source"]) == {"Discover Credit"}
    aug16 = master[master["date"] == "2026-08-16"]
    assert len(aug16) == 1                                        # one copy, not two
    assert master["date"].tolist() == ["2026-08-01", "2026-08-14", "2026-08-16", "2026-08-20",
                                       "2026-09-02", "2026-09-08"]


def test_labels_on_the_discover_history_survive_adding_capital_one(tmp_path):
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    run_pipeline(tmp_path)
    path = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master = pd.read_csv(path)
    master["master_category"] = "Expense"
    master.to_csv(path, index=False)

    _raw(tmp_path, "Discover/CapitalOne_2026-09.csv", HEADER + (
        "2026-09-08,2026-09-09,8255,ANTHROPIC* CLAUDE SUB,Merchandise,103.33,\n"))
    run_pipeline(tmp_path)
    master = pd.read_csv(path, keep_default_na=False)
    old = master[master["date"] < "2026-09-01"]
    assert len(old) == 3 and (old["master_category"] == "Expense").all()
    assert master.loc[master["date"] == "2026-09-08", "master_category"].tolist() == [""]
