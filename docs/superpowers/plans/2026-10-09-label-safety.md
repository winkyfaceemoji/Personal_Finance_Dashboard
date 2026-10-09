# Label Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the user's manual labels (`master_category` / `sub_category`) impossible to lose silently — through a failed rebuild, a changed bank re-export, or an Excel import.

**Architecture:** A small `Modules/safety.py` owns every write to the master file: copy-not-rename timestamped backups, atomic temp-file + `os.replace` writes, and auto-restore when the master is missing. `rebuild_master` (in `main.py`) uses it, tolerates older master schemas, and adds a looser fallback match plus an `orphaned_labels.csv` report for labels it can't place. The import matcher moves out of `app.py` into a pure, tested `Modules/labels.py` that handles Excel's encodings, date formats, and currency formatting.

**Tech Stack:** Python 3.12+, pandas 3.0.2, Dash 4.1.0, pytest 8.4.2.

**Spec:** the architecture review findings #1 (non-atomic rebuild / one-generation `.bak`), #2 (brittle match key, silent label loss), #7 (fragile Excel round-trip), #8 (import writes without backup), as recorded under "Known gaps" in `docs/decisions.md` (section *Rebuild the master from RAW every run — never append*).

## Global Constraints

- Pinned versions stay as in `requirements.txt` / `requirements-dev.txt`: `dash==4.1.0`, `pandas==3.0.2`, `plotly==6.7.0`, `pytest==8.4.2`. No new dependencies.
- Must run on Windows: no `%-d` strftime, temp files in the *same folder* as their target (so `os.replace` is atomic), tolerate `PermissionError` from a master open in Excel.
- Tests never write into the repo — use `tmp_path` only.
- Code style matches the surrounding code: section comments with `# ── … ──`, comments explain *why*, no type-heavy abstractions.
- The master file path and name do not change: `<data_dir>/SORTED/edited_combined_transactions.csv`.
- Existing behaviour that must not regress: same-day repeat purchases carry their labels in order (`tests/test_periods.py` end-to-end run must still pass).

## Review Focus

1. **Master open in Excel on Windows during Reload/Import** — `os.replace` raises `PermissionError`; expected: the original master is untouched, no `.tmp` file is left behind, and the user sees an error message. Pinned in Task 1 (`test_failed_replace_leaves_original_and_no_temp`).
2. **Two rebuilds within the same second** (double-click Reload) — expected: two distinct backups, neither overwriting the other. Pinned in Task 1 (`test_backups_have_unique_names`).
3. **A master written by an old version** (legacy `category` column, no `memo`/`institution`) — expected: labels still carry forward, no crash. Pinned in Task 2 (`test_old_schema_master_keeps_labels`).
4. **An export re-saved by Excel** (`3/15/2024` dates, `-$1,234.50` amounts, `0123` card shown as `123`) — expected: every edited row still matches. Pinned in Task 4 (`test_excel_reformatted_values_still_match`).
5. **User deletes the master on purpose to start fresh** — expected: it's restored from the newest backup *with a printed message naming the backup*, so the behaviour is visible, and the docs say to clear `SORTED/backups/` to truly start over. Pinned in Task 2 (`test_missing_master_restored_from_newest_backup`) and Task 5 (docs).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `Modules/safety.py` (new) | Backups, atomic CSV writes, restore-if-missing, orphan-file helpers. The only code that writes the master. |
| `Modules/labels.py` (new) | Reading an imported CSV and applying its labels onto a master frame — pure functions, no I/O beyond decoding bytes. |
| `main.py` (modify `rebuild_master`) | Rebuild uses `safety`; schema tolerance; fallback match; orphan report. |
| `app.py` (modify `import_csv`, header) | Import uses `labels` + `safety`; header shows an orphaned-labels note. |
| `tests/test_safety.py`, `tests/test_rebuild.py`, `tests/test_labels.py` (new) | One test file per unit above. |
| `docs/decisions.md`, `docs/features/ingest-pipeline.md`, `docs/features/import-export.md`, `docs/features/overview-charts.md`, `readme.md` | Describe the new guarantees; remove the resolved "known gaps". |

---

### Task 1: Safe-write primitives (`Modules/safety.py`)

**Files:**
- Create: `Modules/safety.py`
- Test: `tests/test_safety.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `atomic_write_csv(df: pd.DataFrame, path: Path) -> None`
  - `backup_master(master: Path, keep: int = BACKUP_KEEP) -> Path | None`
  - `list_backups(master: Path, include_legacy: bool = True) -> list[Path]` (newest first)
  - `restore_if_missing(master: Path) -> Path | None` (returns the backup it restored from)
  - `orphans_path(master: Path) -> Path`, `orphan_count(master: Path) -> int`
  - constants `BACKUP_KEEP = 10`, `ORPHANS_NAME = "orphaned_labels.csv"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_safety.py
import os

import pandas as pd
import pytest

from Modules import safety
from Modules.safety import (
    atomic_write_csv,
    backup_master,
    list_backups,
    orphan_count,
    orphans_path,
    restore_if_missing,
)


