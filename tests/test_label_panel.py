import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from Modules.labels import suspect_transfers, transfer_pairs

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


def test_group_card_shows_merchant_and_the_banks_text_apart(appmod):
    from Modules.labels import unlabeled_groups, read_rules, rule_check
    raw = "CENTRAL BANK COLLECTION 590951122973920 WEB ID: 9886281493"
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-04-01", "2025-05-01"]),
        "description": [raw, raw.replace("590951122973920", "111"), raw.replace("590951122973920", "222")],
        "amount": [-500.0, -500.0, -500.0], "master_category": [""] * 3, "sub_category": [""] * 3,
        "source": ["Chase Debit"] * 3, "card_last4": [""] * 3,
    })
    g = unlabeled_groups(df)[0]
    texts = [c for c in _walk(appmod["_group_card"](g, rule_check(df, read_rules("/none"), g)))
             if isinstance(c, str)]
    assert {"MERCHANT", "CENTRAL BANK COLLECTION", "TRANSACTION TEXT · ONE OF SEVERAL"} <= set(texts)
    assert raw in texts                                    # the bank's text, unaltered
    one = unlabeled_groups(df.iloc[:1])[0]
    texts = [c for c in _walk(appmod["_group_card"](one, rule_check(df.iloc[:1], read_rules("/none"), one)))
             if isinstance(c, str)]
    assert "TRANSACTION TEXT" in texts and "TRANSACTION TEXT · ONE OF SEVERAL" not in texts


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
    found = transfer_pairs(g_["df"]) + suspect_transfers(g_["df"])
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
    assert pair["key"] not in {p["key"] for p in transfer_pairs(df)}
    status, _, _, _ = g_["_do_undo"](undo, 1)
    assert status == "Undone." and master.read_bytes() == before


def test_label_all_pairs_refuses_a_stale_list(appmod):
    g_ = _live(appmod)
    _add_transfer_pair(g_, cents=88888)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, _, _, _ = g_["_do_label_pairs"]({"type": "lbl-pair", "pair": "__all__", "sig": "0000000000"}, 0)
    assert status.startswith("The list changed") and master.read_bytes() == before
    sig = g_["_pairs_sig"](transfer_pairs(g_["df"]))
    status, _, _, _ = g_["_do_label_pairs"]({"type": "lbl-pair", "pair": "__all__", "sig": sig}, 0)
    assert status.startswith("Labeled") and transfer_pairs(g_["df"]) == []


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
    assert [p["amount"] for p in transfer_pairs(g_["df"])] == [666.66]


def test_skipped_files_text(appmod):
    text = appmod["skipped_text"]
    assert text([]) == ""
    one = text([("CapitalOne/CapitalOne_2026.csv", "unrecognized format")])
    assert one.startswith("1 RAW file not imported") and "CapitalOne_2026.csv (unrecognized format)" in one
    many = text([(f"f{i}.csv", "unrecognized format") for i in range(5)])
    assert "5 RAW files" in many and "and 2 more" in many and "f3.csv" not in many



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


def test_recurring_view(appmod):
    view = appmod["recurring_view"]
    children, sub = view([])
    assert "None found yet" in str(children) and sub == " · none found yet"
    items = [
        {"merchant": "RENT CO", "cadence": "monthly", "amount": 1500.0, "yearly": 18000.0, "count": 6,
         "first": pd.Timestamp("2025-01-01"), "last": pd.Timestamp("2025-06-01"), "active": True},
        {"merchant": "HULU", "cadence": "monthly", "amount": 7.99, "yearly": 95.88, "count": 5,
         "first": pd.Timestamp("2024-01-15"), "last": pd.Timestamp("2024-05-15"), "active": False},
    ]
    children, sub = view(items, as_of=pd.Timestamp("2025-06-10"))
    assert sub == " · 1 · $18,000 a year"
    text = str(children)
    assert "across all your history, not just this period" in text
    assert "RENT CO" in text and "$18,000 / yr" in text and "$1,500.00 monthly · last Jun 1'" in text
    assert "No longer charging (1)" in text and "HULU" in text
    assert "last May 15, 2024" in text                  # another year: the year is shown


