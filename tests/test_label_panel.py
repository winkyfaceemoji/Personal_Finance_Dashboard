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
    shutil.copy(REPO / "Test Data" / "SORTED" / "rules.csv", rules)          # never write the demo rules
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
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-02", "2025-03-03"]),
        "description": ["AMAZON MKTP 1", "AMAZON MKTP 2", "#99999"], "amount": [-20.0, 20.0, -5.0],
        "master_category": ["", "", ""], "sub_category": ["", "", ""],
        "source": ["Chase Credit"] * 3, "card_last4": ["", "", ""],
    })
    for g in unlabeled_groups(df):
        assert g["mixed"] or g["fallback"]
        card = appmod["_group_card"](g, remember_check(df, g, read_merchants(None)))
        ids = _ids(card)
        assert not any(isinstance(i, dict) and i.get("type") == "lbl-group" for i in ids)
        assert any(isinstance(i, dict) and i.get("type") == "lbl-row" for i in ids)


def test_group_card_row_ids_unique(appmod):
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-01"]),
        "description": ["CAFE", "CAFE"], "amount": [-4.5, -4.5],
        "master_category": ["", ""], "sub_category": ["", ""],
        "source": ["Chase Credit"] * 2, "card_last4": ["", ""],
    })
    g = unlabeled_groups(df)[0]
    card = appmod["_group_card"](g, remember_check(df, g, read_merchants(None)))
    ids = [str(i) for i in _ids(card)]
    assert len(ids) == len(set(ids))            # twins don't collide


def test_group_card_shows_merchant_and_the_banks_text_apart(appmod):
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    raw = "CENTRAL BANK COLLECTION 590951122973920 WEB ID: 9886281493"
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-04-01", "2025-05-01"]),
        "description": [raw, raw.replace("590951122973920", "111"), raw.replace("590951122973920", "222")],
        "amount": [-500.0, -500.0, -500.0], "master_category": [""] * 3, "sub_category": [""] * 3,
        "source": ["Chase Debit"] * 3, "card_last4": [""] * 3,
    })
    g = unlabeled_groups(df)[0]
    texts = [c for c in _walk(appmod["_group_card"](g, remember_check(df, g, read_merchants(None))))
             if isinstance(c, str)]
    assert {"CENTRAL BANK COLLECTION", "Transaction text", "+2 other wordings"} <= set(texts)
    assert raw in texts                                    # the bank's text, unaltered
    one = unlabeled_groups(df.iloc[:1])[0]
    texts = [c for c in _walk(appmod["_group_card"](one, remember_check(df.iloc[:1], one, read_merchants(None))))
             if isinstance(c, str)]
    assert "Transaction text" in texts and not any("other wording" in t for t in texts)


def test_nameless_group_card_says_no_clear_merchant(appmod):
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01"]), "description": ["#1234"], "amount": [-4.5],
        "master_category": [""], "sub_category": [""], "source": ["Chase Credit"], "card_last4": [""],
    })
    g = unlabeled_groups(df)[0]
    texts = [c for c in _walk(appmod["_group_card"](g, remember_check(df, g, read_merchants(None))))
             if isinstance(c, str)]
    assert "No clear merchant" in texts and "#1234" in texts     # the text itself, unaltered
    assert texts.count("#1234") == 1                             # once, not again in the row
    card = appmod["_group_card"](g, remember_check(df, g, read_merchants(None)))
    remember = next(c for c in _walk(card) if getattr(c, "id", None) == {"type": "lbl-remember", "group": g["key"]})
    assert remember.style == {"display": "none"} and remember.value == []
    assert not any("no recognizable" in t for t in texts)


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
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01"]), "description": ["AB 12"], "amount": [-4.5],
        "master_category": [""], "sub_category": [""], "source": ["Chase Credit"], "card_last4": [""],
    })
    # A short name is fine now: a merchant's rule matches whole spellings, so
    # "ab" can't sweep up other merchants the way a keyword could (ADR 0025).
    # One transaction is still thin evidence: allowed, never ticked by default
    g = unlabeled_groups(df)[0]
    chk = remember_check(df, g, read_merchants(None))
    card = appmod["_group_card"](g, chk)
    remember = next(c for c in _walk(card) if getattr(c, "id", None) == {"type": "lbl-remember", "group": g["key"]})
    assert remember.value == [] and remember.options[0]["disabled"] is False


