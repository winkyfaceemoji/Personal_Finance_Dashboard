# Features overview

The app is split into two runtime concerns: an **ingest pipeline** (`main.py`) that turns raw bank CSVs into a clean master file, and a **Dash dashboard** (`app.py`) that reads that file and presents an interactive spending dashboard. Running `main.py` triggers both in sequence.

**Dev workflow (Docker with hot-reload):**
```cmd
docker run -p 127.0.0.1:8050:8050 -v "%cd%:/app" personal-finance
```
Save any `.py` file → Dash reloads automatically. Rebuild the image only when `requirements.txt` changes.

```
config.py  ─────────────────────────────────────────────────────────────
│  resolve data directory: FINANCE_DATA_DIR env var
│                        → config.json (saved via setup screen)
│                        → Test Data/ (built-in demo, default)
       │
       ▼
Bank CSVs (RAW/)
       │
       ▼
  main.py  ──────────────────────────────────────────────────────────────
  │  detect format (Chase Debit / Chase Credit / Discover Credit)
  │  normalise to unified schema
  │  merge overlapping exports by date coverage (per account)
  │  rebuild the master from RAW, carrying forward master_category / sub_category
       │
       ▼
  SORTED/edited_combined_transactions.csv  (the master file)
       │
       ▼
  app.py  ────────────────────────────────────────────────────────────────
  │  setup overlay  ← auto-ingests Test Data/ on first launch;
  │                    reopen anytime via CHANGE DATA FOLDER
  │  Modules/transforms.py  ← totals, period maths (week/month/year), helpers
  │  rules.csv              ← keyword auto-categorization rules
  │
  └─ Single-page dashboard
       ├─ Header  (data freshness, stale-data notice, unlabeled rows + $)
       ├─ Period bar  (WEEK | MONTH | YEAR · ‹ period › · LATEST) — drives everything below
       ├─ Stat cards  (spent / income / net / savings rate vs previous and typical)
       ├─ Pace strip  (spending so far vs typical by now — in-progress periods)
       ├─ Spending over time  (bar per week/month/year; click to open a period)
       ├─ Categories  (sorted bars for the period + click-to-merchants drilldown)
       ├─ Seasonality  (same-month lines per year, selected year highlighted)
       └─ Settings gear  (import/export CSV, reload, change data folder, theme)
```

---

## Feature docs

Each doc declares the source file(s) it documents in its `resource:` frontmatter — the `Resource` column mirrors it, so a code change points straight to the docs that cover it.

| Document | Resource | What it covers |
|----------|----------|---------------|
| [ingest-pipeline.md](ingest-pipeline.md) | `main.py`, `config.py` | Data directory config, format detection, normalisation, date-coverage merge, master-file rebuild |
| [setup-screen.md](setup-screen.md) | `app.py`, `config.py` | Setup overlay: first-launch auto-ingest, Change Data Folder / Browse / Save & Launch / Cancel |
| [transforms.md](transforms.md) | `Modules/transforms.py` | load_transactions, auto-labeling rules, period maths, aggregation helpers |
| [overview-charts.md](overview-charts.md) | `app.py`, `Modules/transforms.py` | Period bar, stat cards, pace strip, spending-over-time and seasonality charts, header |
| [category-breakdown.md](category-breakdown.md) | `app.py` | Category bars for the selected period, click-to-merchants drilldown |
| [import-export.md](import-export.md) | `app.py`, `Modules/transforms.py` | Import/export in the settings menu: CSV labeling workflow, category system, transfers |