def _master(tmp_path, rows=(("2025-01-01", "Expense"),)):
    path = tmp_path / "SORTED" / "edited_combined_transactions.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(rows, columns=["date", "master_category"]).to_csv(path, index=False)
    return path


def test_atomic_write_replaces_content(tmp_path):
    path = _master(tmp_path)
    atomic_write_csv(pd.DataFrame({"a": [1]}), path)
    assert pd.read_csv(path).columns.tolist() == ["a"]
    assert [p.name for p in path.parent.iterdir()] == [path.name]   # no temp left


def test_failed_replace_leaves_original_and_no_temp(tmp_path, monkeypatch):
    path = _master(tmp_path)
    before = path.read_text()

    def locked(*_):
        raise PermissionError("file is open in Excel")
    monkeypatch.setattr(safety.os, "replace", locked)

    with pytest.raises(PermissionError):
        atomic_write_csv(pd.DataFrame({"a": [1]}), path)
    assert path.read_text() == before
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_backup_is_a_copy(tmp_path):
    path = _master(tmp_path)
    dest = backup_master(path)
    assert path.exists() and dest.exists()
    assert dest.read_text() == path.read_text()
    assert dest.parent.name == "backups"


def test_backups_have_unique_names(tmp_path):
    path = _master(tmp_path)
    a, b = backup_master(path), backup_master(path)
    assert a != b and a.exists() and b.exists()


def test_backups_pruned_to_keep_newest(tmp_path):
    path = _master(tmp_path)
    made = [backup_master(path, keep=3) for _ in range(5)]
    kept = list_backups(path, include_legacy=False)
    assert kept == list(reversed(made))[:3]


def test_legacy_bak_listed_last_and_never_pruned(tmp_path):
    path = _master(tmp_path)
    legacy = path.with_suffix(".csv.bak")
    legacy.write_text("date,master_category\n")
    for _ in range(4):
        backup_master(path, keep=2)
    backups = list_backups(path)
    assert backups[-1] == legacy and legacy.exists()
    assert len(backups) == 3


def test_restore_if_missing(tmp_path):
    path = _master(tmp_path)
    dest = backup_master(path)
    path.unlink()
    assert restore_if_missing(path) == dest
    assert path.read_text() == dest.read_text()


def test_restore_is_noop_when_master_exists_or_no_backup(tmp_path):
    path = _master(tmp_path)
    assert restore_if_missing(path) is None          # master present
    path.unlink()
    assert restore_if_missing(path) is None          # nothing to restore from


def test_orphan_count(tmp_path):
    path = _master(tmp_path)
    assert orphan_count(path) == 0
    pd.DataFrame({"x": [1, 2]}).to_csv(orphans_path(path), index=False)
    assert orphan_count(path) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_safety.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'Modules.safety'`

- [ ] **Step 3: Write the implementation**

```python
# Modules/safety.py
"""
Crash-safe writes and versioned backups for the master file — the one file
holding labels that can't be regenerated from RAW. Every write to the master
goes through here.
"""
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

BACKUP_DIRNAME = "backups"
BACKUP_KEEP    = 10
ORPHANS_NAME   = "orphaned_labels.csv"


def _backup_dir(master: Path) -> Path:
    return Path(master).parent / BACKUP_DIRNAME


def _replace_from(src: Path, dest: Path) -> None:
    """Copy src over dest atomically: temp file beside dest, then os.replace."""
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write df so that `path` is always either the old file or the complete
    new one, never a truncated mix. The temp file lives in the same folder
    so os.replace is atomic (Windows and POSIX); if the replace fails — e.g.
    the file is open in Excel — the temp file is removed and the error raised."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def list_backups(master: Path, include_legacy: bool = True) -> list[Path]:
    """Backups of the master, newest first. Timestamped names sort
    chronologically. The single `.csv.bak` written by older versions is
    listed last (it's the oldest) and is never pruned."""
    master = Path(master)
    d = _backup_dir(master)
    found = sorted(d.glob(f"{master.stem}.*{master.suffix}"), reverse=True) if d.exists() else []
    legacy = master.with_suffix(master.suffix + ".bak")
    if include_legacy and legacy.exists():
        found.append(legacy)
    return found


def backup_master(master: Path, keep: int = BACKUP_KEEP) -> Path | None:
    """Copy the master into SORTED/backups/ under a timestamped name and keep
    the newest `keep`. A copy, not a rename: if anything after this fails,
    the master is still in place."""
    master = Path(master)
    if not master.exists():
        return None
    d = _backup_dir(master)
    d.mkdir(parents=True, exist_ok=True)
    # Microseconds keep two backups in the same second (double-clicked
    # Reload) from overwriting each other
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = d / f"{master.stem}.{stamp}{master.suffix}"
    shutil.copy2(master, dest)
    for old in list_backups(master, include_legacy=False)[keep:]:
        old.unlink(missing_ok=True)
    return dest


def restore_if_missing(master: Path) -> Path | None:
    """If the master is gone but a backup exists, put the newest backup back
    and return the backup used. Without this, a failed run followed by the
    startup auto-ingest would write a fresh master with no labels at all."""
    master = Path(master)
    if master.exists():
        return None
    backups = list_backups(master)
    if not backups:
        return None
    master.parent.mkdir(parents=True, exist_ok=True)
    _replace_from(backups[0], master)
    return backups[0]


