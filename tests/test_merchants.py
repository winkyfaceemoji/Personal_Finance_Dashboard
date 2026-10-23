"""Merchants (ADR 0025): the two merchant files, each row's merchant, merchant
rules on load, and the two-file save. Terms are in CONTEXT.md."""
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from Modules.merchants import (
    apply_conversion, convert_proposals, dismiss, find_merchant, freeze_keyword_labels, keep_past, label_changes,
    review_choices, rule_labels, valid_keywords, merchant_list, merchant_of, merchant_overview, merchants_from, merge,
    names_in_use, pattern_suggestions, read_merchants, remember, remember_check, rename, restore_files, save_change,
    save_merchants, set_patterns, snapshot_files, sort_merchants, split,
)
from Modules.transforms import load_transactions, read_rules_csv


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


def test_demo_merchants_give_what_the_old_keywords_gave_and_only_add_their_own(tmp_path, old_demo_rules):
    import contextlib
    import io
    import shutil

    from main import main as run_ingest
    data = tmp_path / "data"
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    with contextlib.redirect_stdout(io.StringIO()):
        run_ingest(data)
    master = data / "SORTED" / "edited_combined_transactions.csv"
    keywords = load_transactions(master, rules_path=old_demo_rules)
    for name in ("merchants.csv", "merchant_aliases.csv"):
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    with_ = load_transactions(master)

    m = read_merchants(data / "SORTED")
    assert m.problems == []
    assert merchant_list(with_["description"], m)["Zelle received"] == [
        "zelle payment from alex morrow", "zelle payment from casey lin", "zelle payment from jordan rivers",
        "zelle payment from priya nandan", "zelle payment from sam okafor"]
    changed = (with_["master_category"] != keywords["master_category"]) | (
        with_["sub_category"] != keywords["sub_category"])
    assert set(with_.loc[changed, "description"]) == {"CITYLINE TRANSIT FARE"}     # the only rule no keyword had
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


# ── Merge, split, rename (ticket 05) ──────────────────────────────────────────

VENMO = ("merchant,master_category,sub_category,patterns,added\nVenmo,,Venmo,venmo,\n",
         "spelling,merchant,status\nvenmo payment,Venmo,alias\nvenmo cashout,Venmo,alias\n"
         "zelle payment to alex morrow,Venmo,dismissed\n")


def test_merging_two_bare_spellings_names_the_new_merchant_after_the_bigger_spender(tmp_path):
    m = read_merchants(tmp_path)
    after = merchants_from(*merge(m, "wholefds usq", "wholefds ues", {"wholefds usq": 300.0, "wholefds ues": 900.0}))
    assert after.problems == []
    assert after.alias_of == {"wholefds usq": "wholefds ues", "wholefds ues": "wholefds ues"}


def test_a_merchant_made_by_a_merge_takes_its_highest_spend_spelling(tmp_path):
    m = read_merchants(_files(tmp_path, *VENMO))
    spend = {"venmo payment": 5500.0, "venmo cashout": 0.0, "atm withdrawal": 2200.0}
    after = merchants_from(*merge(m, "Venmo", "atm withdrawal", spend))
    assert after.alias_of == {s: "venmo payment" for s in ("venmo payment", "venmo cashout", "atm withdrawal")}
    assert after.problems == []


def test_merging_into_a_named_merchant_moves_every_spelling_and_drops_the_old_rule(tmp_path):
    m = read_merchants(_files(tmp_path, AMAZON[0] + "Prime Video,Income,,,\n",
                              AMAZON[1] + "prime video,Prime Video,alias\n"))
    after = merchants_from(*merge(m, "Prime Video", "Amazon", {}))
    assert after.alias_of == {"amzn mktp us": "Amazon", "amazon prime": "Amazon", "prime video": "Amazon"}
    assert after.table["merchant"].tolist() == ["Amazon"]          # its rule went with it
    assert after.problems == []