def _summary(spent, typ=None, full=None, partial=False, day=31, days=31, periods=None):
    t = {"exp": typ} if typ is not None else None
    f = {"exp": full if full is not None else typ} if typ is not None else None
    if periods is None:      # a few full earlier months by default
        periods = [pd.Period("2026-09", "M"), pd.Period("2026-08", "M")] if typ is not None else []
    return {"cur": {"exp": spent}, "typical": t, "typical_full": f,
            "partial": partial, "days_elapsed": day, "days_total": days,
            "through": pd.Timestamp(f"2026-10-{day:02d}") if partial else None,
            "typical_periods": periods}


_OK = {"current": True, "age": 3, "as_of": pd.Timestamp("2026-10-07"),
       "unlabeled_out": 0.0, "unlabeled_n": 0}


def test_headline_compares_with_typical(appmod):
    view = appmod["headline_view"]
    c = appmod["_CHART"]["dark"]
    over, fix = view(_summary(1400.0, 1000.0), "month", _OK, c)
    assert "$400 over a typical month" in str(over) and not fix
    # In progress: where the data stops, in the same words everywhere
    partial = str(view(_summary(700.0, 1000.0, 2000.0, partial=True, day=15), "month", _OK, c)[0])
    assert "SPENDING THROUGH OCT 15" in partial and "$300 under a typical month" in partial
    assert "typical by Oct 15 $1,000" in partial and "typical full month $2,000" in partial
    assert "DAY " not in partial and "typical pace" not in partial
    assert "In line with a typical month" in str(view(_summary(1030.0, 1000.0), "month", _OK, c)[0])
    none = str(view(_summary(50.0), "month", _OK, c)[0])
    assert "$50 spent" in none and "No full earlier month to compare against" in none
    early = str(view(_summary(80.0, 10.0, 2000.0, partial=True, day=2), "month", _OK, c)[0])
    assert "Too early to call — $80 spent" in early and "over" not in early
    # One full earlier period isn't "typical": it's named
    one = str(view(_summary(1400.0, 1000.0, periods=[pd.Period("2024", "Y")]), "year", _OK, c)[0])
    assert "$400 over 2024" in one and "2024 $1,000" in one and "typical" not in one
    one = str(view(_summary(700.0, 1000.0, 2000.0, partial=True, day=15,
                            periods=[pd.Period("2025", "Y")]), "year", _OK, c)[0])
    assert "$300 under 2025" in one and "2025 by Oct 15 $1,000" in one and "all of 2025 $2,000" in one


def test_headline_refuses_on_stale_or_unlabeled_data(appmod):
    view = appmod["headline_view"]
    c = appmod["_CHART"]["dark"]
    s = _summary(1400.0, 1000.0)
    stale = dict(_OK, age=40)
    text, fix = view(s, "month", stale, c)
    assert "Can't say yet" in str(text) and "40 days ago" in str(text) and not fix
    # A past period isn't affected by how old the newest data is
    assert "over a typical month" in str(view(s, "month", dict(stale, current=False), c)[0])
    unlabeled = dict(_OK, unlabeled_out=200.0, unlabeled_n=7)       # 200 / 1600 > 10%
    text, fix = view(s, "month", unlabeled, c)
    assert "Can't say yet" in str(text) and "7 transactions" in str(text) and fix
    a_little = dict(_OK, unlabeled_out=100.0, unlabeled_n=2)         # 100 / 1500 < 10%
    assert "over a typical month" in str(view(s, "month", a_little, c)[0])


