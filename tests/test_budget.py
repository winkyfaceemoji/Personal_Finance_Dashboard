import json

import pytest

from Modules.budget import budget_for, budget_status, read_budget, save_budget


def _master(tmp_path):
    m = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    m.parent.mkdir()
    return m


def test_read_and_save_roundtrip(tmp_path):
    m = _master(tmp_path)
    assert read_budget(m) == {"week": None, "month": None}
    save_budget(m, week=250, month=3000)
    assert read_budget(m) == {"week": 250.0, "month": 3000.0}
    save_budget(m, week=None, month=3000)                      # clearing one keeps the other
    assert read_budget(m) == {"week": None, "month": 3000.0}


def test_bad_values_are_refused_and_bad_files_read_as_unset(tmp_path):
    m = _master(tmp_path)
    with pytest.raises(ValueError):
        save_budget(m, week=-5, month=None)
    (m.parent / "budget.json").write_text("{not json")
    assert read_budget(m) == {"week": None, "month": None}
    (m.parent / "budget.json").write_text(json.dumps({"week": "abc", "month": 0}))
    assert read_budget(m) == {"week": None, "month": None}


def test_budget_for_each_period():
    b = {"week": 250.0, "month": 3000.0}
    assert budget_for(b, "week") == 250.0
    assert budget_for(b, "month") == 3000.0
    assert budget_for(b, "year") == 36000.0                    # 12 monthly budgets
    assert budget_for({"week": 250.0, "month": None}, "year") is None


def test_status_in_progress_under_and_over_pace():
    # Day 10 of 30, $3,000 budget: $1,000 is on pace
    s = budget_status(spent=800, budget=3000, days_elapsed=10, days_total=30, partial=True)
    assert s["left"] == 2200 and s["by_now"] == 1000 and not s["over_pace"] and not s["over"]
    assert s["per_day_left"] == pytest.approx(2200 / 20)
    s = budget_status(spent=1400, budget=3000, days_elapsed=10, days_total=30, partial=True)
    assert s["over_pace"] and not s["over"]


def test_status_over_budget_and_complete_period():
    s = budget_status(spent=3200, budget=3000, days_elapsed=25, days_total=30, partial=True)
    assert s["over"] and s["left"] == -200 and s["per_day_left"] is None
    s = budget_status(spent=2700, budget=3000, days_elapsed=30, days_total=30, partial=False)
    assert s["by_now"] is None and s["left"] == 300 and not s["over"]
