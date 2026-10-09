import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from main import MASTER_COLUMNS, UNIFIED_COLUMNS, rebuild_master
from Modules.labels import (
    LAST_IMPORT_NAME, label_rows, last_import_ids, row_id, row_ids, unlabeled_groups,
)
from Modules.safety import atomic_write_csv, backup_master, restore_backup, restore_if_missing
from Modules.transforms import load_transactions, period_totals

REPO = Path(__file__).resolve().parent.parent


def _master_df(rows):
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "card_last4"])
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    return df[MASTER_COLUMNS]


def _as_rows(master, idx):
    recs = master.loc[idx].to_dict("records")
    for r in recs:
        r["date"] = pd.Timestamp(r["date"])
        r["amount"] = float(r["amount"])
    return recs


def test_label_rows_twins_once_each():
    master = _master_df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, ""),
                         ("2025-03-02", "OTHER", -9.0, "")])
    out, n = label_rows(master, _as_rows(master, [0, 1]), "Expense", "Coffee")
    assert n == 2
    assert out["master_category"].tolist() == ["Expense", "Expense", ""]
    assert out.loc[0, "sub_category"] == "Coffee"


def test_label_rows_never_overwrites_a_labeled_twin():
    master = _master_df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, "")])
    master.loc[0, "master_category"] = "Income"            # hand-labeled twin
    out, n = label_rows(master, _as_rows(master, [1]), "Expense")
    assert n == 1 and out["master_category"].tolist() == ["Income", "Expense"]


def test_label_rows_card_aware():
    master = _master_df([("2025-03-01", "CAFE", -4.5, "0123"), ("2025-03-01", "CAFE", -4.5, "4567")])
    out, n = label_rows(master, _as_rows(master, [0]), "Expense")
    assert n == 1 and out["master_category"].tolist() == ["Expense", ""]


def test_restore_backup(tmp_path):
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    master.write_text("a\n1\n")
    b = backup_master(master)
    master.write_text("a\n2\n")
    restore_backup(b, master)
    assert master.read_text() == "a\n1\n"


def test_snapshot_survives_backup_rotation(tmp_path):
    from Modules.safety import list_backups, snapshot_master
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    master.write_text("a\n0\n")
    snap = snapshot_master(master)
    assert snap.name == f"before-labeling-{date.today().isoformat()}.csv"
    for i in range(1, 13):
        master.write_text(f"a\n{i}\n")
        backup_master(master, keep=3)
    assert snap.exists() and snap.read_text() == "a\n0\n"
    assert snap not in list_backups(master)
    master.unlink()
    restore_if_missing(master)                   # restores a rotating backup, never the snapshot
    assert master.read_text() != "a\n0\n"


def test_snapshot_kept_once_per_day(tmp_path):
    from Modules.safety import snapshot_master
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir()
    master.write_text("a\n0\n")
    first = snapshot_master(master)
    master.write_text("a\n1\n")                 # labeled, DONE, reopened the same day
    second = snapshot_master(master)
    assert second == first and first.read_text() == "a\n0\n"


def _combined(rows):
    df = pd.DataFrame(rows, columns=["date", "description", "amount"])
    for col in UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df["date"] = pd.to_datetime(df["date"])
    return df[UNIFIED_COLUMNS]


def test_last_import_records_only_new_rows(tmp_path):
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    a = ("2025-03-01", "CAFE", -4.5)
    b = ("2025-03-02", "BOOKS", -12.0)
    rebuild_master(_combined([a]), master)                       # first import: no record
    assert last_import_ids(master) is None
    rebuild_master(_combined([a, b]), master)
    ids = last_import_ids(master)
    expected = row_id({"date": pd.Timestamp(b[0]), "description": b[1], "amount": b[2],
                       "source": "Chase Credit", "card_last4": ""})
    assert ids == [expected]
    assert (master.parent / LAST_IMPORT_NAME).exists()
    rebuild_master(_combined([a, b]), master)                    # no-op Reload
    assert last_import_ids(master) == [expected]                 # still remembered