def _card_remember(appmod, rows):
    """(Remember checklist, note text) for the card of the first group in rows."""
    from Modules.labels import unlabeled_groups
    from Modules.merchants import read_merchants, remember_check
    df = pd.DataFrame({
        "date": pd.to_datetime([r[0] for r in rows]), "description": [r[1] for r in rows],
        "amount": [r[2] for r in rows], "master_category": [""] * len(rows),
        "sub_category": [""] * len(rows), "source": ["Chase Credit"] * len(rows),
        "card_last4": [""] * len(rows),
    })
    g = unlabeled_groups(df)[0]
    card = appmod["_group_card"](g, remember_check(df, g, read_merchants(None)))
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


def test_only_a_regular_merchant_starts_ticked(appmod):
    # Two charges in one month (a trip): the user's call
    remember, note = _card_remember(appmod, [("2025-03-01", "STARBUCKS STORE 1", -5.0),
                                             ("2025-03-02", "STARBUCKS STORE 2", -6.0)])
    assert remember.value == [] and remember.options[0]["disabled"] is False
    assert "seen in 1 month — tick to remember anyway" in note and "only one transaction" not in note
    remember, note = _card_remember(appmod, [("2025-03-01", "STARBUCKS STORE 1", -5.0),
                                             ("2025-04-02", "STARBUCKS STORE 2", -6.0)])
    assert remember.value == [] and "seen in 2 months" in note
    # Seen in three different months: a regular, worth remembering
    remember, note = _card_remember(appmod, [("2025-03-01", "STARBUCKS STORE 1", -5.0),
                                             ("2025-04-02", "STARBUCKS STORE 2", -6.0),
                                             ("2025-06-09", "STARBUCKS STORE 3", -4.0)])
    assert remember.value == ["yes"] and remember.options[0]["disabled"] is False
    assert "tick to remember" not in note


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
    cards = [c for c in children if getattr(c, "className", "") == "app-card label-group"]
    section = next((i for i, c in enumerate(children) if getattr(c, "className", "") == "lg-section"), len(children))
    named = [c for c in children[:section] if c in cards]
    nameless = [c for c in children[section:] if c in cards]
    # Up to LABEL_TOP_N merchants, then up to LABEL_TOP_N nameless rows in their own section
    assert 0 < len(named) <= appmod["LABEL_TOP_N"] and len(nameless) <= appmod["LABEL_TOP_N"]
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


def _merged(name, *spellings):
    """Merchant files merging `spellings` into one merchant with no rule yet.
    Each test uses its own demo spellings: the app module, and its master,
    are shared across tests."""
    return ("merchant,master_category,sub_category,patterns,added" + chr(10) + f"{name},,,," + chr(10),
            "spelling,merchant,status" + chr(10) + "".join(f"{s},{name},alias" + chr(10) for s in spellings))


@pytest.fixture
def merchant_files(appmod):
    """Write merchant files into the app's temp data folder for one test, then
    take them away again (the app module is shared across tests)."""
    g_ = _live(appmod)
    folder = g_["MASTER_PATH"].parent
    master = g_["MASTER_PATH"].read_bytes()       # put back after, so later tests still find unlabeled rows

    def write(merchants_csv, aliases_csv):
        (folder / "merchants.csv").write_text(merchants_csv, encoding="utf-8")
        (folder / "merchant_aliases.csv").write_text(aliases_csv, encoding="utf-8")
        g_["df"] = g_["load_transactions"](g_["MASTER_PATH"], rules_path=g_["RULES_PATH"])
    yield write
    for name in ("merchants.csv", "merchant_aliases.csv"):
        (folder / name).unlink(missing_ok=True)
    g_["MASTER_PATH"].write_bytes(master)
    g_["df"] = g_["load_transactions"](g_["MASTER_PATH"], rules_path=g_["RULES_PATH"])


def _merchant_group(g_, name):
    return next(g for g in g_["_todo_groups"]("all") if g["merchant"] == name)


def test_to_label_groups_a_merchants_spellings_and_labels_them_in_one_click(appmod, merchant_files):
    from Modules.merchants import merchant_of, read_merchants
    g_ = _live(appmod)
    merchant_files(*_merged("Shelf Finds", "quillfield books", "sp lantern goods"))
    grp = _merchant_group(g_, "Shelf Finds")
    assert grp["spellings"] == ["quillfield books", "sp lantern goods"]
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    assert status.startswith(f"Labeled {grp['count']} Shelf Finds rows as Expense")
    df = g_["df"]
    mine = merchant_of(df["description"], read_merchants(g_["MASTER_PATH"].parent)) == "Shelf Finds"
    assert mine.sum() == grp["count"] and (df.loc[mine, "master_category"] == "Expense").all()