def test_attention_line_is_silent_when_healthy(appmod):
    parts = appmod["attention_parts"]
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-10-01", "2026-10-05"]), "description": ["A", "B"],
        "amount": [-5.0, -7.0], "source": ["Chase Debit", "Chase Credit"],
        "card_last4": ["", ""], "master_category": ["Expense", "Expense"],
    })
    today = pd.Timestamp("2026-10-08")
    assert not any(parts(frame, [], None, 0, [], today).values())
    frame.loc[0, "master_category"] = ""
    frame.loc[1, "date"] = pd.Timestamp("2026-10-20")
    got = parts(frame, [], None, 2, [("x.csv", "unrecognized format")], pd.Timestamp("2026-11-30"))
    assert got["unlabeled"] == "1 unlabeled ($5) not counted"
    assert "no transactions in 41 days" in got["other"]
    assert "Chase Debit only through Oct 1" in got["other"]
    # ...unless its export was downloaded later: then it was just quiet
    quiet = parts(frame, [], None, 0, [], pd.Timestamp("2026-11-30"),
                  exported={"Chase Debit": pd.Timestamp("2026-10-19")})
    assert "Chase Debit" not in quiet["other"]
    assert "2 labels match no transaction" in got["other"] and "x.csv" in got["other"]
    left = pd.DataFrame({"file": ["CapitalOne/c.csv"] * 2, "date": ["2026-08-14"] * 2,
                         "description": ["A", "B"], "amount": [-52.26, -10.0]})
    got = parts(frame, [], None, 0, [], today, left_out=left)
    assert "2 transactions ($62) left out where two exports overlap" in got["other"]


def test_every_callback_id_is_in_the_layout(appmod):
    app = appmod["app"]
    layout = {i for i in _ids(app.layout) if isinstance(i, str)}
    used = set()
    for key, cb in app.callback_map.items():
        for dep in cb["inputs"] + cb.get("state", []):
            used.add(dep["id"])
        for out in key.lstrip(".").split("..."):
            used.add(out.split(".")[0].split("@")[0])
    used = {i for i in used if not i.startswith("{")}             # pattern-matching ids
    assert used <= layout, used - layout


def _ly_summary(cur, last, partial=False):
    return {"cur": cur, "last_year": last, "partial": partial,
            "last_year_period": pd.Period("2024-10", "M"),
            "last_year_window": (pd.Timestamp("2024-10-01"), pd.Timestamp("2024-10-26"))}


def test_last_year_lines_in_dollars_and_words(appmod):
    lines = appmod["last_year_lines"]
    s = _ly_summary({"exp": 2870.0, "inc": 2406.0, "net": -464.0},
                    {"exp": 2420.0, "inc": 3106.0, "net": 686.0})
    got = {k: str(v) for k, v in lines(s, "month", 0.0).items()}
    assert "$450 more" in got["exp"] and "delta-bad" in got["exp"] and "Oct 2024 ($2,420)" in got["exp"]
    assert "$700 less" in got["inc"] and "delta-bad" in got["inc"] and "($3,106)" in got["inc"]
    assert "$1,150 worse" in got["net"] and "delta-bad" in got["net"] and "($686)" in got["net"]
    assert "%" not in "".join(got.values())
    better = lines(_ly_summary({"exp": 100.0, "inc": 500.0, "net": 400.0},
                               {"exp": 300.0, "inc": 500.0, "net": 200.0}), "month", 0.0)
    assert "$200 less" in str(better["exp"]) and "delta-good" in str(better["exp"])
    assert "Same as Oct 2024" in str(better["inc"])
    assert "$200 better" in str(better["net"]) and "delta-good" in str(better["net"])
    # In progress: say which day last year it's measured to
    partial = lines(_ly_summary({"exp": 10.0, "inc": 0.0, "net": -10.0},
                                {"exp": 5.0, "inc": 0.0, "net": -5.0}, partial=True), "month", 0.0)
    assert "Oct 2024 through Oct 26" in str(partial["exp"])


