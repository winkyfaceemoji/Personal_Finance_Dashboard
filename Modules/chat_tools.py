"""
The AI chat's tools (ADR 0021, spec docs/specs/ai-chat.md).

The model only picks a tool and its inputs. Every number it may quote comes
from here, already totalled and formatted, so it never does arithmetic.
Pure functions: the app passes the selected period's rows, the unreviewed
amount (counted the way the stat cards count it) and the period's wording.
Totals are label-based (ADR 0007).
"""
import json
import re

import pandas as pd

from Modules.merchants import Merchants, merchant_list, merchant_of
from Modules.transforms import CATEGORY_TOP_N, category_split, normalize_description

DIRECTIONS = {"out": ("Expense", -1, "money out"), "in": ("Income", 1, "money in")}
COUNTED = "Labeled transactions only. Transfers and unlabeled money are not counted."


def dollars(v: float) -> str:
    """$1,234.56, the stat cards' format; -0.0 and -0.001 read $0.00."""
    v = round(float(v), 2) + 0.0
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _share(part: float, total: float) -> str:
    return f"{part / total * 100:.0f}%" if total > 0 else "0%"


def _categories(picked: pd.DataFrame) -> pd.Series:
    """Each row's category as the chart shows it."""
    return picked["category_display"].where(picked["category_display"] != "", "Uncategorized")


def _picked(rows: pd.DataFrame, direction: str) -> tuple[pd.DataFrame, float]:
    """The rows one direction counts, and the total as a positive amount."""
    label, sign, _ = DIRECTIONS[direction]
    picked = rows[rows["master_category"] == label]
    return picked, float(picked["amount"].sum() * sign)


def _frame(direction: str, period: dict, total: float, unreviewed: float) -> dict:
    return {**period, "direction": DIRECTIONS[direction][2], "total": dollars(total),
            "unreviewed": dollars(unreviewed), "counted": COUNTED}


def spending_by_category(rows: pd.DataFrame, direction: str, *, period: dict, unreviewed: float,
                         top_n: int = CATEGORY_TOP_N) -> dict:
    """Money out or in by category: the chart's bars and Other, each with its
    share of the bars (as the chart shows it) and its number of transactions.
    The total is the stat card's, so a refund-only category, which has no bar,
    still nets into it."""
    picked, total = _picked(rows, direction)
    counts = _categories(picked).value_counts()
    top, rest = category_split(rows, direction, top_n)
    bars = float(top["total"].sum())
    lines = []
    for r in top.itertuples():
        n = int(counts.get(r.category, 0)) if r.category in counts else int(counts[rest].sum())
        lines.append({"category": r.category, "amount": dollars(r.total),
                      "share": _share(r.total, bars), "transactions": n})
    return {**_frame(direction, period, total, unreviewed), "lines": lines}


NO_NAME = "(no recognisable name)"


def spending_by_merchant(rows: pd.DataFrame, direction: str, *, period: dict, unreviewed: float,
                         merchants: Merchants, category: str | None = None, name: str | None = None,
                         top_n: int = 10) -> dict:
    """Money out or in by merchant (ADR 0025's `merchant_of`), largest first,
    with the rest folded into Other. `category` narrows to one category;
    `name` keeps the merchants whose name or bank text contains it and says
    which merchants (and their spellings) it matched."""
    picked, _ = _picked(rows, direction)
    sign = DIRECTIONS[direction][1]
    extra = {}
    if category:
        picked = picked[_categories(picked) == category]
        extra["category"] = category
    who = merchant_of(picked["description"], merchants)
    if name is not None:
        needle = normalize_description(name)
        hit = (who.map(normalize_description).str.contains(needle, regex=False)
               | picked["description"].map(normalize_description).str.contains(needle, regex=False)
               ) & (needle != "")                    # "*" normalizes to nothing: it matches nothing
        top_n = len(picked)                          # a search lists every merchant it matched
        picked, who = picked[hit], who[hit]
        spellings = merchant_list(picked["description"], merchants)
        extra["matched"] = [{"merchant": m, "spellings": spellings.get(m, [])}
                            for m in sorted(set(who) - {""})]
        if picked.empty:
            extra["note"] = f"No merchant or bank text in this period matches “{name}”."
    g = (picked.assign(merchant=who.replace("", NO_NAME), amount=picked["amount"] * sign)
         .groupby("merchant")["amount"].agg(["sum", "count"])
         .sort_values(["sum", "count"], ascending=False))
    top, rest = g.head(top_n), g.iloc[top_n:]
    lines = [_merchant_line(m, r["sum"], r["count"]) for m, r in top.iterrows()]
    if not rest.empty:
        lines.append(_merchant_line(f"Other · {len(rest)} merchants", rest["sum"].sum(), rest["count"].sum()))
    total = float(g["sum"].sum())
    return {**_frame(direction, period, total, unreviewed), **extra, "lines": lines}


