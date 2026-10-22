"""AI chat tools (spec docs/specs/ai-chat.md, ADR 0021): the category split
shared with the chart, the two data tools, and the number check."""
import pandas as pd
import pytest

from Modules.merchants import read_merchants
from Modules.transforms import category_split


def _rows(items):
    """(master_category, category_display, amount, description) tuples."""
    return pd.DataFrame(items, columns=["master_category", "category_display", "amount", "description"])


PERIOD = _rows([
    ("Expense", "Groceries", -50.00, "TRADER JOE S #552"),
    ("Expense", "Groceries", -30.00, "TRADER JOE S #108"),
    ("Expense", "Dining",    -20.00, "TST* JOES PIZZA"),
    ("Expense", "Dining",      5.00, "TST* JOES PIZZA"),       # refund nets against spending
    ("Expense", "Travel",    -10.00, "MTA*NYCT PAYGO"),
    ("Expense", "",           -7.00, "#48213"),                 # no category, no spelling
    ("Income",  "Salary",   1000.00, "ACME PAYROLL"),
    ("Transfer", "Payment", -500.00, "CHASE CARD AUTOPAY"),     # counts nowhere
    ("",        "Shopping",  -99.00, "AMZN Mktp US*2K4"),       # unlabeled: counts nowhere
])


def test_money_out_splits_into_top_categories_and_other():
    top, rest = category_split(PERIOD, "out", top_n=2)
    assert top.to_dict("records") == [
        {"category": "Groceries", "total": 80.0},
        {"category": "Dining", "total": 15.0},
        {"category": "Other · 2 categories", "total": 17.0},
    ]
    assert rest == ["Travel", "Uncategorized"]


def test_money_in_splits_the_same_way():
    top, rest = category_split(PERIOD, "in", top_n=2)
    assert top.to_dict("records") == [{"category": "Salary", "total": 1000.0}]
    assert rest == []


OCT = {"period": "October 2026", "dates": "Oct 1 – Oct 31, 2026"}


def test_spending_by_category_gives_formatted_lines_total_and_unreviewed():
    from Modules.chat_tools import spending_by_category
    got = spending_by_category(PERIOD, "out", period=OCT, unreviewed=99.0)
    assert got["period"] == "October 2026" and got["dates"] == "Oct 1 – Oct 31, 2026"
    assert got["direction"] == "money out"
    assert got["total"] == "$112.00"
    assert got["lines"] == [
        {"category": "Groceries", "amount": "$80.00", "share": "71%", "transactions": 2},
        {"category": "Dining", "amount": "$15.00", "share": "13%", "transactions": 2},
        {"category": "Travel", "amount": "$10.00", "share": "9%", "transactions": 1},
        {"category": "Uncategorized", "amount": "$7.00", "share": "6%", "transactions": 1},
    ]
    assert got["unreviewed"] == "$99.00"


def test_spending_by_category_folds_small_categories_into_other_with_their_count():
    from Modules.chat_tools import spending_by_category
    got = spending_by_category(PERIOD, "out", period=OCT, unreviewed=0.0, top_n=2)
    assert got["lines"][-1] == {"category": "Other · 2 categories", "amount": "$17.00",
                                "share": "15%", "transactions": 2}


def test_money_in_by_category():
    from Modules.chat_tools import spending_by_category
    got = spending_by_category(PERIOD, "in", period=OCT, unreviewed=0.0)
    assert got["direction"] == "money in" and got["total"] == "$1,000.00"
    assert got["lines"] == [{"category": "Salary", "amount": "$1,000.00", "share": "100%", "transactions": 1}]


SHOPS = _rows([
    ("Expense", "Shopping",  -40.00, "AMZN Mktp US*2K4AB1"),
    ("Expense", "Shopping",  -15.00, "AMAZON PRIME*9XZ"),
    ("Expense", "Groceries", -50.00, "TRADER JOE S #552"),
    ("Expense", "Groceries", -30.00, "TRADER JOE S #108"),
    ("Expense", "Dining",    -20.00, "TST* JOES PIZZA"),
    ("Expense", "",           -7.00, "#48213"),
    ("Income",  "Salary",   1000.00, "ACME PAYROLL"),
])


@pytest.fixture
def amazon(tmp_path):
    (tmp_path / "merchants.csv").write_text(
        "merchant,master_category,sub_category,patterns,added\nAmazon,,,,2026-10-22\n", encoding="utf-8")
    (tmp_path / "merchant_aliases.csv").write_text(
        "spelling,merchant,status\namzn mktp us,Amazon,alias\namazon prime,Amazon,alias\n", encoding="utf-8")
    return read_merchants(tmp_path)


def test_spending_by_merchant_groups_spellings_into_their_merchant(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon)
    assert got["total"] == "$162.00"
    assert got["lines"] == [
        {"merchant": "trader joe s", "amount": "$80.00", "charges": 2, "average": "$40.00"},
        {"merchant": "Amazon", "amount": "$55.00", "charges": 2, "average": "$27.50"},
        {"merchant": "tst joes pizza", "amount": "$20.00", "charges": 1, "average": "$20.00"},
        {"merchant": "(no recognisable name)", "amount": "$7.00", "charges": 1, "average": "$7.00"},
    ]


def test_spending_by_merchant_folds_the_rest_into_other(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, top_n=2)
    assert got["lines"][-1] == {"merchant": "Other · 2 merchants", "amount": "$27.00",
                                "charges": 2, "average": "$13.50"}


