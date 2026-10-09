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
