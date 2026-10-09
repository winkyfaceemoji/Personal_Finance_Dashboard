# Personal Finance Dashboard

A local Plotly Dash app for tracking personal spending across Chase and Discover accounts. Raw CSV exports from your bank become a unified, category-tagged transaction ledger. A browser dashboard answers two questions — **am I on track?** and **where did the money go?** — for any week, month, or year: what you spent and earned, how that compares with the previous period and with a typical one, your pace so far, and which categories and merchants it went to. Everything runs on your machine; no bank logins.

---

## Project layout

```
.
├── main.py                  # Ingest pipeline → launches dashboard
├── app.py                   # Dash dashboard (layout + all callbacks)
├── config.py                # Data directory resolution (env var > config.json > Test Data/)
├── config.json              # Your saved data folder path — git-ignored, created on first save
├── rules.csv                # Keyword → category auto-tagging rules (the labeling panel adds to it)
├── Modules/
│   ├── transforms.py        # Data helpers (load, label, period maths, aggregate)
│   ├── safety.py            # Backups + atomic writes for the master (your labels)
│   └── labels.py            # Merchant groups, rule safety, label writes, imported-CSV matcher
├── Test Data/               # Anonymized demo data — works out of the box
│   ├── RAW/                 # Demo bank CSVs, one subfolder per institution (tracked in git)
│   └── SORTED/              # Pipeline output — regenerated on first run (git-ignored)
├── assets/
│   ├── app.css              # All styles — theme tokens only, generated from _CHART in app.py
│   └── theme_sync.js        # Mirrors the theme class onto <body> for dropdown popups
├── tests/                   # pytest: period maths + an end-to-end run on Test Data
├── docs/
│   ├── design.md            # UI design system
│   ├── decisions.md         # Architecture decisions
│   └── features/            # Per-feature architecture docs
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt     # + pytest
```

---

## Prerequisites

- Python 3.12+
- Supported bank CSV formats: Chase Debit, Chase Credit, Discover Credit

---

## Setup

### Windows

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Docker

Build the image once (only needed again if `requirements.txt` changes):

```bash
docker build -t personal-finance .
```

Run with your local code mounted so file changes reload automatically — no rebuild required:

```cmd
# CMD (Windows) — run from the project root directory
docker run -p 127.0.0.1:8050:8050 -v "%cd%:/app" personal-finance

# PowerShell (Windows)
docker run -p 127.0.0.1:8050:8050 -v "$($(Get-Location).Path):/app" personal-finance

# bash / macOS / Linux
docker run -p 127.0.0.1:8050:8050 -v $(pwd):/app personal-finance
```

The volume mount overlays your local project directory onto `/app` inside the container. Dash's built-in hot-reloader watches `.py` files and restarts the server within a second or two of any save. A data folder inside the project (such as `Test Data/`) is mounted along with it, so the ingest pipeline reads and writes CSV files directly on your machine.

`-p 127.0.0.1:8050:8050` publishes the port to this computer only. The dashboard has no login, so don't use a bare `-p 8050:8050`: that would let anyone on your network open it, export your transactions, or change your labels.

---

## First launch

On first launch the app resolves a data directory (see priority below) and automatically runs the ingest pipeline against it if it hasn't been ingested yet — so the included `Test Data/` folder, with its anonymized demo transactions, populates and displays immediately. No setup required — just run and open the browser.

To use your own bank data, open the settings menu (gear icon) and click **CHANGE DATA FOLDER** at any time. This reopens the setup overlay — prefilled with your current path — where you can browse to a new directory and click **Save & Launch**, or click **Cancel** to close it without changing anything. The chosen path is saved to `config.json` and used on every subsequent start.

The overlay only blocks the dashboard automatically if no data directory could be resolved at all (for example, if `Test Data/` is deleted and nothing else is configured).

**Data directory priority:**
1. `FINANCE_DATA_DIR` environment variable (useful for Docker / CI)
2. `config.json` in the project root (set via the in-app setup screen)
3. `Test Data/` folder in the project root (built-in demo data)

---

## Running

One command starts everything — the ingest pipeline runs first, then the dashboard launches automatically:

```bash
# Windows
.venv\Scripts\python main.py

# Linux / macOS / Docker entrypoint
python main.py
```

Open `http://localhost:8050` in a browser. To stop: `Ctrl+C`.

By default the server only accepts connections from this computer, with debug mode off. Two environment variables change that:

