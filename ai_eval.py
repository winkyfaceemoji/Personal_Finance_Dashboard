"""
The AI chat's question set, run against the real model (by hand, not in CI).

    .venv/Scripts/python.exe ai_eval.py

Start the model first (start_llm.ps1). Runs each question through the same
turn the chat panel runs (app._chat_turn) on a temp copy of Test Data, for
March 2026, and checks the tool the model picked, its inputs, and that the
reply has no amount a tool didn't return. Prints one line per question and
how many passed. Answers from a 9B model vary a little between runs, so read
a single failure as a hint, not a verdict.
"""
import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
STORE = {"freq": "month", "start": "2026-03-01"}
CANT = ("can't", "cannot", "can not", "not able", "unable", "don't have", "isn't available", "not available")

# (question, the tool calls that count as right: any one of them, each a tool
# name and the inputs it must have; "name" matches as a substring) or None
# when the right answer is to say it can't answer that yet
CASES = [
    ("What did I spend the most on this month?", [("spending_by_category", {"direction": "out"})]),
    ("Break down my spending by category.", [("spending_by_category", {"direction": "out"})]),
    ("How much did I spend in total?", [("spending_by_category", {"direction": "out"}),
                                        ("spending_by_merchant", {"direction": "out"})]),
    ("How much money came in this month?", [("spending_by_category", {"direction": "in"}),
                                            ("spending_by_merchant", {"direction": "in"})]),
    ("Where did my income come from?", [("spending_by_category", {"direction": "in"}),
                                        ("spending_by_merchant", {"direction": "in"})]),
    ("Which merchants paid me?", [("spending_by_merchant", {"direction": "in"})]),
    ("How much did I spend on groceries?", [("spending_by_category", {"direction": "out"}),
                                            ("spending_by_merchant", {"direction": "out", "category": "Groceries"})]),
    ("Which stores did I buy groceries at?", [("spending_by_merchant", {"direction": "out", "category": "Groceries"})]),
    ("Where did the Transit money go?", [("spending_by_merchant", {"direction": "out", "category": "Transit"})]),
    ("How much did I spend on Health & Wellness?", [
        ("spending_by_category", {"direction": "out"}),
        ("spending_by_merchant", {"direction": "out", "category": "Health & Wellness"})]),
    ("Who were my top merchants this month?", [("spending_by_merchant", {"direction": "out"})]),
    ("How much did I spend at Maple Street Grocery?", [("spending_by_merchant", {"direction": "out", "name": "maple"})]),
    ("How much did I pay Cityline Transit?", [("spending_by_merchant", {"direction": "out", "name": "cityline"}),
                                              ("spending_by_merchant", {"direction": "out", "category": "Transit"})]),
    ("How much did I send by Zelle?", [("spending_by_merchant", {"direction": "out", "name": "zelle"}),
                                       ("spending_by_merchant", {"direction": "out", "category": "Zelle"}),
                                       ("spending_by_category", {"direction": "out"})]),
    ("How much did I receive through Zelle?", [("spending_by_merchant", {"direction": "in", "name": "zelle"}),
                                               ("spending_by_category", {"direction": "in"})]),
    ("What share of my spending went to groceries?", [("spending_by_category", {"direction": "out"})]),
    ("Compare this month with last month.", None),
    ("What subscriptions am I paying for?", None),
    ("When did I last pay Maple Street Grocery?", None),
    ("Should I cut back on groceries?", None),
]


def _matches(call: tuple, want: tuple) -> bool:
    (name, args), (want_name, want_args) = call, want
    if name != want_name:
        return False
    for k, v in want_args.items():
        got = args.get(k)
        if k == "name":
            if not isinstance(got, str) or v not in got.lower():
                return False
        elif got != v:
            return False
    return True


def judge(turn: dict, expected) -> str:
    """'' when the turn passes, else why it doesn't."""
    if turn["error"]:
        return turn["error"]
    if expected is None:
        return "" if any(w in turn["reply"].lower() for w in CANT) else "should have said it can't answer"
    if not any(_matches(c, w) for c in turn["calls"] for w in expected):
        return f"tools {turn['calls']}"
    return ""


def main() -> int:
    from Modules.chat import health, llm_url
    from Modules.chat_tools import unverified_amounts
    if health(llm_url()) != "ok":
        print(f"The model server at {llm_url()} isn't ready. Start it with start_llm.ps1.")
        return 1
    data = Path(tempfile.mkdtemp(prefix="ai_eval_"))
    try:
        shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
        (data / "SORTED").mkdir()
        for name in ("rules.csv", "merchants.csv", "merchant_aliases.csv"):     # never the real data
            shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
        os.environ["FINANCE_DATA_DIR"] = str(data)
        os.environ["FINANCE_RULES_PATH"] = str(data / "SORTED" / "rules.csv")
        app = runpy.run_path(str(REPO / "app.py"), run_name="ai_eval")
        passed = 0
        for question, expected in CASES:
            turn, _, _, _ = app["_chat_turn"](question, [], STORE, "eval")
            why = judge(turn, expected)
            if not why and turn["reply"]:
                bad = unverified_amounts(turn["reply"], turn["results"])
                why = f"unverified {bad}" if bad else ""
            passed += not why
            print(f"{'PASS' if not why else 'FAIL'}  {question}" + (f"\n      {why}" if why else ""))
        print(f"\n{passed}/{len(CASES)} passed")
        return 0
    finally:
        shutil.rmtree(data, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