def test_one_spelling_of_a_merged_merchant_can_move_on_its_own(tmp_path):
    m = read_merchants(_files(tmp_path, AMAZON[0] + "Video,Expense,,,\n", AMAZON[1]))
    after = merchants_from(*merge(m, "amazon prime", "Video", {}))
    assert after.alias_of == {"amzn mktp us": "Amazon", "amazon prime": "Video"}
    assert sorted(after.table["merchant"]) == ["Amazon", "Video"]  # Amazon keeps its other spelling and rule


def test_dismissed_suggestions_follow_a_rename_or_merge(tmp_path):
    m = read_merchants(_files(tmp_path, *VENMO))
    table, aliases = rename(m, "Venmo", "Pay apps", in_use=set())
    assert aliases.query("status == 'dismissed'")["merchant"].tolist() == ["Pay apps"]
    # tying a dismissed spelling to that very merchant clears the dismissal
    _, aliases = merge(m, "zelle payment to alex morrow", "Venmo", {})
    assert (aliases["status"] == "dismissed").sum() == 0


def test_splitting_a_spelling_out_makes_it_its_own_merchant(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    after = merchants_from(*split(m, "amazon prime"))
    assert after.alias_of == {"amzn mktp us": "Amazon"}
    assert merchant_of(pd.Series(["AMAZON PRIME*9XZ"]), after).tolist() == ["amazon prime"]


def test_splitting_out_the_last_spelling_ends_the_merchant(tmp_path):
    m = read_merchants(_files(tmp_path, AMAZON[0], "spelling,merchant,status\namzn mktp us,Amazon,alias\n"))
    after = merchants_from(*split(m, "amzn mktp us"))
    assert after.table.empty and after.alias_of == {}


def test_renaming_keeps_the_rule_and_every_spelling(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    after = merchants_from(*rename(m, "Amazon", "Amazon (shopping)", in_use=set()))
    assert after.alias_of == {"amzn mktp us": "Amazon (shopping)", "amazon prime": "Amazon (shopping)"}
    assert after.table.set_index("merchant").loc["Amazon (shopping)", "master_category"] == "Expense"


def test_renaming_a_bare_spelling_gives_it_a_merchant_of_its_own(tmp_path):
    after = merchants_from(*rename(read_merchants(tmp_path), "trader joe s", "Trader Joe's", in_use=set()))
    assert after.alias_of == {"trader joe s": "Trader Joe's"} and after.problems == []


def test_a_rename_to_a_name_or_spelling_in_use_is_refused_whatever_its_case(tmp_path):
    m = read_merchants(_files(tmp_path, *AMAZON))
    in_use = names_in_use(m, ["trader joe s", "amzn mktp us", "amazon prime"])
    for taken in ("trader joe s", "TRADER JOE S", "amazon prime"):        # another merchant, or its own spelling
        with pytest.raises(ValueError, match=f"Another merchant or spelling is already called {taken}"):
            rename(m, "Amazon", taken, in_use)
    with pytest.raises(ValueError, match="That's already its name"):
        rename(m, "Amazon", "amazon", in_use)
    with pytest.raises(ValueError, match="A merchant needs a name"):
        rename(m, "Amazon", "  ", in_use)


def test_find_merchant_matches_a_typed_name_whatever_its_case():
    names = {"Amazon": "Amazon", "TRADER JOE S": "trader joe s"}
    assert find_merchant("trader Joe s", names) == "trader joe s"
    assert find_merchant(" amazon ", names) == "Amazon"
    assert find_merchant("nobody", names) is None


def _steps_state(monkeypatch, folder):
    """read_merchants at every moment a crash could stop a save: before each swap."""
    states, real = [], os.replace

    def replace(src, dst):
        if Path(dst).parent == Path(folder) and not Path(dst).name.startswith("."):
            states.append(read_merchants(folder).problems)
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    return states


@pytest.mark.parametrize("change", ["rename", "merge named into bare", "merge into named", "split", "bare into bare"])
def test_a_crash_at_any_point_of_a_change_leaves_files_that_agree(tmp_path, monkeypatch, change):
    m = read_merchants(_files(tmp_path, *VENMO))
    table, aliases = {
        "rename": lambda: rename(m, "Venmo", "Pay apps", in_use=set()),
        "merge named into bare": lambda: merge(m, "Venmo", "atm withdrawal", {"atm withdrawal": 1.0}),
        "merge into named": lambda: merge(m, "atm withdrawal", "Venmo", {}),
        "split": lambda: split(m, "venmo cashout"),
        "bare into bare": lambda: merge(m, "atm withdrawal", "atm cash", {}),
    }[change]()
    states = _steps_state(monkeypatch, tmp_path)
    save_change(tmp_path, m, table, aliases)
    assert states and all(p == [] for p in states)
    assert read_merchants(tmp_path).problems == []


def test_a_refused_second_save_of_a_two_step_change_puts_everything_back(tmp_path, monkeypatch):
    m = read_merchants(_files(tmp_path, *VENMO))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    table, aliases = rename(m, "Venmo", "Pay apps", in_use=set())
    real, calls = os.replace, []

    def replace(src, dst):
        calls.append(Path(dst).name)
        if len(calls) == 4:                       # the second save's second swap
            raise PermissionError(13, "Access is denied", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(PermissionError, match="Nothing changed: .* is open in another program"):
        save_change(tmp_path, m, table, aliases)
    monkeypatch.setattr(os, "replace", real)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_merging_into_a_spelling_of_another_merchant_merges_into_that_merchant(tmp_path):
    m = read_merchants(_files(tmp_path, *VENMO))
    after = merchants_from(*merge(m, "streamly.com", "venmo payment", {}))
    assert after.alias_of["streamly.com"] == "Venmo" and after.alias_of["venmo payment"] == "Venmo"


def test_a_locked_first_file_says_nothing_changed(tmp_path, monkeypatch):
    m = read_merchants(_files(tmp_path, *VENMO))
    real = os.replace

    def replace(src, dst):
        if Path(dst).name == "merchant_aliases.csv":                   # split writes the aliases first
            raise PermissionError(13, "Access is denied", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(PermissionError, match="Nothing changed: merchant_aliases.csv is open in another program"):
        save_change(tmp_path, m, *split(m, "venmo cashout"))


def test_label_changes_lists_what_a_change_would_relabel(tmp_path):
    before = read_merchants(_files(tmp_path, *AMAZON))
    hand = _rows(("2026-01-02", "AMZN Mktp US*1", -20.0, ""),           # labeled by Amazon's rule
                 ("2026-01-03", "AMZN Mktp US*2", -30.0, "Income"),     # a hand label: never moves
                 ("2026-01-04", "PRIME VIDEO", -9.0, ""))               # unlabeled
    after = merchants_from(*merge(before, "prime video", "Amazon", {}))
    assert label_changes(hand, before, after, None, None) == [
        {"from": "unlabeled", "to": "Expense · Shopping", "rows": 1, "dollars": 9.0}]


def test_label_changes_shows_a_category_that_goes_away(tmp_path):
    before = read_merchants(_files(tmp_path, *VENMO))
    hand = _rows(("2026-01-02", "VENMO PAYMENT 1", -20.0, ""))
    after = merchants_from(*rename(before, "Venmo", "Pay apps", in_use=set()))
    assert label_changes(hand, before, after, None, None) == []
    after = merchants_from(*split(before, "venmo payment"))
    assert label_changes(hand, before, after, None, None) == [
        {"from": "unlabeled · Venmo", "to": "unlabeled", "rows": 1, "dollars": 20.0}]


# ── Patterns and pattern suggestions (ticket 07) ──────────────────────────────

ZELLE = ("merchant,master_category,sub_category,patterns,added\n"
         "Zelle in,Income,,zelle payment from,\n"
         "Bakery,Expense,,bake | bread,\n",
         "spelling,merchant,status\n"
         "zelle payment from sam,Zelle in,alias\n"
         "zelle payment from jo,Bakery,dismissed\n")


def test_a_spelling_containing_a_pattern_is_suggested_never_joined(tmp_path):
    m = read_merchants(_files(tmp_path, *ZELLE))
    spellings = ["zelle payment from sam", "zelle payment from ann", "zelle payment from jo",
                 "little fern bakery", "corner bread bakery", "trader joe s"]
    assert pattern_suggestions(spellings, m) == {
        "zelle payment from ann": "Zelle in",      # contains Zelle in's pattern
        "zelle payment from jo": "Zelle in",       # dismissed for Bakery only, not for Zelle in
        "little fern bakery": "Bakery",
        "corner bread bakery": "Bakery",           # either of Bakery's patterns
    }                                              # sam is already Zelle in's; joe matches nothing
    assert merchant_of(pd.Series(["ZELLE PAYMENT FROM ANN"]), m).tolist() == ["zelle payment from ann"]


def test_a_dismissed_pattern_suggestion_stays_dismissed(tmp_path):
    m = read_merchants(_files(tmp_path, *ZELLE))
    m2 = merchants_from(*dismiss(m, "little fern bakery", "Bakery"))
    assert pattern_suggestions(["little fern bakery"], m2) == {}
    assert m2.alias_of.get("little fern bakery") is None             # dismissing joins nothing


def test_the_longest_matching_pattern_wins(tmp_path):
    m = read_merchants(_files(tmp_path, "merchant,master_category,sub_category,patterns,added\n"
                                        "Zelle,,,zelle,\nZelle in,Income,,zelle payment from,\n",
                              "spelling,merchant,status\n"))
    assert pattern_suggestions(["zelle payment from ann"], m) == {"zelle payment from ann": "Zelle in"}


def test_patterns_are_set_on_a_merchant_and_a_bare_spelling_gets_a_row(tmp_path):
    m = read_merchants(_files(tmp_path, *ZELLE))
    after = merchants_from(*set_patterns(m, "Bakery", " bakery |  | patisserie "))
    assert after.table.set_index("merchant").loc["Bakery", "patterns"] == "bakery | patisserie"
    after = merchants_from(*set_patterns(m, "trader joe s", "trader joe"))
    assert after.alias_of["trader joe s"] == "trader joe s"
    assert after.table.set_index("merchant").loc["trader joe s", "patterns"] == "trader joe"


def test_patterns_follow_a_merge_and_short_or_empty_ones_are_refused(tmp_path):
    m = read_merchants(_files(tmp_path, *ZELLE))
    after = merchants_from(*merge(m, "Bakery", "Zelle in", {}))
    assert after.table.set_index("merchant").loc["Zelle in", "patterns"] == "zelle payment from | bake | bread"
    with pytest.raises(ValueError, match="A pattern needs at least 3 letters: e"):
        set_patterns(m, "Bakery", "bake | e")
    with pytest.raises(ValueError, match="No patterns to save"):
        set_patterns(m, "trader joe s", " | ")


def test_suggestions_count_in_the_overview_and_needs_attention(tmp_path):
    m = read_merchants(_files(tmp_path, *ZELLE))
    df = _rows(("2026-01-02", "ZELLE PAYMENT FROM ANN", 20.0, ""), ("2026-01-03", "TRADER JOE S #1", -5.0, ""))
    items, _ = merchant_overview(df, m)
    by = {i["mkey"]: i for i in items}
    assert by["zelle payment from ann"]["suggestions"] == 1 and by["trader joe s"]["suggestions"] == 0
    assert by["zelle payment from ann"]["suggested"] == "Zelle in"


# ── Converting the old rules (ticket 08) ──────────────────────────────────────

def _keywords(*rows):
    return pd.DataFrame([dict(zip(["keyword", "master_category", "sub_category"], r)) for r in rows])


CONVERT_ROWS = (("2026-01-02", "ZELLE PAYMENT FROM ANN", 50.0, ""),
                ("2026-01-03", "ZELLE PAYMENT FROM BO", 20.0, ""),
                ("2026-01-04", "SQ *THE BEAN", -5.0, ""),
                ("2026-01-05", "SQ *THE EGG SHOP", -9.0, ""),
                ("2026-01-06", "VENMO PAYMENT 1", -8.0, ""))


def test_each_rule_proposes_one_merchant_with_the_spellings_it_matches_today(tmp_path):
    rules = _keywords(("zelle payment from", "Income", ""), ("sq *the", "Expense", ""), ("venmo", "", "Venmo"),
                      ("nothing matches this", "Expense", ""))
    props = convert_proposals(_rows(*CONVERT_ROWS), rules, read_merchants(tmp_path))
    assert [(p["keyword"], p["name"], p["label"], p["category"], p["spellings"]) for p in props] == [
        ("zelle payment from", "zelle payment from ann", "Income", "", ["zelle payment from ann", "zelle payment from bo"]),
        ("sq *the", "sq the egg shop", "Expense", "", ["sq the bean", "sq the egg shop"]),
        ("venmo", "venmo payment", "", "Venmo", ["venmo payment"]),
        ("nothing matches this", "nothing matches this", "Expense", "", []),   # kept as a pattern only
    ]


def test_keywords_that_stack_on_a_spelling_stay_stacked(tmp_path):
    # "cashout" labels it, then "venmo" adds a category to the same row: one merchant carries both
    rows = _rows(("2026-01-02", "VENMO CASHOUT", 40.0, ""), ("2026-01-03", "VENMO PAYMENT 1", -8.0, ""))
    props = convert_proposals(rows, _keywords(("cashout", "Income", ""), ("venmo", "", "Venmo")), read_merchants(tmp_path))
    assert [(p["keyword"], p["label"], p["category"], p["spellings"]) for p in props] == [
        ("cashout", "Income", "Venmo", ["venmo cashout"]),
        ("venmo", "", "Venmo", ["venmo payment"])]


def test_a_keyword_whose_spellings_end_up_labeled_differently_splits_in_two(tmp_path):
    rows = _rows(("2026-01-02", "ZELLE PAYMENT FROM ANN", 40.0, ""), ("2026-01-03", "ZELLE PAYMENT FROM DAD", 9.0, ""))
    rules = _keywords(("zelle payment from dad", "Transfer", ""), ("zelle payment from", "Income", ""),
                      ("dad", "", "Family"))
    props = convert_proposals(rows, rules, read_merchants(tmp_path))
    assert [(p["keyword"], p["label"], p["category"], p["spellings"]) for p in props] == [
        ("zelle payment from dad", "Transfer", "Family", ["zelle payment from dad"]),   # "dad" adds its category
        ("zelle payment from", "Income", "", ["zelle payment from ann"]),
        ("dad", "", "Family", [])]


def test_a_spelling_goes_to_the_first_rule_that_matches_it_and_never_one_already_merged(tmp_path):
    m = read_merchants(_files(tmp_path, "merchant,master_category,sub_category,patterns,added\nCafe,Expense,,,\n",
                              "spelling,merchant,status\nsq the bean,Cafe,alias\n"))
    props = convert_proposals(_rows(*CONVERT_ROWS), _keywords(("sq *the", "Expense", ""), ("egg", "Income", "")), m)
    assert [p["spellings"] for p in props] == [["sq the egg shop"], []]


def test_converting_keeps_every_label_the_rules_gave(tmp_path):
    rules_path = tmp_path / "rules.csv"
    rules_path.write_text("keyword,master_category,sub_category\nzelle payment from,Income,\nsq *the,Expense,\n"
                          "venmo,,Venmo\n", encoding="utf-8")
    m = read_merchants(tmp_path / "m")
    hand = _rows(*CONVERT_ROWS)
    props = convert_proposals(hand, read_rules_csv(rules_path), m)
    after = merchants_from(*apply_conversion(m, props))
    assert rule_labels(hand, after, None).equals(rule_labels(hand, m, rules_path))   # no keywords needed now
    assert after.table.set_index("merchant").loc["zelle payment from ann", "patterns"] == "zelle payment from"


def test_the_past_is_frozen_and_a_rule_that_would_move_it_is_dropped(tmp_path):
    rules_path = tmp_path / "rules.csv"
    # "maple street grocery 0142" labels only the 0142 store's rows of that spelling
    rules_path.write_text("keyword,master_category,sub_category\nmaple street grocery 0142,Expense,Groceries\n",
                          encoding="utf-8")
    hand = _rows(("2026-01-02", "MAPLE STREET GROCERY 0142", -20.0, ""),
                 ("2026-01-03", "MAPLE STREET GROCERY 0377", -30.0, ""))
    m = read_merchants(tmp_path / "m")
    frozen, shown, changed = freeze_keyword_labels(hand, m, rules_path)
    assert changed.tolist() == [True, False]
    assert frozen[["master_category", "sub_category"]].values.tolist() == [["Expense", "Groceries"], ["", ""]]
    props = convert_proposals(hand, read_rules_csv(rules_path), m)
    kept, dropped = keep_past(frozen, shown, m, props)
    assert dropped == 1 and (kept[0]["label"], kept[0]["category"]) == ("", "")   # it would label the 0377 row
    after = merchants_from(*apply_conversion(m, kept))
    assert rule_labels(frozen, after, None).equals(shown)


def test_a_spelling_a_merchant_is_named_after_is_never_taken_over(tmp_path):
    # A merchant row named exactly like a spelling owns it, with no alias row
    folder = tmp_path / "m"
    save_merchants(folder, pd.DataFrame([{"merchant": "sq little fern bakery", "master_category": "Expense",
                                          "sub_category": "Coffee", "patterns": "", "added": ""}]),
                   pd.DataFrame(columns=["spelling", "merchant", "status"]), True)
    m = read_merchants(folder)
    rules_path = tmp_path / "rules.csv"
    rules_path.write_text("keyword,master_category,sub_category\nlittle fern,Expense,Dining\n", encoding="utf-8")
    hand = _rows(("2026-01-02", "SQ *LITTLE FERN BAKERY", -6.0, ""), ("2026-01-09", "SQ *LITTLE FERN BAKERY", -7.0, ""))
    props = convert_proposals(hand, read_rules_csv(rules_path), m)
    assert [p["spellings"] for p in props] == [[]]
    frozen, kept, _ = freeze_keyword_labels(hand, m, rules_path)
    props, dropped = keep_past(frozen, kept, m, props)
    after = merchants_from(*apply_conversion(m, props))
    assert rule_labels(frozen, after, None).values.tolist() == [["Expense", "Coffee"]] * 2


def test_the_review_decides_what_past_rows_keep(tmp_path):
    rules_path = tmp_path / "rules.csv"
    rules_path.write_text("keyword,master_category,sub_category\nsq,Expense,Dining\nmaple street,Expense,\n",
                          encoding="utf-8")
    hand = _rows(("2026-01-02", "SQ *LITTLE FERN BAKERY", -6.0, ""),       # an accidental match
                 ("2026-01-03", "MAPLE STREET GROCERY", 30.0, ""))
    m = read_merchants(tmp_path / "m")
    defaults = convert_proposals(hand, read_rules_csv(rules_path), m)
    reviewed = [dict(defaults[0], spellings=[], label="", category=""),
                dict(defaults[1], label="Income")]
    choices = review_choices(defaults, reviewed)
    assert choices == {"sq little fern bakery": None, "maple street grocery": ("Income", "")}
    frozen, kept, stored = freeze_keyword_labels(hand, m, rules_path, choices)
    assert kept.values.tolist() == [["", ""], ["Income", ""]] and stored.tolist() == [False, True]
    assert frozen[["master_category", "sub_category"]].values.tolist() == [["", ""], ["Income", ""]]
    with pytest.raises(ValueError):
        review_choices(defaults, reviewed[:1])


def test_a_review_change_never_overwrites_a_hand_label(tmp_path):
    rules_path = tmp_path / "rules.csv"
    rules_path.write_text("keyword,master_category,sub_category\nbrightleaf,Expense,Health\n", encoding="utf-8")
    hand = _rows(("2026-01-02", "BRIGHTLEAF PHARMACY", -6.0, "Expense"),     # hand label; the keyword gave the category
                 ("2026-01-03", "BRIGHTLEAF PHARMACY", -7.0, ""))
    m = read_merchants(tmp_path / "m")
    defaults = convert_proposals(hand, read_rules_csv(rules_path), m)
    choices = review_choices(defaults, [dict(defaults[0], label="Income", category="Changed")])
    _, kept, _ = freeze_keyword_labels(hand, m, rules_path, choices)
    assert kept.values.tolist() == [["Expense", "Health"], ["Income", "Changed"]]


def test_conversion_names_clash_ignoring_case(tmp_path):
    folder = tmp_path / "m"
    save_merchants(folder, pd.DataFrame([{"merchant": "Venmo", "master_category": "", "sub_category": "Venmo",
                                          "patterns": "", "added": ""}]),
                   pd.DataFrame(columns=["spelling", "merchant", "status"]), True)
    prop = {"name": "venmo", "label": "Expense", "category": "", "pattern": "", "spellings": []}
    with pytest.raises(ValueError, match="already exists"):
        apply_conversion(read_merchants(folder), [prop])
    with pytest.raises(ValueError, match="Two merchants"):
        apply_conversion(read_merchants(tmp_path / "none"), [prop, dict(prop, name="VENMO")])


def test_default_names_never_collide(tmp_path):
    rows = _rows(("2026-01-02", "VENMO CASHOUT", 40.0, ""), ("2026-01-03", "VENMO PAYMENT 1", -8.0, ""))
    rules = _keywords(("venmo", "Expense", ""), ("venmo cashout", "Income", ""), ("venmo", "Transfer", ""))
    names = [p["name"] for p in convert_proposals(rows, rules, read_merchants(tmp_path))]
    assert len(set(n.casefold() for n in names)) == len(names) == 3


def test_only_keywords_loading_applies_count(tmp_path):
    rules = _keywords(("good", "Expense", ""), ("", "Income", ""), ("typo", "Expnse", ""), ("typo2", "Expnse", "Cat"),
                      ("cat only", "", "Cat"), ("spaced", "Expense ", " Fun "))
    got = valid_keywords(rules)
    assert [k["keyword"] for k in got] == ["good", "cat only", "spaced"]       # stripped, as loading strips
    assert (got[2]["label"], got[2]["category"]) == ("Expense", "Fun")


def test_the_review_can_split_spellings_out_drop_a_pattern_and_rename(tmp_path):
    m = read_merchants(tmp_path)
    props = convert_proposals(_rows(*CONVERT_ROWS), _keywords(("sq *the", "Expense", "")), m)
    props[0].update(name="The Bean", spellings=["sq the bean"], pattern="")
    after = merchants_from(*apply_conversion(m, props))
    assert after.alias_of == {"sq the bean": "The Bean"}                       # the egg shop is left on its own
    assert after.table.set_index("merchant").loc["The Bean", "patterns"] == ""
    with pytest.raises(ValueError, match="Two merchants would be called The Bean"):
        apply_conversion(m, props + [dict(props[0], spellings=[])])


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