| Variable | Default | Set it to… |
|----------|---------|-----------|
| `FINANCE_HOST` | `127.0.0.1` | `0.0.0.0` to open the dashboard from another device on your network (anyone on that network can then use it) |
| `FINANCE_DEBUG` | `0` | `1` for hot reload, Dash dev tools, and error tracebacks while developing |

The ingest step reads every CSV in the configured `RAW/` folder, normalises each file to a unified schema, merges overlapping exports of the same account by date coverage, and **rebuilds** `edited_combined_transactions.csv` from scratch — carrying forward the `master_category` / `sub_category` labels you've already assigned. See [ingest-pipeline.md](docs/features/ingest-pipeline.md) for how labels are matched. Every rebuild and import first copies your master to `SORTED/backups/` (newest 10 kept).

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover the week / month / year maths and run the full ingest on a temporary copy of `Test Data/` — they never write into the repo. GitHub Actions runs them on every pull request and every push to `main`, on Linux and Windows (`.github/workflows/tests.yml`).

---

## UI tour

One page, driven by one control. The header shows your sources, how recent your data is (`data through Dec 26, 2025`, plus any account lagging behind), a notice when your newest transaction is over a week old, and a red note with the count and dollar size of unlabeled rows, with a **LABEL THEM →** button beside it. After an import, a second line says what the last import added (`31 new · 27 labeled · 4 need you`) with a **REVIEW →** button. The settings gear (top right) holds **DATA** (**IMPORT CSV** / **EXPORT CSV** for labeling, **RELOAD DATA** to re-run the ingest), **SOURCE** (**CHANGE DATA FOLDER**), and **THEME**.

### Pick a period

