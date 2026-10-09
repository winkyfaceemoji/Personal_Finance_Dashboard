# tests/test_rebuild.py
from pathlib import Path

import pandas as pd
import pytest

from main import MASTER_COLUMNS, UNIFIED_COLUMNS, rebuild_master
from main import main as run_pipeline
from Modules import safety
from Modules.safety import backup_master, list_backups, orphan_count, orphans_path


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


def test_changed_raw_field_keeps_label(master):
    # The bank re-maps the category on a later export: the exact key no
    # longer matches, the date/description/amount/source fallback does
    _write_master(master, [ROW + ("Expense", "Coffee")])
    changed = ("2025-03-01", "COFFEE SHOP", -4.5, "Dining")
    result = rebuild_master(_combined([changed]), master)
    out = pd.read_csv(master)
    assert out.loc[0, "sub_category"] == "Coffee"
    assert result["rescued"] == 1 and result["orphaned"] == 0


def test_unplaceable_label_is_reported_not_dropped(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [ROW + ("Expense", ""), gone + ("Expense", "Gifts")])
    result = rebuild_master(_combined([ROW]), master)
    assert result["orphaned"] == 1
    orphans = pd.read_csv(orphans_path(master))
    assert orphans.loc[0, "description"] == "OLD MERCHANT"
    assert orphans.loc[0, "sub_category"] == "Gifts"
    assert orphan_count(master) == 1


def test_orphans_survive_later_rebuilds_and_reattach(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [gone + ("Expense", "Gifts")])
    rebuild_master(_combined([ROW]), master)          # transaction missing from RAW
    rebuild_master(_combined([ROW]), master)          # a later reload must not forget it
    assert orphan_count(master) == 1

    result = rebuild_master(_combined([ROW, gone]), master)   # it's back
    out = pd.read_csv(master).set_index("description")
    assert out.loc["OLD MERCHANT", "sub_category"] == "Gifts"
    assert result["orphaned"] == 0
    assert not orphans_path(master).exists()


def test_unlabeled_old_rows_are_not_orphans(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [gone + ("", "")])
    assert rebuild_master(_combined([ROW]), master)["orphaned"] == 0


def test_old_master_without_memo_rescued_by_fallback(master):
    # Old-schema master has no memo column; the new export carries a memo,
    # so the exact key misses and the fallback key must place the label
    _write_master(master, [ROW + ("Expense", "Coffee")], drop=("memo",))
    combined = _combined([ROW])
    combined.loc[0, "memo"] = "card swipe"
    result = rebuild_master(combined, master)
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"
    assert result["rescued"] == 1


def test_failed_master_write_does_not_lose_prior_orphan(master, monkeypatch):
    # An orphaned label's transaction is back in RAW, but the master can't be
    # written (open in Excel): the orphan file must still hold the label
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [gone + ("Expense", "Gifts")])
    rebuild_master(_combined([ROW]), master)          # label orphaned
    assert orphan_count(master) == 1
    before = master.read_text()
    orphans_before = orphans_path(master).read_text()

    real_replace = safety.os.replace

    def locked_master(src, dst):
        if Path(dst).name == "edited_combined_transactions.csv":
            raise PermissionError("open in Excel")
        return real_replace(src, dst)
    monkeypatch.setattr(safety.os, "replace", locked_master)

    with pytest.raises(PermissionError):
        rebuild_master(_combined([ROW, gone]), master)  # would place the label
    assert orphans_path(master).read_text() == orphans_before
    assert "Gifts" in orphans_path(master).read_text()
    assert master.read_text() == before


# ── Unreadable master ─────────────────────────────────────────────────────────
# A torn or badly saved master must not be backed up: every failed run would
# otherwise push one more bad copy in and prune a good, labelled one out.

def test_unreadable_master_never_evicts_labelled_backups(master):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    rebuild_master(_combined([ROW]), master)          # good, labelled backup
    master.write_text('date,description\n"torn')       # unparseable (EOF in quotes)
    for _ in range(12):                                # e.g. a dozen Reload clicks
        with pytest.raises(Exception):
            rebuild_master(_combined([ROW]), master)
    assert any("Coffee" in b.read_text() for b in list_backups(master))


def test_empty_master_restored_from_backup(master):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    rebuild_master(_combined([ROW]), master)
    master.write_text("")                              # power loss mid-save
    result = rebuild_master(_combined([ROW]), master)
    assert result["restored_from"] is not None
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"


def test_unchanged_master_is_not_backed_up_again(master):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    rebuild_master(_combined([ROW]), master)
    rebuild_master(_combined([ROW]), master)
    n = len(list_backups(master, include_legacy=False))
    for _ in range(3):                                 # Reload with nothing new
        rebuild_master(_combined([ROW]), master)
    assert len(list_backups(master, include_legacy=False)) == n


# ── Orphan file trouble ───────────────────────────────────────────────────────
# The orphan file is a side report the user is told to open — often in
# Excel, which locks it on Windows and rewrites its dates as M/D/YYYY.

GONE = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")


def test_locked_orphan_file_does_not_fail_rebuild(master, monkeypatch, capsys):
    _write_master(master, [ROW + ("Expense", "Coffee"), GONE + ("Expense", "Gifts")])
    real_replace = safety.os.replace

    def locked_orphans(src, dst):
        if Path(dst).name == "orphaned_labels.csv":
            raise PermissionError("open in Excel")
        return real_replace(src, dst)
    monkeypatch.setattr(safety.os, "replace", locked_orphans)

    result = rebuild_master(_combined([ROW]), master)   # returns normally
    assert result["orphaned"] == 1
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"
    assert "orphaned_labels.csv" in capsys.readouterr().out


