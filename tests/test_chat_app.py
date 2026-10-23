"""The chat panel's callbacks (spec docs/specs/ai-chat.md), through app.py
loaded against a temp copy of Test Data and a fake llama-server."""
import json
import os
import runpy
import shutil
from pathlib import Path

import dash
import pytest

from test_chat_loop import FakeServer

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def appmod(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    (data / "SORTED").mkdir()
    for name in ("merchants.csv", "merchant_aliases.csv"):     # never write the demo files
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    keys = ("FINANCE_DATA_DIR", "FINANCE_EMBED_URL", "FINANCE_LLM_URL")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["FINANCE_DATA_DIR"] = str(data)
    os.environ.pop("FINANCE_EMBED_URL", None)
    try:
        yield runpy.run_path(str(REPO / "app.py"), run_name="test_chat_app")
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


@pytest.fixture
def model(monkeypatch):
    servers = []

    def make(script, **kw):
        servers.append(FakeServer(script, **kw))
        monkeypatch.setenv("FINANCE_LLM_URL", servers[-1].url)
        return servers[-1]
    yield make
    for s in servers:
        s.close()


def _top_category(appmod):
    """The biggest bar of the latest month on the category chart."""
    _, p = appmod["_selected_period"](None)
    top, _ = appmod["_category_split"](appmod["filter_period"](appmod["df"], p))
    return top["category"].iloc[0]


def _call(category):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": "spending_by_merchant", "arguments": json.dumps({"direction": "out", "category": category})}}]}


def test_a_turn_answers_flags_made_up_amounts_and_selects_the_category(appmod, model):
    cat = _top_category(appmod)
    seen = []
    server = model([_call(cat), {"role": "assistant", "content": "About $123,456.78 there."}],
                   hook=lambda n: seen.append(appmod["chat_poll"](1, "t1")) if n == 1 else None)
    history, typed, selected, pending, status = appmod["chat_send"](1, None, "Where did my money go?", [], None, "t1")
    assert typed == pending == status == "" and selected == cat
    question, answer = history
    assert question == {"role": "user", "text": "Where did my money go?"}
    assert answer["text"] == "About $123,456.78 there." and answer["unverified"] == ["$123,456.78"]
    assert answer["period"]                                      # the date range under every answer
    out, inn = appmod["unreviewed_amounts"](appmod["_counted_rows"](
        appmod["filter_period"](appmod["df"], appmod["_selected_period"](None)[1]), appmod["_pending"]()))
    assert answer["unreviewed"] == appmod["_unreviewed_note"](out, inn)   # the stat cards' figure, from code
    assert seen == [f"Looking up {cat} by merchant…"]       # the status line, mid-turn
    assert appmod["chat_poll"](2, "t1") == ""                    # cleared once the turn ends
    system = server.requests[0]["messages"][0]
    assert system["role"] == "system" and answer["period"] in system["content"]


def test_the_model_sees_earlier_questions_and_answers(appmod, model):
    server = model([{"role": "assistant", "content": "Yes."}])
    before = [{"role": "user", "text": "Hi"}, {"role": "assistant", "text": "Hello.", "period": "x"}]
    appmod["chat_send"](1, None, "Still there?", before, None, "t2")
    sent = [(m["role"], m["content"]) for m in server.requests[0]["messages"][1:]]
    assert sent == [("user", "Hi"), ("assistant", "Hello."), ("user", "Still there?")]


def test_a_server_that_is_down_answers_with_how_to_start_it(appmod, monkeypatch):
    monkeypatch.setenv("FINANCE_LLM_URL", "http://127.0.0.1:9")
    history, _, selected, _, _ = appmod["chat_send"](1, None, "hello", [], None, "t3")
    assert "start_llm.ps1" in history[-1]["error"] and selected is dash.no_update


def test_an_empty_question_does_nothing(appmod):
    with pytest.raises(dash.exceptions.PreventUpdate):
        appmod["chat_send"](1, None, "   ", [], None, "t4")


def test_opening_the_panel_says_when_the_model_is_not_running(appmod, monkeypatch):
    monkeypatch.setenv("FINANCE_LLM_URL", "http://127.0.0.1:9")
    cls, note, chat_id = appmod["toggle_chat"](1, 0, "chat-panel")
    assert "open" in cls and "start_llm.ps1" in note and chat_id
    cls, _, _ = appmod["toggle_chat"](2, 0, cls)
    assert "open" not in cls


def test_the_unreviewed_note_says_what_isnt_counted(appmod):
    note = appmod["_unreviewed_note"]
    assert note(544.2, 0.0) == "+ $544 money out unreviewed, not counted"
    assert note(10.0, 25.0) == "+ $10 money out and $25 money in unreviewed, not counted"
    assert note(0.2, 0.0) == ""


def test_test_datas_merged_merchant_comes_out_as_one_line(appmod):
    from Modules.chat_tools import spending_by_merchant
    from Modules.merchants import read_merchants
    got = spending_by_merchant(appmod["df"], "in", period={}, unreviewed=0.0, top_n=1000,
                               merchants=read_merchants(appmod["MASTER_PATH"].parent))
    names = [line["merchant"] for line in got["lines"]]
    assert names.count("Zelle received") == 1
    assert not any(n.startswith("zelle payment from") for n in names)


def test_the_category_tool_gives_the_charts_bars_on_test_data(appmod):
    from Modules.chat_tools import spending_by_category
    rows = appmod["filter_period"](appmod["df"], appmod["_selected_period"]({"freq": "month", "start": "2026-03-01"})[1])
    bars, _ = appmod["_category_split"](rows)
    got = spending_by_category(rows, "out", period={}, unreviewed=0.0)
    assert [(line["category"], line["amount"]) for line in got["lines"]] == \
        [(r.category, appmod["_dollar"](r.total_expenses)) for r in bars.itertuples()]