def orphans_path(master: Path) -> Path:
    return Path(master).parent / ORPHANS_NAME


def orphan_count(master: Path) -> int:
    """Labels from the previous master that the last rebuild couldn't place."""
    p = orphans_path(master)
    if not p.exists():
        return 0
    try:
        return len(pd.read_csv(p))
    except Exception:
        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_safety.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add Modules/safety.py tests/test_safety.py
git commit -m "Add crash-safe master writes and versioned backups"
```

---

### Task 2: Crash-safe, schema-tolerant `rebuild_master`

**Files:**
- Modify: `main.py` — imports (top of file) and `rebuild_master` (currently `main.py:186-242`)
- Test: `tests/test_rebuild.py`

**Interfaces:**
- Consumes: `atomic_write_csv`, `backup_master`, `restore_if_missing` from Task 1.
- Produces: `rebuild_master(combined: pd.DataFrame, master_file: Path) -> dict` — now returns `{"carried": int, "rescued": int, "orphaned": int, "restored_from": Path | None}` (Task 3 fills `rescued`/`orphaned`; this task returns them as 0). Callers that ignore the return value keep working.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rebuild.py
import pandas as pd
import pytest

import main
from main import MASTER_COLUMNS, UNIFIED_COLUMNS, rebuild_master
from Modules import safety
from Modules.safety import backup_master, list_backups


def _combined(rows):
    """Freshly-merged pipeline output: (date, description, amount, original_category)."""
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "original_category"])
    for col in UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df["date"] = pd.to_datetime(df["date"])
    return df[UNIFIED_COLUMNS]


def _write_master(path, rows, drop=()):
    """Prior master with labels: rows of (date, description, amount,
    original_category, master_category, sub_category)."""
    df = pd.DataFrame(rows, columns=["date", "description", "amount",
                                     "original_category", "master_category", "sub_category"])
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["source"] = "Chase Credit"
    df = df[[c for c in MASTER_COLUMNS if c not in drop]]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


@pytest.fixture
def master(tmp_path):
    return tmp_path / "SORTED" / "edited_combined_transactions.csv"


ROW = ("2025-03-01", "COFFEE SHOP", -4.5, "Food")


def test_labels_carry_and_backup_is_kept(master):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    rebuild_master(_combined([ROW]), master)
    out = pd.read_csv(master)
    assert out.loc[0, "master_category"] == "Expense"
    assert out.loc[0, "sub_category"] == "Coffee"
    assert len(list_backups(master, include_legacy=False)) == 1
    assert not master.with_suffix(".csv.bak").exists()   # old rename-away is gone


def test_old_schema_master_keeps_labels(master):
    # A master from an old version: no memo / institution columns, and the
    # bank category still under its legacy name "category"
    _write_master(master, [ROW + ("Expense", "")], drop=("memo", "institution"))
    old = pd.read_csv(master).rename(columns={"original_category": "category"})
    old.to_csv(master, index=False)

    rebuild_master(_combined([ROW]), master)
    assert pd.read_csv(master).loc[0, "master_category"] == "Expense"


def test_crash_during_write_leaves_master_intact(master, monkeypatch):
    _write_master(master, [ROW + ("Expense", "")])
    before = master.read_text()

    def locked(*_):
        raise PermissionError("open in Excel")
    monkeypatch.setattr(safety.os, "replace", locked)

    with pytest.raises(PermissionError):
        rebuild_master(_combined([ROW]), master)
    assert master.read_text() == before


def test_missing_master_restored_from_newest_backup(master, capsys):
    _write_master(master, [ROW + ("Expense", "Coffee")])
    backup_master(master)
    master.unlink()                                  # e.g. a failed earlier run

    result = rebuild_master(_combined([ROW]), master)
    assert result["restored_from"] is not None
    assert "restored labels from backup" in capsys.readouterr().out
    assert pd.read_csv(master).loc[0, "sub_category"] == "Coffee"


def test_same_day_repeats_keep_order(master):
    _write_master(master, [ROW + ("Expense", "First"), ROW + ("Expense", "Second")])
    rebuild_master(_combined([ROW, ROW, ROW]), master)
    subs = pd.read_csv(master)["sub_category"].fillna("").tolist()
    assert subs == ["First", "Second", ""]          # third occurrence is new
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rebuild.py -v`
Expected: `test_labels_carry_and_backup_is_kept` FAILS (no `backups/` entry — the old code renames to `.bak`), `test_old_schema_master_keeps_labels` FAILS with `KeyError: 'memo'`, `test_crash_during_write_leaves_master_intact` FAILS (master renamed away), `test_missing_master_restored_from_newest_backup` FAILS (`TypeError: 'NoneType' object is not subscriptable`). `test_same_day_repeats_keep_order` passes (regression guard).

- [ ] **Step 3: Write the implementation**

In `main.py`, add to the imports at the top:

```python
from Modules.safety import atomic_write_csv, backup_master, restore_if_missing
```

Replace the whole `rebuild_master` function with:

