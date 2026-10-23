"""What the charts say beside their bars: labels that don't sit on a bar,
and the striped (in progress) bar explained in words. Through app.py
loaded against a temp copy of Test Data."""
import os
import runpy
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def appmod(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    (data / "SORTED").mkdir()
    for name in ("merchants.csv", "merchant_aliases.csv"):     # never write the demo files
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    keys = ("FINANCE_DATA_DIR", "FINANCE_EMBED_URL")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["FINANCE_DATA_DIR"] = str(data)
    os.environ.pop("FINANCE_EMBED_URL", None)                   # never a real embedding server
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_readability")
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_the_median_is_named_under_the_chart_not_on_its_bars(appmod):
    # bars near the median hid a label drawn on the line, wherever it sat
    fig, _, note = appmod["update_period_chart"](None, "expenses", "light", 0)
    assert not fig.layout.annotations
    assert any(s.type == "line" and s.line.dash == "dash" for s in fig.layout.shapes)   # the line stays
    assert note.startswith("Dashed line: median of the complete months shown, $")


def test_the_striped_bar_is_explained_in_words(appmod):
    # the latest month is the one the demo data stops in, so it's in progress
    _, _, note = appmod["update_period_chart"](None, "expenses", "light", 0)
    as_of = appmod["_as_of"]()
    assert note.endswith(f" · Striped bar: {as_of:%b %Y} so far, through {as_of:%b} {as_of.day}")


def test_the_year_view_names_the_running_year(appmod):
    first = appmod["df"]["date"].min()
    store = {"freq": "year", "start": f"{first.year}-01-01"}
    _, _, note = appmod["update_period_chart"](store, "expenses", "light", 0)
    as_of = appmod["_as_of"]()
    assert note.endswith(f"Striped bar: {as_of.year} so far, through {as_of:%b} {as_of.day}")


def test_a_transfer_pair_button_names_its_pair(appmod):
    side = {"source": "chase", "card_last4": "", "description": "ONLINE TRANSFER", "label": "", "amount": 0}
    pair = {"key": "k", "amount": 250.0, "gap": 1, "to_label": [1, 2],
            "out": {**side, "date": "2026-03-04", "amount": -250.0},
            "in": {**side, "date": "2026-03-05", "amount": 250.0}}
    button = appmod["_pair_card"](pair).children[0].children[1]
    assert getattr(button, "aria-label") == "Label both Transfer: $250.00 moved Mar 4 to Mar 5"


def test_the_drilldown_says_transactions_not_txns(appmod):
    _, p = appmod["_selected_period"](None)
    top, _ = appmod["_category_split"](appmod["filter_period"](appmod["df"], p))
    panel = appmod["category_drilldown"](top["category"].iloc[0], "light", None)
    assert "txn" not in str(panel) and "transaction" in str(panel)