def test_remember_saves_the_merchants_rule_and_undo_takes_it_back(appmod, merchant_files):
    from Modules.merchants import read_merchants
    g_ = _live(appmod)
    merchant_files(*_merged("Screen and Stay", "sundial cinemas", "oakridge hotel"))
    folder = g_["MASTER_PATH"].parent
    files = [g_["MASTER_PATH"], folder / "merchants.csv", folder / "merchant_aliases.csv"]
    before = [f.read_bytes() for f in files]
    grp = _merchant_group(g_, "Screen and Stay")
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "Outings", True, 0, "all")
    assert status.endswith(" · remembered: Screen and Stay is Expense")
    rule = read_merchants(folder).table.set_index("merchant").loc["Screen and Stay"]
    assert (rule["master_category"], rule["sub_category"]) == ("Expense", "Outings")
    status2, _, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status2 == "Undone."
    assert [f.read_bytes() for f in files] == before


def test_remember_on_an_unmerged_spelling_makes_it_a_merchant(appmod, merchant_files):
    from Modules.merchants import read_merchants
    g_ = _live(appmod)
    merchant_files(*_merged("Shelf Finds", "quillfield books"))
    grp = _merchant_group(g_, "NORTHGATE AIRLINES")
    status, _, _, _ = g_["_do_label"](_group_trig(grp), "", True, 0, "all")
    assert status.endswith(" · remembered: NORTHGATE AIRLINES is Expense")     # named as the card shows it
    m = read_merchants(g_["MASTER_PATH"].parent)
    assert m.alias_of["northgate airlines"] == "northgate airlines"
    assert m.table.set_index("merchant").loc["northgate airlines", "master_category"] == "Expense"


def test_an_alias_change_makes_the_open_list_stale(appmod, merchant_files):
    g_ = _live(appmod)
    merchant_files(*_merged("Gym and Games", "ironworks gym", "starlight games store"))
    grp = _merchant_group(g_, "Gym and Games")
    merchant_files(*_merged("Gym and Games", "ironworks gym", "starlight games store",
                            "open hands fund"))   # changed since it was drawn
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    status, _, _, _ = g_["_do_label"](_group_trig(grp), "", False, 0, "all")
    assert status.startswith("The list changed")
    assert master.read_bytes() == before