```python
def rebuild_master(combined: pd.DataFrame, master_file: Path) -> dict:
    """
    Rebuild edited_combined_transactions.csv from the freshly-merged combined
    data, carrying forward existing master_category / sub_category
    assignments by matching each row's MATCH_COLUMNS key against the prior
    master file.

    Every unified-schema column is regenerated from RAW on every run — only
    the user-assigned categorization is preserved. A match key that occurs
    more times in the new combined data than in the prior master inherits
    the categorization of existing occurrences, in order; any occurrence
    beyond what the prior master had is genuinely new and starts blank.

    Label safety: the prior master is *copied* to SORTED/backups/ (never
    renamed away), a master missing after a failed run is restored from the
    newest backup first, older master schemas are tolerated, and the new
    master is written atomically — so a crash at any point leaves either
    the old master or the complete new one.
    """
    combined = combined.copy()
    for col in ["date", "post_date"]:
        combined[col] = pd.to_datetime(combined[col], errors="coerce").dt.strftime("%Y-%m-%d")
    combined["master_category"] = None
    combined["sub_category"]    = None

    def row_key(d: pd.DataFrame) -> pd.Series:
        return d[MATCH_COLUMNS].fillna("").astype(str).apply(tuple, axis=1)

    result = {"carried": 0, "rescued": 0, "orphaned": 0, "restored_from": None}

    restored = restore_if_missing(master_file)
    if restored:
        result["restored_from"] = restored
        print(f"  Master file was missing — restored labels from backup {restored.name}")

    if master_file.exists():
        backup_master(master_file)
        old_master = pd.read_csv(master_file, dtype={"card_last4": str})
        if "category" in old_master.columns and "original_category" not in old_master.columns:
            old_master = old_master.rename(columns={"category": "original_category"})
        # Masters written by older versions lack newer columns; a missing
        # column reads as blank rather than aborting the rebuild
        for col in MASTER_COLUMNS:
            if col not in old_master.columns:
                old_master[col] = None
        for col in ["date", "post_date"]:
            old_master[col] = pd.to_datetime(old_master[col], errors="coerce").dt.strftime("%Y-%m-%d")

        categorization = defaultdict(deque)
        for key, mc, sc in zip(row_key(old_master), old_master["master_category"], old_master["sub_category"]):
            categorization[key].append((mc, sc))

        for idx, key in zip(combined.index, row_key(combined)):
            bucket = categorization.get(key)
            if bucket:
                mc, sc = bucket.popleft()
                combined.at[idx, "master_category"] = mc
                combined.at[idx, "sub_category"]    = sc
                result["carried"] += 1
        print(f"  Categorization carried over for {result['carried']}/{len(combined)} row(s)")

    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined.sort_values("date", inplace=True, ignore_index=True, kind="stable")
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    atomic_write_csv(combined[MASTER_COLUMNS], master_file)
    print(f"  Master file rebuilt with {len(combined)} rows -> {master_file}")
    return result
```

(`kind="stable"` keeps same-day rows in pipeline order so identical rows on two cards can't swap labels between runs.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all pass (5 new in `test_rebuild.py`, plus the existing 12 and Task 1's 9).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_rebuild.py
git commit -m "Make master rebuild crash-safe and tolerant of old schemas"
```

---

### Task 3: Fallback matching and the orphaned-labels report

**Files:**
- Modify: `main.py` — `rebuild_master` (from Task 2)
- Modify: `app.py` — header layout (after `unlabeled-note`) and a new `update_orphan_note` callback
- Test: `tests/test_rebuild.py` (append)

**Interfaces:**
- Consumes: Task 2's `rebuild_master`; `atomic_write_csv`, `orphans_path`, `orphan_count` from Task 1.
- Produces: `FALLBACK_COLUMNS = ["date", "description", "amount", "source"]` in `main.py`; `rebuild_master` result keys `rescued` / `orphaned` now populated; file `SORTED/orphaned_labels.csv` (MASTER_COLUMNS) holding every label not yet placed — kept across rebuilds, re-tried on each one, deleted only when empty; header element `orphan-note`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_rebuild.py`)

```python
from Modules.safety import orphan_count, orphans_path


def test_changed_raw_field_keeps_label(master):
    # The bank re-maps the category on a later export: the exact key no
    # longer matches, the date/description/amount/source fallback does
    _write_master(master, [ROW + ("Expense", "Coffee")])
    changed = ("2025-03-01", "COFFEE SHOP", -4.5, "Dining")
    result = rebuild_master(_combined([changed]), master)
    out = pd.read_csv(master)
    assert out.loc[0, "sub_category"] == "Coffee"
    assert result["rescued"] == 1 and result["orphaned"] == 0


def test_unplaceable_label_is_reported_not_dropped(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [ROW + ("Expense", ""), gone + ("Expense", "Gifts")])
    result = rebuild_master(_combined([ROW]), master)
    assert result["orphaned"] == 1
    orphans = pd.read_csv(orphans_path(master))
    assert orphans.loc[0, "description"] == "OLD MERCHANT"
    assert orphans.loc[0, "sub_category"] == "Gifts"
    assert orphan_count(master) == 1


def test_orphans_survive_later_rebuilds_and_reattach(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [gone + ("Expense", "Gifts")])
    rebuild_master(_combined([ROW]), master)          # transaction missing from RAW
    rebuild_master(_combined([ROW]), master)          # a later reload must not forget it
    assert orphan_count(master) == 1

    result = rebuild_master(_combined([ROW, gone]), master)   # it's back
    out = pd.read_csv(master).set_index("description")
    assert out.loc["OLD MERCHANT", "sub_category"] == "Gifts"
    assert result["orphaned"] == 0
    assert not orphans_path(master).exists()


def test_unlabeled_old_rows_are_not_orphans(master):
    gone = ("2025-02-01", "OLD MERCHANT", -20.0, "Shopping")
    _write_master(master, [gone + ("", "")])
    assert rebuild_master(_combined([ROW]), master)["orphaned"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rebuild.py -v`
