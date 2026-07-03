# Personal Finance Dashboard

A local Plotly Dash app for tracking personal spending across Chase and Discover accounts. Raw CSV exports from your bank become a unified, category-tagged transaction ledger. A browser dashboard lets you explore spending by month, year, and category.

---

## Project layout

```
.
├── main.py                  # Ingest pipeline → launches dashboard
├── app.py                   # Dash dashboard (layout + all callbacks)
├── rules.csv                # Keyword → category auto-tagging rules
├── Modules/
│   └── transforms.py        # Data helpers (load, filter, aggregate)
├── Data/
│   ├── RAW/                 # Drop your bank CSVs here (git-ignored)
│   └── SORTED/
│       ├── combined_transactions.csv          # Pipeline output (git-ignored)
│       └── edited_combined_transactions.csv   # Master file with categories (git-ignored)
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
- Bank CSV exports placed in `Data/RAW/`
  Supported formats: Chase Debit, Chase Credit, Discover Credit

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

## Running

One command starts everything — the ingest pipeline runs first, then the dashboard launches automatically:

```bash
# Windows
.venv\Scripts\python main.py

# Linux / macOS / Docker entrypoint
python main.py
```

Open `http://localhost:8050` in a browser. To stop: `Ctrl+C`.

The ingest step reads every CSV in `Data/RAW/`, normalises each file to a unified schema, deduplicates rows, and merges into `edited_combined_transactions.csv` — preserving any category assignments already present. New transactions are appended; existing ones are untouched.

---

## UI tour

The dashboard has two tabs selectable from the top nav bar.

### Filter bar (both tabs)

A persistent bar at the top of every page. All controls here apply to both the Summary charts and the All Transactions table simultaneously.

| Control | What it does |
|---------|-------------|
| SOURCE | Filter to one bank account or all |
| YEAR | Filter to a specific year or all |
| MONTH | Filter to a specific month (options update based on Source + Year) |
| SHOW ON CHARTS | Toggle expenses and/or income bars on the main chart |
| VIEW | Switch between MONTH BY MONTH and ALL YEARS chart modes |
| Uncategorized badge | Shows count of transactions with no master category assigned |
| RELOAD DATA | Re-runs the ingest pipeline without leaving the browser |

### Summary tab

| Area | What it shows |
|------|---------------|
| Stat cards | Total expenses, total income, average spend — each shows a MoM or YoY delta when a specific month or year is filtered |
| Main chart | Monthly or yearly expense/income bars; monthly view adds a 3-month rolling-average overlay on expenses |
| Net chart | Income minus expenses per period; green bars = positive net, red = negative |
| Category breakdown | Horizontal bar chart of spend by category; click any bar to expand a transaction drilldown beneath it |

> **Note:** Rows tagged `Transfer` in the **Type of Transaction** field are automatically excluded from all income and expense calculations. Use the Excel import workflow to tag transfers, brokerage moves, and credit card payments as `Transfer` so they don't distort your totals.

### All Transactions tab

Displays every transaction in the active filter scope as a pageable, sortable table. Columns shown:

| Column | Source |
|--------|--------|
| DATE | Transaction date |
| DESCRIPTION | Merchant / memo text |
| AMOUNT | Signed dollar amount |
| SOURCE | Bank account (Chase Debit / Chase Credit / Discover Credit) |
| CARD | Last 4 digits of the card (Chase only; extracted from filename) |
| TYPE OF TRANSACTION | User-assigned: `Expense`, `Income`, or `Transfer` |
| CATEGORY | Sub-category if set, otherwise the bank-provided original category |

Use **EXPORT CSV** to download for bulk editing in Excel, then **IMPORT CSV** to write `master_category` and `sub_category` assignments back. The table and Summary charts always reflect the same filter state.

### Theme

A floating button in the bottom-right corner toggles between dark and light themes. The choice persists in your browser's local storage.

---

## Category system

Each transaction has three category fields:

| Field | Who sets it | Purpose |
|-------|------------|---------|
| `original_category` | Bank (import) | Raw label from the bank CSV |
| `master_category` | You (via Excel import) | High-level type: `Expense`, `Income`, or `Transfer` |
| `sub_category` | You (optional, via Excel import) | Detail label within the type (e.g. "Rent", "Paycheck", "Fidelity") |

The dashboard displays a single **CATEGORY** column: `sub_category` if set, otherwise `original_category`.

Rows tagged `Transfer` are silently excluded from all income and expense totals — they represent money moving between accounts, not actual spending or earning.

---

## Bulk category workflow

1. Click **EXPORT CSV** on the All Transactions tab
2. Open in Excel — fill `master_category` (`Expense`, `Income`, or `Transfer`) and optionally `sub_category` for each row
3. Save and click **IMPORT CSV** — the app matches rows by description + amount + source + date and writes the values back to the master file

---

## Auto-categorization

`rules.csv` maps keyword substrings to categories. On each data load, any transaction with no `master_category` whose description contains a matching keyword is automatically assigned the corresponding `effective_category`. The first matching rule wins; `master_category` always takes priority over rules.

Edit `rules.csv` directly to add, remove, or adjust rules — no code change needed.

---

## Data files

`Data/RAW/` and `Data/SORTED/` are git-ignored. The `.gitkeep` files preserve the empty directories in the repository. Do not commit your transaction CSVs.

---

## Further reading

- [Feature overview](docs/features/README.md)
- [Ingest pipeline](docs/features/ingest-pipeline.md)
- [Data transforms layer](docs/features/transforms.md)
- [Global filters](docs/features/global-filters.md)
- [Overview charts](docs/features/overview-charts.md)
- [Category breakdown & drilldown](docs/features/category-breakdown.md)
- [All Transactions tab](docs/features/all-transactions.md)
