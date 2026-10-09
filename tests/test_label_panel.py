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
