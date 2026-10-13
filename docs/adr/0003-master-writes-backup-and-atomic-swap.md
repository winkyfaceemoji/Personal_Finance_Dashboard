# 0003. Every master write is a backup plus an atomic swap

Status: Accepted

## Context
The old rebuild renamed the master to a single `.bak` before reading it. One failed run, followed by the startup auto-ingest and a Reload, could destroy every label.

## Decision
`Modules/safety.py` is the only code that writes the master.

- `backup_master` makes a UTC-timestamped copy in `SORTED/backups/` and keeps the newest 10. It skips the copy when the master is identical to the newest backup. A rebuild backs up only a master that parsed.
- `atomic_write_csv` then writes a temp file in the same folder and swaps it in with `os.replace`.
- Rebuild and Import both hold `MASTER_LOCK`.
- A missing or empty master is restored from the newest backup at the very start of `main()`, even when RAW is empty.

Rejected: the single-generation rename-to-`.bak` (reverted).

## Consequences
- A crash leaves either the old file or the complete new one.
- A Reload and an Import running on the dev server's threads can't overwrite each other.
- Failed runs and no-change Reloads can't rotate good backups out.
- Ten generations mean one bad import can be rolled back by hand.
- The swap keeps the file's permissions, so a master written from Docker stays readable on the host. On Linux, files the container creates are owned by root.
