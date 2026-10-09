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


def _edit(path, n):
    """Change the master so the next backup isn't skipped as identical."""
    pd.DataFrame({"date": ["2025-01-01"], "master_category": [f"v{n}"]}).to_csv(path, index=False)


def test_identical_master_not_backed_up_twice(tmp_path):
    path = _master(tmp_path)
    a, b = backup_master(path), backup_master(path)
    assert a == b and len(list_backups(path)) == 1


def test_backups_have_unique_names(tmp_path, monkeypatch):
    # Windows clocks can tick every ~15 ms, so two backups may get the same
    # timestamp: they must still be distinct files, listed newest first
    monkeypatch.setattr(safety, "_stamp", lambda: "20250101-000000-000000")
    path = _master(tmp_path)
    made = []
    for n in range(12):
        _edit(path, n)
        made.append(backup_master(path, keep=20))
    assert len(set(made)) == 12 and all(p.exists() for p in made)
    assert list_backups(path) == list(reversed(made))


def test_backups_pruned_to_keep_newest(tmp_path):
    path = _master(tmp_path)
    made = []
    for n in range(5):
        _edit(path, n)
        made.append(backup_master(path, keep=3))
    kept = list_backups(path, include_legacy=False)
    assert kept == list(reversed(made))[:3]


def test_legacy_bak_listed_last_and_never_pruned(tmp_path):
    path = _master(tmp_path)
    legacy = path.with_suffix(".csv.bak")
    legacy.write_text("date,master_category\n")
    for n in range(4):
        _edit(path, n)
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


# ── File permissions (POSIX only) ─────────────────────────────────────────────
# mkstemp creates temp files 0600 and os.replace carries that mode to the
# master, which would lock the host user out of a Docker bind-mounted file.

def _umask():
    old = os.umask(0)
    os.umask(old)
    return old


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_new_file_gets_umask_default_mode(tmp_path):
    path = tmp_path / "SORTED" / "new.csv"
    atomic_write_csv(pd.DataFrame({"a": [1]}), path)
    assert path.stat().st_mode & 0o777 == 0o666 & ~_umask()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_overwrite_keeps_existing_mode(tmp_path):
    path = _master(tmp_path)
    os.chmod(path, 0o640)
    atomic_write_csv(pd.DataFrame({"a": [1]}), path)
    assert path.stat().st_mode & 0o777 == 0o640
