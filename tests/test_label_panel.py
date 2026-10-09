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


def test_render_label_list_top_n(appmod):
    children, summary = appmod["render_label_list"]({"display": "block"}, 0, "todo", "dark", "all")
    assert 0 < len(children) <= appmod["LABEL_TOP_N"] + 1     # + the subcategory datalist
    assert "merchants" in summary


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
    assert (df.loc[row_ids(df) == row["row_id"], "master_category"] == "Transfer").all()


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