Expected: the 3 new rescue/orphan tests FAIL (`rescued`/`orphaned` are 0, no orphans file); `test_unlabeled_old_rows_are_not_orphans` passes.

- [ ] **Step 3: Write the implementation**

In `main.py`, below `MATCH_COLUMNS`:

```python
# Looser key tried for labels the exact key couldn't place: a re-export that
# changes a secondary field (bank category, memo, running balance) still
# lands its label. Labels neither key places go to orphaned_labels.csv.
FALLBACK_COLUMNS = ["date", "description", "amount", "source"]
```

Add `orphans_path` to the safety import:

```python
from Modules.safety import atomic_write_csv, backup_master, orphans_path, restore_if_missing
```

In `rebuild_master`, add a second key function next to `row_key`:

```python
    def fallback_key(d: pd.DataFrame) -> pd.Series:
        amount = pd.to_numeric(d["amount"], errors="coerce").round(2).astype(str)
        parts = d[["date", "description", "source"]].fillna("").astype(str)
        parts["description"] = parts["description"].str.strip()
        return pd.Series(list(zip(parts["date"], parts["description"], amount, parts["source"])),
                         index=d.index)
```

Replace the block from `categorization = defaultdict(deque)` through the `print(f"  Categorization carried over …")` line with:

```python
        # Labels orphaned by earlier rebuilds get another chance every run —
        # appended after the master's own rows so those take precedence
        prior_orphans = orphans_path(master_file)
        if prior_orphans.exists():
            extra = pd.read_csv(prior_orphans, dtype={"card_last4": str})
            for col in MASTER_COLUMNS:
                if col not in extra.columns:
                    extra[col] = None
            old_master = pd.concat([old_master[MASTER_COLUMNS], extra[MASTER_COLUMNS]],
                                   ignore_index=True)

        old_master["master_category"] = old_master["master_category"].fillna("")
        old_master["sub_category"]    = old_master["sub_category"].fillna("")
        labeled = (old_master["master_category"] != "") | (old_master["sub_category"] != "")

        def _take(idx, i):
            combined.at[idx, "master_category"] = old_master.at[i, "master_category"] or None
            combined.at[idx, "sub_category"]    = old_master.at[i, "sub_category"] or None
            used.add(i)

        # Pass 1: exact key, in order (same-day repeats inherit in sequence)
        exact = defaultdict(deque)
        for i, key in zip(old_master.index, row_key(old_master)):
            exact[key].append(i)
        used, matched = set(), set()
        for idx, key in zip(combined.index, row_key(combined)):
            bucket = exact.get(key)
            if bucket:
                _take(idx, bucket.popleft())
                matched.add(idx)
                result["carried"] += 1

        # Pass 2: labeled rows pass 1 couldn't place, by the looser key
        spare = old_master[labeled & ~old_master.index.isin(used)]
        fallback = defaultdict(deque)
        for i, key in zip(spare.index, fallback_key(spare)):
            fallback[key].append(i)
        rest = combined[~combined.index.isin(matched)]
        for idx, key in zip(rest.index, fallback_key(rest)):
            bucket = fallback.get(key)
            if bucket:
                _take(idx, bucket.popleft())
                result["rescued"] += 1

        # Whatever's still unplaced is kept and reported, never silently dropped
        orphans = old_master[labeled & ~old_master.index.isin(used)]
        result["orphaned"] = len(orphans)
        if orphans.empty:
            orphans_path(master_file).unlink(missing_ok=True)
        else:
            atomic_write_csv(orphans[MASTER_COLUMNS], orphans_path(master_file))
        print(f"  Categorization carried over for {result['carried']}/{len(combined)} row(s)"
              f"; {result['rescued']} rescued by the fallback match")
        if result["orphaned"]:
            print(f"  ⚠ {result['orphaned']} label(s) matched no transaction — saved to "
                  f"{orphans_path(master_file)}")
```

In `app.py`, add the import:

```python
from Modules.safety import orphan_count
```

In the header layout, directly after the `unlabeled-note` paragraph:

```python
            # Labels the last rebuild couldn't place (kept in a side file)
            html.P(id="orphan-note", className="notice warn-text"),
```

And add the callback next to `update_unlabeled_note`:

