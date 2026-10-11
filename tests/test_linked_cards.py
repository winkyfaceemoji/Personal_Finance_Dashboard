# tests/test_linked_cards.py — a replacement card's repeated charges count once
import io
from pathlib import Path

import pandas as pd

import check_data
from main import main as run_pipeline
from Modules.linked_cards import LINK_COLUMNS, card_map, links_path, recent_links
from Modules.safety import orphan_count, read_overlap_only

HEAD = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"


def _row(day: str, desc: str, amount: float) -> str:
    d = pd.Timestamp(day)
    return f"{d:%m/%d/%Y},{d:%m/%d/%Y},{desc},Shopping,Sale,{amount:.2f},\n"


# 25 charges in Jan–Mar 2026: on the old card's export AND the new card's
SHARED = [(f"2026-{1 + i // 9:02d}-{2 + 3 * (i % 9):02d}", f"SHOP {i}", -(10 + i)) for i in range(25)]
OLD_ONLY = [(f"2025-{10 + i // 3:02d}-{5 + 9 * (i % 3):02d}", f"OLD {i}", -(5 + i)) for i in range(9)]
NEW_ONLY = [(f"2026-04-{2 + 3 * i:02d}", f"NEW {i}", -(20 + i)) for i in range(5)]


def _raw(tmp_path: Path, name: str, rows) -> None:
    f = tmp_path / "RAW" / "Chase" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(HEAD + "".join(_row(*r) for r in rows))


def _replacement(tmp_path, extra_new=()):
    # The old number's export runs to Mar 27; the new number's repeats Jan–Mar
    _raw(tmp_path, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED + [("2026-03-27", "LAST OLD", -3.0)])
    _raw(tmp_path, "Chase9956_Activity_20261010.csv",
         SHARED + [("2026-03-27", "LAST OLD", -3.0)]
         + list(extra_new) + NEW_ONLY)


def _master(tmp_path) -> pd.DataFrame:
    return pd.read_csv(tmp_path / "SORTED" / "edited_combined_transactions.csv",
                       dtype=str, keep_default_na=False)


def _links(tmp_path) -> pd.DataFrame:
    return pd.read_csv(tmp_path / "SORTED" / "linked_cards.csv", dtype=str, keep_default_na=False)


def _write_links(tmp_path, status):
    (tmp_path / "SORTED").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"source": "Chase Credit", "old_card": "6236", "new_card": "9956", "status": status,
                   "matched": "", "linked_on": ""}])[LINK_COLUMNS].to_csv(
        tmp_path / "SORTED" / "linked_cards.csv", index=False)


