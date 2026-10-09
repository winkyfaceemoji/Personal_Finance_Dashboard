import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def appmod(tmp_path_factory):
    """app.py loaded against a temp copy of Test Data (never the repo's)."""
    import runpy
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    rules = data / "rules.csv"
    shutil.copy(REPO / "rules.csv", rules)          # never write the repo's rules.csv
    saved = {k: os.environ.get(k) for k in ("FINANCE_DATA_DIR", "FINANCE_RULES_PATH")}
    os.environ["FINANCE_DATA_DIR"] = str(data)
    os.environ["FINANCE_RULES_PATH"] = str(rules)
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_app")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_rules_path_override(appmod):
    assert Path(appmod["RULES_PATH"]).parent != REPO


def test_unreviewed_amounts(appmod):
    pdf = pd.DataFrame({"amount": [-10.0, -5.0, 7.0, -100.0],
                        "master_category": ["", "", "", "Expense"]})
    assert appmod["unreviewed_amounts"](pdf) == (15.0, 7.0)


def test_last_import_text(appmod):
    from Modules.labels import row_ids
    df = appmod["df"]
    ids = row_ids(df.head(3)).tolist()
    text, need = appmod["last_import_text"](df, ids)
    assert text.startswith("Last import: 3 new")
    assert need == int((~df.head(3)["master_category"].isin(["Expense", "Income", "Transfer"])).sum())
    assert appmod["last_import_text"](df, None) == ("", 0)


def _ids(component):
    """Every component id in a Dash tree."""
    out, stack = [], [component]
    while stack:
        c = stack.pop()
        if isinstance(c, (list, tuple)):
            stack.extend(c)
            continue
        if getattr(c, "id", None) is not None:
            out.append(c.id)
        kids = getattr(c, "children", None)
        if kids is not None:
            stack.append(kids)
    return out


def test_mixed_and_fallback_groups_have_no_group_buttons(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-02", "2025-03-03"]),
        "description": ["AMAZON MKTP 1", "AMAZON MKTP 2", "#99999"], "amount": [-20.0, 20.0, -5.0],
        "master_category": ["", "", ""], "sub_category": ["", "", ""],
        "source": ["Chase Credit"] * 3, "card_last4": ["", "", ""],
    })
    for g in unlabeled_groups(df):
        assert g["mixed"] or g["fallback"]
        card = appmod["_group_card"](g, rule_check(df, read_rules("/none"), g))
        ids = _ids(card)
        assert not any(isinstance(i, dict) and i.get("type") == "lbl-group" for i in ids)
        assert any(isinstance(i, dict) and i.get("type") == "lbl-row" for i in ids)


def test_group_card_row_ids_unique(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-01"]),
        "description": ["CAFE", "CAFE"], "amount": [-4.5, -4.5],
        "master_category": ["", ""], "sub_category": ["", ""],
        "source": ["Chase Credit"] * 2, "card_last4": ["", ""],
    })
    g = unlabeled_groups(df)[0]
    card = appmod["_group_card"](g, rule_check(df, read_rules("/none"), g))
    ids = [str(i) for i in _ids(card)]
    assert len(ids) == len(set(ids))            # twins don't collide


def _walk(component):
    stack = [component]
    while stack:
        c = stack.pop()
        if isinstance(c, (list, tuple)):
            stack.extend(c)
            continue
        yield c
        kids = getattr(c, "children", None)
        if kids is not None:
            stack.append(kids)


def test_group_card_remember_state(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01"]), "description": ["AB 12"], "amount": [-4.5],
        "master_category": [""], "sub_category": [""], "source": ["Chase Credit"], "card_last4": [""],
    })
    g = unlabeled_groups(df)[0]
    chk = rule_check(df, read_rules("/none"), g)
    card = appmod["_group_card"](g, chk)
    remember = next(c for c in _walk(card) if getattr(c, "id", None) == {"type": "lbl-remember", "group": g["key"]})
    assert remember.value == [] and remember.options[0]["disabled"] is True


def _card_remember(appmod, rows):
    """(Remember checklist, note text) for the card of the first group in rows."""
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    df = pd.DataFrame({
        "date": pd.to_datetime([r[0] for r in rows]), "description": [r[1] for r in rows],
        "amount": [r[2] for r in rows], "master_category": [""] * len(rows),
        "sub_category": [""] * len(rows), "source": ["Chase Credit"] * len(rows),
        "card_last4": [""] * len(rows),
    })
    g = unlabeled_groups(df)[0]
    card = appmod["_group_card"](g, rule_check(df, read_rules("/none"), g))
    remember = next(c for c in _walk(card) if getattr(c, "id", None) == {"type": "lbl-remember", "group": g["key"]})
    note = " ".join(c.children for c in _walk(card) if isinstance(getattr(c, "children", None), str))
    return remember, note


