# Personal Finance Dashboard

A local Plotly Dash app for tracking personal spending across Chase and Discover accounts. Raw CSV exports from your bank become a unified, category-tagged transaction ledger. A browser dashboard lets you explore spending by month, year, and category.

---

## Project layout

```
.
├── main.py                  # Ingest pipeline → launches dashboard
├── app.py                   # Dash dashboard (layout + all callbacks)
├── config.py                # Data directory resolution (env var > config.json > Test Data/)
├── config.json              # Your saved data folder path — git-ignored, created on first save
├── rules.csv                # Keyword → category auto-tagging rules
├── Modules/
│   └── transforms.py        # Data helpers (load, filter, aggregate)
├── Test Data/               # Anonymized demo data — works out of the box
│   ├── RAW/                 # Demo bank CSVs, one subfolder per institution (tracked in git)
│   └── SORTED/              # Pipeline output — regenerated on first run (git-ignored)
├── assets/
│   ├── dropdown_theme.css   # Dash 4 dropdown theme overrides
│   └── dropdown_theme.js    # Runtime CSS-variable injection for theming
├── docs/
│   └── features/            # Per-feature architecture docs
├── Dockerfile
└── requirements.txt
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
docker run -p 8050:8050 -v "%cd%:/app" personal-finance

# PowerShell (Windows)
docker run -p 8050:8050 -v "$($(Get-Location).Path):/app" personal-finance

# bash / macOS / Linux
docker run -p 8050:8050 -v $(pwd):/app personal-finance
```

The volume mount overlays your local project directory onto `/app` inside the container. Dash's built-in hot-reloader watches `.py` files and restarts the server within a second or two of any save. Your `Data/` folder is also mounted, so the ingest pipeline reads and writes CSV files directly on your machine.

---

## First launch

On first launch the app resolves a data directory (see priority below) and automatically runs the ingest pipeline against it if it hasn't been ingested yet — so the included `Test Data/` folder, with its anonymized demo transactions, populates and displays immediately. No setup required — just run and open the browser.

To use your own bank data, click **CHANGE DATA FOLDER** in the nav bar at any time. This reopens the setup overlay — prefilled with your current path — where you can browse to a new directory and click **Save & Launch**, or click **Cancel** to close it without changing anything. The chosen path is saved to `config.json` and used on every subsequent start.

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

The ingest step reads every CSV in the configured `RAW/` folder, normalises each file to a unified schema, deduplicates rows, and merges into `edited_combined_transactions.csv` — preserving any category assignments already present. New transactions are appended; existing ones are untouched.

---

## UI tour

The dashboard is a single page of four cards. The header subtitle lists the data sources and the latest transaction date (e.g. `3 sources: Chase Credit, Chase Debit, Discover Credit · latest transaction Jun 27, 2026`), with a red note beneath it counting any unlabeled rows. The settings gear at the header's top-right corner opens a Settings menu grouped into **DATA** (**IMPORT CSV** / **EXPORT CSV** for the labeling round-trip, and **RELOAD DATA** to re-run the ingest pipeline without leaving the browser), **SOURCE** (**CHANGE DATA FOLDER**, reopens the setup overlay), and **THEME** (light/dark toggle). All menu buttons share one consistent style.

### The cards

Each graph carries only its own controls — there is no global filter.

| Card | What it shows |
|------|---------------|
| SUMMARY | Four year-to-date stat cards — income, expenses, net, savings rate — each with a delta vs the same period last year (green/red by good-or-bad for that metric, savings rate in percentage points) |
| CASH FLOW | Monthly bars within a calendar-anchored range (YTD / 1Y / 3Y chips, YTD default); the metric selector on the left (Net Cash Flow / Expenses / Income) doubles as the card title |
| TRENDS | Same-month year-over-year comparison: one line per year over a Jan–Dec axis (current year bold, older years muted), so Feb '25 vs Feb '26 is a straight vertical read; always all data, no range control |
| CATEGORIES | Pie of spending by category for one year (year chips, latest year default), top 9 categories + "Other"; click a slice to pop it out and expand a top-merchants breakdown beneath it (click again to deselect) |

> **Note:** All totals are label-based — a row only counts as an expense or income if its **Type of Transaction** field is `Expense` or `Income`. Rows tagged `Transfer` and rows with no label are excluded from every calculation; a note in the header shows how many unlabeled rows are being ignored. Use the Excel import workflow to label your transactions and tag transfers, brokerage moves, and credit card payments as `Transfer` so they don't distort your totals.

### Import / export

Open the settings menu (gear icon) and use **EXPORT CSV** to download all transactions for bulk editing in Excel, then **IMPORT CSV** to write `master_category` and `sub_category` assignments back. A red note in the header counts any rows with no valid label. To inspect individual transactions in the app, click a slice on the Categories pie to open its drilldown.

### Theme

The LIGHT / DARK buttons in the settings menu (gear icon) switch themes. The choice persists in your browser's local storage.

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

On each data load, any transaction with no `master_category` whose description contains a matching keyword is labeled automatically — so freshly imported statements count in the totals immediately instead of sitting unlabeled and ignored. The first matching rule wins; a hand-assigned `master_category` always takes priority; `sub_category` is optional and only fills rows that don't already have one (and never rows the user labeled with a different master). A rule may also be **sub-only** (blank master, e.g. `venmo,,Venmo`) — useful for descriptions too ambiguous to label but that still deserve a display category in the spend pie. Rules are applied in-memory, never written to the master file — edit or delete a rule and the next reload re-labels history accordingly.

Edit `rules.csv` directly to add, remove, or adjust rules — no code change needed. The unlabeled-rows note in the header tells you how many rows your rules don't yet cover.

---

## Data files

`Test Data/RAW/` contains anonymized demo CSVs and is tracked in git. `Test Data/SORTED/` (pipeline output) is git-ignored and regenerated on each run.

If you point the app at your own data directory, that folder is entirely outside the repository — your real transaction CSVs are never committed. `config.json` (which stores the path to your folder) is also git-ignored. As a fallback, a `Data/` folder at the project root (the old default before configurable data directories existed) is also git-ignored, in case one still exists from before this feature was added.

---

## Further reading

Start at the [docs index](docs/README.md), or jump in:

- [UI design system](docs/design.md) — colours, themes, component patterns, CSS gotchas
- [Architecture decisions](docs/decisions.md) — the load-bearing choices and why
- [Feature overview](docs/features/README.md)
  - [Ingest pipeline](docs/features/ingest-pipeline.md)
  - [Setup screen](docs/features/setup-screen.md)
  - [Data transforms layer](docs/features/transforms.md)
  - [Overview charts](docs/features/overview-charts.md)
  - [Category breakdown & drilldown](docs/features/category-breakdown.md)
  - [Import / export & labeling](docs/features/import-export.md)