The period bar under the header — **WEEK | MONTH | YEAR** and a **‹ period ›** stepper — chooses what everything below it shows. Weeks run Monday to Sunday. It opens on the period containing your **newest transaction** (not today's date, so stale exports never show an empty page), and **LATEST** jumps back there. Switching between week, month, and year keeps your place, and the bar stays pinned while you scroll.

### The cards

| Card | What it shows |
|------|---------------|
| STAT CARDS | Spent, income, net, and savings rate for the period — each vs the previous period and vs your **typical** period (median of the last 12 weeks/months, or of earlier years). While a period is still in progress they read *so far* and compare against the same number of days of earlier periods |
| PACE | (in-progress periods) Spending so far against what you typically spend by this point, and a typical full period — `$782 over your typical pace` |
| SPENDING OVER TIME | A bar per week (last 26), month (last 24), or year (all), with a dashed typical line; the selected period is outlined and an in-progress one hatched. **Click a bar to open that period.** The title dropdown switches Expenses / Income / Net Cash Flow |
| SPEND BY CATEGORY | Sorted bars for the selected period — top 9 categories + Other, with `$ · %`. Click a bar for its top merchants and largest transaction (click again to close) |
| BY CALENDAR MONTH | One line per year over Jan–Dec, the selected period's year highlighted — spot seasonal spikes. Click a year in the legend to hide it |

> **Note:** All totals are label-based — a row only counts as an expense or income if its **Type of Transaction** field is `Expense` or `Income`. Rows tagged `Transfer` and rows with no label are excluded from every calculation; the header shows how many unlabeled rows (and dollars) are being left out. Label transactions in the labeling panel, with the Excel workflow, or with `rules.csv`, and tag transfers, brokerage moves, and credit card payments as `Transfer` so they don't distort your totals. Weekly tracking needs this most: new transactions arrive unlabeled unless a rule matches them.

### Label transactions

**LABEL THEM →** (or **REVIEW →**, for just the last import's rows) opens a full-screen labeling panel. Unlabeled transactions are grouped by merchant, biggest dollars first (the top 25 are shown). Each group has **EXPENSE / INCOME / TRANSFER** buttons that label every row in it at once, an optional subcategory, and a **Remember for future statements** checkbox that adds a `rules.csv` rule, ticked by default only when the rule provably matches that merchant alone. A group that looks like a card payment gets a starred *suggested* `★ TRANSFER` button. The **TRANSFER PAIRS** tab finds the same amount leaving one of your accounts and arriving in another within 5 days (a card payment, a move to savings) and labels both sides Transfer in one click. Groups with money both in and out (a **MIXED** badge) or no recognizable name are labeled row by row. A collapsible guide explains how to choose a label; **UNDO** reverts the last click; the **RULES** tab lists and deletes the rules the panel added; **DONE** refreshes the dashboard. The first time the panel opens each day, it saves `SORTED/backups/before-labeling-YYYY-MM-DD.csv` so you can get back to where you started. The stat cards show what is still unlabeled as `+ $X unreviewed`. Details in [labeling-panel.md](docs/features/labeling-panel.md).

### Import / export

Label in the app first: the labeling panel above clears most of a backlog in a few clicks. Use Excel for bulk edits and for changing labels that are already set. Open the settings menu (gear icon) and use **EXPORT CSV** to download all transactions, then **IMPORT CSV** to write `master_category` and `sub_category` assignments back. To inspect individual transactions in the app, click a category bar to open its drilldown.

### Theme

The LIGHT / DARK buttons in the settings menu switch themes; the active one is highlighted. The choice persists in your browser's local storage, as does your week / month / year choice.

---

## Category system

Each transaction has three category fields:

| Field | Who sets it | Purpose |
|-------|------------|---------|
| `original_category` | Bank (import) | Raw label from the bank CSV |
| `master_category` | You (via Excel import) | High-level type: `Expense`, `Income`, or `Transfer` |
| `sub_category` | You (optional, via Excel import) | Detail label within the type (e.g. "Rent", "Paycheck", "Fidelity") |

The dashboard displays a single **CATEGORY** column: `sub_category` if set, otherwise `original_category`.

Rows tagged `Transfer` are excluded from all income and expense totals — they represent money moving between accounts, not actual spending or earning. Unlabeled rows are also excluded (they haven't been classified yet); a note in the header counts how many are being ignored.

---

## Bulk category workflow

For a handful of merchants, the labeling panel is quicker (see above). For a bulk edit:

1. Click **EXPORT CSV** in the settings menu
2. Open in Excel — fill `master_category` (`Expense`, `Income`, or `Transfer`) and optionally `sub_category` for each row
3. Save and click **IMPORT CSV** — the app matches rows by description + amount + source + date and writes the values back to the master file

---

## Auto-labeling rules

`rules.csv` maps keyword substrings to labels:

```csv
keyword,master_category,sub_category
payroll,Income,Paycheck
netflix,Expense,Entertainment
fidelity,Transfer,
```

On each data load, any transaction with no `master_category` whose description contains a matching keyword is labeled automatically — so freshly imported statements count in the totals immediately instead of sitting unlabeled and ignored. The first matching rule wins; a hand-assigned `master_category` always takes priority; `sub_category` is optional and only fills rows that don't already have one (and never rows the user labeled with a different master). A rule may also be **sub-only** (blank master, e.g. `venmo,,Venmo`) — useful for descriptions too ambiguous to label but that still deserve a display category in the category breakdown. Rules are applied in-memory, never written to the master file — edit or delete a rule and the next reload re-labels history accordingly.

Edit `rules.csv` directly to add, remove, or adjust rules — no code change needed. The labeling panel also appends rules (with an extra `added` date column, which the loader ignores) when you tick **Remember for future statements**, and its RULES tab can delete those. To make the app use a different rules file (tests and scripted checks do), set `FINANCE_RULES_PATH`. The unlabeled-rows note in the header tells you how many rows your rules don't yet cover.

---

## Data files

`Test Data/RAW/` contains anonymized demo CSVs and is tracked in git. `Test Data/SORTED/` (pipeline output) is git-ignored and regenerated on each run.

If you point the app at your own data directory, that folder is entirely outside the repository — your real transaction CSVs are never committed. `config.json` (which stores the path to your folder) is also git-ignored. As a fallback, a `Data/` folder at the project root (the old default before configurable data directories existed) is also git-ignored, in case one still exists from before this feature was added.

---

## Further reading

Start at the [docs index](docs/README.md), or jump in:

- [UI design system](docs/design.md) — theme tokens, component patterns, CSS gotchas
- [Architecture decisions](docs/decisions.md) — the load-bearing choices and why
- [Feature overview](docs/features/README.md)
  - [Ingest pipeline](docs/features/ingest-pipeline.md)
  - [Setup screen](docs/features/setup-screen.md)
  - [Data transforms layer](docs/features/transforms.md)
  - [Period view & charts](docs/features/overview-charts.md)
  - [Category breakdown & drilldown](docs/features/category-breakdown.md)
  - [Import / export & labeling](docs/features/import-export.md)
  - [Labeling panel](docs/features/labeling-panel.md)
