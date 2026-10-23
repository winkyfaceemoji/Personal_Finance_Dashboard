from pathlib import Path

from config import get_rules_path


def test_rules_live_in_the_data_folder():
    assert get_rules_path(Path("data")) == Path("data") / "SORTED" / "rules.csv"


def test_an_old_rules_path_override_is_ignored(monkeypatch, tmp_path):
    # FINANCE_RULES_PATH is gone: the old keywords are only ever the data folder's
    monkeypatch.setenv("FINANCE_RULES_PATH", str(tmp_path / "copy.csv"))
    assert get_rules_path(Path("data")) == Path("data") / "SORTED" / "rules.csv"


def test_no_data_folder_means_no_rules():
    assert get_rules_path(None) is None
