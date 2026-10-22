"""Merchants (ADR 0025): the two merchant files, each row's merchant, merchant
rules on load, and the two-file save. Terms are in CONTEXT.md."""
import os
from pathlib import Path

import pandas as pd
import pytest

from Modules.merchants import merchant_list, merchant_of, read_merchants, save_merchants
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


def test_merchant_rules_label_rows_on_load_and_a_hand_label_always_wins(tmp_path):
    sorted_dir = _files(tmp_path / "SORTED",
                        "merchant,master_category,sub_category,patterns,added\n"
                        "Amazon,Expense,Shopping,,\n"
                        "venmo payment,,Venmo,,\n",
                        "spelling,merchant,status\namzn mktp us,Amazon,alias\namazon prime,Amazon,alias\n")
    master = _master(sorted_dir, [
        ("2026-01-02", "AMZN Mktp US*2K4AB1", -20.0, "", ""),                 # rule labels it
        ("2026-01-03", "AMAZON PRIME*9XZ", 14.99, "Income", ""),             # hand label wins, no sub
        ("2026-01-04", "TRADER JOE S #552", -30.0, "", ""),                   # no merchant rule
        ("2026-01-05", "VENMO PAYMENT 1000000001 WEB ID: 3000000001", -8.0, "", ""),   # category only
    ])
    before = master.read_bytes()
    df = load_transactions(master)
    assert df["master_category"].tolist() == ["Expense", "Income", "", ""]
    assert df["sub_category"].tolist() == ["Shopping", "", "", "Venmo"]
    assert master.read_bytes() == before                                   # never written


def test_a_merchant_rule_wins_over_an_old_text_rule(tmp_path):
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
    with pytest.raises(PermissionError):
        save_merchants(folder, table, aliases, adding=True)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before   # no temp files left either


def test_adding_writes_merchants_first_and_removing_writes_aliases_first(tmp_path, monkeypatch):
    m = read_merchants(_files(tmp_path, *AMAZON))
    order, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda s, d: (order.append(Path(d).name), real(s, d)))
    save_merchants(tmp_path, m.table, m.aliases, adding=True)
    save_merchants(tmp_path, m.table, m.aliases, adding=False)
    assert order == ["merchants.csv", "merchant_aliases.csv", "merchant_aliases.csv", "merchants.csv"]


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


def test_no_merchant_files_means_every_spelling_is_its_own_merchant(tmp_path):
    m = read_merchants(tmp_path)
    assert merchant_of(pd.Series(["AMZN Mktp US*2K4AB1"]), m).tolist() == ["amzn mktp us"]