def test_mixed_card_remember_disabled_and_unticked(appmod):
    # No group buttons on a mixed card, so a ticked Remember could never be used
    remember, _ = _card_remember(appmod, [("2025-03-01", "AMAZON MKTP 1", -20.0),
                                          ("2025-03-02", "AMAZON MKTP 2", 20.0)])
    assert remember.value == [] and remember.options[0]["disabled"] is True


def test_single_row_ok_group_starts_unticked(appmod):
    remember, note = _card_remember(appmod, [("2025-03-01", "STARBUCKS STORE 1", -5.0)])
    assert remember.value == [] and remember.options[0]["disabled"] is False
    assert "only one transaction — tick to remember anyway" in note


def test_two_row_ok_group_starts_ticked(appmod):
    remember, note = _card_remember(appmod, [("2025-03-01", "STARBUCKS STORE 1", -5.0),
                                             ("2025-03-02", "STARBUCKS STORE 2", -6.0)])
    assert remember.value == ["yes"] and remember.options[0]["disabled"] is False
    assert "only one transaction" not in note


def _render(appmod, kept_sub=None, kept_rem=None, kept_open=None, toggles=None):
    """render_label_list with optional card state as the browser would send it:
    each kept_* is {group_key: value}; toggles is {group_key: summary n_clicks}."""
    def _state(kind, kept):
        kept = kept or {}
        return list(kept.values()), [{"type": kind, "group": k} for k in kept]
    return appmod["render_label_list"]({"display": "block"}, 0, "todo", "all",
                                       *_state("lbl-sub", kept_sub),
                                       *_state("lbl-remember", kept_rem),
                                       *_state("lbl-rows", kept_open),
                                       *_state("lbl-rows-sum", toggles))


def test_render_label_list_top_n(appmod):
    children, summary = _render(appmod)
    assert 0 < len(children) <= appmod["LABEL_TOP_N"] + 1     # + the subcategory datalist
    assert "merchants" in summary


def test_render_keeps_what_the_user_set_on_cards(appmod):
    # Labeling one group re-renders the list; typed subcategories, Remember
    # choices and opened row lists on the other cards must survive it
    from Modules.labels import unlabeled_groups
    g = next(x for x in unlabeled_groups(_live(appmod)["df"]) if not x["fallback"] and not x["mixed"])
    # rendered closed, then the user clicked its summary once: now open
    children, _ = _render(appmod, kept_sub={g["key"]: "Coffee"}, kept_rem={g["key"]: []},
                          kept_open={g["key"]: False}, toggles={g["key"]: 1})
    by_id = {str(c.id): c for c in _walk(children) if getattr(c, "id", None) is not None}
    assert by_id[str({"type": "lbl-sub", "group": g["key"]})].value == "Coffee"
    rem = by_id[str({"type": "lbl-remember", "group": g["key"]})]
    assert rem.value == [] or rem.options[0]["disabled"]
    assert by_id[str({"type": "lbl-rows", "group": g["key"]})].open is True


def test_rules_view_pluralizes_matches(appmod):
    texts = [c.children for c in _walk(appmod["_rules_view"]())
             if isinstance(getattr(c, "children", None), str)]
    assert not any("matches 1 rows" in t for t in texts)


def _live(appmod):
    """The app module's live globals (runpy returns a copy; callbacks rebind df)."""
    return appmod["_do_label"].__globals__


def _bulk_group(g_):
    from Modules.labels import unlabeled_groups
    return next(g for g in unlabeled_groups(g_["df"]) if not g["fallback"] and not g["mixed"])


def _group_trig(grp, cat="Expense", sig=None):
    return {"type": "lbl-group", "group": grp["key"], "sig": sig or grp["sig"], "cat": cat}


def test_label_click_ignores_rerender(appmod):
    real = appmod["_is_real_click"]
    pid = '{"cat":"Expense","group":"x","sig":"s","type":"lbl-group"}.n_clicks'
    assert not real([])
    assert not real([{"prop_id": pid, "value": 0}])
    assert not real([{"prop_id": pid, "value": None}])
    assert real([{"prop_id": pid, "value": 1}])