def test_a_locked_merchant_file_keeps_the_labels_and_undo(appmod, merchant_files, monkeypatch):
    g_ = _live(appmod)
    merchant_files(*_merged("Snacks", "tst copper pot diner", "sq little fern bakery"))
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    real = os.replace

    def replace(src, dst):
        if Path(dst).name == "merchants.csv":
            raise PermissionError(13, "open in Excel", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    status, undo, _, _ = g_["_do_label"](_group_trig(_merchant_group(g_, "Snacks")), "", True, 0, "all")
    assert status.startswith("Labeled") and status.endswith(
        " · not remembered: a merchant file is open in another program")
    assert undo and undo["backup"] and master.read_bytes() != before


@pytest.mark.parametrize("locked", ["restore_backup", "restore_files"])
def test_undo_with_a_locked_file_changes_nothing(appmod, merchant_files, monkeypatch, locked):
    g_ = _live(appmod)
    spellings = {"restore_backup": ("pixelplay monthly", "streamly.com"),
                 "restore_files": ("cloudnote subscription", "paypal pixelforge")}[locked]
    merchant_files(*_merged("Subs " + locked, *spellings))
    folder = g_["MASTER_PATH"].parent
    files = [g_["MASTER_PATH"], folder / "merchants.csv", folder / "merchant_aliases.csv"]
    _, undo, _, _ = g_["_do_label"](_group_trig(_merchant_group(g_, "Subs " + locked)), "", True, 0, "all")
    after = [f.read_bytes() for f in files]

    def refuse(*a, **k):
        raise PermissionError("open in Excel")
    monkeypatch.setitem(g_, locked, refuse)
    status, _, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status.startswith("⚠") and "close it and try again" in status
    assert [f.read_bytes() for f in files] == after              # not half undone


def test_rows_with_no_merchant_name_come_last_in_their_own_section(appmod):
    g_ = _live(appmod)
    children, _ = g_["render_label_list"]({"display": "block"}, 0, "todo", "all",
                                          [], [], [], [], [], [], [], [])
    def in_order(c):                                 # page order (_walk doesn't keep it)
        if isinstance(c, str):
            yield c
        elif isinstance(c, (list, tuple)):
            for x in c:
                yield from in_order(x)
        elif getattr(c, "children", None) is not None:
            yield from in_order(c.children)
    texts = list(in_order(children))
    assert "NO MERCHANT NAME" in texts
    heading = texts.index("NO MERCHANT NAME")
    assert "No clear merchant" not in texts[:heading]            # nameless cards only after it
    assert "No clear merchant" in texts[heading:]


def _in_order(c):
    """Every string in a component tree, in page order."""
    if isinstance(c, str):
        yield c
    elif isinstance(c, (list, tuple)):
        for x in c:
            yield from _in_order(x)
    elif getattr(c, "children", None) is not None:
        yield from _in_order(c.children)


def _merchants_view(g_, sort="spend"):
    return g_["render_label_list"]({"display": "block"}, 0, "merchants", "all",
                                   [], [], [], [], [], [], [], [], sort)


@pytest.mark.parametrize("sort", ["spend", "attention"])
def test_all_merchants_lists_every_merchant_all_time_and_folds_the_rest(appmod, sort):
    from Modules.merchants import merchant_overview, sort_merchants
    g_ = _live(appmod)
    children, summary = _merchants_view(g_, sort)
    items, nameless = merchant_overview(g_["df"], g_["_merchants"]())
    n = g_["LABEL_TOP_N"]
    assert len(items) > n                                        # the demo has enough to fold
    by_spend = sort_merchants(items, "spend")
    biggest, rest = by_spend[:n], by_spend[n:]                   # "Other" always holds the smallest
    texts = list(_in_order(children))
    titles = [t for t in texts if t in {i["name"] for i in items}]
    assert titles == [i["name"] for i in sort_merchants(biggest, sort)]   # the biggest, in the chosen order
    assert max(i["out"] for i in rest) <= min(i["out"] for i in biggest)
    other = next(t for t in texts if t.startswith("Other · "))
    assert other == (f"Other · {len(rest)} merchants · {g_['_dollar0'](sum(i['out'] for i in rest))} out · "
                     f"{g_['_dollar0'](sum(i['inn'] for i in rest))} in")
    assert any(t.startswith(f"No merchant name · {nameless['rows']} rows") for t in texts)
    assert summary == (f"{len(items)} merchants · {g_['_dollar0'](sum(i['out'] for i in items))} out · "
                       f"{g_['_dollar0'](sum(i['inn'] for i in items))} in, all time")


def test_needs_attention_never_folds_away_a_big_merchant(appmod, merchant_files):
    g_ = _live(appmod)
    # The biggest spender (the demo's rent) has a rule, so it needs no
    # attention and sorts last — yet it must keep its card, not fold into Other
    merchant_files("merchant,master_category,sub_category,patterns,added\nRent,Expense,Housing,,\n",
                   "spelling,merchant,status\nzelle payment to alex morrow,Rent,alias\n")
    children, _ = _merchants_view(g_, "attention")
    texts = list(_in_order(children))
    assert "Rent" in texts
    assert texts.index("Rent") > texts.index("PAYMENT TO CHASE CARD ENDING IN")   # still last in attention order


def test_all_merchants_survives_a_merchant_with_no_dates_and_counts_like_the_rest(appmod, monkeypatch):
    g_ = _live(appmod)
    frame = g_["df"].copy()
    hit = frame["description"].str.startswith("NORTHGATE AIRLINES")
    frame.loc[hit, "date"] = pd.NaT                           # every date emptied in Excel
    monkeypatch.setitem(g_, "df", frame)
    children, summary = _merchants_view(g_)                   # must not raise
    texts = list(_in_order(children))
    assert any(t.endswith("· no dates") for t in texts)
    assert summary.endswith(" in, all time") and " out · " in summary   # money in is in the summary too
    # Copies waiting on a replacement-card question count nowhere else, so not here either
    monkeypatch.setitem(g_, "_without_pending_dups", lambda d: d[~d["description"].str.startswith("NORTHGATE")])
    _, summary2 = _merchants_view(g_)
    assert summary2.split(" merchant")[0] == str(int(summary.split(" merchant")[0]) - 1)


def test_all_merchants_still_counts_nameless_rows_with_no_merchants(appmod, monkeypatch):
    g_ = _live(appmod)
    frame = g_["df"]
    monkeypatch.setitem(g_, "df", frame[frame["description"].str.startswith("REAL TIME PAYMENT")])
    children, _ = _merchants_view(g_)
    texts = list(_in_order(children))
    assert "No merchants yet" in texts and any(t.startswith("No merchant name · ") for t in texts)


def test_the_merchants_button_opens_where_the_work_is(appmod, monkeypatch):
    g_ = _live(appmod)
    assert g_["_todo_groups"]("all")                             # something unlabeled
    assert g_["_opening_tab"]("open-merchants-btn") == "todo"
    monkeypatch.setitem(g_, "_todo_groups", lambda filt: [])     # everything labeled
    assert g_["_opening_tab"]("open-merchants-btn") == "merchants"
    assert g_["_opening_tab"]("open-transfer-check") == "pairs"


# ── Merge, split, rename (ticket 05) ──────────────────────────────────────────

def _open_spellings(g_, k):
    """k bare spellings that are still wholly unlabeled, one direction of money,
    and not merged: the app module (and its master) is shared across tests."""
    picks = [g["mkey"] for g in g_["_todo_groups"]("all")
             if not g["fallback"] and not g["mixed"] and g["mkey"] == g["mkey"].lower()
             and g["spellings"] == [g["mkey"]] and not g["mkey"].startswith(("payment", "zelle", "venmo"))]
    assert len(picks) >= k
    return picks[:k]


def _travel(spelling):
    return ("merchant,master_category,sub_category,patterns,added" + chr(10) + "Travel,Expense,Trips,," + chr(10),
            "spelling,merchant,status" + chr(10) + f"{spelling},Travel,alias" + chr(10))


def _files_of(g_):
    folder = g_["MASTER_PATH"].parent
    return [folder / "merchants.csv", folder / "merchant_aliases.csv"]


def test_merge_previews_what_it_relabels_then_does_exactly_that_and_undoes(appmod, merchant_files):
    from Modules.merchants import display_name, merchant_of
    g_ = _live(appmod)
    anchor, source = _open_spellings(g_, 2)
    merchant_files(*_travel(anchor))
    df = g_["df"]
    mine = merchant_of(df["description"], g_["_merchants"]()) == source
    n, dollars = int(mine.sum()), df.loc[mine, "amount"].abs().sum()
    assert n and (df.loc[mine, "master_category"] == "").all()
    before = [f.read_bytes() for f in _files_of(g_)]
    pending, text = g_["_merchant_preview"]("merge", source, "Travel")
    assert text == (f"Merge {display_name(source)} into Travel: {n} row{'s' if n != 1 else ''} "
                    f"({g_['_dollar0'](dollars)}) unlabeled → Expense · Trips")
    status, undo, _, version = g_["_do_merchant_change"](pending, 0)
    assert status == f"Merged {display_name(source)} into Travel." and version == 1
    df = g_["df"]
    assert (df.loc[mine, "master_category"] == "Expense").all()          # exactly what the preview said
    assert (merchant_of(df["description"], g_["_merchants"]())[mine] == "Travel").all()
    status2, _, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status2 == "Undone." and [f.read_bytes() for f in _files_of(g_)] == before


def test_split_takes_a_spelling_out_and_its_rule_with_it(appmod, merchant_files):
    g_ = _live(appmod)
    a, b = _open_spellings(g_, 2)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10) + "Shelves,Expense,,," + chr(10),
                   "spelling,merchant,status" + chr(10) + f"{a},Shelves,alias" + chr(10) + f"{b},Shelves,alias" + chr(10))
    pending, text = g_["_merchant_preview"]("split", "Shelves", None, b)
    assert text.startswith(f"Split {b} out of Shelves: ") and "Expense → unlabeled" in text
    status, _, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status == f"Split {b} out of Shelves."
    assert b in {g["mkey"] for g in g_["_todo_groups"]("all")}           # its own merchant again, unlabeled


