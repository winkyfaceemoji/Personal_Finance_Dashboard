# 0001. Data lives outside the repo, in a configurable data directory

Status: Accepted

## Context
RAW exports and the master file need a home. The master holds the user's hand-assigned labels and is the one irreplaceable artifact: RAW can be re-downloaded, labels cannot.

## Decision
All data lives in a `data_dir`, not in the app folder. It is resolved from `FINANCE_DATA_DIR` → `config.json` → the bundled `Test Data/` (`config.get_data_dir()`). `RAW/` and `SORTED/` sit under it.

Rejected: storing data app-side. It ties labels to one install, breaks the multi-dataset model, and risks committing real finances.

## Consequences
- Backing up, moving or cloud-syncing a data folder carries its labels along with their source data.
- Separate data folders are independent datasets.
- Real financial data stays outside the tracked tree. `config.json`, `Test Data/SORTED/` and the legacy `Data/` folder are git-ignored.