def test_label_then_undo_roundtrip(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = _bulk_group(g_)
    status, undo, _, version = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    assert status.startswith("Labeled") and undo and version == 1
    assert master.read_bytes() != before
    undo = json.loads(json.dumps(undo))          # what the browser hands back
    status2, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status2 == "Undone." and undo2 is None
    assert master.read_bytes() == before


def test_undo_record_survives_json(appmod):
    g_ = _live(appmod)
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    assert isinstance(undo["master_mtime"], str) and isinstance(undo["rules_mtime"], str)
    assert json.loads(json.dumps(undo)) == undo


def test_undo_refuses_after_change(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    changed = master.read_bytes() + b"\n"
    master.write_bytes(changed)                  # something else wrote the master
    status, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert master.read_bytes() == changed


def test_undo_refuses_after_rules_change(appmod):
    g_ = _live(appmod)
    master, rules = g_["MASTER_PATH"], g_["RULES_PATH"]
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    after = master.read_bytes()
    rules.write_text(rules.read_text() + "zzz unrelated shop,Expense,\n")
    status, undo2, _, _ = g_["_do_undo"](undo, 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert master.read_bytes() == after


def test_label_click_refuses_stale_sig(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, undo, _, version = g_["_do_label"](_group_trig(_bulk_group(g_), sig="0000000000"), "", False, 0, "all")
    assert status.startswith("The list changed") and version == 1
    assert master.read_bytes() == before


def test_label_click_refuses_group_label_on_mixed_or_fallback(appmod):
    from Modules.labels import unlabeled_groups
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    risky = [g for g in unlabeled_groups(g_["df"]) if g["fallback"] or g["mixed"]]
    assert risky, "Test Data should contain at least one mixed or fallback group"
    status, _, _, _ = g_["_do_label"](_group_trig(risky[0]), "", False, 0, "all")
    assert status.startswith("Label these one at a time")
    assert master.read_bytes() == before


def test_row_click_labels_by_row_id(appmod):
    from Modules.labels import row_ids
    g_ = _live(appmod)
    grp = _bulk_group(g_)
    row = grp["rows"][-1]
    status, _, _, _ = g_["_do_label"](
        {"type": "lbl-row", "group": grp["key"], "row": row["row_id"], "cat": "Transfer"}, "", False, 0, "all")
    assert status.startswith("Labeled")
    df = g_["df"]
    sel = row_ids(df) == row["row_id"]
    assert sel.any()
    assert (df.loc[sel, "master_category"] == "Transfer").all()


def test_label_survives_rules_file_locked(appmod, monkeypatch):
    from Modules.labels import read_rules, rule_check, unlabeled_groups
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    rules = read_rules(g_["RULES_PATH"])
    # A group whose rule is allowed, so add_rule is actually reached
    grp = next(g for g in unlabeled_groups(g_["df"])
               if not g["fallback"] and not g["mixed"] and rule_check(g_["df"], rules, g)["ok"])

    def locked(*a, **k):
        raise PermissionError("open in Excel")
    monkeypatch.setitem(g_, "add_rule", locked)
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", True, 0, "all")
    assert status.startswith("Labeled") and "not remembered" in status
    assert undo and undo["rule"] is None          # the label still has an undo
    assert master.read_bytes() != before


def test_label_refreshes_when_master_changed_underneath(appmod):
    from Modules.labels import row_ids
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    grp = _bulk_group(g_)
    first = grp["rows"][0]
    # Something outside the app labels one of this group's rows
    raw = pd.read_csv(master, dtype=str, keep_default_na=False)
    hit = ((raw["description"] == first["description"])
           & (pd.to_datetime(raw["date"]) == pd.Timestamp(first["date"]))
           & (raw["amount"].astype(float).round(2) == round(float(first["amount"]), 2)))
    assert hit.any()
    raw.loc[hit, "master_category"] = "Expense"
    raw.to_csv(master, index=False)
    before = master.read_bytes()
    status, undo, _, version = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    assert status.startswith("The list changed") and version == 1
    assert master.read_bytes() == before                      # nothing written
    df = g_["df"]                                             # reloaded: the list can now be redrawn correctly
    assert (df.loc[row_ids(df) == first["row_id"], "master_category"] == "Expense").all()


def _rule_safe_group(g_):
    """A bulk group whose rule is allowed right now (so add_rule is reached)."""
    from Modules.labels import read_rules, rule_check, unlabeled_groups
    rules = read_rules(g_["RULES_PATH"])
    return next(g for g in unlabeled_groups(g_["df"])
                if not g["fallback"] and not g["mixed"] and rule_check(g_["df"], rules, g)["ok"])


def test_label_keeps_undo_when_rules_unreadable(appmod, monkeypatch):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = _rule_safe_group(g_)

    def unreadable(*a, **k):
        raise UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "invalid continuation byte")
    monkeypatch.setitem(g_, "read_rules", unreadable)
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", True, 0, "all")
    assert status.startswith("Labeled") and "not remembered" in status
    assert undo and undo["rule"] is None
    assert master.read_bytes() != before


def test_label_keeps_undo_when_reload_fails(appmod, monkeypatch):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = _bulk_group(g_)
    real_load = g_["load_transactions"]

    def broken(*a, **k):
        raise ValueError("bad row")
    monkeypatch.setitem(g_, "load_transactions", broken)
    try:
        status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    finally:
        g_["df"] = real_load(master, rules_path=g_["RULES_PATH"])
    assert status.startswith("Labeled") and "RELOAD DATA" in status
    assert undo and undo["backup"]
    assert master.read_bytes() != before


def test_label_rejects_unknown_category(appmod):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_), cat="Groceries"), "", False, 0, "all")
    assert "Groceries" in status and not status.startswith("Labeled")
    assert undo is g_["dash"].no_update
    assert master.read_bytes() == before