def test_move_takes_one_spelling_to_another_merchant_and_undo_brings_it_back(appmod, merchant_files):
    g_ = _live(appmod)
    a, b, c = _open_spellings(g_, 3)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10) + "Pair,,,," + chr(10)
                   + "Travel,Expense,,," + chr(10),
                   "spelling,merchant,status" + chr(10) + f"{a},Pair,alias" + chr(10) + f"{b},Pair,alias" + chr(10)
                   + f"{c},Travel,alias" + chr(10))
    before = [f.read_bytes() for f in _files_of(g_)]
    pending, text = g_["_merchant_preview"]("move", "Pair", "travel", b)       # typed in any case
    assert text.startswith(f"Move {b} to Travel: ") and "unlabeled → Expense" in text
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status == f"Moved {b} to Travel." and g_["_merchants"]().alias_of == {a: "Pair", b: "Travel", c: "Travel"}
    g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert [f.read_bytes() for f in _files_of(g_)] == before


def test_rename_keeps_everything_and_refuses_a_name_in_use(appmod, merchant_files):
    g_ = _live(appmod)
    anchor, other = _open_spellings(g_, 2)
    merchant_files(*_travel(anchor))
    pending, text = g_["_merchant_preview"]("rename", "Travel", "Hotel")
    assert text == "Rename Travel to Hotel: no labels change"
    g_["_do_merchant_change"](pending, 0)
    m = g_["_merchants"]()
    assert m.table["merchant"].tolist() == ["Hotel"] and m.alias_of == {anchor: "Hotel"}
    pending, text = g_["_merchant_preview"]("rename", "Hotel", other)
    assert pending is None and text == f"Another merchant or spelling is already called {other}"


