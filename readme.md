# Personal Finance Dashboard

A local Plotly Dash app for tracking personal spending across Chase and Discover accounts. Raw CSV exports from your bank become a unified, category-tagged transaction ledger. A browser dashboard answers two questions — **am I on track?** and **where did the money go?** — for any week, month, or year: one sentence on how your spending compares with a typical period, what you spent and earned, and which categories and merchants it went to. Everything runs on your machine; no bank logins.

---

## Project layout

```
.
├── main.py                  # Ingest pipeline → launches dashboard
├── app.py                   # Dash dashboard (layout + all callbacks)
├── config.py                # Data directory resolution (env var > config.json > Test Data/)
├── config.json              # Your saved data folder path — git-ignored, created on first save
├── Modules/
│   ├── transforms.py        # Data helpers (load, label, period maths, aggregate)
│   ├── safety.py            # Backups + atomic writes for the master (your labels)
│   └── labels.py            # Merchant groups, label writes, imported-CSV matcher
├── Test Data/               # Made-up demo data (make_demo_data.py) — works out of the box
│   ├── RAW/                 # Demo bank CSVs, one subfolder per institution (tracked in git)
│   └── SORTED/              # Pipeline output — regenerated on first run (git-ignored), plus made-up demo merchant files (tracked)
├── assets/
│   ├── app.css              # All styles — theme tokens only, generated from _CHART in app.py
│   └── theme_sync.js        # Mirrors the theme class onto <body> for dropdown popups
├── tests/                   # pytest: period maths + an end-to-end run on Test Data
├── docs/
│   └── adr/                 # Architecture decision records
├── CLAUDE.md                # Notes for Claude Code (area rules in .claude/rules/)
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt     # + pytest
```

---

## Prerequisites

- Python 3.12+
- Supported bank CSV formats: Chase Debit, Chase Credit, Discover Credit, and Capital One's exports of the Discover card (in any folder — e.g. `RAW/CapitalOne/` — they're read as the Discover account)

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

On first launch the app resolves a data directory (see priority below) and automatically runs the ingest pipeline against it if it hasn't been ingested yet — so the included `Test Data/` folder, with its made-up demo transactions, populates and displays immediately. No setup required — just run and open the browser.

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

The ingest step reads every CSV in the configured `RAW/` folder, normalises each file to a unified schema, merges overlapping exports of the same account by date coverage, and **rebuilds** `edited_combined_transactions.csv` from scratch — carrying forward the `master_category` / `sub_category` labels you've already assigned. Labels follow their transaction first by an exact key, then by date, description, amount and source. Any label that can't be placed is kept in `SORTED/orphaned_labels.csv` and flagged in the header (see [ADR 0002](docs/adr/0002-rebuild-master-from-raw.md)). Every rebuild and import first copies your master to `SORTED/backups/` (newest 10 kept).

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover the week / month / year maths and run the full ingest on a temporary copy of `Test Data/` — they never write into the repo. GitHub Actions runs them on every pull request and every push to `main`, on Linux and Windows (`.github/workflows/tests.yml`).

---

## UI tour

One page, driven by one control. The header shows how recent your data is (`Data through Dec 26, 2025`) and, only when something needs you, one red line: unlabeled rows and their dollars (**LABEL →**), new rows from the last import that still need a label (**REVIEW →**), likely transfers counted as spending (**CHECK →**), data over two weeks old, an account lagging behind, and RAW files that couldn't be imported. The settings gear (top right) holds **DATA** (**IMPORT CSV** / **EXPORT CSV** for labeling, **RELOAD DATA** to re-run the ingest), **SOURCE** (**CHANGE DATA FOLDER**), and **THEME**.

### Pick a period

