# tests/test_linked_cards.py — a replacement card: asked about, then counted once
import io
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

import check_data
from main import main as run_pipeline
from Modules.linked_cards import (
    LINK_COLUMNS, answer_link, card_map, links_unreadable, month_span, pending_duplicates,
    pending_links, read_links, answered_links,
)
from Modules.safety import orphan_count, read_overlap_only
from Modules.transforms import load_transactions

REPO = Path(__file__).resolve().parent.parent
HEAD = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
PAIR = "Chase Credit|6236|9956"


def _row(day: str, desc: str, amount: float) -> str:
    d = pd.Timestamp(day)
    return f"{d:%m/%d/%Y},{d:%m/%d/%Y},{desc},Shopping,Sale,{amount:.2f},\n"


# 25 charges in Jan–Mar 2026: on the old card's export AND the new card's
SHARED = [(f"2026-{1 + i // 9:02d}-{2 + 3 * (i % 9):02d}", f"SHOP {i}", -(10 + i)) for i in range(25)]
OLD_ONLY = [(f"2025-{10 + i // 3:02d}-{5 + 9 * (i % 3):02d}", f"OLD {i}", -(5 + i)) for i in range(9)]
NEW_ONLY = [(f"2026-04-{2 + 3 * i:02d}", f"NEW {i}", -(20 + i)) for i in range(5)]
DOUBLED = sum(10 + i for i in range(25)) + 3.0        # SHARED plus LAST OLD


def _raw(root: Path, name: str, rows) -> None:
    f = root / "RAW" / "Chase" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(HEAD + "".join(_row(*r) for r in rows))


def _replacement(root, extra_new=()):
    # The old number's export runs to Mar 27; the new number's repeats Jan–Mar
    _raw(root, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED + [("2026-03-27", "LAST OLD", -3.0)])
    _raw(root, "Chase9956_Activity_20261010.csv",
         SHARED + [("2026-03-27", "LAST OLD", -3.0)] + list(extra_new) + NEW_ONLY)


def _mpath(root) -> Path:
    return root / "SORTED" / "edited_combined_transactions.csv"


def _master(root) -> pd.DataFrame:
    return pd.read_csv(_mpath(root), dtype=str, keep_default_na=False)


def _links(root) -> pd.DataFrame:
    return pd.read_csv(root / "SORTED" / "linked_cards.csv", dtype=str, keep_default_na=False)


def _write_links(root, status):
    (root / "SORTED").mkdir(parents=True, exist_ok=True)
    row = dict.fromkeys(LINK_COLUMNS, "")
    row.update(source="Chase Credit", institution="Chase", old_card="6236", new_card="9956", status=status)
    pd.DataFrame([row])[LINK_COLUMNS].to_csv(root / "SORTED" / "linked_cards.csv", index=False)


def _report(root) -> str:
    out = io.StringIO()
    check_data.run(root, out=out)
    return out.getvalue()


