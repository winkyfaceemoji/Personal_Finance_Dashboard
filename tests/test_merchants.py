"""Merchants (ADR 0025): the two merchant files, each row's merchant, merchant
rules on load, and the two-file save. Terms are in CONTEXT.md."""
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from Modules.merchants import (
    merchant_list, merchant_of, merchant_overview, read_merchants, remember, remember_check, restore_files,
    save_merchants, snapshot_files, sort_merchants,
)
from Modules.transforms import load_transactions


def _files(folder: Path, merchants: str, aliases: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "merchants.csv").write_text(merchants, encoding="utf-8")
    (folder / "merchant_aliases.csv").write_text(aliases, encoding="utf-8")
    return folder


AMAZON = ("merchant,master_category,sub_category,patterns,added\n"
          "Amazon,Expense,Shopping,amzn mktp,2026-10-22\n",
          "spelling,merchant,status\n"
          "amzn mktp us,Amazon,alias\n"
          "amazon prime,Amazon,alias\n")


def test_each_row_belongs_to_its_merchant_its_own_spelling_or_none(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    rows = pd.Series(["AMZN Mktp US*2K4AB1", "AMAZON PRIME*9XZ", "TRADER JOE S #552", "#48213"])
    assert merchant_of(rows, m).tolist() == ["Amazon", "Amazon", "trader joe s", ""]


def test_merchant_list_names_every_merchant_with_the_spellings_it_covers(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    rows = pd.Series(["AMZN Mktp US*2K4AB1", "TRADER JOE S #552", "TRADER JOE S #108", "#48213"])
    assert merchant_list(rows, m) == {"Amazon": ["amazon prime", "amzn mktp us"],
                                      "trader joe s": ["trader joe s"]}


def _master(folder: Path, rows) -> Path:
    path = folder / "edited_combined_transactions.csv"
    pd.DataFrame([{"date": d, "post_date": d, "description": desc, "amount": amt, "source": "Chase Credit",
                   "original_category": "", "master_category": lab, "sub_category": sub, "card_last4": "1111"}
                  for d, desc, amt, lab, sub in rows]).to_csv(path, index=False)
    return path


def test_rules_label_a_merchants_rows_on_load_and_a_hand_label_always_wins(tmp_path):
    sorted_dir = _files(tmp_path / "SORTED",
                        "merchant,master_category,sub_category,patterns,added\n"
                        "Amazon,Expense,Shopping,,\n"
                        "venmo payment,,Venmo,,\n",
                        "spelling,merchant,status\namzn mktp us,Amazon,alias\namazon prime,Amazon,alias\n")
    master = _master(sorted_dir, [
        ("2026-01-02", "AMZN Mktp US*2K4AB1", -20.0, "", ""),                 # rule labels it
        ("2026-01-03", "AMAZON PRIME*9XZ", 14.99, "Income", ""),             # hand label wins, no sub
        ("2026-01-04", "TRADER JOE S #552", -30.0, "", ""),                   # its merchant has no rule
        ("2026-01-05", "VENMO PAYMENT 1000000001 WEB ID: 3000000001", -8.0, "", ""),   # category only
    ])
    before = master.read_bytes()
    df = load_transactions(master)
    assert df["master_category"].tolist() == ["Expense", "Income", "", ""]
    assert df["sub_category"].tolist() == ["Shopping", "", "", "Venmo"]
    assert master.read_bytes() == before                                   # never written


def test_a_merchants_rule_wins_over_a_rules_csv_keyword(tmp_path):
    sorted_dir = _files(tmp_path / "SORTED", *AMAZON)
    master = _master(sorted_dir, [("2026-01-02", "AMZN Mktp US*2K4AB1", -20.0, "", "")])
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\namzn,Transfer,Moves\n", encoding="utf-8")
    df = load_transactions(master, rules_path=rules)
    assert (df["master_category"].iat[0], df["sub_category"].iat[0]) == ("Expense", "Shopping")


def test_saved_merchant_files_read_back_the_same(tmp_path):
    m = read_merchants(_files(tmp_path / "a", *AMAZON))
    save_merchants(tmp_path / "b", m.table, m.aliases, adding=True)
    again = read_merchants(tmp_path / "b")
    assert again.alias_of == {"amzn mktp us": "Amazon", "amazon prime": "Amazon"}
    assert again.table.to_dict("records") == m.table.to_dict("records")


def _refuse(monkeypatch, name):
    """os.replace refuses `name`, the way Windows does while Excel has it open."""
    real = os.replace

    def replace(src, dst):
        if Path(dst).name == name:
            raise PermissionError(13, "file is open in another program", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)


def test_a_refused_second_file_rolls_back_the_first_and_changes_nothing(tmp_path, monkeypatch):
    folder = _files(tmp_path, *AMAZON)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    m = read_merchants(folder)
    table = pd.concat([m.table, pd.DataFrame([{**dict.fromkeys(m.table.columns, ""), "merchant": "Steam",
                                                "master_category": "Expense"}])], ignore_index=True)
    aliases = pd.concat([m.aliases, pd.DataFrame([{"spelling": "steamgames.com", "merchant": "Steam",
                                                    "status": "alias"}])], ignore_index=True)
    _refuse(monkeypatch, "merchant_aliases.csv")                 # adding: merchants.csv goes first
    with pytest.raises(PermissionError, match="Nothing changed: merchant_aliases.csv is open in another program"):
        save_merchants(folder, table, aliases, adding=True)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before   # no temp files left either


def _mid_save_state(monkeypatch, folder):
    """What read_merchants would see if the app died between the two swaps."""
    seen, real = [], os.replace

    def replace(src, dst):
        if seen == [] and Path(dst).parent == folder and not Path(dst).name.startswith("."):
            seen.append("first")
        elif seen == ["first"]:
            m = read_merchants(folder)
            seen.append((m.problems, dict(m.alias_of)))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    return seen


def test_a_crash_between_the_two_swaps_leaves_valid_files(tmp_path, monkeypatch):
    m = read_merchants(_files(tmp_path, *AMAZON))
    steam = pd.DataFrame([{**dict.fromkeys(m.table.columns, ""), "merchant": "Steam", "master_category": "Expense"}])
    steam_alias = pd.DataFrame([{"spelling": "steamgames.com", "merchant": "Steam", "status": "alias"}])
    seen = _mid_save_state(monkeypatch, tmp_path)                 # adding a merchant and its spelling
    save_merchants(tmp_path, pd.concat([m.table, steam]), pd.concat([m.aliases, steam_alias]), adding=True)
    assert seen[1][0] == []                                       # half-done, yet nothing disagrees
    added = read_merchants(tmp_path)
    seen = _mid_save_state(monkeypatch, tmp_path)                 # and removing them again
    save_merchants(tmp_path, m.table, m.aliases, adding=False)
    assert seen[1][0] == [] and seen[1][1] == {"amzn mktp us": "Amazon", "amazon prime": "Amazon"}
    assert added.alias_of["steamgames.com"] == "Steam"


def test_disagreeing_files_fall_back_to_the_spelling_and_say_so(tmp_path):
    m = read_merchants(_files(tmp_path, AMAZON[0],
                              "spelling,merchant,status\n"
                              "steamgames.com,Steam,alias\n"          # Steam isn't in merchants.csv
                              "amzn mktp us,Amazon,alias\n"
                              "amazon prime,Amazon,alias\n"
                              "amazon prime,Prime Video,alias\n"))    # one spelling, two merchants
    rows = pd.Series(["STEAMGAMES.COM 4259522", "AMAZON PRIME*9XZ", "AMZN Mktp US*2K4AB1"])
    assert merchant_of(rows, m).tolist() == ["steamgames.com", "amazon prime", "Amazon"]
    assert m.problems == ["steamgames.com points at a merchant that doesn't exist (Steam)",
                          "amazon prime is filed under 2 merchants"]


REPO = Path(__file__).resolve().parent.parent


def test_demo_merchants_change_only_the_rows_they_mean_to(tmp_path):
    import contextlib
    import io
    import shutil

    from main import main as run_ingest
    data = tmp_path / "data"
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    with contextlib.redirect_stdout(io.StringIO()):
        run_ingest(data)
    master = data / "SORTED" / "edited_combined_transactions.csv"
    rules = REPO / "Test Data" / "SORTED" / "rules.csv"
    without = load_transactions(master, rules_path=rules)
    for name in ("merchants.csv", "merchant_aliases.csv"):
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    with_ = load_transactions(master, rules_path=rules)

    m = read_merchants(data / "SORTED")
    assert m.problems == []
    assert merchant_list(with_["description"], m)["Zelle received"] == [
        "zelle payment from alex morrow", "zelle payment from casey lin", "zelle payment from jordan rivers",
        "zelle payment from priya nandan", "zelle payment from sam okafor"]
    changed = (with_["master_category"] != without["master_category"]) | (
        with_["sub_category"] != without["sub_category"])
    assert set(with_.loc[changed, "description"]) == {"CITYLINE TRANSIT FARE"}     # the only new rule
    assert (with_.loc[changed, ["master_category", "sub_category"]] == ["Expense", "Transit"]).all().all()


def test_untrustworthy_rows_are_ignored_and_reported(tmp_path):
    m = read_merchants(_files(tmp_path,
                              "merchant,master_category,sub_category,patterns,added\n"
                              ",,,,\n"                                         # Excel's empty row
                              "Amazon,Expense,,,\n"
                              "Amazon,Income,,,\n"                             # listed twice
                              "Steam,Expense,,,\n",                            # no spellings yet
                              "spelling,merchant,status\n"
                              "AMZN  Mktp US,Amazon,alias\n"                   # typed by hand
                              "trader joe s,,alias\n"))                        # blank merchant
    rows = pd.Series(["AMZN Mktp US*2K4AB1", "TRADER JOE S #552"])
    assert merchant_of(rows, m).tolist() == ["Amazon", "trader joe s"]
    assert merchant_list(rows, m) == {"Amazon": ["amzn mktp us"], "Steam": [], "trader joe s": ["trader joe s"]}
    assert m.problems == ["Amazon is listed twice in merchants.csv (the first row is used)",
                          "trader joe s points at a merchant that doesn't exist ()"]


def test_an_unreadable_merchant_file_is_reported_not_fatal(tmp_path):
    sorted_dir = _files(tmp_path / "SORTED", *AMAZON)
    (sorted_dir / "merchants.csv").write_bytes(b"merchant\n\x81\x8d\x8f\x90\x9d\n")   # neither UTF-8 nor 1252
    m = read_merchants(sorted_dir)
    assert m.problems == ["merchants.csv can't be read, so no merchants are used"]
    assert merchant_of(pd.Series(["AMZN Mktp US*2K4AB1"]), m).tolist() == ["amzn mktp us"]
    master = _master(sorted_dir, [("2026-01-02", "AMZN Mktp US*2K4AB1", -20.0, "", "")])
    assert load_transactions(master)["master_category"].tolist() == [""]


def test_no_merchant_files_means_every_spelling_is_its_own_merchant(tmp_path):
    m = read_merchants(tmp_path)
    assert merchant_of(pd.Series(["AMZN Mktp US*2K4AB1"]), m).tolist() == ["amzn mktp us"]


# ── Remember (ticket 03) ──────────────────────────────────────────────────────

def test_remember_makes_a_merchant_of_an_unmerged_spelling(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    save_merchants(tmp_path, *remember(m, "trader joe s", ["trader joe s"], "Expense", "Groceries", "2026-10-22"),
                   adding=True)
    m2 = read_merchants(tmp_path)
    assert m2.alias_of["trader joe s"] == "trader joe s" and m2.problems == []
    assert m2.table.set_index("merchant").loc["trader joe s"].tolist() == [
        "Expense", "Groceries", "", "2026-10-22"]


def test_remember_sets_an_existing_merchants_label_and_keeps_its_category_when_none_is_given(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    save_merchants(tmp_path, *remember(m, "Amazon", ["amzn mktp us", "amazon prime"], "Transfer", "", "2026-10-22"),
                   adding=True)
    m2 = read_merchants(tmp_path)
    assert m2.table.set_index("merchant").loc["Amazon", ["master_category", "sub_category"]].tolist() == [
        "Transfer", "Shopping"]
    assert len(m2.aliases) == 2                      # nothing added twice


def test_remember_replaces_an_alias_it_couldnt_trust(tmp_path):
    m = read_merchants(_files(tmp_path, AMAZON[0], "spelling,merchant,status\nsteamgames.com,Steam,alias\n"))
    assert m.problems                                # Steam doesn't exist
    save_merchants(tmp_path, *remember(m, "steamgames.com", ["steamgames.com"], "Expense", "", "2026-10-22"),
                   adding=True)
    m2 = read_merchants(tmp_path)
    assert m2.problems == [] and m2.alias_of == {"steamgames.com": "steamgames.com"}


def _rows(*rows):
    return pd.DataFrame([{"date": pd.Timestamp(d), "description": desc, "amount": amt, "master_category": lab,
                          "sub_category": "", "source": "Chase Credit", "card_last4": "1111"}
                         for d, desc, amt, lab in rows])


def test_remember_looks_at_every_row_of_the_merchant_not_only_the_ones_shown():
    from Modules.labels import row_ids, unlabeled_groups
    df = _rows(("2026-01-05", "HARBOR OUTFITTERS", 40.0, ""),        # an older refund, still unlabeled
               ("2026-02-05", "HARBOR OUTFITTERS", -90.0, "Expense"),
               ("2026-03-05", "HARBOR OUTFITTERS", -60.0, ""))         # the last import's row
    m = read_merchants(None)
    shown = unlabeled_groups(df, only_row_ids=[row_ids(df).iat[2]], merchants=m)[0]
    assert not shown["mixed"]                        # REVIEW → shows only money out
    chk = remember_check(df, shown, m)
    assert chk["blocking"] and chk["reason"] == "money in and out among its unlabeled rows — label them one at a time"
    assert chk["months"] == 3                        # a regular: seen in Jan, Feb and Mar


def test_merchant_files_round_trip_through_undo_byte_for_byte(tmp_path):
    folder = _files(tmp_path / "a", *AMAZON)
    (folder / "merchants.csv").write_bytes("merchant,master_category\r\nCafé,Expense\r\n".encode("cp1252"))
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    saved = snapshot_files(folder)
    m = read_merchants(folder)
    save_merchants(folder, *remember(m, "Café", ["cafe x"], "Income", "", "2026-10-22"), adding=True)
    assert read_merchants(folder).version != m.version
    restore_files(folder, json.loads(json.dumps(saved)))    # through the browser and back
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


# ── All merchants (ticket 04) ─────────────────────────────────────────────────

def test_overview_sums_each_merchant_over_all_its_rows(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    df = _rows(("2024-02-01", "AMZN Mktp US*1", -20.0, "Expense"),
               ("2025-06-01", "AMAZON PRIME*2", -14.0, "Income"),         # labels differ
               ("2025-07-01", "AMAZON PRIME*3", 5.0, ""),                 # a refund
               ("2025-03-01", "TRADER JOE S #552", -30.0, "Expense"),
               ("2025-03-02", "#48213", -7.0, ""))                        # no merchant name
    items, nameless = merchant_overview(df, m)
    amazon = next(i for i in items if i["name"] == "Amazon")
    assert {k: amazon[k] for k in ("spellings", "label", "category", "patterns", "out", "inn", "rows", "labels",
                                   "has_rule")} == {
        "spellings": ["amazon prime", "amzn mktp us"], "label": "Expense", "category": "Shopping",
        "patterns": "amzn mktp", "out": 34.0, "inn": 5.0, "rows": 3, "labels": ["Expense", "Income"],
        "has_rule": True}
    assert (amazon["first"], amazon["last"]) == (pd.Timestamp("2024-02-01"), pd.Timestamp("2025-07-01"))
    joe = next(i for i in items if i["name"] == "TRADER JOE S")       # a bare spelling, in capitals
    assert (joe["has_rule"], joe["labels"], joe["out"]) == (False, ["Expense"], 30.0)
    assert nameless == {"rows": 1, "out": 7.0, "inn": 0.0}


def test_merchants_sort_by_spend_or_by_what_needs_attention(tmp_path):
    def item(name, out, labels=("Expense",), has_rule=True, suggestions=0):
        return {"name": name, "out": out, "inn": 0.0, "labels": list(labels), "has_rule": has_rule,
                "suggestions": suggestions}
    items = [item("Big", 900.0), item("Unruled", 50.0, has_rule=False), item("Mixed", 10.0, ("Expense", "Income")),
             item("Small", 5.0), item("Suggested", 1.0, suggestions=1)]
    assert [i["name"] for i in sort_merchants(items, "spend")] == ["Big", "Unruled", "Mixed", "Small", "Suggested"]
    # open suggestions, then labels that differ, then no rule, then by spend
    assert [i["name"] for i in sort_merchants(items, "attention")] == [
        "Suggested", "Mixed", "Unruled", "Big", "Small"]


def test_restoring_files_that_were_missing_removes_them(tmp_path):
    saved = snapshot_files(tmp_path)
    assert saved == {"merchants.csv": None, "merchant_aliases.csv": None}
    save_merchants(tmp_path, *remember(read_merchants(tmp_path), "x shop", ["x shop"], "Expense", "", "d"), adding=True)
    restore_files(tmp_path, saved)
    assert list(tmp_path.iterdir()) == [] and read_merchants(tmp_path).version == ""
