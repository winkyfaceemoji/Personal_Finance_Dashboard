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
