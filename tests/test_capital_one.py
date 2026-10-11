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


def _master(tmp_path):
    return pd.read_csv(tmp_path / "SORTED" / "edited_combined_transactions.csv", keep_default_na=False)


def test_capital_one_folder_is_the_discover_account(tmp_path):
    # RAW/CapitalOne/ keeps the files apart on disk; they're still the Discover
    # card, so the dates both exports cover are counted once — Discover's copy
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "CapitalOne/CapitalOne_2026-09.csv",
         SAMPLE + "2026-08-20,2026-08-21,8255,GROCER #12,Groceries,35.00,\n")
    run_pipeline(tmp_path)
    master = _master(tmp_path)
    assert set(master["source"]) == {"Discover Credit"} and set(master["institution"]) == {"Discover"}
    assert master["date"].tolist() == ["2026-08-01", "2026-08-16", "2026-08-20", "2026-09-02", "2026-09-08"]
    assert master.loc[master["date"] == "2026-08-20", "description"].tolist() == ["GROCER"]


def test_a_charge_only_capital_one_has_is_reported_not_dropped_silently(tmp_path):
    from Modules.safety import read_overlap_only
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "CapitalOne/CapitalOne_2026-09.csv",
         SAMPLE + "2026-08-20,2026-08-21,8255,GROCER #12,Groceries,35.00,\n")
    run_pipeline(tmp_path)
    master_path = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    # Aug 14 OBSIDIAN is inside Discover's dates but not in its export; Aug 16
    # and Aug 20 are in both (worded differently) and aren't reported
    left = read_overlap_only(master_path)
    assert left["description"].tolist() == ["OBSIDIAN"]
    assert left["amount"].tolist() == [-52.26] and left["date"].tolist() == ["2026-08-14"]
    assert left["file"].tolist() == [str(Path("CapitalOne/CapitalOne_2026-09.csv"))]
    # Gone once the exports agree
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv",
         DISCOVER + "08/14/2026,08/15/2026,OBSIDIAN,52.26,Services\n")
    run_pipeline(tmp_path)
    assert read_overlap_only(master_path).empty


def test_a_wider_capital_one_export_never_takes_labeled_discover_dates(tmp_path):
    from Modules.safety import orphan_count
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    run_pipeline(tmp_path)
    path = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master = pd.read_csv(path)
    master["master_category"] = "Expense"
    master.to_csv(path, index=False)

    # "Download everything": Capital One reaching back past the Discover history
    _raw(tmp_path, "CapitalOne/CapitalOne_all.csv", HEADER + (
        "2026-09-08,2026-09-09,8255,ANTHROPIC* CLAUDE SUB,Merchandise,103.33,\n"
        "2026-08-20,2026-08-21,8255,GROCER #12,Groceries,35.00,\n"
        "2026-08-16,2026-08-17,8255,ANTHROPIC* CLAUDE SUB,Merchandise,21.78,\n"
        "2026-08-01,2026-08-02,8255,GROCER #12,Groceries,40.00,\n"
        "2026-07-03,2026-07-04,8255,BOOKSHOP,Merchandise,12.00,\n"))
    run_pipeline(tmp_path)
    master = _master(tmp_path)
    old = master[master["date"].between("2026-08-01", "2026-08-20")]
    assert len(old) == 3 and (old["master_category"] == "Expense").all()
    assert orphan_count(path) == 0
    assert master["date"].tolist() == ["2026-07-03", "2026-08-01", "2026-08-16", "2026-08-20", "2026-09-08"]


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


def test_a_charge_two_losing_exports_share_is_reported_once(tmp_path):
    from Modules.safety import read_overlap_only
    _raw(tmp_path, "Discover/Discover-AllAvailable.csv", DISCOVER)
    extra = "2026-08-14,2026-08-15,8255,OBSIDIAN,Internet,52.26,\n"
    _raw(tmp_path, "CapitalOne/a.csv", HEADER + extra)
    _raw(tmp_path, "CapitalOne/b.csv", HEADER + extra
         + "2026-08-16,2026-08-17,8255,ANTHROPIC* CLAUDE SUB,Merchandise,21.78,\n")
    run_pipeline(tmp_path)
    left = read_overlap_only(tmp_path / "SORTED" / "edited_combined_transactions.csv")
    assert left["description"].tolist() == ["OBSIDIAN"]


def test_overlapping_re_downloads_of_one_format_are_not_reported(tmp_path):
    from Modules.safety import overlap_path
    _raw(tmp_path, "Discover/Discover-AllAvailable.csv", DISCOVER)
    _raw(tmp_path, "Discover/Discover-Statement-a.csv",
         "Trans. Date,Post Date,Description,Amount,Category\n"
         "08/14/2026,08/15/2026,SOMETHING ELSE,9.99,Services\n")
    run_pipeline(tmp_path)
    assert not overlap_path(tmp_path / "SORTED" / "edited_combined_transactions.csv").exists()


def test_filename_dates():
    from main import filename_date
    today = pd.Timestamp("2026-10-11")
    assert filename_date("2026-10-10_transaction_download.csv", today) == pd.Timestamp("2026-10-10")
    assert filename_date("Chase3094_Activity20240411_20260411_20260411.CSV", today) == pd.Timestamp("2026-04-11")
    assert filename_date("Discover-Statement-20230527.csv", today) == pd.Timestamp("2023-05-27")
    assert filename_date("Chase4823_Activity_20250210.CSV", today) == pd.Timestamp("2025-02-10")
    assert filename_date("Discover-2026-YearToDateSummary.csv", today) is None
    assert filename_date("statement_20261301.csv", today) is None          # no month 13
    assert filename_date("export_20990101.csv", today) is None             # after today


def test_a_quiet_card_with_a_recent_download_is_not_behind(tmp_path):
    from Modules.safety import read_exported_through
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "CapitalOne/2026-10-10_transaction_download.csv", SAMPLE)
    _raw(tmp_path, "Chase/Chase3094_Activity_20261009.CSV",
         "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
         "10/09/2026,10/09/2026,CAFE,Food,Sale,-4.50,\n")
    run_pipeline(tmp_path)
    master_path = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    through = read_exported_through(master_path)
    assert through["Discover Credit"] == pd.Timestamp("2026-10-10")
    assert through["Chase Credit"] == pd.Timestamp("2026-10-09")