```python
@app.callback(
    Output("orphan-note", "children"),
    Input("refresh-trigger", "data"),
)
def update_orphan_note(_refresh):
    n = orphan_count(MASTER_PATH) if MASTER_PATH else 0
    if not n:
        return ""
    return (f"⚠ {n} label{'s' if n != 1 else ''} currently match no transaction. They're kept "
            f"in SORTED/orphaned_labels.csv and re-attach automatically if those "
            f"transactions come back in a later export.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add main.py app.py tests/test_rebuild.py
git commit -m "Rescue labels with a fallback match; report the rest as orphans"
```

---

### Task 4: Safe, Excel-tolerant label import

**Files:**
- Create: `Modules/labels.py`
- Modify: `app.py` — `import_csv` callback and imports
- Test: `tests/test_labels.py`

**Interfaces:**
- Consumes: `atomic_write_csv`, `backup_master` from Task 1.
- Produces:
  - `read_import_csv(raw: bytes) -> pd.DataFrame` (all columns as `str`, blanks as `""`)
  - `apply_label_import(master: pd.DataFrame, imp: pd.DataFrame) -> tuple[pd.DataFrame, int, int]` → `(updated master, rows updated, import rows skipped)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_labels.py
import pandas as pd
import pytest

from Modules.labels import apply_label_import, read_import_csv


def _master():
    return pd.DataFrame({
        "date":            ["2024-03-15", "2024-03-15", "2024-03-16"],
        "description":     ["CAFE", "CAFE", "BOOKSHOP"],
        "amount":          [-1234.5, -1234.5, -12.0],
        "source":          ["Chase Credit"] * 3,
        "card_last4":      ["0123", "4567", "0123"],
        "master_category": ["", "", ""],
        "sub_category":    ["", "", ""],
    })


def _imp(**cols):
    return pd.DataFrame(cols).astype(str)


def test_reads_bom_and_windows_1252():
    assert read_import_csv("﻿description\nCAFÉ\n".encode("utf-8")).columns[0] == "description"
    assert read_import_csv("description\nCAFÉ\n".encode("cp1252")).iloc[0, 0] == "CAFÉ"


def test_excel_reformatted_values_still_match():
    imp = _imp(date=["3/15/2024"], description=["CAFE"], amount=["-$1,234.50"],
               source=["Chase Credit"], card_last4=["123"],
               master_category=["Expense"], sub_category=["Coffee"])
    out, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (1, 0)
    assert out.loc[0, "sub_category"] == "Coffee"      # card 0123 only
    assert out.loc[1, "sub_category"] == ""            # same purchase, other card


def test_parenthesised_negative_amount():
    imp = _imp(date=["2024-03-16"], description=["BOOKSHOP"], amount=["($12.00)"],
               source=["Chase Credit"], master_category=["Expense"])
    _, updated, _ = apply_label_import(_master(), imp)
    assert updated == 1


def test_blank_date_is_skipped_not_mass_applied():
    imp = _imp(date=[""], description=["CAFE"], amount=["-1234.5"],
               source=["Chase Credit"], master_category=["Transfer"])
    out, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (0, 1)
    assert (out["master_category"] == "").all()


def test_rows_without_labels_are_ignored_and_unmatched_counted():
    imp = _imp(date=["2024-03-15", "2024-01-01"], description=["CAFE", "NOWHERE"],
               amount=["-1234.5", "-1"], source=["Chase Credit"] * 2,
               master_category=["", "Expense"])
    _, updated, skipped = apply_label_import(_master(), imp)
    assert (updated, skipped) == (0, 1)


def test_without_card_column_matches_every_card():
    imp = _imp(date=["2024-03-15"], description=["CAFE"], amount=["-1234.5"],
               source=["Chase Credit"], master_category=["Expense"])
    out, updated, _ = apply_label_import(_master(), imp)
    assert updated == 2 and (out.loc[:1, "master_category"] == "Expense").all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_labels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'Modules.labels'`

- [ ] **Step 3: Write the implementation**