def test_spending_by_merchant_within_one_category(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon,
                               category="Groceries")
    assert got["category"] == "Groceries" and got["total"] == "$80.00"
    assert [line["merchant"] for line in got["lines"]] == ["trader joe s"]


def test_a_category_with_nothing_this_period_is_zero(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, category="Travel")
    assert got["total"] == "$0.00" and got["lines"] == []


def test_name_search_finds_a_merchant_by_name_and_says_which_spellings_it_covers(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, name="amazon")
    assert got["total"] == "$55.00"
    assert got["matched"] == [{"merchant": "Amazon", "spellings": ["amazon prime", "amzn mktp us"]}]


def test_name_search_also_matches_the_bank_text(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, name="Pizza")
    assert got["total"] == "$20.00"
    assert got["matched"] == [{"merchant": "tst joes pizza", "spellings": ["tst joes pizza"]}]


def test_name_search_with_no_match_says_so(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, name="costco")
    assert got["total"] == "$0.00" and got["lines"] == [] and got["matched"] == []
    assert "costco" in got["note"]


def test_tool_schemas_hold_the_model_to_real_directions_and_categories():
    from Modules.chat_tools import tool_schemas
    tools = {t["function"]["name"]: t["function"]["parameters"] for t in tool_schemas(["Dining", "Groceries"])}
    assert set(tools) == {"spending_by_category", "spending_by_merchant"}
    assert tools["spending_by_category"]["properties"]["direction"]["enum"] == ["out", "in"]
    merchant = tools["spending_by_merchant"]
    assert merchant["properties"]["category"]["enum"] == ["Dining", "Groceries"]
    assert merchant["properties"]["name"]["type"] == "string"
    assert merchant["required"] == ["direction"]


def test_all_categories_lists_every_labeled_category_in_the_history():
    from Modules.chat_tools import all_categories
    assert all_categories(PERIOD) == ["Dining", "Groceries", "Salary", "Travel", "Uncategorized"]


def _call(name, args, merchants):
    from Modules.chat_tools import call_tool
    return call_tool(name, args, rows=SHOPS, period=OCT, unreviewed=(12.0, 3.0), merchants=merchants,
                     categories=["Dining", "Groceries", "Shopping", "Travel"])


def test_call_tool_runs_the_named_tool_with_its_direction_s_unreviewed_amount(amazon):
    got = _call("spending_by_merchant", {"direction": "out", "category": "Groceries"}, amazon)
    assert got["total"] == "$80.00" and got["unreviewed"] == "$12.00"
    assert _call("spending_by_category", {"direction": "in"}, amazon)["unreviewed"] == "$3.00"


@pytest.mark.parametrize("name, args, says", [
    ("delete_everything", {}, "no tool"),
    ("spending_by_category", {"direction": "sideways"}, "direction"),
    ("spending_by_merchant", {"direction": "out", "category": "Yachts"}, "category"),
    ("spending_by_merchant", {"direction": "out", "name": 7}, "name"),
])
def test_call_tool_refuses_bad_requests_with_a_reason_instead_of_guessing(amazon, name, args, says):
    got = _call(name, args, amazon)
    assert set(got) == {"error"} and says in got["error"]


RESULTS = [{"total": "$1,000.00", "lines": [{"amount": "$80.00"}, {"amount": "-$5.00"}]}]


@pytest.mark.parametrize("reply, unverified", [
    ("You spent $80.00 on groceries out of $1,000.00.", []),
    ("About $80 on groceries.", []),                          # same amount without cents
    ("A refund of -$5.00 came back.", []),
    ("You spent $81.00, then $81.00 again and $3.50.", ["$81.00", "$3.50"]),
    ("Groceries plus dining came to $95.00.", ["$95.00"]),     # the model added: not from a tool
    ("No amounts here.", []),
])
def test_number_check_lists_amounts_no_tool_returned(reply, unverified):
    from Modules.chat_tools import unverified_amounts
    assert unverified_amounts(reply, RESULTS) == unverified


def test_number_check_with_no_tool_results_flags_every_amount():
    from Modules.chat_tools import unverified_amounts
    assert unverified_amounts("Probably $40.00.", []) == ["$40.00"]


def test_shares_are_of_the_bars_like_the_chart_even_with_a_refund_only_category():
    from Modules.chat_tools import spending_by_category
    rows = pd.concat([PERIOD, _rows([("Expense", "Gifts", 12.00, "REFUND GIFT SHOP")])])  # nets below zero: no bar
    got = spending_by_category(rows, "out", period=OCT, unreviewed=0.0)
    assert got["total"] == "$100.00"                           # the SPENT card: refunds net in
    assert [line["share"] for line in got["lines"]] == ["71%", "13%", "9%", "6%"]   # of the $112 of bars


def test_a_name_with_no_letters_or_digits_matches_nothing(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, name="*")
    assert got["lines"] == [] and got["matched"] == [] and "*" in got["note"]


def test_a_name_search_lists_every_merchant_it_matched_not_just_the_top(amazon):
    from Modules.chat_tools import spending_by_merchant
    got = spending_by_merchant(SHOPS, "out", period=OCT, unreviewed=0.0, merchants=amazon, name="o", top_n=1)
    assert "Other" not in " ".join(line["merchant"] for line in got["lines"])
    assert len(got["lines"]) == len(got["matched"]) == 3       # trader joe s, Amazon, tst joes pizza