def test_a_merchant_change_on_stale_or_locked_files_writes_nothing(appmod, merchant_files, monkeypatch):
    g_ = _live(appmod)
    anchor, source, third = _open_spellings(g_, 3)
    merchant_files(*_travel(anchor))
    pending, _ = g_["_merchant_preview"]("merge", source, "Travel")
    files = _travel(anchor)
    merchant_files(files[0], files[1] + f"{third},Travel,alias" + chr(10))      # changed since the preview
    before = [f.read_bytes() for f in _files_of(g_)]
    status, _, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status.startswith("The merchants changed") and [f.read_bytes() for f in _files_of(g_)] == before
    pending, _ = g_["_merchant_preview"]("merge", source, "Travel")

    def locked(*a, **k):
        raise PermissionError("Nothing changed: merchants.csv is open in another program")
    monkeypatch.setitem(g_, "save_change", locked)
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status.startswith("⚠ Nothing changed: merchants.csv is open in another program")
    assert undo is g_["dash"].no_update and [f.read_bytes() for f in _files_of(g_)] == before


# ── Relabel a merchant (ticket 06) ────────────────────────────────────────────

def _hand_labeled(g_, spelling, cat="Expense"):
    """Label every row of a bare spelling by hand (a group click, no rule)."""
    grp = next(g for g in g_["_todo_groups"]("all") if g["mkey"] == spelling)
    status, _, _, _ = g_["_do_label"](_group_trig(grp, cat=cat), "", False, 0, "all")
    assert status.startswith("Labeled")
    return grp["count"]


def test_relabel_rewrites_past_hand_labels_and_the_rule_then_undoes(appmod, merchant_files):
    from Modules.merchants import merchant_of
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    n = _hand_labeled(g_, spelling)
    files = [g_["MASTER_PATH"], *_files_of(g_)]
    before = [f.read_bytes() for f in files]
    df = g_["df"]
    mine = merchant_of(df["description"], g_["_merchants"]()) == spelling
    dollars = df.loc[mine, "amount"].abs().sum()
    pending, text = g_["_merchant_preview"]("relabel", spelling, "Gifts", cat="Transfer")
    assert text == (f"Relabel {spelling.upper()} as Transfer · Gifts: {n} row{'s' if n != 1 else ''} "
                    f"({g_['_dollar0'](dollars)}) Expense → Transfer · Gifts")
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status == (f"Relabeled {spelling.upper()} as Transfer · Gifts · {n} hand label{'s' if n != 1 else ''} "
                      f"rewritten · rule saved")
    df = g_["df"]
    assert (df.loc[mine, "master_category"] == "Transfer").all() and (df.loc[mine, "sub_category"] == "Gifts").all()
    rule = g_["_merchants"]().table.set_index("merchant").loc[spelling]
    assert (rule["master_category"], rule["sub_category"]) == ("Transfer", "Gifts")
    status2, _, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status2 == "Undone." and [f.read_bytes() for f in files] == before


def test_relabel_leaves_a_row_whose_label_changed_since_and_says_so(appmod, merchant_files):
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    n = _hand_labeled(g_, spelling)
    pending, _ = g_["_merchant_preview"]("relabel", spelling, "", cat="Income")
    master = g_["MASTER_PATH"]
    raw = pd.read_csv(master, dtype=str, keep_default_na=False)
    from Modules.labels import merchant_key
    first = raw.index[raw["description"].map(merchant_key) == spelling][0]
    raw.loc[first, "master_category"] = "Transfer"                      # changed in Excel since the preview
    raw.to_csv(master, index=False)
    status, _, _, _ = g_["_do_merchant_change"](pending, 0)
    assert f" · {n - 1} hand label{'s' if n - 1 != 1 else ''} rewritten" in status
    assert status.endswith(" · 1 row left as it was (its label changed since)")
    assert pd.read_csv(master, dtype=str, keep_default_na=False).loc[first, "master_category"] == "Transfer"


def test_relabel_keeps_labels_and_undo_when_the_rule_cant_be_saved(appmod, merchant_files, monkeypatch):
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    _hand_labeled(g_, spelling)
    pending, _ = g_["_merchant_preview"]("relabel", spelling, "", cat="Income")

    def locked(*a, **k):
        raise PermissionError("Nothing changed: merchants.csv is open in another program")
    monkeypatch.setitem(g_, "save_change", locked)
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status.startswith("Relabeled ") and status.endswith(
        " · rule not saved: a merchant file is open in another program")
    assert undo["backup"] and "merchant_files" not in undo