def test_stale_orphan_does_not_label_a_new_repeat(master):
    _write_master(master, [GONE + ("Expense", "Gifts")])
    rebuild_master(_combined([ROW]), master)          # label orphaned
    stale = orphans_path(master).read_text()
    rebuild_master(_combined([ROW, GONE]), master)    # re-attached...
    orphans_path(master).write_text(stale)            # ...but the file couldn't be removed

    result = rebuild_master(_combined([ROW, GONE]), master)
    assert result["orphaned"] == 0                    # not re-reported forever
    rebuild_master(_combined([ROW, GONE, GONE]), master)   # a genuinely new repeat
    subs = pd.read_csv(master).set_index("description").loc["OLD MERCHANT", "sub_category"]
    assert subs.fillna("").tolist() == ["Gifts", ""]


def test_excel_saved_orphans_still_reattach(master):
    _write_master(master, [GONE + ("Expense", "Gifts")])
    rebuild_master(_combined([ROW]), master)          # label orphaned
    o = pd.read_csv(orphans_path(master))
    o["date"], o["post_date"] = "2/1/2025", "2/1/2025"  # what Excel saves back
    o.to_csv(orphans_path(master), index=False)

    result = rebuild_master(_combined([ROW, GONE]), master)
    out = pd.read_csv(master).set_index("description")
    assert out.loc["OLD MERCHANT", "sub_category"] == "Gifts"
    assert result["orphaned"] == 0


def test_restore_runs_even_when_raw_is_empty(master):
    # main() returns early with nothing in RAW; the restore must not be skipped
    _write_master(master, [ROW + ("Expense", "Coffee")])
    backup_master(master)
    master.unlink()
    data_dir = master.parent.parent
    (data_dir / "RAW").mkdir()
    run_pipeline(data_dir)
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"


def test_statement_with_an_empty_column_still_imports(tmp_path):
    # A Chase card statement holding only payments has no Category in any row;
    # pandas reads that column as float NaN, which used to abort the whole import
    raw = tmp_path / "RAW" / "Chase"
    raw.mkdir(parents=True)
    (raw / "Chase3094_Activity_20260110.CSV").write_text(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        "01/06/2026,01/06/2026,AUTOMATIC PAYMENT - THANK,,Payment,1250.00,\n")
    run_pipeline(tmp_path)
    master = pd.read_csv(tmp_path / "SORTED" / "edited_combined_transactions.csv")
    assert master["description"].tolist() == ["AUTOMATIC PAYMENT - THANK"]
    assert master["amount"].tolist() == [1250.0]


def _raw_file(tmp_path, rel, text):
    p = tmp_path / "RAW" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


GOOD_CHASE = ("Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
              "01/06/2026,01/06/2026,CAFE,Food,Sale,-4.50,\n")


def test_unrecognized_and_broken_files_are_recorded_not_silent(tmp_path, monkeypatch):
    from Modules.safety import read_skipped
    import main as main_mod
    _raw_file(tmp_path, "Chase/Chase3094_Activity_20260110.CSV", GOOD_CHASE)
    _raw_file(tmp_path, "CapitalOne/CapitalOne_2026.csv",
              "Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit\n"
              "2026-01-05,2026-01-06,1234,SHOP,Merchandise,12.00,\n")

    # A normalizer that blows up on one file must skip that file, not the import
    real = main_mod.NORMALIZERS["discover_credit"]
    monkeypatch.setitem(main_mod.NORMALIZERS, "discover_credit",
                        lambda df: (_ for _ in ()).throw(ValueError("bad row")))
    _raw_file(tmp_path, "Discover/Discover-Statement-20260127.csv",
              "Trans. Date,Post Date,Description,Amount,Category\n01/05/2026,01/06/2026,X,1.00,Y\n")
    run_pipeline(tmp_path)
    monkeypatch.setitem(main_mod.NORMALIZERS, "discover_credit", real)

    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    assert pd.read_csv(master)["description"].tolist() == ["CAFE"]     # the good file imported
    skipped = dict(read_skipped(master))
    assert set(skipped) == {str(Path("CapitalOne/CapitalOne_2026.csv")),
                            str(Path("Discover/Discover-Statement-20260127.csv"))}
    assert skipped[str(Path("CapitalOne/CapitalOne_2026.csv"))] == "unrecognized format"
    assert "bad row" in skipped[str(Path("Discover/Discover-Statement-20260127.csv"))]

    # Fixed (or removed) files clear the record on the next run
    (tmp_path / "RAW" / "CapitalOne" / "CapitalOne_2026.csv").unlink()
    (tmp_path / "RAW" / "Discover" / "Discover-Statement-20260127.csv").unlink()
    run_pipeline(tmp_path)
    assert read_skipped(master) == []


def test_skipped_files_recorded_even_when_nothing_imports(tmp_path):
    from Modules.safety import read_skipped
    _raw_file(tmp_path, "Odd/odd.csv", "a,b\n1,2\n")
    run_pipeline(tmp_path)
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    assert read_skipped(master) == [(str(Path("Odd/odd.csv")), "unrecognized format")]
