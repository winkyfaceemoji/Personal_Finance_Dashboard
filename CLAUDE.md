# CLAUDE.md

This is a local Plotly Dash personal-finance dashboard. `main.py` ingests bank CSVs from `RAW/` into a master CSV, then launches `app.py`. Human-facing setup and the UI tour are in `readme.md`. Area-specific pitfalls live in `.claude/rules/`, and decisions live in `docs/adr/`.

## Commands

Always use the project venv. Never use a bare `python` or `pip`.

| Task | Command |
|------|---------|
| Ingest, then run the dashboard (http://127.0.0.1:8050) | `.venv/Scripts/python.exe main.py` |
| Dashboard only | `.venv/Scripts/python.exe app.py` |
| Ingest only | `.venv/Scripts/python.exe -c "import main; main.main()"` |
| Tests | `.venv/Scripts/python.exe -m pytest` |
| Smoke import | `.venv/Scripts/python.exe -c "import app"` |
| Rewrite the made-up demo exports | `.venv/Scripts/python.exe make_demo_data.py` |
| Start the chat model (own terminal) | `powershell -ExecutionPolicy Bypass -File start_llm.ps1` |
| Chat question set, real model (by hand, not CI) | `.venv/Scripts/python.exe ai_eval.py` |
| Data health check (read-only) | `.venv/Scripts/python.exe check_data.py [--save f.csv \| --compare f.csv]` |
| What the screen says (read-only) | `.venv/Scripts/python.exe screen_check.py > before.txt` |
| Docker dev, hot reload | `docker build -t personal-finance .`, then `docker run -p 127.0.0.1:8050:8050 -v "%cd%:/app" personal-finance` |

Docker without the `-v` mount bakes the code into the image. The labels are then written inside the container and lost when it is removed, so mount a data folder for real use.

Install dev dependencies with `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`. It adds pytest and Playwright. `tests/test_ui_states.py` needs Chromium (`python -m playwright install chromium`) and skips itself without it. CI (`.github/workflows/tests.yml`) runs `pytest tests -q -p no:cacheprovider` on Ubuntu and Windows with Python 3.12. Windows is in the matrix because file locking, atomic replace and paths behave differently there.

## Environment variables

| Variable | Effect |
|----------|--------|
| `FINANCE_DATA_DIR` | Data folder. It overrides `config.json`, which overrides `Test Data/` (ADR 0001). |
| `FINANCE_RULES_PATH` | Rules file. Defaults to `SORTED/rules.csv` in the data dir (ADR 0024). |
| `FINANCE_LLM_URL` / `FINANCE_LLM_MODEL` | The chat's llama-server, default `http://127.0.0.1:8080`, and the model `start_llm.ps1` loads (ADR 0021). |
| `FINANCE_HOST` / `FINANCE_DEBUG` / `FINANCE_PORT` | Defaults are `127.0.0.1` / `0` / `8050`. Keep local-only and debug-off as defaults (ADR 0016). |

## Data layout (under the data dir)

- `RAW/<institution>/*.csv` is the input. The top-level folder is the institution (ADR 0004). Files may sit at any depth.
- `SORTED/edited_combined_transactions.csv` is **the master**: the unified columns plus `master_category` / `sub_category`.
- `SORTED/combined_transactions.csv` is raw pipeline output. The app doesn't read it.
- `SORTED/rules.csv` holds the rules. It names real merchants, so it is data, not code (ADR 0024).
- `SORTED/merchants.csv` and `SORTED/merchant_aliases.csv` hold merchants and which spellings belong to them. Read with `read_merchants`, written only with `save_merchants` (ADR 0025). When they disagree or can't be read, the header's attention line says so.
- `SORTED/backups/` holds rotating master backups (10 kept) and the daily `before-labeling-*.csv` snapshots, which are never pruned.
- Other side files in `SORTED/` feed the header's attention line:
  - `orphaned_labels.csv`
  - `skipped_files.csv`
  - `overlap_only.csv`
  - `exported_through.csv`
  - `linked_cards.csv`
  - `last_import.csv`
  - `not_transfers.csv`
- `Test Data/RAW/` is made-up demo data from `make_demo_data.py`, tracked. Never copy real exports into it (ADR 0024). `Test Data/SORTED/` (except its made-up `rules.csv` and merchant files), `config.json`, a root `rules.csv` and the legacy `Data/` are git-ignored. Real data never enters the repo.

## Conventions

- `amount < 0` is money out and `amount > 0` is money in. Discover amounts are negated on ingest.
- `master_category` is one of `Expense`, `Income` or `Transfer` (`PREDEFINED_CATEGORIES`). Anything else, or blank, is "unlabeled".
- The displayed category is `sub_category`, falling back to `original_category`.
- Every total is label-based. Transfer and unlabeled rows count nowhere (ADR 0007). Unlabeled money is *shown* (attention line, `+ $X unreviewed`), never counted.
- No CSS framework. All colour comes from `_CHART` in `app.py` (see the dashboard-ui rule).
- UI copy states facts in plain words. Red and green never carry meaning alone.
- Pure logic goes in `Modules/` with tests in `tests/`. `app.py` holds the layout and callbacks.
- Docs: put pitfalls in `.claude/rules/<area>.md`, scoped by `paths:`. Add an ADR in `docs/adr/` only for a rejected alternative, a reverted experiment or a cross-cutting choice, and add its line to the index below. Don't add per-file docs or `resource:` frontmatter.

## Project-wide gotchas

- **The master's labels are irreplaceable.** Only `Modules/safety.py` writes the master: backup, atomic swap, `MASTER_LOCK` (ADR 0003). Never write it with `to_csv` directly.
- **Tests and scripts must never touch the real `rules.csv` or data.** Point `FINANCE_RULES_PATH` and `FINANCE_DATA_DIR` at copies, because the app can add and delete rules. The ingest tests already run on a temp copy of `Test Data/`.
- **`import app` has side effects.** It resolves the data dir, auto-runs the ingest if no master exists, and loads the module-global `df`.
- **Never anchor to today.** "Latest" means the newest transaction (ADR 0013).
- **Excel round-trips.** Users open the CSVs in Excel. Every reader must accept a UTF-8 BOM or Windows-1252, `3/15/2024` dates, `($1,234.50)` amounts, and card numbers stripped of leading zeros. A file held open by Excel fails writes on Windows, so report it in the UI rather than crashing.
- **No background callbacks** (ADR 0010).

## ADRs

- [0001](docs/adr/0001-data-directory-outside-repo.md) Data lives outside the repo, in a configurable data directory
- [0002](docs/adr/0002-rebuild-master-from-raw.md) Rebuild the master from RAW every run, never append
- [0003](docs/adr/0003-master-writes-backup-and-atomic-swap.md) Every master write is a backup plus an atomic swap
- [0004](docs/adr/0004-folder-authoritative-institution.md) The RAW folder is authoritative for institution identity
- [0005](docs/adr/0005-capital-one-is-the-discover-account.md) Capital One exports are the Discover account; Discover history owns its dates
- [0006](docs/adr/0006-confirm-replacement-cards-before-merging.md) A replacement card is asked about, then counted once
- [0007](docs/adr/0007-label-based-totals-coverage-based-merges.md) Totals are label-based; merges are coverage-based
- [0009](docs/adr/0009-net-worth-from-balance-snapshots.md) Net worth needs balance snapshots, not transactions (not yet built)
- [0010](docs/adr/0010-no-background-callbacks.md) No Dash background callbacks
- [0011](docs/adr/0011-category-selection-store-and-patch.md) Category selection lives in a Store and is patched, not driven by clickData
- [0012](docs/adr/0012-one-period-control.md) One period control drives the whole page
- [0013](docs/adr/0013-anchor-periods-to-latest-transaction.md) Periods are anchored to the latest transaction, not today
- [0014](docs/adr/0014-typical-is-a-like-for-like-median.md) In-progress periods compare like-for-like; "typical" is a median
- [0015](docs/adr/0015-partly-covered-periods-and-as-of-wording.md) Comparisons say where the data stops and skip partly covered periods
- [0016](docs/adr/0016-local-only-debug-off-by-default.md) Local-only and debug-off by default
- [0017](docs/adr/0017-transfer-pairs-only-when-certain.md) Transfer pairs are suggested only when the match is certain
- [0018](docs/adr/0018-one-page-spending-vs-typical-no-budget.md) One high-level page: spending vs typical, no budget
- [0019](docs/adr/0019-stat-cards-vs-last-year-in-dollars.md) Stat cards compare with the same period last year, in dollars
- [0020](docs/adr/0020-recurring-charges-follow-latest-price.md) Recurring charges are labeled by what they are; price follows the latest charge
- [0021](docs/adr/0021-ai-chat-uses-pre-written-tools.md) The AI chat answers only through pre-written tools, from a local llama-server
- [0022](docs/adr/0022-recommendations-cite-a-knowledge-base.md) Recommendations must cite a public knowledge base (not yet built)
- [0024](docs/adr/0024-no-real-data-in-the-repo.md) No real financial data in the repo: rules live in the data folder, demo data is made up
- [0025](docs/adr/0025-merchants-own-rules-and-labeling.md) Merchants own the rules; one panel labels and reviews them, with every 0008 safeguard
