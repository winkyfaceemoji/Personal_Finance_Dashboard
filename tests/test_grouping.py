# tests/test_grouping.py
import pandas as pd

from Modules.labels import (
    looks_like_transfer, merchant_key, row_id, row_ids, rule_keyword, unlabeled_groups,
)
from Modules.transforms import apply_auto_categories, normalize_description


def _df(rows):
    """rows: (date, description, amount, master_category[, card_last4])."""
    recs = [dict(date=r[0], description=r[1], amount=r[2], master_category=r[3],
                 sub_category="", source="Chase Credit",
                 card_last4=r[4] if len(r) > 4 else "") for r in rows]
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_normalize_description():
    assert normalize_description("VENMO            PAYMENT  1234") == "venmo payment 1234"
    assert normalize_description("PAYPAL *NETFLIX") == "paypal netflix"
    assert normalize_description("STARBUCKS #12") == "starbucks 12"


def test_merchant_key():
    assert merchant_key("STARBUCKS STORE 01234 SEATTLE") == "starbucks store"
    assert merchant_key("STARBUCKS STORE 09876 NEW YORK") == "starbucks store"
    assert merchant_key("PAYPAL *NETFLIX 4029357733") == "paypal netflix"
    assert merchant_key("PAYPAL *SPOTIFY 4029357733") == "paypal spotify"
    assert merchant_key("MORGAN STANLEY ACH DEBIT PPD ID: 123") == "morgan stanley"
    assert merchant_key("COINBASE INC. RTL-TPPSGD WEB ID: 1") == "coinbase inc"
    assert merchant_key("COINBASE INC. RTL-QRARKLK WEB ID: 2") == "coinbase inc"
    assert merchant_key("VENMO            PAYMENT 1234") == "venmo payment"
    assert merchant_key("   ") == ""
    assert merchant_key("#1234") == ""


def test_merchant_key_keeps_numeric_and_hyphenated_names():
    # Names that start with a number or contain a hyphen must not collapse
    # into one shared bucket (council round 2)
    assert merchant_key("7-ELEVEN 12345") == "7-eleven"
    assert merchant_key("99 RANCH MARKET #12") == "99 ranch market"
    assert merchant_key("1-800-FLOWERS") == "1-800-flowers"
    assert merchant_key("23ANDME") == "23andme"
    assert merchant_key("76 FUEL 1234") == "76 fuel"
    assert merchant_key("WAL-MART #1234") == "wal-mart"


def test_rule_keyword_is_common_prefix_and_substring():
    descs = ["STARBUCKS STORE 01234 SEATTLE", "STARBUCKS STORE 09876 NY"]
    kw = rule_keyword(descs)
    assert kw == "starbucks store"
    assert all(kw in normalize_description(d) for d in descs)
    assert rule_keyword(["PAYPAL *NETFLIX 1", "PAYPAL *NETFLIX 2"]) == "paypal netflix"
    assert rule_keyword(["AMAZON MKTP US", "AMAZON.COM"]) == ""
    assert rule_keyword([]) == ""
    assert rule_keyword(["7-ELEVEN 123", "7-ELEVEN 456"]) == "7-eleven"
    assert rule_keyword(["MORGAN STANLEY ACH DEBIT PPD ID: 123"]) == "morgan stanley"


def test_row_id_stable_and_twins_equal():
    df = _df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, ""),
              ("2025-03-01", "CAFE", -4.5, "", "0123")])
    ids = row_ids(df)
    assert ids.iloc[0] == ids.iloc[1] != ids.iloc[2]
    assert row_id(df.iloc[0].to_dict()) == ids.iloc[0]
    assert len(ids.iloc[0]) == 12


def test_looks_like_transfer():
    assert looks_like_transfer("PAYMENT THANK YOU - WEB")
    assert looks_like_transfer("Online Transfer to SAV ...1234")
    assert not looks_like_transfer("STARBUCKS STORE 123")


def test_unlabeled_groups():
    df = _df([
        ("2025-03-01", "STARBUCKS STORE 1", -5.0, ""),
        ("2025-03-02", "STARBUCKS STORE 2", -6.0, ""),
        ("2025-03-03", "RENT CO 9", -900.0, ""),
        ("2025-03-04", "PAYCHECK ACME", 2000.0, "Income"),      # labeled: excluded
        ("2025-03-05", "PAYMENT THANK YOU", 300.0, "Transfer"),  # labeled: excluded
        ("2025-03-06", "AMAZON MKTP 1", -20.0, ""),
        ("2025-03-07", "AMAZON MKTP 2", 20.0, ""),               # refund: mixed group
    ])
    groups = unlabeled_groups(df)
    assert [g["merchant"] for g in groups] == ["RENT CO", "AMAZON MKTP", "STARBUCKS STORE"]
    sb = groups[2]
    assert sb["count"] == 2 and sb["total"] == -11.0 and sb["abs_total"] == 11.0
    assert not sb["mixed"] and groups[1]["mixed"]
    assert sb["first"] == pd.Timestamp("2025-03-01") and sb["last"] == pd.Timestamp("2025-03-02")
    assert {r["row_id"] for r in sb["rows"]} == set(row_ids(df.iloc[:2]))
    assert all(r["count"] == 1 for r in sb["rows"]) and not sb["fallback"]
    assert sb["sig"] == unlabeled_groups(df)[2]["sig"] and len(sb["sig"]) == 10
    assert sb["key"] == unlabeled_groups(df)[2]["key"]          # stable
    only = unlabeled_groups(df, only_row_ids=[sb["rows"][0]["row_id"]])
    assert len(only) == 1 and only[0]["count"] == 1
    assert unlabeled_groups(df.iloc[3:5]) == []