def test_relabel_rewrites_a_hand_label_that_has_an_unlabeled_twin(appmod, merchant_files):
    from Modules.labels import merchant_key
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    master = g_["MASTER_PATH"]
    raw = pd.read_csv(master, dtype=str, keep_default_na=False)
    mine = raw.index[raw["description"].map(merchant_key) == spelling]
    raw = pd.concat([raw.loc[mine[:1]].assign(master_category="Expense"), raw.loc[mine[:1]], raw.drop(mine[:1])],
                    ignore_index=True)                          # one row hand-labeled, its identical twin not
    raw.to_csv(master, index=False)
    g_["df"] = g_["load_transactions"](master, rules_path=g_["RULES_PATH"])
    pending, _ = g_["_merchant_preview"]("relabel", spelling, "", cat="Income")
    status, _, _, _ = g_["_do_merchant_change"](pending, 0)
    assert "left as it was" not in status
    after = pd.read_csv(master, dtype=str, keep_default_na=False)
    assert (after.loc[after["description"].map(merchant_key) == spelling, "master_category"]
            .isin(["Income", ""])).all() and (after["master_category"] == "Income").any()


def test_relabel_with_the_master_open_in_excel_changes_nothing(appmod, merchant_files, monkeypatch):
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    _hand_labeled(g_, spelling)
    pending, _ = g_["_merchant_preview"]("relabel", spelling, "", cat="Income")
    files = [g_["MASTER_PATH"], *_files_of(g_)]
    before = [f.read_bytes() for f in files]

    def locked(*a, **k):
        raise PermissionError("open in Excel")
    monkeypatch.setitem(g_, "atomic_write_csv", locked)
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status == g_["_LOCKED_MSG"] and undo is g_["dash"].no_update
    assert [f.read_bytes() for f in files] == before


def test_relabel_preview_lists_refunds_on_their_own(appmod, merchant_files):
    g_ = _live(appmod)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10),
                   "spelling,merchant,status" + chr(10))
    harbor = next(g for g in g_["_todo_groups"]("all") if g["mkey"] == "harbor outfitters")   # money in and out
    for row in harbor["rows"]:                                      # label it row by row, as the panel would
        g_["_do_label"]({"type": "lbl-row", "group": harbor["key"], "row": row["row_id"], "cat": "Expense"},
                        "", False, 0, "all")
    _, text = g_["_merchant_preview"]("relabel", "harbor outfitters", "", cat="Transfer")
    refunds = [r for r in harbor["rows"] if r["amount"] > 0]
    n = sum(r["count"] for r in refunds)
    assert f" · includes {n} refund{'s' if n != 1 else ''} (" in text


# ── Patterns and pattern suggestions (ticket 07) ──────────────────────────────

def _with_pattern(spelling):
    """Merchant files where 'Look-alikes' owns a pattern matching `spelling`."""
    word = spelling.split()[-1]
    return ("merchant,master_category,sub_category,patterns,added" + chr(10) + f"Look-alikes,Expense,,{word}," + chr(10),
            "spelling,merchant,status" + chr(10))


def test_a_pattern_suggestion_shows_on_both_views_and_joins_only_on_confirm(appmod, merchant_files):
    from Modules.merchants import display_name
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files(*_with_pattern(spelling))
    assert spelling not in g_["_merchants"]().alias_of                    # suggested, not joined
    todo, _ = g_["render_label_list"]({"display": "block"}, 0, "todo", "all", [], [], [], [], [], [], [], [])
    allm, _ = _merchants_view(g_)
    line = "Same as Look-alikes?"
    assert line in list(_in_order(todo)) and line in list(_in_order(allm))
    pending, text = g_["_merchant_preview"]("accept", spelling)
    assert text.startswith(f"Join {display_name(spelling)} to Look-alikes: ") and "unlabeled → Expense" in text
    status, _, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status == f"Joined {display_name(spelling)} to Look-alikes."
    assert g_["_merchants"]().alias_of[spelling] == "Look-alikes"


def test_a_dismissed_suggestion_never_comes_back(appmod, merchant_files):
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files(*_with_pattern(spelling))
    pending, text = g_["_merchant_preview"]("dismiss", spelling)
    assert text.endswith("no labels change")
    status, undo, _, _ = g_["_do_merchant_change"](pending, 0)
    assert status.startswith("Won't suggest")
    todo, _ = g_["render_label_list"]({"display": "block"}, 0, "todo", "all", [], [], [], [], [], [], [], [])
    assert "Same as Look-alikes?" not in list(_in_order(todo))
    assert spelling not in g_["_merchants"]().alias_of                    # dismissing joins nothing


