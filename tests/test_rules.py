import pandas as pd

from Modules.labels import read_rules
from Modules.transforms import apply_auto_categories


def _df(rows):
    recs = [dict(date=r[0], description=r[1], amount=r[2], master_category=r[3],
                 sub_category="", source="Chase Credit", card_last4="") for r in rows]
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_rules_bom_and_quoting(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_bytes('keyword,master_category,sub_category\npayroll,Income,\n"smith, jones & co",Expense,"Legal, fees"\n'
                     .encode("utf-8-sig"))
    r = read_rules(path)
    assert r["keyword"].tolist() == ["payroll", "smith, jones & co"]
    assert r.loc[1, "sub_category"] == "Legal, fees"


def test_an_added_column_is_ignored_on_load(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_text("keyword,master_category,sub_category,added\nstarbucks store,Expense,Coffee,2026-01-01\n")
    df = _df([("2025-03-01", "STARBUCKS STORE 1", -5.0, "")])
    out = apply_auto_categories(df.copy(), path)
    assert (out.loc[0, "master_category"], out.loc[0, "sub_category"]) == ("Expense", "Coffee")


def test_read_rules_empty_file(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_bytes(b"")                                     # zero-byte, no header
    r = read_rules(path)
    assert r.empty and list(r.columns) == ["keyword", "master_category", "sub_category", "added"]
    df = _df([("2025-03-01", "CAFE 1", -5.0, "")])
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
