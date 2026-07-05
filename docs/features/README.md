# Features overview

The app is split into two runtime concerns: an **ingest pipeline** (`main.py`) that turns raw bank CSVs into a clean master file, and a **Dash dashboard** (`app.py`) that reads that file and presents an interactive spending dashboard. Running `main.py` triggers both in sequence.

**Dev workflow (Docker with hot-reload):**
```cmd
docker run -p 8050:8050 -v "%cd%:/app" personal-finance
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
  │  deduplicate
  │  merge into master, preserving existing master_category values
       │
       ▼
  SORTED/edited_combined_transactions.csv  (the master file)
       │
       ▼
  app.py  ────────────────────────────────────────────────────────────────
  │  setup overlay  ← auto-ingests Test Data/ on first launch;
  │                    reopen anytime via CHANGE DATA FOLDER
  │  Modules/transforms.py  ← all aggregation / filtering helpers
  │  rules.csv              ← keyword auto-categorization rules
  │
  └─ Single-page dashboard
       ├─ Graph card  (net · trends · categories dropdown; 1M/YTD/1Y/3Y range chips; source)
       │    ├─ Net view  (per-period net bars, daily on 1M)
       │    ├─ Trends  (same-month year-over-year, all years — ignores range chips)
       │    └─ Categories  (share-of-spend lines over time; snapshot bars on 1M; drilldown)
       ├─ Performance card  (expenses / income / net / savings rate + deltas)
       └─ Import / export card  (CSV labeling round-trip + unlabeled-rows note)
```

---

## Feature docs

| Document | What it covers |
|----------|---------------|
| [ingest-pipeline.md](ingest-pipeline.md) | `main.py`: data directory config, format detection, normalisation, date-coverage merge, master-file rebuild |
| [setup-screen.md](setup-screen.md) | Setup overlay: first-launch auto-ingest, Change Data Folder / Browse / Save & Launch / Cancel |
| [transforms.md](transforms.md) | `Modules/transforms.py`: load_transactions, auto-categorization, aggregation helpers |
| [overview-charts.md](overview-charts.md) | Range chips, chart selector, net view, year-over-year trends, performance card |
| [category-breakdown.md](category-breakdown.md) | Categories chart (share lines / snapshot bars), click-to-drilldown |
| [import-export.md](import-export.md) | Import/export card: CSV labeling workflow, category system, transfers |
