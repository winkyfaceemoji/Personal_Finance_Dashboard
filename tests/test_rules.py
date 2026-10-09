import pandas as pd

from Modules.labels import (
    add_rule, delete_rule, read_rules, rule_check, unlabeled_groups,
)
from Modules.transforms import apply_auto_categories


def _df(rows):
    recs = [dict(date=r[0], description=r[1], amount=r[2], master_category=r[3],
                 sub_category="", source="Chase Credit", card_last4="") for r in rows]
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _group(df, merchant):
    return next(g for g in unlabeled_groups(df) if g["merchant"] == merchant)


def test_rule_check_ok():
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, ""),
              ("2025-03-02", "STARBUCKS STORE 2", -6.0, ""),
              ("2025-03-03", "RENT CO 9", -900.0, "")])
    chk = rule_check(df, read_rules("/nonexistent/rules.csv"), _group(df, "STARBUCKS STORE"))
    assert chk["ok"] and not chk["blocking"] and chk["reason"] is None
    assert chk["keyword"] == "starbucks store"
    assert chk["rows_now"] == 2 and chk["dollars_now"] == 11.0
    assert chk["direction"] == "money out"


def test_rule_check_blocks_fallback_groups():
    df = _df([("2025-03-01", "#123456", -5.0, "")])
    g = unlabeled_groups(df)[0]
    assert g["fallback"]
    chk = rule_check(df, read_rules("/nonexistent"), g)
    assert not chk["ok"] and chk["blocking"] and "name" in chk["reason"]


def test_rule_check_too_short():
    df = _df([("2025-03-01", "AB 12", -5.0, "")])
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AB"))
    assert not chk["ok"] and chk["blocking"] and "long enough" in chk["reason"]


def test_rule_check_matches_other_merchant_even_if_labeled():
    df = _df([("2025-03-01", "AMAZON MKTP 1", -20.0, ""),
              ("2025-03-02", "AMAZON MKTP US 99", -30.0, "Expense")])   # labeled, other merchant
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AMAZON MKTP"))
    assert not chk["ok"] and chk["blocking"]
    assert chk["others"] == ["AMAZON MKTP US"] and "AMAZON MKTP US" in chk["reason"]


def test_rule_check_existing_rule_overlap(tmp_path):
    rules = tmp_path / "rules.csv"
    rules.write_text("keyword,master_category,sub_category\nstarbucks,,Coffee\n")   # sub-only rule
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, "")])
    chk = rule_check(df, read_rules(rules), _group(df, "STARBUCKS STORE"))
    assert not chk["ok"] and chk["blocking"] and '"starbucks"' in chk["reason"]


def test_rule_check_mixed_sign_is_not_blocking():
    df = _df([("2025-03-01", "AMAZON MKTP 1", -20.0, ""),
              ("2025-03-02", "AMAZON MKTP 2", 20.0, "")])
    chk = rule_check(df, read_rules("/nonexistent"), _group(df, "AMAZON MKTP"))
    assert not chk["ok"] and not chk["blocking"] and "in and out" in chk["reason"]
    assert chk["direction"] == "mixed"


def test_add_rule_new_file_and_refusals(tmp_path):
    path = tmp_path / "rules.csv"
    assert add_rule(path, "starbucks store", "Expense", "Coffee")
    r = read_rules(path)
    assert r[["keyword", "master_category", "sub_category"]].values.tolist() == \
        [["starbucks store", "Expense", "Coffee"]]
    assert len(r.loc[0, "added"]) == 10                       # ISO date
    assert not add_rule(path, "Starbucks   Store", "Expense")   # duplicate after normalizing
    assert not add_rule(path, "rent co", "Groceries")          # not a predefined category
    assert not add_rule(path, "ab", "Expense")                 # too short
    assert len(read_rules(path)) == 1


def test_rules_bom_and_quoting_roundtrip(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_bytes("keyword,master_category,sub_category\npayroll,Income,\n".encode("utf-8-sig"))
    assert add_rule(path, "smith, jones & co", "Expense", "Legal, fees")
    r = read_rules(path)
    assert r["keyword"].tolist() == ["payroll", "smith, jones & co"]
    assert r.loc[1, "sub_category"] == "Legal, fees"


def test_added_rule_is_applied_and_extra_column_ignored(tmp_path):
    path = tmp_path / "rules.csv"
    add_rule(path, "starbucks store", "Expense", "Coffee")
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, "")])
    out = apply_auto_categories(df.copy(), path)
    assert (out.loc[0, "master_category"], out.loc[0, "sub_category"]) == ("Expense", "Coffee")


def test_delete_rule(tmp_path):
    path = tmp_path / "rules.csv"
    add_rule(path, "starbucks store", "Expense")
    add_rule(path, "rent co", "Expense")
    assert delete_rule(path, "STARBUCKS STORE")
    assert read_rules(path)["keyword"].tolist() == ["rent co"]
    assert not delete_rule(path, "nothing like this")


def test_read_rules_empty_file(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_bytes(b"")                                     # zero-byte, no header
    r = read_rules(path)
    assert r.empty and list(r.columns) == ["keyword", "master_category", "sub_category", "added"]
    assert add_rule(path, "starbucks store", "Expense")
    assert read_rules(path)["keyword"].tolist() == ["starbucks store"]
    df = _df([("2025-03-01", "CAFE 1", -5.0, "")])
    path.write_bytes(b"")
    assert apply_auto_categories(df.copy(), path).loc[0, "master_category"] == ""


def test_read_rules_cp1252(tmp_path):
    # Excel's plain "CSV" save on Windows is Windows-1252, not UTF-8
    path = tmp_path / "rules.csv"
    path.write_bytes("keyword,master_category,sub_category\ncafé luna,Expense,Café\n".encode("cp1252"))
    r = read_rules(path)
    assert r.loc[0, "keyword"] == "café luna" and r.loc[0, "sub_category"] == "Café"
    df = _df([("2025-03-01", "CAFÉ LUNA 12", -5.0, "")])
    out = apply_auto_categories(df.copy(), path)
    assert (out.loc[0, "master_category"], out.loc[0, "sub_category"]) == ("Expense", "Café")