def test_last_year_lines_refuse_rather_than_mislead(appmod):
    lines = appmod["last_year_lines"]
    none = dict(_ly_summary({"exp": 1.0, "inc": 0.0, "net": -1.0}, None), last_year_period=None)
    assert lines(none, "week", None) == {"exp": None, "inc": None, "net": None}
    no_data = _ly_summary({"exp": 1.0, "inc": 0.0, "net": -1.0}, None)
    assert all("No data for Oct 2024" in str(v) for v in lines(no_data, "month", None).values())
    s = _ly_summary({"exp": 10.0, "inc": 0.0, "net": -10.0}, {"exp": 5.0, "inc": 0.0, "net": -5.0})
    assert all("Oct 2024 isn't fully labeled" in str(v) for v in lines(s, "month", 0.4).values())
    # Last year's period only partly in the data: a note, never a number
    part = dict(_ly_summary({"exp": 10.0, "inc": 0.0, "net": -10.0}, None), last_year_partial=True)
    assert all(str(v).count("Oct 2024 only partly covered") == 1 for v in lines(part, "month", None).values())


def test_stat_cards_render_for_every_view(appmod):
    # The callback itself, on the demo data: every view builds, weeks carry
    # no last-year line, and a blocked period (stale demo data) shows none
    update = appmod["update_stats"]
    for freq in ("week", "month", "year"):
        cards, headline, _ = update({"freq": freq}, "dark", 0)
        text = str(cards)
        assert "SPENT" in text and "INCOME" in text and "NET" in text
        if "Can't say yet" in str(headline) or freq == "week":
            assert " than " not in text
    cards, headline, _ = update({"freq": "year", "start": "2024-01-01"}, "light", 0)
    assert "Can't say yet" in str(headline) or " than 2023" in str(cards) or "2023" in str(cards)


def test_stat_cards_compare_with_last_year_on_labeled_data(appmod, monkeypatch):
    rows = []
    for year, (rent, pay) in {2024: (2420.0, 3106.0), 2025: (2870.0, 2406.0)}.items():
        for m in range(1, 13):
            rows.append((f"{year}-{m:02d}-05", "RENT", -rent, "Expense"))
            rows.append((f"{year}-{m:02d}-15", "PAYROLL", pay, "Income"))
    rows.append(("2026-01-05", "RENT", -2870.0, "Expense"))   # 2025 is then a finished year
    frame = pd.DataFrame(rows, columns=["date", "description", "amount", "master_category"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.assign(source="Chase Debit", card_last4="4823", sub_category="")
    g_ = _live(appmod)
    monkeypatch.setitem(g_, "df", frame)
    cards, headline, _ = g_["update_stats"]({"freq": "month", "start": "2025-10-01"}, "dark", 0)
    text = str(cards)
    assert "$450 more" in text and "Oct 2024 ($2,420)" in text
    assert "$700 less" in text and "($3,106)" in text
    assert "$1,150 worse" in text and "($686)" in text
    cards, _, _ = g_["update_stats"]({"freq": "year", "start": "2025-01-01"}, "dark", 0)
    assert "than 2024" in str(cards) and "$5,400 more" in str(cards)       # 12 × $450
    # A month whose year-ago month isn't labeled says so instead
    frame.loc[frame["date"] == "2024-09-05", "master_category"] = ""
    cards, _, _ = g_["update_stats"]({"freq": "month", "start": "2025-09-01"}, "dark", 0)
    assert "Sep 2024 isn't fully labeled" in str(cards)


def test_period_header_says_where_the_data_stops(appmod, monkeypatch):
    # Data ending Dec 26, 2025: December is the "latest" period, but it ended
    # long ago — the header must not call it in progress
    g_ = _live(appmod)
    frame = pd.DataFrame({"date": pd.to_datetime(["2025-11-03", "2025-12-26"]),
                          "amount": [-5.0, -7.0], "master_category": ["Expense", "Expense"]})
    monkeypatch.setitem(g_, "df", frame)
    label, sub, *_ = g_["update_period_header"]({"freq": "month", "start": "2025-12-01"})
    assert label == "Dec 2025" and sub == "through Dec 26"
    # The same words whatever today's date is: the screen depends on the data
    today = pd.Timestamp.today().normalize()
    if today != today.to_period("M").end_time.normalize():
        monkeypatch.setitem(g_, "df", frame.assign(date=[today - pd.Timedelta(days=40), today]))
        start = today.to_period("M").start_time.strftime("%Y-%m-%d")
        assert g_["update_period_header"]({"freq": "month", "start": start})[1] == \
            f"through {today:%b} {today.day}"
    # A first period the data only partly covers says where it starts
    monkeypatch.setitem(g_, "df", frame.assign(date=pd.to_datetime(["2023-02-16", "2023-05-01"])))
    assert g_["update_period_header"]({"freq": "month", "start": "2023-02-01"})[1] == "data starts Feb 16"
    assert g_["update_period_header"]({"freq": "year", "start": "2023-01-01"})[1] == "through May 1"


def test_dollar_formatting_never_shows_negative_zero(appmod):
    d, d0 = appmod["_dollar"], appmod["_dollar0"]
    assert d(-0.0) == "$0.00" and d(-0.001) == "$0.00" and d0(-0.0) == "$0" and d0(-0.4) == "$0"
    assert d(-12.5) == "-$12.50" and d0(-1234.6) == "-$1,235" and d(1234.5) == "$1,234.50"


def test_attention_count_leaves_out_what_the_headline_leaves_out(appmod):
    from Modules.labels import row_id
    parts = appmod["attention_parts"]
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-02"]),
        "description": ["SHOP", "CARD PAYMENT", "PAYMENT THANK YOU"],
        "amount": [-5.0, -300.0, 300.0], "source": ["Chase Credit", "Chase Debit", "Chase Credit"],
        "card_last4": ["", "", ""], "master_category": ["", "", ""],
    })
    today = pd.Timestamp("2026-10-03")
    assert parts(frame, [], None, 0, [], today)["unlabeled"] == "3 unlabeled ($605) not counted"
    # The two sides of a certain transfer pair aren't missing spending
    pair = {row_id(r) for r in frame.iloc[1:].to_dict("records")}
    got = parts(frame, [], None, 0, [], today, uncounted_ids=pair)
    assert got["unlabeled"] == "1 unlabeled ($5) not counted"


