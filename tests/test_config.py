from pathlib import Path

from config import get_rules_path


def test_rules_live_in_the_data_folder(monkeypatch):
    monkeypatch.delenv("FINANCE_RULES_PATH", raising=False)
    assert get_rules_path(Path("data")) == Path("data") / "SORTED" / "rules.csv"


def test_rules_path_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_RULES_PATH", str(tmp_path / "copy.csv"))
    assert get_rules_path(Path("data")) == tmp_path / "copy.csv"


def test_no_data_folder_means_no_rules(monkeypatch):
    monkeypatch.delenv("FINANCE_RULES_PATH", raising=False)
    assert get_rules_path(None) is None