def test_remembered_label_undo_restores_master_and_removes_rule(appmod):
    from Modules.labels import read_rules
    g_ = _live(appmod)
    master, rules = g_["MASTER_PATH"], g_["RULES_PATH"]
    before = master.read_bytes()
    grp = _rule_safe_group(g_)
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", True, 0, "all")
    assert undo["rule"] and "rule" in status
    assert undo["rule"] in read_rules(rules)["keyword"].tolist()
    status2, _, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status2 == "Undone."
    assert master.read_bytes() == before
    assert undo["rule"] not in read_rules(rules)["keyword"].tolist()


def test_delete_rule_unlabels_its_rows(appmod):
    from Modules.labels import add_rule, row_ids
    g_ = _live(appmod)
    grp = _rule_safe_group(g_)
    kw = g_["rule_check"](g_["df"], g_["read_rules"](g_["RULES_PATH"]), grp)["keyword"]
    ids = {r["row_id"] for r in grp["rows"]}
    assert add_rule(g_["RULES_PATH"], kw, "Expense")
    g_["df"] = g_["load_transactions"](g_["MASTER_PATH"], rules_path=g_["RULES_PATH"])
    sel = row_ids(g_["df"]).isin(ids)
    assert sel.any() and (g_["df"].loc[sel, "master_category"] == "Expense").all()
    status, version = g_["_do_delete_rule"](kw, 0)
    assert status.startswith("Rule") and version == 1
    df = g_["df"]
    sel = row_ids(df).isin(ids)
    assert sel.any() and (df.loc[sel, "master_category"] == "").all()   # unlabeled again


def test_snapshot_failure_does_not_block_panel(appmod, monkeypatch):
    g_ = _live(appmod)

    def full(*a, **k):
        raise OSError("disk full")
    monkeypatch.setitem(g_, "snapshot_master", full)
    g_["_snapshot_before_labeling"]()            # must not raise


def _add_transfer_pair(g_, cents=77777, labels=("", "")):
    """Append a certain card-payment pair to the temp master and reload df.
    labels: (out side, in side) master_category."""
    master = g_["MASTER_PATH"]
    m = pd.read_csv(master, dtype=str, keep_default_na=False)
    amt = f"{cents / 100:.2f}"
    base = {c: "" for c in m.columns}
    out_row = {**base, "date": "2026-01-05", "post_date": "2026-01-05", "source": "Chase Debit",
               "description": "ACME SAVINGS XFER OUT 4823", "amount": f"-{amt}",
               "card_last4": "4823", "master_category": labels[0]}
    in_row = {**base, "date": "2026-01-06", "post_date": "2026-01-06", "source": "Chase Credit",
              "description": "ACME SAVINGS XFER IN 3094", "amount": amt, "card_last4": "3094",
              "master_category": labels[1]}
    m = pd.concat([m, pd.DataFrame([out_row, in_row])], ignore_index=True)
    m.to_csv(master, index=False)
    g_["df"] = g_["load_transactions"](master, rules_path=g_["RULES_PATH"])
    found = g_["transfer_pairs"](g_["df"]) + g_["suspect_transfers"](g_["df"])
    return next(p for p in found if p["amount"] == cents / 100)