The period bar under the header — **WEEK | MONTH | YEAR** and a **‹ period ›** stepper — chooses what everything below it shows. Weeks run Monday to Sunday. It opens on the period containing your **newest transaction** (not today's date, so stale exports never show an empty page), and **LATEST** jumps back there. Switching between week, month, and year keeps your place, and the bar stays pinned while you scroll.

### The cards

| Card | What it shows |
|------|---------------|
| HEADLINE | One sentence: the period's spending against your **typical** period (median of the last 12 weeks/months, or of earlier years) — `$782 over your typical pace`, `$198 under a typical month`, `In line with a typical week`. While a period is in progress it compares against the same number of days of earlier periods. It says **Can't say yet** (and why) when your newest data is over two weeks old or over 10% of the period's money out is unlabeled |
| STAT CARDS | Spent, income, and net for the period, with `+ $X unreviewed` for unlabeled money |
| SPENDING OVER TIME | A bar per week (last 26), month (last 24), or year (all), with a dashed median line; the selected period is drawn in full ink and an in-progress one striped. The line under the chart says what the dashed line and the striped bar are. **Click a bar to open that period.** The title dropdown switches Expenses / Income / Net Cash Flow |
| SPEND BY CATEGORY | Sorted bars for the selected period — top 9 categories + Other, with `$ · %`. Click a bar, or choose it in **Pick a category**, for its top merchants and largest transaction (click again to close) |
| MORE → RECURRING CHARGES | (folded) Subscriptions, rent, utilities — merchants charging a steady amount monthly, quarterly or yearly (3+ times), with the latest charge and its cost per year. Stopped ones fold away under *Stopped* |

> **Note:** All totals are label-based — a row only counts as an expense or income if its **Type of Transaction** field is `Expense` or `Income`. Rows tagged `Transfer` and rows with no label are excluded from every calculation; the header shows how many unlabeled rows (and dollars) are being left out. Label transactions in the labeling panel or with the Excel workflow, and tag transfers, brokerage moves, and credit card payments as `Transfer` so they don't distort your totals. Weekly tracking needs this most: new transactions arrive unlabeled unless their merchant has a rule.

### Label transactions

**LABEL THEM →** (or **REVIEW →**, for just the last import's rows) opens a full-screen labeling panel. Unlabeled transactions are grouped by merchant, all of a merchant's spellings together, biggest dollars first (the top 25 are shown). Each group has **EXPENSE / INCOME / TRANSFER** buttons that label every row in it at once, an optional subcategory, and a **Remember for future statements** checkbox that saves the label as that merchant's rule, ticked by default only when the merchant has charged in at least 3 different months. A group that looks like a card payment gets a starred *suggested* `★ TRANSFER` button. The **TRANSFER PAIRS** tab finds the same amount leaving one of your accounts and arriving in another within 5 days (a card payment, a move to savings) and labels both sides Transfer in one click; pairs already labeled Expense or Income are flagged in the attention line (**CHECK →**) so a card payment isn't counted twice. Groups with money both in and out (a **MIXED** badge) are labeled row by row, and rows with no recognizable name sit in their own **NO MERCHANT NAME** section. The **ALL MERCHANTS** tab lists every merchant over all time, with its rule, the labels its rows carry, its spellings and its money, sorted **BY SPEND** or by what **NEEDS ATTENTION**. Under **Change this merchant** you can rename it, merge it into another merchant, split a spelling out or move one spelling to another merchant, relabel every row of it (fixing a past call: its hand labels that still show the old label, and its rule), and give it **patterns**: a new spelling containing one is offered as "Same as …?" on its card, joined only when you say YES. Each change shows which rows would change label before you **CONFIRM**, and **UNDO** takes it back. If you still have `rules.csv` keywords, the header offers **CONVERT →**: each keyword becomes a merchant you can review first (rename it, change its label, untick a spelling or split one out into its own merchant), every label a keyword gave a past row is stored on that row, so no total moves unless you change it in the review, `rules.csv` is kept as a dated backup, and UNDO takes it all back (to see the result first, run `python convert_check.py`: it converts a temp copy and lists any row whose label would change); the settings menu's **LABELS & MERCHANTS** opens it even when nothing is left to label. A collapsible guide explains how to choose a label; **UNDO** reverts the last click; **DONE** refreshes the dashboard. The first time the panel opens each day, it saves `SORTED/backups/before-labeling-YYYY-MM-DD.csv` so you can get back to where you started. The stat cards show what is still unlabeled as `+ $X unreviewed`. Why it works this way: [ADR 0025](docs/adr/0025-merchants-own-rules-and-labeling.md) and [ADR 0017](docs/adr/0017-transfer-pairs-only-when-certain.md).

### Ask the chat

**CHAT** (top right) opens a panel beside the page. You can ask about the period you've picked, for example "where did the grocery money go?", "who were my top merchants?" or "how much did I get through Zelle?". A local model answers. While the model isn't running, the panel says how to start it and SEND is off. It only chooses between two pre-written lookups (by category, by merchant), and every number in its answer comes from them. Under each answer you'll see the dates it covers and any unreviewed money left out. An amount that didn't come from a lookup is marked **⚠ Not from a tool**. When an answer is about one spending category, the page selects that bar and opens its drilldown. Nothing is saved, and reloading the page clears the chat. The chat can't change your data. Why it works this way: [ADR 0021](docs/adr/0021-ai-chat-uses-pre-written-tools.md).

The chat needs `llama-server` running on this computer:

1. Install llama.cpp once: `winget install ggml.llamacpp`.
2. Get a GGUF chat model. It's built and tested with Qwen3.5-9B (`Qwen3.5-9B-Q8_0.gguf`, about 9 GB, fits a 16 GB GPU).
3. In its own terminal, run `powershell -ExecutionPolicy Bypass -File start_llm.ps1`. Pass `-Model <path>` or set `FINANCE_LLM_MODEL` if the model isn't at `Documents\GGUF Models\Qwen3.5-9B-Q8_0.gguf`.

Without the server, the panel says so in one line, and everything else on the page works as before. To use a server at another address, set `FINANCE_LLM_URL`; the default is `http://127.0.0.1:8080`. To check the model's tool choices after changing the model or the prompt, run `.venv\Scripts\python ai_eval.py`. It asks 20 questions about the demo data and reports how many passed.

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

## Merchants and their rules

A **merchant** is one place you spend, however the bank spells it (`AMZN MKTP` and `AMAZON.COM` can be one merchant). Its **rule** is the label it gives its rows: on each data load, every row of the merchant with no label of its own gets the rule's label, so freshly imported statements count in the totals at once. A hand label always wins, and a rule's subcategory only fills a blank one. Rules are applied in memory, never written to the master, so changing a merchant's rule relabels its history; every change shows which rows would move before you confirm it, and UNDO takes it back.

Merchants live in two files in your data folder, `SORTED/merchants.csv` (each merchant, its rule and its patterns) and `SORTED/merchant_aliases.csv` (which spellings belong to which merchant). They name the places you spend, so they live with your data and never in the repo ([ADR 0024](docs/adr/0024-no-real-data-in-the-repo.md)); the demo's in `Test Data/SORTED/` are made up. Manage them in the labeling panel (**Remember for future statements**, **ALL MERCHANTS**) rather than by hand: the app writes both together and reports a problem if they disagree.

Older versions kept keyword rules in `SORTED/rules.csv`. While that file exists its keywords still apply, after the merchants' rules, and the header offers **CONVERT →** to turn them into merchants; past labels stay as they are ([ADR 0026](docs/adr/0026-conversion-stores-the-past.md)).

---

## Data files

`Test Data/RAW/` contains made-up demo CSVs, written by `make_demo_data.py` (seeded, so a rerun gives the same files), and is tracked in git. `Test Data/SORTED/` (pipeline output) is git-ignored and regenerated on each run.

If you point the app at your own data directory, that folder is entirely outside the repository — your real transaction CSVs are never committed. `config.json` (which stores the path to your folder) is also git-ignored. As a fallback, a `Data/` folder at the project root (the old default before configurable data directories existed) is also git-ignored, in case one still exists from before this feature was added.

---

## Roadmap

- **Local AI chat** (built, see *Ask the chat*): spec in [docs/specs/ai-chat.md](docs/specs/ai-chat.md).
- **Recommendations from a cited knowledge base** (after the chat): see the same spec.
- **Model runs inside the app** (later, not now): the first version talks to a `llama-server` you start yourself. Later the app should run the model itself, with no manual server, and offer a setting to connect your own model instead.

---

## Further reading

- [Architecture decision records](docs/adr/): the load-bearing choices and why. They are indexed in [CLAUDE.md](CLAUDE.md#adrs).
- [CLAUDE.md](CLAUDE.md): commands, conventions and project-wide gotchas.
- [`.claude/rules/`](.claude/rules/): per-area pitfalls and invariants (ingest, transforms, labeling, dashboard UI).
