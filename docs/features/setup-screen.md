---
type: Feature Doc
title: Setup screen
description: First-launch data-directory setup overlay and automatic ingest.
resource: app.py, config.py
updated: 2026-07-06
---

# Setup screen

A full-screen overlay in `app.py` for choosing which folder the dashboard reads its data from. It auto-fills with the built-in `Test Data/` on first launch, and can be reopened at any time to point the app at a different folder.

---

## Controls

| Control | ID | Notes |
|---------|----|-------|
| Change Data Folder (nav button) | `open-setup-btn` | Reopens the overlay, prefilled with the currently configured directory |
| Path input | `setup-path-input` | Free-text folder path; also filled by Browse |
| Browse | `setup-browse-btn` | Opens a native OS folder picker (`_pick_folder()`) and writes the result into the path input |
| Save & Launch | `setup-save-btn` | Validates the path, ingests it if needed, and switches the dashboard to it |
| Cancel | `setup-cancel-btn` | Closes the overlay without changing anything |

---

## First-launch auto-ingest

At module load, `app.py` resolves a data directory via `config.get_data_dir()` and derives the master file path via `config.get_master_path()` (see [ingest-pipeline.md](ingest-pipeline.md#data-directory)). If that directory doesn't have a master file yet, the ingest pipeline is run automatically before the layout renders, via the shared `_run_ingest_pipeline()` helper:

```python
def _run_ingest_pipeline(data_dir: Path | None = None) -> None:
    from main import main as run_ingest
    run_ingest(data_dir)


MASTER_PATH = get_master_path(get_data_dir())

if MASTER_PATH and not MASTER_PATH.exists():
    try:
        _run_ingest_pipeline()
    except Exception as e:
        print(f"Warning: auto-ingest at startup failed: {e}")
```

This is what makes the bundled `Test Data/` populate and display immediately on a fresh checkout — no manual setup step required. If ingest fails or produces nothing (e.g. an empty `RAW/` folder, or no data directory resolved at all), the failure is printed to the console, `MASTER_PATH` still won't exist, and the overlay is shown blocking the dashboard, same as before.

`_run_ingest_pipeline()` is also used by `reload_data` and `save_setup` below, so there's a single place that imports and calls `main.main()`.

---

## Reopening the overlay

The **CHANGE DATA FOLDER** nav button (`open-setup-btn`) shows the overlay on demand, independent of whether data is currently loaded. It prefills the path input with the directory backing the currently loaded `MASTER_PATH`, so switching folders starts from your current location rather than a blank field.

---

## Native folder picker (`_pick_folder`)

| Platform | Method |
|----------|--------|
| Windows | PowerShell `System.Windows.Forms.FolderBrowserDialog`, invoked via `subprocess` |
| macOS / Linux | `tkinter.filedialog.askdirectory` |

Returns `""` on cancel or failure, in which case the path input is left unchanged (`dash.no_update`).

---

## Save & Launch (`save_setup`)

```
1. Reject empty path
2. Reject path that doesn't exist on disk
3. If <path>/SORTED/edited_combined_transactions.csv doesn't exist yet,
   run _run_ingest_pipeline(data_dir) — passing the picked folder explicitly
4. save_data_dir(path) → writes config.json
5. Reload df from the new MASTER_PATH
6. Hide the overlay
```

**Why the picked folder is passed explicitly (step 3):** `main.main()` normally resolves its own data directory via `config.get_data_dir()`. If ingest were triggered before `save_data_dir()` (step 4) without passing `data_dir` in, it would silently ingest whatever directory was *previously* configured instead of the one just picked — new, never-before-ingested folders would then fail with "Ingest ran but master file was not created," with no way to complete setup. Passing `data_dir` into `main(data_dir)` directly avoids depending on `config.json` being written first.

Any failure at steps 2–5 shows an inline error in `setup-status` and leaves the overlay open — the dashboard keeps showing whatever data was loaded before.

---

## Cancel (`cancel_setup`)

Simply hides the overlay and clears `setup-status`. Does not touch `df`, `MASTER_PATH`, or `config.json` — whatever was loaded before stays loaded. This is the escape hatch if you open the overlay (via the nav button) and can't find or don't want to change the directory.

---

## Dash wiring note

`setup-overlay.style` and `setup-status.children` are each written by three separate callbacks (`open_setup`, `cancel_setup`, `save_setup`), so all three — plus `browse_for_folder` and `open_setup`, which both write `setup-path-input.value` — use `allow_duplicate=True`.
