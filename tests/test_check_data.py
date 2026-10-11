# tests/test_check_data.py — the read-only data check (check_data.py)
import io
from pathlib import Path

import pandas as pd

import check_data
from main import main as run_pipeline

DISCOVER = ("Trans. Date,Post Date,Description,Amount,Category\n"
            "08/01/2026,08/02/2026,GROCER,40.00,Supermarkets\n"
            "08/16/2026,08/17/2026,ANTHROPIC CLAUDE SUB,21.78,Services\n")
CAPITAL_ONE = ("Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit\n"
               "2026-08-16,2026-08-17,8255,ANTHROPIC* CLAUDE SUB,Merchandise,21.78,\n"
               "2026-09-08,2026-09-09,8255,ANTHROPIC* CLAUDE SUB,Merchandise,103.33,\n")


def _raw(tmp_path: Path, rel: str, text: str) -> None:
    f = tmp_path / "RAW" / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def _files(root: Path) -> dict:
    return {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def _report(tmp_path, **kw) -> str:
    out = io.StringIO()
    check_data.run(tmp_path, out=out, **kw)
    return out.getvalue()


def test_flags_one_card_split_across_two_accounts(tmp_path):
    # A lowercase "discover" folder: Capital One rows are filed under "Discover"
    _raw(tmp_path, "discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "CapitalOne/2026-10-10_transaction_download.csv", CAPITAL_ONE)
    report = _report(tmp_path)
    assert "SAME CARD, TWO ACCOUNTS" in report
    assert "(folder: discover)" in report and "(folder: Discover)" in report
    assert "Both cover 2026-08-16 … 2026-08-16" in report
    assert "discover: 1 discover_credit file → Discover Credit (folder: discover)" in report
    # Freshness per card: the download date stands in for where the data ends
    assert "Discover Credit: data ends 2026-09-08 · treated as up to date through 2026-10-10" in report
    assert "32 days later than the data" in report
    assert "first month Aug 2026 complete" in report


def test_no_warning_when_the_card_is_one_account(tmp_path):
    _raw(tmp_path, "Discover/Discover-Statement-20260827.csv", DISCOVER)
    _raw(tmp_path, "CapitalOne/2026-10-10_transaction_download.csv", CAPITAL_ONE)
    assert "✓ no card is split across two accounts" in _report(tmp_path)


def test_is_read_only_and_compares_saved_totals(tmp_path):
    _raw(tmp_path, "discover/Discover-Statement-20260827.csv", DISCOVER)
    run_pipeline(tmp_path)
    before_files = _files(tmp_path)
    saved = tmp_path.parent / f"{tmp_path.name}-before.csv"
    report = _report(tmp_path, save=saved)
    assert _files(tmp_path) == before_files                      # nothing in the data folder changed
    assert "Discover Credit: 2 rows" in report and "Unmatched labels" in report
    snap = pd.read_csv(saved, dtype={"month": str})
    assert snap["rows"].sum() == 2

    # Label one row by hand, then compare: the month's spending moved
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    m = pd.read_csv(master, keep_default_na=False)
    m.loc[m["description"] == "GROCER", "master_category"] = "Expense"
    m.to_csv(master, index=False)
    report = _report(tmp_path, against=saved)
    assert "Discover Credit 2026-08: rows 2→2 · spent $0.00→$40.00" in report

    # A missing saved file is reported, not a crash
    report = _report(tmp_path, against=tmp_path.parent / "no-such-file.csv")
    assert "can't read" in report and "save one first with --save" in report