def test_twins_merged_into_one_row():
    df = _df([("2025-03-01", "CAFE", -4.5, ""), ("2025-03-01", "CAFE", -4.5, "")])
    g = unlabeled_groups(df)[0]
    assert g["count"] == 2 and len(g["rows"]) == 1 and g["rows"][0]["count"] == 2


def test_nameless_descriptions_are_separate_fallback_groups():
    df = _df([("2025-03-01", "#1234", -4.5, ""), ("2025-03-02", "#5678", -9.0, ""),
              ("2025-03-03", "STARBUCKS 1", -3.0, "")])
    groups = unlabeled_groups(df)
    assert len(groups) == 3
    fb = [g for g in groups if g["fallback"]]
    assert len(fb) == 2 and all(g["count"] == 1 for g in fb)


def test_suggest_transfer_flag():
    df = _df([("2025-03-01", "AUTOPAY PAYMENT", -300.0, "")])
    assert unlabeled_groups(df)[0]["suggest_transfer"]


def test_padded_rule_keyword_matches(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nvenmo payment,Transfer,\n")
    df = _df([("2025-03-01", "VENMO            PAYMENT 77", -10.0, "")])
    out = apply_auto_categories(df.copy(), rules)
    assert out.loc[0, "master_category"] == "Transfer"


def test_existing_star_rules_still_match(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nmta*nyct paygo,Expense,\nsq *the,Expense,\n")
    df = _df([("2025-03-01", "MTA*NYCT PAYGO NEW YORK", -2.9, ""),
              ("2025-03-02", "SQ *THE COFFEE PLACE", -4.0, ""),
              ("2025-03-03", "SQ *OTHER SHOP", -4.0, "")])
    out = apply_auto_categories(df.copy(), rules)
    assert out["master_category"].tolist() == ["Expense", "Expense", ""]


def _old_apply(df, rules):
    """The matching loop as it was before the normalizer (for the regression gate)."""
    from Modules.transforms import PREDEFINED_CATEGORIES
    desc = df["description"].str.lower()
    unlabeled = df["master_category"] == ""
    for _, rule in rules.iterrows():
        keyword = str(rule["keyword"]).strip().lower()
        mc = str(rule.get("master_category", "")).strip()
        sc = str(rule.get("sub_category", "")).strip()
        if not keyword or (mc and mc not in PREDEFINED_CATEGORIES) or (not mc and not sc):
            continue
        hits = desc.str.contains(keyword, regex=False, na=False)
        if mc:
            take = unlabeled & hits
            df.loc[take, "master_category"] = mc
            unlabeled = unlabeled & ~take
        if sc:
            fill = hits & (df["sub_category"] == "")
            if mc:
                fill = fill & (df["master_category"] == mc)
            df.loc[fill, "sub_category"] = sc
    return df


def test_normalizer_regression_gate(tmp_path, capsys):
    """Every demo row whose rule label changes under the normalizer must be
    explained by it: the normalizer must actually have altered that row's
    description (padding, '*' or '#'). Prints the diff for the report."""
    import shutil
    from pathlib import Path
    from main import main as run_ingest
    repo = Path(__file__).resolve().parent.parent
    data = tmp_path / "data"
    shutil.copytree(repo / "Test Data" / "RAW", data / "RAW")
    run_ingest(data)
    master = pd.read_csv(data / "SORTED" / "edited_combined_transactions.csv",
                         dtype=str, keep_default_na=False)
    base = master[["description", "master_category", "sub_category"]].copy()
    rules = pd.read_csv(repo / "rules.csv", encoding="utf-8-sig").fillna("")
    old = _old_apply(base.copy(), rules)
    new = apply_auto_categories(base.copy(), repo / "rules.csv")
    changed = ((old["master_category"] != new["master_category"])
               | (old["sub_category"] != new["sub_category"]))
    with capsys.disabled():
        print(f"\n[regression gate] {int(changed.sum())} of {len(base)} demo rows change label")
        for i in base.index[changed][:20]:
            print(f"  {base.at[i, 'description']!r}: {old.at[i, 'master_category'] or '-'}"
                  f" -> {new.at[i, 'master_category'] or '-'}")
    for d in base.loc[changed, "description"]:
        assert normalize_description(d) != str(d).lower().strip(), f"unexplained change: {d!r}"


def test_rules_file_with_bom(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_bytes("keyword,master_category,sub_category\npayroll,Income,\n".encode("utf-8-sig"))
    df = _df([("2025-03-01", "ACME PAYROLL", 100.0, "")])
    assert apply_auto_categories(df.copy(), rules).loc[0, "master_category"] == "Income"