def test_a_replacement_cards_repeated_charges_count_once(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    m = _master(tmp_path)
    assert len(m) == len(OLD_ONLY) + len(SHARED) + 1 + len(NEW_ONLY)   # LAST OLD once
    assert (m.groupby(["date", "description", "amount"]).size() == 1).all()
    assert set(m["card_last4"]) == {"6236"}                                   # filed under the old number
    links = _links(tmp_path)
    assert links[["source", "old_card", "new_card", "status", "matched"]].values.tolist() == \
        [["Chase Credit", "6236", "9956", "same", "26/26"]]

    # The link is recorded once: another import neither duplicates nor drops it
    run_pipeline(tmp_path)
    assert len(_links(tmp_path)) == 1 and len(_master(tmp_path)) == len(m)


def test_two_different_cards_are_never_linked(tmp_path):
    # Overlapping for months, sharing two coincidental charges
    _raw(tmp_path, "Chase1039_Activity_20260401.csv",
         [(d, f"A {i}", -(1 + i)) for i, (d, _, _) in enumerate(SHARED)] + SHARED[:2])
    _raw(tmp_path, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED)
    run_pipeline(tmp_path)
    assert not (tmp_path / "SORTED" / "linked_cards.csv").exists()
    assert set(_master(tmp_path)["card_last4"]) == {"1039", "6236"}


def test_a_tiny_overlap_is_not_enough_to_link(tmp_path):
    _raw(tmp_path, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED[:3])
    _raw(tmp_path, "Chase9956_Activity_20261010.csv", SHARED[:3] + NEW_ONLY)
    run_pipeline(tmp_path)
    assert not (tmp_path / "SORTED" / "linked_cards.csv").exists()


def test_marked_different_cards_stay_apart(tmp_path):
    _replacement(tmp_path)
    _write_links(tmp_path, "different")
    run_pipeline(tmp_path)
    m = _master(tmp_path)
    assert set(m["card_last4"]) == {"6236", "9956"}
    assert len(_links(tmp_path)) == 1 and _links(tmp_path)["status"].iat[0] == "different"


def test_an_unreadable_links_file_is_left_alone(tmp_path):
    _replacement(tmp_path)
    (tmp_path / "SORTED").mkdir(parents=True)
    bad = tmp_path / "SORTED" / "linked_cards.csv"
    bad.write_text("not,a\nlinks,file\n")
    run_pipeline(tmp_path)
    assert bad.read_text() == "not,a\nlinks,file\n"
    assert set(_master(tmp_path)["card_last4"]) == {"6236", "9956"}


def _label(m, desc, card, cat, sub=""):
    hit = (m["description"] == desc) & (m["card_last4"] == card)
    assert hit.sum() == 1
    m.loc[hit, ["master_category", "sub_category"]] = [cat, sub]


def test_labels_on_either_copy_survive_and_only_a_real_conflict_is_shown(tmp_path):
    # Before the fix: both copies in the master, labeled every which way
    _replacement(tmp_path)
    _write_links(tmp_path, "different")
    run_pipeline(tmp_path)
    m = _master(tmp_path)
    _label(m, "SHOP 0", "6236", "Expense", "Shopping")       # only the old copy labeled
    _label(m, "SHOP 1", "9956", "Expense", "Gifts")          # only the new copy labeled
    _label(m, "SHOP 2", "6236", "Expense", "Shopping")       # both, the same
    _label(m, "SHOP 2", "9956", "Expense", "Shopping")
    _label(m, "SHOP 3", "6236", "Expense", "Shopping")       # both, different
    _label(m, "SHOP 3", "9956", "Transfer")
    _label(m, "SHOP 4", "9956", "Transfer")                  # a Transfer on one copy only
    _label(m, "NEW 0", "9956", "Expense", "Gas")             # new card, outside the overlap
    m.to_csv(tmp_path / "SORTED" / "edited_combined_transactions.csv", index=False)

    # The check, run before the link, says what the merge will do to them
    (tmp_path / "SORTED" / "linked_cards.csv").unlink()
    out = io.StringIO()
    check_data.run(tmp_path, out=out)
    report = out.getvalue()
    assert "WARNING: a replacement card" in report
    assert "Labels on the two copies: 1 same on both, 3 on one copy only, 21 on neither, 1 different" in report
    assert "SHOP 3: 6236 says Expense / Shopping, 9956 says Transfer" in report
    assert "SHOP 4: Transfer" in report

    run_pipeline(tmp_path)
    m = _master(tmp_path).set_index("description")
    assert m.loc["SHOP 0", ["master_category", "sub_category"]].tolist() == ["Expense", "Shopping"]
    assert m.loc["SHOP 1", ["master_category", "sub_category"]].tolist() == ["Expense", "Gifts"]
    assert m.loc["SHOP 2", ["master_category", "sub_category"]].tolist() == ["Expense", "Shopping"]
    assert m.loc["SHOP 3", "master_category"] in ("Expense", "Transfer")
    assert m.loc["SHOP 4", "master_category"] == "Transfer"
    assert m.loc["NEW 0", ["master_category", "sub_category"]].tolist() == ["Expense", "Gas"]
    assert orphan_count(tmp_path / "SORTED" / "edited_combined_transactions.csv") == 1   # SHOP 3's other label

    out = io.StringIO()
    check_data.run(tmp_path, out=out)
    assert "OK: linked as one card" in out.getvalue()


def test_a_charge_only_the_new_export_has_is_reported(tmp_path):
    # Pending when the old number's last export was taken: only in the new one
    _replacement(tmp_path, extra_new=[("2026-03-26", "LATE POST", -42.0)])
    run_pipeline(tmp_path)
    left = read_overlap_only(tmp_path / "SORTED" / "edited_combined_transactions.csv")
    assert left["description"].tolist() == ["LATE POST"]


def test_chains_file_under_the_oldest_number():
    links = pd.DataFrame([["Chase Credit", "1111", "2222", "same", "", ""],
                          ["Chase Credit", "2222", "3333", "same", "", ""],
                          ["Chase Credit", "4444", "5555", "different", "", ""]], columns=LINK_COLUMNS)
    assert card_map(links) == {("Chase Credit", c): "1111" for c in ("1111", "2222", "3333")}


def test_a_new_link_is_explained_for_two_weeks(tmp_path):
    master = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    master.parent.mkdir(parents=True)
    pd.DataFrame([["Chase Credit", "6236", "9956", "same", "116/116", "2026-10-11"]],
                 columns=LINK_COLUMNS).to_csv(links_path(master), index=False)
    assert recent_links(master, today="2026-10-20") == [
        "Chase Credit 9956 is a new number for 6236 — charges on both now count once"]
    assert recent_links(master, today="2026-11-01") == []