@pytest.fixture
def demo(tmp_path):
    from main import main as run_ingest
    data = tmp_path / "data"
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    run_ingest(data)
    return data / "SORTED" / "edited_combined_transactions.csv"


def test_labeling_a_group_raises_totals_by_exactly_its_amount(demo):
    rules = REPO / "rules.csv"
    df = load_transactions(demo, rules_path=rules)
    group = next(g for g in unlabeled_groups(df) if all(r["amount"] < 0 for r in g["rows"]))
    before = period_totals(df, "year")["exp"].sum()

    master = pd.read_csv(demo, dtype={"card_last4": str, "master_category": str, "sub_category": str})
    master, n = label_rows(master, group["rows"], "Expense")
    atomic_write_csv(master, demo)
    df2 = load_transactions(demo, rules_path=rules)

    assert n >= len({r["row_id"] for r in group["rows"]})
    assert period_totals(df2, "year")["exp"].sum() - before == pytest.approx(
        -sum(r["amount"] for r in group["rows"]))
    ids = {r["row_id"] for r in group["rows"]}
    assert (df2.loc[row_ids(df2).isin(ids), "master_category"] == "Expense").all()


def test_acceptance_label_top_groups_then_new_statement(demo, tmp_path):
    """The goal, end to end: labeling the top groups (remembering safe ones)
    shrinks the unreviewed dollars, loses or duplicates nothing, and the next
    statement's matching row is labeled by the new rule automatically."""
    from main import main as run_ingest
    from Modules.labels import add_rule, read_rules, rule_check
    from Modules.transforms import PREDEFINED_CATEGORIES as CATS
    rules = tmp_path / "rules.csv"
    shutil.copy(REPO / "rules.csv", rules)
    df = load_transactions(demo, rules_path=rules)
    n_rows, total = len(df), df["amount"].sum()
    unrev = lambda d: d.loc[~d["master_category"].isin(CATS), "amount"].abs().sum()
    before = unrev(df)

    groups = [g for g in unlabeled_groups(df) if not g["fallback"] and not g["mixed"]][:25]
    master = pd.read_csv(demo, dtype={"card_last4": str, "master_category": str, "sub_category": str})
    labeled, remembered = 0.0, []
    for g in groups:
        cat = "Expense" if g["total"] < 0 else "Income"
        master, n = label_rows(master, g["rows"], cat)
        assert n == sum(r["count"] for r in g["rows"])
        labeled += g["abs_total"]
        chk = rule_check(df, read_rules(rules), g)
        if chk["ok"] and add_rule(rules, chk["keyword"], cat):
            remembered.append(chk["keyword"])
    atomic_write_csv(master, demo)
    df2 = load_transactions(demo, rules_path=rules)

    assert len(df2) == n_rows and df2["amount"].sum() == pytest.approx(total)   # nothing lost or duplicated
    assert unrev(df2) <= before - labeled + 0.01
    buckets = sum(df2.loc[df2["master_category"] == c, "amount"].sum() for c in CATS)
    unrev_amt = df2.loc[~df2["master_category"].isin(CATS), "amount"].sum()
    assert buckets + unrev_amt == pytest.approx(total)                          # every row in one bucket
    assert remembered, "no top group was safe to remember"

    # Next week's statement: one row from a remembered merchant, two new ones
    kw = remembered[0]
    (demo.parent.parent / "RAW" / "Chase" / "Chase9999_Activity_20260110.CSV").write_text(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        f"01/05/2026,01/06/2026,{kw.upper()} 555,Shopping,Sale,-12.34,\n"
        "01/06/2026,01/07/2026,NEWSHOP ALPHA 1,Shopping,Sale,-20.00,\n"
        "01/07/2026,01/08/2026,NEWSHOP BETA 2,Shopping,Sale,-30.00,\n")
    run_ingest(demo.parent.parent)
    ids = last_import_ids(demo)
    df3 = load_transactions(demo, rules_path=rules)
    new = df3[row_ids(df3).isin(set(ids))]
    assert len(ids) == 3
    assert int(new["master_category"].isin(CATS).sum()) == 1                  # the rule caught it