def test_label_them_opens_on_the_rows_holding_back_the_period(appmod):
    from Modules.labels import row_ids, unlabeled_groups
    g_ = _live(appmod)
    df = g_["df"]
    # A month the headline refuses for unlabeled money out
    month = next(q for q in sorted(df["date"].dt.to_period("M").dropna().unique(), reverse=True)
                 if not g_["_blocking_rows"]("month", q).empty)
    blocking = g_["_blocking_rows"]("month", month)
    filt = f"period|month|{month.start_time:%Y-%m-%d}"
    assert g_["_period_filter"](filt) == ("month", month)
    ids, note = g_["_filter_ids"](filt)
    assert ids == set(row_ids(blocking)) and note == f" · in {g_['period_label'](month, 'month')}"
    assert g_["_filter_ids"](filt, pairs=True) == (None, "")     # the pairs tab shows them all
    # The list holds exactly those rows — labeling them is what clears "Can't say yet"
    children, summary = g_["render_label_list"]({"display": "block"}, 0, "todo", filt,
                                                [], [], [], [], [], [], [], [])
    groups = unlabeled_groups(g_["_without_pending_dups"](df), only_row_ids=ids)
    assert sum(gr["count"] for gr in groups) == len(blocking)
    assert summary.startswith(f"{len(blocking):,} rows") and note in summary
    # SHOW ALL is offered on a subset, and goes back to everything
    assert g_["show_all_button"](filt, "todo") == g_["_SHOWN_INLINE"]
    assert g_["show_all_button"]("all", "todo") == g_["_HIDDEN"]
    assert g_["show_all_unlabeled"](1, 3) == ("all", 4)
    assert g_["_period_filter"]("period|nonsense") is None and g_["_period_filter"]("all") is None