def test_saving_patterns_previews_what_they_would_suggest(appmod, merchant_files):
    g_ = _live(appmod)
    spelling, = _open_spellings(g_, 1)
    merchant_files("merchant,master_category,sub_category,patterns,added" + chr(10) + "Look-alikes,Expense,,," + chr(10),
                   "spelling,merchant,status" + chr(10))
    word = spelling.split()[-1]
    pending, text = g_["_merchant_preview"]("patterns", "Look-alikes", f" {word} | ")
    assert text.startswith(f"Patterns for Look-alikes: {word}: no labels change · suggests ")
    g_["_do_merchant_change"](pending, 0)
    assert g_["_merchants"]().table.set_index("merchant").loc["Look-alikes", "patterns"] == word


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
    # nanosecond mtimes are past 2^53: as numbers the browser would round them
    assert undo["stamps"] and all(isinstance(v, str) for v in undo["stamps"].values())
    assert json.loads(json.dumps(undo)) == undo


def test_undo_refuses_after_any_tracked_file_changes(appmod, tmp_path, monkeypatch):
    g_ = _live(appmod)
    extra = tmp_path / "extra.csv"
    extra.write_text("a\n")
    monkeypatch.setitem(g_, "_undo_files", lambda: [g_["MASTER_PATH"], g_["RULES_PATH"], extra])
    _, undo, _, _ = g_["_do_label"](_group_trig(_bulk_group(g_)), "", False, 0, "all")
    after = g_["MASTER_PATH"].read_bytes()
    extra.write_text("a\nb\n")                     # a third file changed since the click
    status, undo2, _, _ = g_["_do_undo"](json.loads(json.dumps(undo)), 1)
    assert status.startswith("Can't undo") and undo2 is None
    assert g_["MASTER_PATH"].read_bytes() == after


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


def test_label_keeps_undo_when_merchant_files_fail(appmod, monkeypatch):
    g_ = _live(appmod)
    master = g_["MASTER_PATH"]
    before = master.read_bytes()
    grp = _bulk_group(g_)

    def broken(*a, **k):
        raise ValueError("can't write")
    monkeypatch.setitem(g_, "save_merchants", broken)
    status, undo, _, _ = g_["_do_label"](_group_trig(grp), "", True, 0, "all")
    assert status.startswith("Labeled") and status.endswith(
        " · not remembered: the merchant files couldn't be read or written")
    assert undo and undo["backup"] and "merchant_files" not in undo
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


def test_delete_rule_unlabels_its_rows(appmod):
    from Modules.labels import add_rule, read_rules, row_ids, rule_check
    g_ = _live(appmod)
    grp = _rule_safe_group(g_)
    kw = rule_check(g_["df"], read_rules(g_["RULES_PATH"]), grp)["keyword"]
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


def test_headline_says_when_unlabeled_periods_were_left_out_of_typical(appmod):
    view = appmod["headline_view"]
    c = appmod["_CHART"]["dark"]
    text = str(view(dict(_summary(1400.0, 1000.0), left_out_unlabeled=2), "month", _OK, c)[0])
    assert "$400 over a typical month" in text and "2 earlier months not fully labeled, left out" in text
    # None left to compare with: say why, not "no earlier month"
    text = str(view(dict(_summary(50.0), left_out_unlabeled=1), "month", _OK, c)[0])
    assert "$50 spent" in text and "1 earlier month not fully labeled, left out" in text
    assert "No full earlier" not in text


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


def test_attention_line_says_when_the_merchant_files_disagree(appmod):
    parts = appmod["attention_parts"]
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-10-01"]), "description": ["SHOP"], "amount": [-5.0],
                          "source": ["Chase Credit"], "card_last4": [""], "master_category": ["Expense"]})
    today = pd.Timestamp("2026-10-03")
    assert parts(frame, [], None, 0, [], today)["other"] == ""
    got = parts(frame, [], None, 0, [], today,
                merchant_problems=["steamgames.com points at a merchant that doesn't exist (Steam)"])
    assert got["other"] == ("SORTED/merchants.csv and merchant_aliases.csv disagree (steamgames.com points "
                            "at a merchant that doesn't exist (Steam)) — those spellings count as their "
                            "own merchants")


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
    n = len(blocking)
    assert summary.startswith(f"{n:,} row{'s' if n != 1 else ''} ·") and note in summary
    # SHOW ALL is offered on a subset, and goes back to everything
    assert g_["show_all_button"](filt, "todo") == g_["_SHOWN_INLINE"]
    assert g_["show_all_button"]("all", "todo") == g_["_HIDDEN"]
    assert g_["show_all_unlabeled"](1, 3) == ("all", 4)
    assert g_["_period_filter"]("period|nonsense") is None and g_["_period_filter"]("all") is None