def test_a_replacement_is_asked_about_and_counted_once_only_after_yes(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    # Proposed, not merged: both numbers' copies still there
    links = _links(tmp_path)
    assert links[["source", "institution", "old_card", "new_card", "status", "matched", "from", "to"]
                 ].values.tolist() == [["Chase Credit", "Chase", "6236", "9956", "proposed", "26/26",
                                        "2026-01-02", "2026-03-27"]]
    assert float(links["out"].iat[0]) == DOUBLED
    assert set(_master(tmp_path)["card_last4"]) == {"6236", "9956"}
    assert "WAITING: answer the card question on the dashboard" in _report(tmp_path)

    # Asked again on the next import? No — one line, still waiting
    run_pipeline(tmp_path)
    assert len(_links(tmp_path)) == 1

    assert answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    run_pipeline(tmp_path)
    m = _master(tmp_path)
    assert len(m) == len(OLD_ONLY) + len(SHARED) + 1 + len(NEW_ONLY)
    assert (m.groupby(["date", "description", "amount"]).size() == 1).all()
    assert set(m["card_last4"]) == {"6236"}                                 # filed under the old number
    assert "OK: you confirmed a replacement card" in _report(tmp_path)


def test_two_different_cards_are_never_proposed(tmp_path):
    # Overlapping for months, sharing two coincidental charges
    _raw(tmp_path, "Chase1039_Activity_20260401.csv",
         [(d, f"A {i}", -(1 + i)) for i, (d, _, _) in enumerate(SHARED)] + SHARED[:2])
    _raw(tmp_path, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED)
    run_pipeline(tmp_path)
    assert not (tmp_path / "SORTED" / "linked_cards.csv").exists()
    assert set(_master(tmp_path)["card_last4"]) == {"1039", "6236"}


def test_a_tiny_overlap_is_not_enough_to_ask(tmp_path):
    _raw(tmp_path, "Chase6236_Activity_20260401.csv", OLD_ONLY + SHARED[:3])
    _raw(tmp_path, "Chase9956_Activity_20261010.csv", SHARED[:3] + NEW_ONLY)
    run_pipeline(tmp_path)
    assert not (tmp_path / "SORTED" / "linked_cards.csv").exists()


def test_no_keeps_them_apart_and_isnt_asked_again_but_the_check_says_so(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    assert answer_link(_mpath(tmp_path), PAIR, "proposed", "different")
    run_pipeline(tmp_path)
    assert set(_master(tmp_path)["card_last4"]) == {"6236", "9956"}
    assert _links(tmp_path)["status"].tolist() == ["different"]
    assert pending_links(_mpath(tmp_path)) == []
    assert "WARNING: you said these are different cards, but they share almost every charge" \
        in _report(tmp_path)


def test_answers_only_apply_once_and_stay_listed_until_undone(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    master = _mpath(tmp_path)
    assert answer_link(master, PAIR, "proposed", "same", today="2026-10-11")
    assert not answer_link(master, PAIR, "proposed", "same")              # a double tap
    assert not answer_link(master, PAIR, "proposed", "different")         # a stale page
    assert [(a["id"], a["status"]) for a in answered_links(master)] == [(PAIR, "same")]  # no time limit
    assert answer_link(master, PAIR, "same", "proposed")
    assert [q["id"] for q in pending_links(master)] == [PAIR]
    assert _links(tmp_path)["answered_on"].tolist() == [""]


def test_a_typo_in_the_status_asks_again_instead_of_settling_it(tmp_path):
    _replacement(tmp_path)
    _write_links(tmp_path, "sme")
    run_pipeline(tmp_path)
    assert set(_master(tmp_path)["card_last4"]) == {"6236", "9956"}       # not merged
    assert read_links(_mpath(tmp_path)).attrs["unknown"] == [("Chase Credit", "6236", "9956", "sme")]
    assert len(pending_links(_mpath(tmp_path))) == 1
    assert 'linked_cards.csv says "sme"' in _report(tmp_path)


def test_an_unreadable_links_file_stops_the_import_before_anything_changes(tmp_path):
    # A confirmed replacement, then the file is saved badly (a header renamed in Excel)
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    run_pipeline(tmp_path)
    sorted_ = tmp_path / "SORTED"
    bad = sorted_ / "linked_cards.csv"
    bad.write_text(bad.read_text().replace("status", "Status ", 1).replace("source", "Source x", 1))
    before = {f.name: f.read_bytes() for f in sorted_.glob("*.csv")}
    _raw(tmp_path, "Chase9956_Activity_20261011.csv", NEW_ONLY + [("2026-04-20", "LATER", -9.0)])

    run_pipeline(tmp_path)
    # Nothing written: not the master (the card isn't split again), not the
    # exported-through dates or the skipped list the header reads
    assert {f.name: f.read_bytes() for f in sorted_.glob("*.csv")} == before
    assert links_unreadable(_mpath(tmp_path))
    out = io.StringIO()
    assert check_data.run(tmp_path, out=out) > 0
    assert "linked_cards.csv can't be read - imports are stopped" in out.getvalue()


def test_a_same_card_re_download_isnt_reported_as_left_out(tmp_path):
    # After YES: a narrower re-download of the old card, where a pending $40
    # has since posted as $48 (a tip). It loses its dates to the old card's
    # wider export — same number, so not a "left out" charge.
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    re_download = [r for r in SHARED[9:18]]
    re_download[0] = (re_download[0][0], re_download[0][1], -48.0)
    _raw(tmp_path, "Chase6236_Activity_20260315.csv", re_download)
    run_pipeline(tmp_path)
    assert read_overlap_only(_mpath(tmp_path)).empty


def test_a_label_on_a_charge_only_the_losing_export_has_is_kept_not_absorbed(tmp_path):
    # Three identical $2.75 rides: the old card's (winning) export has two,
    # the new card's has all three. Five labeled rows before YES; after it two
    # remain, two labels were the new card's copies — and the third ride's
    # label is kept as unmatched (the ride itself is reported as left out).
    ride = ("2026-02-03", "TRANSIT", -2.75)
    _raw(tmp_path, "Chase6236_Activity_20260401.csv",
         OLD_ONLY + SHARED + [ride, ride, ("2026-03-27", "LAST OLD", -3.0)])
    _raw(tmp_path, "Chase9956_Activity_20261010.csv",
         SHARED + [ride, ride, ride, ("2026-03-27", "LAST OLD", -3.0)] + NEW_ONLY)
    run_pipeline(tmp_path)
    m = _master(tmp_path)
    m.loc[m["description"] == "TRANSIT", "master_category"] = "Expense"
    m.to_csv(_mpath(tmp_path), index=False)
    assert answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    run_pipeline(tmp_path)
    assert (_master(tmp_path)["description"] == "TRANSIT").sum() == 2
    assert orphan_count(_mpath(tmp_path)) == 1
    assert read_overlap_only(_mpath(tmp_path))["description"].tolist() == ["TRANSIT"]


def _label(m, desc, card, cat, sub=""):
    hit = (m["description"] == desc) & (m["card_last4"] == card)
    assert hit.sum() == 1
    m.loc[hit, ["master_category", "sub_category"]] = [cat, sub]


def test_labels_on_either_copy_survive_yes_and_only_a_real_conflict_is_shown(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)                                   # proposed: both copies in the master
    m = _master(tmp_path)
    _label(m, "SHOP 0", "6236", "Expense", "Shopping")       # only the old copy labeled
    _label(m, "SHOP 1", "9956", "Expense", "Gifts")          # only the new copy labeled
    _label(m, "SHOP 2", "6236", "Expense", "Shopping")       # both, the same
    _label(m, "SHOP 2", "9956", "Expense", "Shopping")
    _label(m, "SHOP 3", "6236", "Expense", "Shopping")       # both, different
    _label(m, "SHOP 3", "9956", "Transfer")
    _label(m, "SHOP 4", "9956", "Transfer")                  # a Transfer on one copy only
    _label(m, "NEW 0", "9956", "Expense", "Gas")             # new card, outside the overlap
    m.to_csv(_mpath(tmp_path), index=False)

    # The check, before the answer, says what YES will do to them
    report = _report(tmp_path)
    assert "Labels on the two copies: 1 same on both, 3 on one copy only, 21 on neither, 1 different" in report
    assert "SHOP 3: 6236 says Expense / Shopping, 9956 says Transfer" in report
    assert "SHOP 4: Transfer" in report

    answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    run_pipeline(tmp_path)
    m = _master(tmp_path).set_index("description")
    assert m.loc["SHOP 0", ["master_category", "sub_category"]].tolist() == ["Expense", "Shopping"]
    assert m.loc["SHOP 1", ["master_category", "sub_category"]].tolist() == ["Expense", "Gifts"]
    assert m.loc["SHOP 2", ["master_category", "sub_category"]].tolist() == ["Expense", "Shopping"]
    assert m.loc["SHOP 3", "master_category"] in ("Expense", "Transfer")
    assert m.loc["SHOP 4", "master_category"] == "Transfer"
    assert m.loc["NEW 0", ["master_category", "sub_category"]].tolist() == ["Expense", "Gas"]
    assert orphan_count(_mpath(tmp_path)) == 1                # SHOP 3's other label


def test_a_charge_only_the_new_export_has_is_reported(tmp_path):
    # Pending when the old number's last export was taken: only in the new one
    _replacement(tmp_path, extra_new=[("2026-03-26", "LATE POST", -42.0)])
    run_pipeline(tmp_path)
    answer_link(_mpath(tmp_path), PAIR, "proposed", "same")
    run_pipeline(tmp_path)
    assert read_overlap_only(_mpath(tmp_path))["description"].tolist() == ["LATE POST"]


def test_waiting_copies_are_kept_out_of_labeling(tmp_path):
    _replacement(tmp_path)
    run_pipeline(tmp_path)
    df = load_transactions(_mpath(tmp_path))
    mask = pending_duplicates(df, pending_links(_mpath(tmp_path)))
    assert mask.sum() == len(SHARED) + 1
    assert set(df.loc[mask, "card_last4"]) == {"9956"}
    # Works on a slice too: one month holds both copies
    jan = df[df["date"].dt.month.eq(1) & df["date"].dt.year.eq(2026)]
    assert pending_duplicates(jan, pending_links(_mpath(tmp_path))).sum() == 9


def test_chains_file_under_the_oldest_number():
    rows = [("1111", "2222", "same"), ("2222", "3333", "same"), ("4444", "5555", "different"),
            ("6666", "7777", "proposed")]
    links = pd.DataFrame([{**dict.fromkeys(LINK_COLUMNS, ""), "source": "Chase Credit", "old_card": a,
                           "new_card": b, "status": st} for a, b, st in rows])
    assert card_map(links) == {("Chase Credit", c): "1111" for c in ("1111", "2222", "3333")}


def test_month_span():
    t = pd.Timestamp
    assert month_span(t("2026-01-02"), t("2026-03-27")) == "Jan–Mar 2026"
    assert month_span(t("2025-12-31"), t("2026-03-27")) == "Dec 2025–Mar 2026"
    assert month_span(t("2026-03-02"), t("2026-03-27")) == "Mar 2026"


# ── The dashboard: the question, its answers, the headline while it waits ─────

@pytest.fixture(scope="module")
def cardapp(tmp_path_factory):
    """app.py loaded against a data folder holding a replacement card."""
    import runpy
    data = tmp_path_factory.mktemp("cards")
    _replacement(data)
    (data / "SORTED").mkdir(exist_ok=True)
    for name in ("merchants.csv", "merchant_aliases.csv"):
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    saved = {k: os.environ.get(k) for k in ("FINANCE_DATA_DIR", "FINANCE_EMBED_URL")}
    os.environ["FINANCE_DATA_DIR"] = str(data)
    os.environ.pop("FINANCE_EMBED_URL", None)
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_cards_app")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _texts(component) -> list[str]:
    out = []

    def walk(c):
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
        elif hasattr(c, "children"):
            walk(c.children)
    walk(component)
    return out


def test_the_headline_waits_for_the_answer_where_the_doubled_dates_count(cardapp):
    g = cardapp["_do_card_answer"].__globals__
    pending = g["_pending"]()
    reason, P = g["card_question_reason"], pd.Period
    first = P("2025-10", "M")
    assert reason(pending, "month", P("2026-02", "M"), first)                  # the month itself
    assert reason(pending, "month", P("2026-10", "M"), first)                  # in its typical's months
    assert reason(pending, "month", P("2027-04", "M"), first) is None          # baseline Apr 2026 on
    assert reason(pending, "year", P("2026", "Y"), P("2025", "Y"))
    assert "may be counted twice — answer the card question above" in \
        reason(pending, "month", P("2026-02", "M"), first)
    reasons, _ = g["cant_say_reasons"](100.0, "month", {
        "current": False, "age": 0, "as_of": pd.Timestamp("2026-04-14"), "unlabeled_out": 0.0,
        "unlabeled_n": 0, "card_question": "x"})
    assert reasons == ["x"]


def test_the_question_its_second_tap_and_undo(cardapp):
    g = cardapp["_do_card_answer"].__globals__
    pending = g["_pending"]()
    ask = " ".join(_texts(g["card_question_items"](pending, [], None)))
    assert (f"Did Chase replace your card ending 6236 with 9956? 26 charges "
            f"(${DOUBLED:,.0f}, Jan–Mar 2026) are on both and count twice until you answer.") in ask
    assert "YES, REPLACED" in ask and "NO, I HAVE BOTH" in ask

    # NO asks once more, writing nothing; GO BACK returns to the question
    ui, _ = g["_do_card_answer"](PAIR, "no", 0)
    assert ui == {"confirm": PAIR} and g["_pending"]()
    again = " ".join(_texts(g["card_question_items"](g["_pending"](), [], ui["confirm"])))
    assert "stays counted twice" in again and "KEEP BOTH" in again and "GO BACK" in again
    assert g["_do_card_answer"](PAIR, "back", 0)[0] == {}

    # NO and GO BACK only change what the line shows: nothing else re-renders
    assert g["_do_card_answer"](PAIR, "no", 0)[1] is g["dash"].no_update

    # YES merges right away (re-import) and confirms it once, with UNDO
    n_before = len(g["df"])
    ui, _ = g["_do_card_answer"](PAIR, "yes", 0)
    assert ui == {"just": PAIR}
    assert g["_pending"]() == [] and len(g["df"]) == n_before - (len(SHARED) + 1)
    note = " ".join(_texts(g["card_question_items"](
        [], [a for a in answered_links(g["MASTER_PATH"]) if a["id"] == ui["just"]], None)))
    assert "9956 counted as a replacement for 6236" in note and "UNDO" in note
    assert "change this in Settings → Cards" in note
    # The next load (card-ui reset) shows nothing; Settings lists the answer
    assert g["card_question_items"](g["_pending"](), [], None) == []
    rows = " ".join(_texts(g["settings_card_rows"](answered_links(g["MASTER_PATH"]))))
    assert "CARDS" in rows and "6236 → 9956 · counted as one card" in rows and "KEEP APART" in rows
    assert g["_do_card_answer"](PAIR, "yes", 0)[0] == {}                       # a second tap: no-op

    # Settings switches it either way, any time
    assert g["_do_card_answer"](PAIR, "switch", 0)[0] == {"just": PAIR}
    assert len(g["df"]) == n_before
    rows = " ".join(_texts(g["settings_card_rows"](answered_links(g["MASTER_PATH"]))))
    assert "6236 / 9956 · kept apart" in rows and "COUNT AS ONE" in rows
    g["_do_card_answer"](PAIR, "switch", 0)
    assert len(g["df"]) == n_before - (len(SHARED) + 1)

    # UNDO asks the question again
    g["_do_card_answer"](PAIR, "undo", 0)
    assert [q["id"] for q in g["_pending"]()] == [PAIR] and len(g["df"]) == n_before
    assert g["settings_card_rows"](answered_links(g["MASTER_PATH"])) == []


def test_the_dashboard_says_imports_are_paused(cardapp):
    g = cardapp["_do_card_answer"].__globals__
    parts = g["attention_parts"](g["df"].iloc[0:0], [], None, 0, [], links_broken=True)
    assert parts["other"].startswith("SORTED/linked_cards.csv can't be read — imports are paused")
