"""
One overall spending budget, per week and per month (the year view uses 12
monthly budgets). Stored next to the master in SORTED/budget.json, so it
travels with the data folder.
"""
import json
import os
import tempfile
from pathlib import Path

BUDGET_NAME = "budget.json"
_UNSET = {"week": None, "month": None}


def _path(master) -> Path:
    return Path(master).parent / BUDGET_NAME


def _amount(v) -> float | None:
    """A positive number, or None — anything else (blank, 0, text) is unset."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def read_budget(master) -> dict:
    """{"week": float|None, "month": float|None}; a missing or unreadable file
    (hand-edited, half-written) reads as no budget rather than an error."""
    p = _path(master)
    if not p.exists():
        return dict(_UNSET)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_UNSET)
    if not isinstance(raw, dict):
        return dict(_UNSET)
    return {k: _amount(raw.get(k)) for k in _UNSET}


def save_budget(master, week=None, month=None) -> None:
    """Write both budgets (None clears one). Negative amounts are refused;
    the file is replaced atomically so a crash never leaves it half-written."""
    for v in (week, month):
        if v is not None and float(v) < 0:
            raise ValueError("A budget can't be negative")
    data = {"week": _amount(week), "month": _amount(month)}
    p = _path(master)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".budget-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def budget_for(budget: dict, freq: str) -> float | None:
    """The budget for one period of this granularity."""
    if freq == "year":
        return budget["month"] * 12 if budget.get("month") else None
    return budget.get(freq)


def budget_status(spent: float, budget: float, days_elapsed: int, days_total: int,
                  partial: bool) -> dict:
    """
    Where spending stands against a budget. While the period is in progress,
    by_now is the share of the budget its elapsed days would use at an even
    pace, and per_day_left what's left to spend per remaining day (None once
    over budget). A finished period has no by_now: only over or under.
    """
    left = budget - spent
    by_now = budget * days_elapsed / days_total if partial and days_total else None
    days_left = days_total - days_elapsed if partial else 0
    return {
        "spent": spent,
        "budget": budget,
        "left": left,
        "over": left < 0,
        "by_now": by_now,
        "over_pace": by_now is not None and spent > by_now,
        "per_day_left": left / days_left if partial and days_left > 0 and left >= 0 else None,
        "days_left": days_left,
    }