```python
# Modules/labels.py
"""
Applying an edited export (IMPORT CSV) back onto the master file.

The round-trip goes through Excel, which re-saves CSVs in its own way:
UTF-8 with a BOM or Windows-1252, dates as 3/15/2024, amounts as
-$1,234.50 or ($1,234.50), and card numbers without their leading zero.
Everything here tolerates that.
"""
import io

import pandas as pd


def read_import_csv(raw: bytes) -> pd.DataFrame:
    """Decode an uploaded CSV; every column as text, blanks as ''."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    raise ValueError("the file isn't UTF-8 or Windows-1252 text")


def _amount(value) -> float | None:
    text = str(value).strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    try:
        number = float(text.strip("()"))
    except ValueError:
        return None
    return round(-number if negative else number, 2)


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", format="mixed").dt.normalize()


def _last4(value) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(4) if text.isdigit() else text


def apply_label_import(master: pd.DataFrame, imp: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Write master_category / sub_category from `imp` onto matching `master`
    rows. A row matches on description + amount + source, plus date when the
    file has a date column, plus card when the row names one.

    Returns (updated master, master rows updated, import rows skipped). An
    import row is skipped when its amount or date can't be read, or when it
    matches nothing — a row with a date column but a blank date is skipped
    rather than applied to every date. Rows with no labels are ignored.
    """
    master = master.copy()
    for col in ("master_category", "sub_category", "card_last4"):
        if col not in master.columns:
            master[col] = ""
        master[col] = master[col].fillna("").astype(str)

    m_desc  = master["description"].astype(str).str.strip()
    m_amt   = pd.to_numeric(master["amount"], errors="coerce").round(2)
    m_src   = master["source"].astype(str)
    m_date  = _dates(master["date"])
    m_last4 = master["card_last4"].map(_last4)

    has_date, has_sub, has_card = ("date" in imp.columns, "sub_category" in imp.columns,
                                   "card_last4" in imp.columns)
    updated = skipped = 0
    for _, row in imp.iterrows():
        cat = str(row.get("master_category", "")).strip()
        sub = str(row.get("sub_category", "")).strip() if has_sub else ""
        if not cat and not sub:
            continue
        amount = _amount(row["amount"])
        if amount is None:
            skipped += 1
            continue
        mask = (m_desc == str(row["description"]).strip()) & (m_amt == amount) & (m_src == str(row["source"]))
        if has_date:
            day = _dates(pd.Series([row["date"]])).iat[0]
            if pd.isna(day):
                skipped += 1
                continue
            mask &= m_date == day
        if has_card and _last4(row["card_last4"]):
            mask &= m_last4 == _last4(row["card_last4"])
        n = int(mask.sum())
        if n == 0:
            skipped += 1
            continue
        if cat:
            master.loc[mask, "master_category"] = cat
        if sub:
            master.loc[mask, "sub_category"] = sub
        updated += n
    return master, updated, skipped
```

In `app.py`, add the imports:

```python
from Modules.labels import apply_label_import, read_import_csv
from Modules.safety import atomic_write_csv, backup_master, orphan_count
```