def test_pairs_tab_lists_and_labels_a_pair(appmod):
    from Modules.labels import row_ids
    g_ = _live(appmod)
    pair = _add_transfer_pair(g_)
    children, summary = g_["render_label_list"]({"display": "block"}, 0, "pairs", "all",
                                                [], [], [], [], [], [], [], [])
    assert "likely transfer pair" in summary
    ids = [i for i in _ids(children) if isinstance(i, dict) and i.get("type") == "lbl-pair"]
    assert {"type": "lbl-pair", "pair": pair["key"], "sig": pair["key"]} in ids
    assert any(i["pair"] == "__all__" for i in ids)

    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, undo, _, _ = g_["_do_label_pairs"](
        {"type": "lbl-pair", "pair": pair["key"], "sig": pair["key"]}, 0)
    assert status.startswith("Labeled 2 rows (1 pair) as Transfer")
    df = g_["df"]
    both = row_ids(df).isin({pair["out"]["row_id"], pair["in"]["row_id"]})
    assert both.sum() == 2 and (df.loc[both, "master_category"] == "Transfer").all()
    assert pair["key"] not in {p["key"] for p in g_["transfer_pairs"](df)}
    status, _, _, _ = g_["_do_undo"](undo, 1)
    assert status == "Undone." and master.read_bytes() == before


def test_label_all_pairs_refuses_a_stale_list(appmod):
    g_ = _live(appmod)
    _add_transfer_pair(g_, cents=88888)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, _, _, _ = g_["_do_label_pairs"]({"type": "lbl-pair", "pair": "__all__", "sig": "0000000000"}, 0)
    assert status.startswith("The list changed") and master.read_bytes() == before
    sig = g_["_pairs_sig"](g_["transfer_pairs"](g_["df"]))
    status, _, _, _ = g_["_do_label_pairs"]({"type": "lbl-pair", "pair": "__all__", "sig": sig}, 0)
    assert status.startswith("Labeled") and g_["transfer_pairs"](g_["df"]) == []


def test_label_all_pairs_only_labels_the_pairs_shown(appmod, monkeypatch):
    # The tab shows at most LABEL_TOP_N pairs; LABEL ALL must never reach the
    # unseen ones (a coincidental "pair" would silently leave every total)
    g_ = _live(appmod)
    _add_transfer_pair(g_, cents=99999)
    _add_transfer_pair(g_, cents=66666)
    monkeypatch.setitem(g_, "LABEL_TOP_N", 1)
    shown, total = g_["_shown_pairs"]("all")
    assert total == 2 and [p["amount"] for p in shown] == [999.99]
    status, _, _, _ = g_["_do_label_pairs"](
        {"type": "lbl-pair", "pair": "__all__", "sig": g_["_pairs_sig"](shown)}, 0, "all")
    assert status.startswith("Labeled 2 rows (1 pair)")
    assert [p["amount"] for p in g_["transfer_pairs"](g_["df"])] == [666.66]


def test_skipped_files_text(appmod):
    text = appmod["skipped_text"]
    assert text([]) == ""
    one = text([("CapitalOne/CapitalOne_2026.csv", "unrecognized format")])
    assert one.startswith("⚠ 1 file in RAW wasn't imported") and "CapitalOne_2026.csv (unrecognized format)" in one
    many = text([(f"f{i}.csv", "unrecognized format") for i in range(5)])
    assert "5 files" in many and "and 2 more" in many and "f3.csv" not in many



def test_transfer_labeled_expense_is_flagged_fixed_and_undone(appmod):
    from Modules.labels import row_ids
    g_ = _live(appmod)
    pair = _add_transfer_pair(g_, cents=55555, labels=("Expense", "Transfer"))
    assert "labeled Expense or Income" in g_["transfer_check_text"](g_["_suspects"]())
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, undo, _, _ = g_["_do_fix_suspect"]({"pair": pair["key"], "act": "fix"}, 0)
    assert status.startswith("Relabeled 1 row as Transfer")
    df = g_["df"]
    out_row = row_ids(df) == pair["out"]["row_id"]
    assert out_row.sum() == 1 and (df.loc[out_row, "master_category"] == "Transfer").all()
    assert pair["key"] not in {p["key"] for p in g_["_suspects"]()}
    status, _, _, _ = g_["_do_undo"](undo, 1)
    assert status == "Undone." and master.read_bytes() == before


def test_not_a_transfer_stops_the_flag_and_keeps_labels(appmod):
    g_ = _live(appmod)
    pair = _add_transfer_pair(g_, cents=44444, labels=("Expense", "Income"))
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, _, _, _ = g_["_do_fix_suspect"]({"pair": pair["key"], "act": "dismiss"}, 0)
    assert status.startswith("Kept as is")
    assert master.read_bytes() == before
    assert pair["key"] not in {p["key"] for p in g_["_suspects"]()}
