# tests/test_rebuild.py
import pandas as pd
import pytest

import main
from main import MASTER_COLUMNS, UNIFIED_COLUMNS, rebuild_master
from Modules import safety
from Modules.safety import backup_master, list_backups


def _combined(rows):
    """Freshly-merged pipeline output: (date, description, amount, original_category)."""
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "original_category"])
    for col in UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df["date"] = pd.to_datetime(df["date"])
    return df[UNIFIED_COLUMNS]


def _write_master(path, rows, drop=()):
    """Prior master with labels: rows of (date, description, amount,
    original_category, master_category, sub_category)."""
    df = pd.DataFrame(rows, columns=["date", "description", "amount",
                                     "original_category", "master_category", "sub_category"])
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df = df[[c for c in MASTER_COLUMNS if c not in drop]]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


@pytest.fixture
def master(tmp_path):
    return tmp_path / "SORTED" / "edited_combined_transactions.csv"


ROW = ("2025-03-01", "COFFEE SHOP", -4.5, "Food")


def test_labels_carry_and_backup_is_kept(master):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    rebuild_master(_combined([ROW]), master)
    out = pd.read_csv(master)
    assert out.loc[0, "master_category"] == "Expense"
    assert out.loc[0, "sub_category"] == "Coffee"
    assert len(list_backups(master, include_legacy=False)) == 1
    assert not master.with_suffix(".csv.bak").exists()   # old rename-away is gone


def test_old_schema_master_keeps_labels(master):
    # A master from an old version: no memo / institution columns, and the
    # bank category still under its legacy name "category"
    _write_master(master, [ROW + ("Expense", "")], drop=("memo", "institution"))
    old = pd.read_csv(master).rename(columns={"original_category": "category"})
    old.to_csv(master, index=False)

    rebuild_master(_combined([ROW]), master)
    assert pd.read_csv(master).loc[0, "master_category"] == "Expense"


def test_crash_during_write_leaves_master_intact(master, monkeypatch):
    _write_master(master, [ROW + ("Expense", "")])
    before = master.read_text()

    def locked(*_):
        raise PermissionError("open in Excel")
    monkeypatch.setattr(safety.os, "replace", locked)

    with pytest.raises(PermissionError):
        rebuild_master(_combined([ROW]), master)
    assert master.read_text() == before


def test_missing_master_restored_from_newest_backup(master, capsys):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    backup_master(master)
    master.unlink()                                  # e.g. a failed earlier run

    result = rebuild_master(_combined([ROW]), master)
    assert result["restored_from"] is not None
    assert "restored labels from backup" in capsys.readouterr().out
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"


def test_same_day_repeats_keep_order(master):
    _write_master(master, [ROW + ("Expense", "First"), ROW + ("Expense", "Second")])
    rebuild_master(_combined([ROW, ROW, ROW]), master)
    subs = pd.read_csv(master)["sub_category"].fillna("").tolist()
    assert subs == ["First", "Second", ""]          # third occurrence is new