(merge with Task 3's `from Modules.safety import orphan_count` line). Replace the body of `import_csv` after `_, content_string = contents.split(",", 1)` with:

```python
    try:
        import_df = read_import_csv(base64.b64decode(content_string))
    except Exception as e:
        return f"⚠ Could not read CSV: {e}", dash.no_update

    required = {"description", "amount", "source", "master_category"}
    missing = required - set(import_df.columns)
    if missing:
        return f"⚠ Missing columns: {', '.join(sorted(missing))}", dash.no_update

    if not MASTER_PATH or not MASTER_PATH.exists():
        return "⚠ No data directory configured — use the setup screen first.", dash.no_update
    try:
        full_df = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
        full_df, updated, skipped = apply_label_import(full_df, import_df)
        # Versioned backup, then an atomic write: a bad import can be rolled
        # back from SORTED/backups/, and a crash never truncates the master
        backup_master(MASTER_PATH)
        atomic_write_csv(full_df, MASTER_PATH)
        global df
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)

        note = f" · {skipped} row(s) matched nothing" if skipped else ""
        return f"Updated {updated} row(s) from {filename}{note}", (trigger or 0) + 1
    except PermissionError:
        return "⚠ The master file is open in another program (Excel?) — close it and import again.", dash.no_update
    except Exception as e:
        return f"Import error: {e}", dash.no_update
```

Remove the now-unused `import io` from inside `import_csv`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v && python -m pyflakes app.py main.py Modules tests`
Expected: all tests pass; pyflakes reports only the two pre-existing `main.py` f-string warnings.

- [ ] **Step 5: Manual check in the app**

Run `FINANCE_DATA_DIR=<copy of Test Data> python -c "import runpy; runpy.run_path('app.py', run_name='__main__')"`, Export CSV, open in Excel (or edit the dates to `M/D/YYYY` and amounts to `-$x.xx`), label two rows, Import CSV. Expected: `Updated 2 row(s) from transactions_export.csv`; a new file in `SORTED/backups/`.

- [ ] **Step 6: Commit**

```bash
git add Modules/labels.py app.py tests/test_labels.py
git commit -m "Import labels safely and tolerate Excel-reformatted CSVs"
```

---

### Task 5: Docs — describe the guarantees, retire the known gaps

**Files:**
- Modify: `docs/decisions.md`, `docs/features/ingest-pipeline.md`, `docs/features/import-export.md`, `docs/features/overview-charts.md`, `docs/features/transforms.md` (Modules table only), `readme.md`

**Interfaces:**
- Consumes: behaviour from Tasks 1–4.
- Produces: docs only.

- [ ] **Step 1: `docs/decisions.md`** — replace the **Known gaps** paragraph under *Rebuild the master from RAW every run — never append* with:

```markdown
**Label safety:** the labels are the one thing RAW can't regenerate, so every write to the master goes through `Modules/safety.py`: the prior master is *copied* to `SORTED/backups/` (newest 10 kept), the new one is written to a temp file and swapped in atomically, and a master missing after a failed run is restored from the newest backup before anything else happens. Labels are carried by the exact match key first, then by a looser date + description + amount + source key; any label neither places is written to `SORTED/orphaned_labels.csv` and flagged in the header — never silently dropped.

**Still open:** a late-posting charge can fall on a coverage boundary, and `card_last4` only comes from Chase filenames (see *Folder-authoritative institution identity*).
```

And add a new section after it:

```markdown
## Every master write is a backup + atomic swap

`Modules/safety.py` is the only code that writes the master: `backup_master` (timestamped copy, keep 10), then `atomic_write_csv` (temp file in the same folder, then `os.replace`). Rebuild and Import both use it.

**Why:** the old rebuild renamed the master to a single `.bak` before reading it, so one failed run plus the startup auto-ingest and a Reload could destroy every label. A copy keeps the original in place; the atomic swap means a crash leaves either the old file or the complete new one; ten generations mean one bad import can be rolled back by hand.
```

- [ ] **Step 2: `docs/features/ingest-pipeline.md`** — replace the **Backup:** paragraph with:

```markdown
**Backups:** before rebuilding, the existing master is *copied* to `SORTED/backups/edited_combined_transactions.<timestamp>.csv`; the newest 10 are kept (a legacy `.csv.bak` from older versions is left alone and used as a last resort). If the master is missing when a rebuild starts — e.g. after a failed run — the newest backup is restored first and the console says so. To deliberately start over, delete both the master and `SORTED/backups/`.

**Fallback match & orphans:** labels the exact `MATCH_COLUMNS` key can't place are tried again by `FALLBACK_COLUMNS` (date, description, amount, source) — so a re-export that changes a bank category, memo, or running balance keeps its labels. Labels neither key places are kept in `SORTED/orphaned_labels.csv`, re-tried on every later rebuild (so they re-attach if the transaction reappears in a new export), counted in the dashboard header, and the file is deleted once it's empty.

The new master is written atomically (temp file + `os.replace`), so a crash mid-write can't truncate it.
```

And add `SORTED/backups/` and `SORTED/orphaned_labels.csv` rows to the **Outputs** table, replacing the `.csv.bak` row:

```markdown
| `SORTED/backups/edited_combined_transactions.<timestamp>.csv` | Every rebuild and every import (newest 10 kept) | Auto-restore when the master is missing; manual rollback |
| `SORTED/orphaned_labels.csv` | Every rebuild: labels not yet placed (removed when empty) | Re-tried on the next rebuild; header note |
```

- [ ] **Step 3: `docs/features/import-export.md`** — replace the matching bullet list under step 3 of *Import / export workflow* with:

```markdown
   - Reads UTF-8 (with or without BOM) or Windows-1252 — whatever Excel saved
   - Matches rows by `description` + `amount` + `source`, plus `date` when the file has a date column, plus `card_last4` when the row has one. Excel's reformatting is tolerated: `3/15/2024` dates, `-$1,234.50` / `($1,234.50)` amounts, card `123` for `0123`
   - A row whose date is blank or unreadable is **skipped**, never applied to every date; rows that match nothing are counted (`· 3 row(s) matched nothing`)
   - Writes `master_category` and `sub_category` to every matched row — after a versioned backup to `SORTED/backups/`, with an atomic write
   - Skips rows where both label fields are blank
   - Reloads `df` and increments `refresh-trigger` so every card updates
```

- [ ] **Step 4: `docs/features/overview-charts.md`** — in the **Header** list, after the unlabeled-note bullet, add:

```markdown
- **Orphan note** (`orphan-note`, red) — shown while some of your labels match no transaction; they're kept in `SORTED/orphaned_labels.csv` and re-attach automatically if the transactions return. See [ingest-pipeline.md](ingest-pipeline.md).
```

- [ ] **Step 5: `docs/features/transforms.md`** — after the intro paragraph, add:

```markdown
Two sibling modules sit beside it: `Modules/safety.py` (backups, atomic writes, restore — the only code that writes the master) and `Modules/labels.py` (applying an imported CSV's labels). See [ingest-pipeline.md](ingest-pipeline.md) and [import-export.md](import-export.md).
```

- [ ] **Step 6: `readme.md`** — in *Project layout*, under `Modules/`, add:

```
│   ├── safety.py            # Backups + atomic writes for the master (your labels)
│   ├── labels.py            # Applies an imported CSV's labels
```

and in *Running*, replace "and [decisions.md](docs/decisions.md#rebuild-the-master-from-raw-every-run--never-append) for its known gaps (keep a backup of your master file)." with "Every rebuild and import first copies your master to `SORTED/backups/` (newest 10 kept)."

- [ ] **Step 7: Verify and commit**

Run: `grep -rn "\.bak\|known gaps\|Known gaps" readme.md docs` — expected: only the legacy-`.bak` mention in ingest-pipeline.md.
Run: `python -m pytest tests/ -q` — expected: all pass.

```bash
git add docs readme.md
git commit -m "Document backups, atomic writes, fallback matching and orphans"
```

---

## Out of scope (separate plans)

- **In-app labeling** of unlabeled rows (a review table in the dashboard) — its own plan; it will build on `apply_label_import` and `backup_master` from this one.
- **Coverage-boundary drops** for late-posting charges and **account identity** for non-Chase cards — ingest correctness, not label safety.
