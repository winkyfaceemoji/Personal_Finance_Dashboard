"""
Crash-safe writes and versioned backups for the master file — the one file
holding labels that can't be regenerated from RAW. Every write to the master
goes through here.
"""
import filecmp
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BACKUP_DIRNAME = "backups"
BACKUP_KEEP    = 10
ORPHANS_NAME   = "orphaned_labels.csv"

# Dash's dev server runs callbacks on threads: a Reload rebuilding the master
# while an Import rewrites it would let one overwrite the other's labels. Every
# read-modify-write of the master in the app holds this lock.
MASTER_LOCK = threading.Lock()


def _backup_dir(master: Path) -> Path:
    return Path(master).parent / BACKUP_DIRNAME


def _match_mode(tmp: str, dest: Path) -> None:
    """mkstemp makes the temp file 0600, and os.replace carries that mode to
    the destination. Give the temp file the destination's current mode, or
    the umask default for a new file, so the master stays readable by the
    host user when it is a Docker bind mount."""
    if dest.exists():
        shutil.copymode(dest, tmp)
    else:
        old = os.umask(0)   # os.umask can only be read by setting it
        os.umask(old)
        os.chmod(tmp, 0o666 & ~old)


def _discard(tmp: str) -> None:
    """Remove a leftover temp file, but never let a failed cleanup (e.g. a
    read-only temp on Windows) replace the error the user needs to see."""
    try:
        Path(tmp).unlink(missing_ok=True)
    except OSError:
        pass


def _replace_from(src: Path, dest: Path) -> None:
    """Copy src over dest atomically: temp file beside dest, then os.replace."""
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        _match_mode(tmp, dest)
        os.replace(tmp, dest)
    except BaseException:
        _discard(tmp)
        raise


def restore_backup(backup: Path, master: Path) -> None:
    """Put a backup back over the master, atomically (used by the panel's Undo)."""
    _replace_from(Path(backup), Path(master))


def snapshot_master(master: Path, name: str = "before-labeling") -> Path | None:
    """A named copy kept OUTSIDE the backup rotation: labeling takes a backup
    per click, so ten clicks would otherwise prune away the state from before
    the labeling session — the recovery point that matters most."""
    master = Path(master)
    if not master.exists():
        return None
    d = _backup_dir(master)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{name}{master.suffix}"          # outside list_backups' glob
    _replace_from(master, dest)
    return dest


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
        _match_mode(tmp, path)
        os.replace(tmp, path)
    except BaseException:
        _discard(tmp)
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


def _stamp() -> str:
    # UTC, so names keep sorting chronologically through the repeated hour
    # when daylight saving ends
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def backup_master(master: Path, keep: int = BACKUP_KEEP) -> Path | None:
    """Copy the master into SORTED/backups/ under a timestamped name and keep
    the newest `keep`. A copy, not a rename: if anything after this fails,
    the master is still in place. A master identical to the newest backup
    isn't copied again (that backup is returned), so Reloads that change
    nothing don't prune older, different versions away."""
    master = Path(master)
    if not master.exists():
        return None
    newest = list_backups(master, include_legacy=False)
    if newest and filecmp.cmp(master, newest[0], shallow=False):
        return newest[0]
    d = _backup_dir(master)
    d.mkdir(parents=True, exist_ok=True)
    # The clock can tick as coarsely as ~15 ms (Windows), so a stamp can
    # repeat: never overwrite, add a counter instead. "_001" sorts after the
    # bare name ("_" > ".") and zero-padding keeps the counters in order.
    stamp = _stamp()
    dest = d / f"{master.stem}.{stamp}{master.suffix}"
    n = 0
    while dest.exists():
        n += 1
        dest = d / f"{master.stem}.{stamp}_{n:03d}{master.suffix}"
    shutil.copy2(master, dest)
    for old in list_backups(master, include_legacy=False)[keep:]:
        old.unlink(missing_ok=True)
    return dest


def restore_if_missing(master: Path) -> Path | None:
    """If the master is gone (or empty) but a backup exists, put the newest
    backup back and return the backup used. Without this, a failed run
    followed by the startup auto-ingest would write a fresh master with no
    labels at all. A 0-byte master — a save torn by power loss — counts as
    gone: it holds no labels and can't even be parsed."""
    master = Path(master)
    if master.exists() and master.stat().st_size > 0:
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