def _merchant_line(merchant: str, amount: float, charges: int) -> dict:
    return {"merchant": merchant, "amount": dollars(amount), "charges": int(charges),
            "average": dollars(amount / charges)}


def all_categories(rows: pd.DataFrame) -> list[str]:
    """Every category a labeled Expense or Income row has, across the whole
    history: the fixed list the model must choose from (a category with no
    spending this period then answers $0 instead of being made up)."""
    labeled = rows[rows["master_category"].isin(["Expense", "Income"])]
    return sorted(set(_categories(labeled)))


def tool_schemas(categories: list[str]) -> list[dict]:
    """The two tools in the OpenAI format llama-server takes. The enums are
    enforced again by `call_tool`, whatever the server does with them."""
    direction = {"type": "string", "enum": ["out", "in"],
                 "description": "out = spending (money out), in = income (money in)"}
    return [
        {"type": "function", "function": {
            "name": "spending_by_category",
            "description": "Totals by category for the selected period, largest first, with each "
                           "category's share and number of transactions.",
            "parameters": {"type": "object", "properties": {"direction": direction},
                           "required": ["direction"]}}},
        {"type": "function", "function": {
            "name": "spending_by_merchant",
            "description": "Totals by merchant for the selected period, largest first, with charges "
                           "and the average charge. Optionally within one category, or only merchants "
                           "whose name or bank text contains `name`.",
            "parameters": {"type": "object", "properties": {
                "direction": direction,
                "category": {"type": "string", "enum": list(categories)},
                "name": {"type": "string", "description": "part of a merchant's name, e.g. amazon"}},
                "required": ["direction"]}}},
    ]


def call_tool(name: str, args: dict, *, rows: pd.DataFrame, period: dict, unreviewed: tuple[float, float],
              merchants: Merchants, categories: list[str]) -> dict:
    """Run one tool the model asked for. A request outside the schema gets
    {"error": why} back for the model to read, never a guess."""
    if name not in ("spending_by_category", "spending_by_merchant"):
        return {"error": f"There is no tool called {name!r}."}
    args = args if isinstance(args, dict) else {}
    direction = args.get("direction")
    if direction not in DIRECTIONS:
        return {"error": "direction must be \"out\" or \"in\"."}
    shared = {"period": period, "unreviewed": unreviewed[0] if direction == "out" else unreviewed[1]}
    if name == "spending_by_category":
        return spending_by_category(rows, direction, **shared)
    category, text = args.get("category"), args.get("name")
    if category is not None and category not in categories:
        return {"error": f"Unknown category {category!r}. Choose one of: {', '.join(categories)}."}
    if text is not None and not isinstance(text, str):
        return {"error": "name must be text."}
    return spending_by_merchant(rows, direction, merchants=merchants, category=category, name=text, **shared)


_AMOUNT = re.compile(r"-?\$\s?\d[\d,]*(?:\.\d+)?")


def _cents(text: str) -> int:
    return round(abs(float(re.sub(r"[^\d.]", "", text))) * 100)


def unverified_amounts(reply: str, results: list) -> list[str]:
    """Dollar amounts in the model's reply that no tool returned this turn, in
    order, once each. Sign and missing cents don't matter ($80 is $80.00);
    any other difference, a sum the model worked out included, is flagged."""
    known = {_cents(m) for m in _AMOUNT.findall(json.dumps(results, ensure_ascii=False))}
    out = []
    for m in _AMOUNT.findall(reply):
        if _cents(m) not in known and m not in out:
            out.append(m)
    return out
