import base64
import re

import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State, Patch
import plotly.graph_objects as go

from config import get_data_dir, get_master_path, save_data_dir
from Modules.transforms import (
    load_transactions,
    monthly_expenses,
    monthly_income,
    expenses_by_category,
    get_uncategorized,
    available_categories,
    available_years,
    PREDEFINED_CATEGORIES,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
RULES_PATH  = BASE_DIR / "rules.csv"

# ── Settings gear icon (Feather "settings" glyph, painted via CSS mask so it
# picks up the button's currentColor across themes) ───────────────────────────
_GEAR_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
    "stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
    "<circle cx='12' cy='12' r='3'></circle>"
    "<path d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 "
    "1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 "
    "1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 "
    "4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 "
    "0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83"
    "l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'>"
    "</path></svg>"
)
GEAR_ICON_URI = "data:image/svg+xml;base64," + base64.b64encode(_GEAR_SVG.encode()).decode()


def _run_ingest_pipeline(data_dir: Path | None = None) -> None:
    from main import main as run_ingest
    run_ingest(data_dir)


MASTER_PATH = get_master_path(get_data_dir())

# First launch: if a data directory resolved (e.g. the default Test Data/) but
# hasn't been ingested yet, run the pipeline so its data shows immediately.
if MASTER_PATH and not MASTER_PATH.exists():
    try:
        _run_ingest_pipeline()
    except Exception as e:
        print(f"Warning: auto-ingest at startup failed: {e}")

# ── Load data ─────────────────────────────────────────────────────────────────
_EMPTY_DF = pd.DataFrame(columns=[
    "date", "post_date", "amount", "description", "source", "master_category",
    "sub_category", "original_category", "card_last4",
    "effective_category", "category_display", "month", "month_str", "year",
])
df = load_transactions(MASTER_PATH, rules_path=RULES_PATH) if (MASTER_PATH and MASTER_PATH.exists()) else _EMPTY_DF

# ── Colour palette ────────────────────────────────────────────────────────────
# HTML/Dash elements use CSS custom properties so they respond to theme changes.
COLORS = {
    "bg":      "var(--bg)",
    "surface": "var(--surface)",
    "border":  "var(--border)",
    "accent":  "var(--accent)",
    "accent2": "var(--accent2)",
    "accent3": "var(--accent3)",
    "text":    "var(--text)",
    "subtext": "var(--subtext)",
}

# Plotly figures need real hex values — two sets, one per theme.
_CHART = {
    "dark": {
        "text":   "#ffffff", "border": "#252830", "surface": "#111318", "subtext": "#8a8fa8",
        "accent": "#6c8aff", "accent2": "#ff6c8a", "accent3": "#6cffd4",
    },
    "light": {
        "text":   "#0a0a0f", "border": "#dcdee8", "surface": "#f0f1f5", "subtext": "#5c5f72",
        "accent": "#4a68e8", "accent2": "#d63157", "accent3": "#0a9e72",
    },
}

def chart_template(theme="dark"):
    c = _CHART[theme]
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=c["text"], family="IBM Plex Mono, monospace"),
        xaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"]),
        yaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"]),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=40, r=20, t=40, b=40),
    )

PIE_COLORS = [
    "#6c8aff", "#ff6c8a", "#6cffd4", "#ffd46c",
    "#c46cff", "#ff9f6c", "#6cd4ff", "#ff6ccc",
    "#a8ff6c", "#6c6cff", "#ff6c6c", "#6cffb4",
]

# Categories beyond this rank collapse into the pie's grey "Other" slice;
# the drilldown reuses it to reconstruct what that slice aggregates.
CAT_PIE_TOP_N = 9


# ── Helper: card wrapper ───────────────────────────────────────────────────────
def card(children, style=None):
    base = {"borderRadius": "12px", "padding": "24px", "marginBottom": "24px"}
    if style:
        base.update(style)
    return html.Div(children, className="app-card", style=base)


def section_title(text):
    return html.P(text, className="app-label", style={
        "fontSize": "11px", "letterSpacing": "2px", "marginBottom": "16px",
    })


# ── App ────────────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title="Finance Dashboard",
    suppress_callback_exceptions=True,
)

app.index_string = ('''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { margin: 0; padding: 0; font-family: "IBM Plex Mono", monospace; }
        ::-webkit-scrollbar { width: 6px; }

        /* ── DARK THEME ─────────────────────────────────────────────────── */
        /* Override Dash 4 CSS variables (defined on :root in Dash bundle) */
        .dark-theme {
            background: #0a0a0f !important;
            color: #ffffff !important;
            --Dash-Fill-Inverse-Strong: #111318;
            --Dash-Stroke-Strong: #252830;
            --Dash-Stroke-Weak: rgba(255,255,255,0.05);
            --Dash-Text-Primary: #ffffff;
            --Dash-Text-Strong: #ffffff;
            --Dash-Text-Weak: #c8cadb;
            --Dash-Text-Disabled: #8a8fa8;
            --Dash-Fill-Interactive-Strong: #6c8aff;
            --Dash-Fill-Interactive-Weak: rgba(108,138,255,0.15);
            --Dash-Fill-Primary-Hover: #252830;
            --Dash-Fill-Primary-Active: #2a2e3a;
            --Dash-Fill-Disabled: #252830;
            --Dash-Shading-Strong: rgba(0,0,0,0.5);
            --Dash-Shading-Weak: rgba(0,0,0,0.3);
        }
        .dark-theme ::-webkit-scrollbar-track { background: #0a0a0f; }
        .dark-theme ::-webkit-scrollbar-thumb { background: #252830; border-radius: 3px; }
        .dark-theme .app-card {
            background: #111318 !important;
            border: 1px solid #252830 !important;
            color: #ffffff !important;
        }
        .dark-theme .app-card * { color: #ffffff !important; }
        /* Dash 4 dropdown classes */
        .dark-theme .dash-dropdown { background-color: #111318 !important; border-color: #252830 !important; color: #ffffff !important; }
        .dark-theme .dash-dropdown-content { background-color: #111318 !important; border-color: #252830 !important; color: #ffffff !important; }
        .dark-theme .dash-dropdown-option { color: #ffffff !important; }
        .dark-theme .dash-dropdown-option:hover,
        .dark-theme .dash-dropdown-option:focus { background-color: #252830 !important; }
        .dark-theme .dash-dropdown-placeholder { color: #8a8fa8 !important; }
        .dark-theme .dash-dropdown-search { color: #ffffff !important; background: transparent !important; }
        .dark-theme .dash-dropdown-search-container { background-color: #111318 !important; border-color: #252830 !important; }
        .dark-theme .dash-dropdown-clear { color: #8a8fa8 !important; }
        .dark-theme .app-label { color: #e0e2f0 !important; }
        .dark-theme .tab-container .tab {
            background: #111318 !important; border: 1px solid #252830 !important;
            border-bottom: none !important; color: #8a8fa8 !important;
        }
        .dark-theme .tab-container .tab--selected {
            background: #0a0a0f !important; color: #6c8aff !important;
            border-bottom: 2px solid #6c8aff !important;
        }
        .dark-theme .tab-container .tab:hover { color: #ffffff !important; }
        .dark-theme #summary-range label, .dark-theme #category-year label,
        .dark-theme #toggle-income-expenses label {
            color: #8a8fa8; background: #0a0a0f; border: 1px solid #252830;
            transition: all 0.15s;
        }
        .dark-theme #summary-range .dash-options-list-option.selected,
        .dark-theme #category-year .dash-options-list-option.selected,
        .dark-theme #toggle-income-expenses .dash-options-list-option.selected {
            color: #ffffff !important; border-color: #6c8aff !important;
            background: rgba(108,138,255,0.18) !important; font-weight: 600 !important;
        }
        .dark-theme .btn-primary { background: #6c8aff; color: #0a0a0f; }
        .dark-theme .btn-secondary { color: #6c8aff; border-color: #6c8aff; }
        .dark-theme #settings-menu-btn { background: #111318; border-color: #252830; color: #ffffff; }

        /* ── LIGHT THEME ────────────────────────────────────────────────── */
        /* Override Dash 4 CSS variables for light theme */
        .light-theme {
            background: #ffffff !important;
            color: #0a0a0f !important;
            --Dash-Fill-Inverse-Strong: #f0f1f5;
            --Dash-Stroke-Strong: #dcdee8;
            --Dash-Stroke-Weak: rgba(0,0,0,0.05);
            --Dash-Text-Primary: #0a0a0f;
            --Dash-Text-Strong: #0a0a0f;
            --Dash-Text-Weak: #5c5f72;
            --Dash-Text-Disabled: #5c5f72;
            --Dash-Fill-Interactive-Strong: #4a68e8;
            --Dash-Fill-Interactive-Weak: rgba(74,104,232,0.1);
            --Dash-Fill-Primary-Hover: #dcdee8;
            --Dash-Fill-Primary-Active: #d0d2e0;
            --Dash-Fill-Disabled: #dcdee8;
            --Dash-Shading-Strong: rgba(0,0,0,0.2);
            --Dash-Shading-Weak: rgba(0,0,0,0.1);
        }
        .light-theme ::-webkit-scrollbar-track { background: #ffffff; }
        .light-theme ::-webkit-scrollbar-thumb { background: #dcdee8; border-radius: 3px; }
        .light-theme .app-card {
            background: #f0f1f5 !important;
            border: 1px solid #dcdee8 !important;
            color: #0a0a0f !important;
        }
        .light-theme .app-card * { color: #0a0a0f !important; }
        .light-theme .app-label { color: #5c5f72 !important; }
        .light-theme .tab-container .tab {
            background: #f0f1f5 !important; border: 1px solid #dcdee8 !important;
            border-bottom: none !important; color: #5c5f72 !important;
        }
        .light-theme .tab-container .tab--selected {
            background: #ffffff !important; color: #4a68e8 !important;
            border-bottom: 2px solid #4a68e8 !important;
        }
        .light-theme .tab-container .tab:hover { color: #0a0a0f !important; }
        /* Dash 4 dropdown classes - light */
        .light-theme .dash-dropdown { background-color: #f0f1f5 !important; border-color: #dcdee8 !important; color: #0a0a0f !important; }
        .light-theme .dash-dropdown-content { background-color: #f0f1f5 !important; border-color: #dcdee8 !important; color: #0a0a0f !important; }
        .light-theme .dash-dropdown-option { color: #0a0a0f !important; }
        .light-theme .dash-dropdown-option:hover,
        .light-theme .dash-dropdown-option:focus { background-color: #dcdee8 !important; }
        .light-theme .dash-dropdown-placeholder { color: #5c5f72 !important; }
        .light-theme .dash-dropdown-search { color: #0a0a0f !important; background: transparent !important; }
        .light-theme .dash-dropdown-search-container { background-color: #f0f1f5 !important; border-color: #dcdee8 !important; }
        .light-theme .dash-dropdown-clear { color: #5c5f72 !important; }
        .light-theme #summary-range label, .light-theme #category-year label,
        .light-theme #toggle-income-expenses label {
            color: #5c5f72; background: #ffffff; border: 1px solid #dcdee8;
            transition: all 0.15s;
        }
        .light-theme #summary-range .dash-options-list-option.selected,
        .light-theme #category-year .dash-options-list-option.selected,
        .light-theme #toggle-income-expenses .dash-options-list-option.selected {
            color: #0a0a0f !important; border-color: #4a68e8 !important;
            background: rgba(74,104,232,0.12) !important; font-weight: 600 !important;
        }
        .light-theme .btn-primary { background: #4a68e8; color: #ffffff; }
        .light-theme .btn-secondary { color: #4a68e8; border-color: #4a68e8; }
        .light-theme #settings-menu-btn { background: #f0f1f5; border-color: #dcdee8; color: #0a0a0f; }

        /* ── Portal-level theming (dash-dropdown-content renders in body) ── */
        body.dark-theme {
            --Dash-Fill-Inverse-Strong: #111318;
            --Dash-Stroke-Strong: #252830;
            --Dash-Stroke-Weak: rgba(255,255,255,0.05);
            --Dash-Text-Primary: #ffffff;
            --Dash-Text-Strong: #ffffff;
            --Dash-Text-Weak: #c8cadb;
            --Dash-Text-Disabled: #8a8fa8;
            --Dash-Fill-Interactive-Strong: #6c8aff;
            --Dash-Fill-Interactive-Weak: rgba(108,138,255,0.15);
            --Dash-Fill-Primary-Hover: #252830;
            --Dash-Fill-Primary-Active: #2a2e3a;
            --Dash-Fill-Disabled: #252830;
            --Dash-Shading-Strong: rgba(0,0,0,0.5);
            --Dash-Shading-Weak: rgba(0,0,0,0.3);
        }
        body.dark-theme .dash-dropdown-content { background-color: #111318 !important; border-color: #252830 !important; color: #ffffff !important; }
        body.dark-theme .dash-dropdown-option { color: #ffffff !important; }
        body.dark-theme .dash-dropdown-option:hover,
        body.dark-theme .dash-dropdown-option:focus { background-color: #252830 !important; }
        body.dark-theme .dash-dropdown-placeholder { color: #8a8fa8 !important; }
        body.dark-theme .dash-dropdown-search { color: #ffffff !important; }
        body.dark-theme .dash-dropdown-search-container { background-color: #111318 !important; border-color: #252830 !important; }

        body.light-theme {
            --Dash-Fill-Inverse-Strong: #f0f1f5;
            --Dash-Stroke-Strong: #dcdee8;
            --Dash-Stroke-Weak: rgba(0,0,0,0.05);
            --Dash-Text-Primary: #0a0a0f;
            --Dash-Text-Strong: #0a0a0f;
            --Dash-Text-Weak: #5c5f72;
            --Dash-Text-Disabled: #5c5f72;
            --Dash-Fill-Interactive-Strong: #4a68e8;
            --Dash-Fill-Interactive-Weak: rgba(74,104,232,0.1);
            --Dash-Fill-Primary-Hover: #dcdee8;
            --Dash-Fill-Primary-Active: #d0d2e0;
            --Dash-Fill-Disabled: #dcdee8;
            --Dash-Shading-Strong: rgba(0,0,0,0.2);
            --Dash-Shading-Weak: rgba(0,0,0,0.1);
        }
        body.light-theme .dash-dropdown-content { background-color: #f0f1f5 !important; border-color: #dcdee8 !important; color: #0a0a0f !important; }
        body.light-theme .dash-dropdown-option { color: #0a0a0f !important; }
        body.light-theme .dash-dropdown-option:hover,
        body.light-theme .dash-dropdown-option:focus { background-color: #dcdee8 !important; }

        /* ── Shared ─────────────────────────────────────────────────────── */
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td,
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th {
            font-family: "IBM Plex Mono", monospace !important; font-size: 12px !important;
        }
        .btn-primary {
            border: none; border-radius: 6px; padding: 10px 20px;
            font-family: "IBM Plex Mono", monospace; font-size: 12px;
            font-weight: 600; letter-spacing: 1px; cursor: pointer;
        }
        .btn-primary:hover { opacity: 0.85; }
        .btn-secondary {
            background: transparent; border-radius: 6px; padding: 10px 20px;
            font-family: "IBM Plex Mono", monospace; font-size: 12px;
            font-weight: 600; letter-spacing: 1px; cursor: pointer;
        }
        .btn-secondary:hover { opacity: 0.85; }
        .btn-secondary:disabled { opacity: 0.35; cursor: default; }
        /* Settings panel: section labels, muted button, active-theme highlight,
           status line. Declared after the .app-card * rules so the !important
           colors here win the source-order tie. */
        .dark-theme .settings-label { color: #8a8fa8 !important; }
        .light-theme .settings-label { color: #5c5f72 !important; }
        .dark-theme .settings-status { color: #6cffd4 !important; }
        .light-theme .settings-status { color: #0a9e72 !important; }
        .dark-theme .warn-text { color: #ff6c8a !important; }
        .light-theme .warn-text { color: #d63157 !important; }
        .dark-theme .muted-text { color: #8a8fa8 !important; }
        .light-theme .muted-text { color: #5c5f72 !important; }
        /* Fullscreen reload/import overlay — dcc.Loading hardcodes a white
           backdrop; theme it so it matches the page instead of flashing white */
        .dark-theme .dash-spinner-container { background-color: rgba(10,10,15,0.9) !important; }
        .light-theme .dash-spinner-container { background-color: rgba(255,255,255,0.9) !important; }
        #settings-menu-wrapper { position: absolute; top: 0; right: 0; z-index: 9999; }
        #settings-menu-btn {
            width: 44px; height: 44px; border-radius: 50%;
            cursor: pointer; z-index: 9999;
            box-shadow: 0 4px 16px rgba(0,0,0,0.25); transition: all 0.2s;
            display: flex; align-items: center; justify-content: center;
            line-height: 1; padding: 0;
        }
        #settings-menu-btn:hover { transform: scale(1.1); }
        #settings-menu-btn .gear-icon {
            width: 20px; height: 20px; display: inline-block;
            background-color: currentColor;
            -webkit-mask: url("__GEAR_ICON_URI__") center / contain no-repeat;
            mask: url("__GEAR_ICON_URI__") center / contain no-repeat;
        }
        #settings-menu-panel {
            position: absolute; top: 56px; right: 0;
            min-width: 220px; box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''.replace("__GEAR_ICON_URI__", GEAR_ICON_URI))

# ── Layout ────────────────────────────────────────────────────────────────────
_OVERLAY_HIDDEN  = {
    "display": "none", "position": "fixed", "inset": "0", "zIndex": "9999",
    "background": "var(--bg, #111)", "alignItems": "center", "justifyContent": "center",
}
_OVERLAY_VISIBLE = {**_OVERLAY_HIDDEN, "display": "flex"}

app.layout = html.Div(
    id="app-root",
    className="dark-theme",
    style={"minHeight": "100vh", "padding": "32px 40px", "transition": "background 0.2s, color 0.2s"},
    children=[

        # Theme state
        dcc.Store(id="theme-store", data="dark"),
        html.Div(id="theme-dummy", style={"display": "none"}),

        # Data-freshness counter — incremented by any write operation so dependent
        # callbacks (charts, uncategorized badge) re-render automatically.
        dcc.Store(id="refresh-trigger", data=0),

        dcc.Store(id="settings-menu-open", data=False),

        # Clicked pie slice — drives both the pop-out and the drilldown. A Store
        # (not clickData directly) so rebuilding the pie to pop a slice doesn't
        # clear the selection.
        dcc.Store(id="selected-category"),

        # ── Setup overlay (shown when no data directory is configured) ──────
        html.Div(
            id="setup-overlay",
            style=_OVERLAY_HIDDEN if (MASTER_PATH and MASTER_PATH.exists()) else _OVERLAY_VISIBLE,
            children=html.Div(style={
                "background": "var(--card-bg, #1a1a1a)",
                "border": "1px solid var(--border, #333)",
                "borderRadius": "12px", "padding": "48px",
                "width": "480px", "maxWidth": "90vw",
            }, children=[
                html.H1("FINANCE", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "32px",
                    "fontWeight": "800", "letterSpacing": "-1px",
                    "color": "var(--text)", "display": "inline",
                }),
                html.Span(" DASHBOARD", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "32px",
                    "fontWeight": "800", "letterSpacing": "-1px",
                    "color": COLORS["accent"],
                }),
                html.P(
                    "Choose the folder that contains your RAW and SORTED data.",
                    style={"marginTop": "24px", "marginBottom": "16px",
                           "color": "var(--subtext, #888)", "fontSize": "14px"},
                ),
                html.Div(style={"display": "flex", "gap": "8px", "marginBottom": "12px"}, children=[
                    dcc.Input(
                        id="setup-path-input",
                        type="text",
                        placeholder=r"e.g. C:\Users\you\Finance\Data",
                        debounce=False,
                        style={
                            "flex": "1", "padding": "10px 14px",
                            "background": "var(--input-bg, #222)",
                            "border": "1px solid var(--border, #444)",
                            "borderRadius": "6px", "color": "var(--text, #fff)",
                            "fontSize": "13px",
                        },
                    ),
                    html.Button("Browse", id="setup-browse-btn", n_clicks=0, style={
                        "padding": "10px 16px", "background": "var(--card-bg, #1a1a1a)",
                        "border": "1px solid var(--border, #555)",
                        "borderRadius": "6px", "color": "var(--text, #fff)",
                        "cursor": "pointer", "whiteSpace": "nowrap",
                    }),
                ]),
                html.Div(style={"display": "flex", "gap": "8px"}, children=[
                    html.Button("Cancel", id="setup-cancel-btn", n_clicks=0, style={
                        "flex": "1", "padding": "12px",
                        "background": "var(--card-bg, #1a1a1a)",
                        "border": "1px solid var(--border, #555)",
                        "borderRadius": "6px", "color": "var(--text, #fff)",
                        "fontSize": "14px", "fontWeight": "600", "cursor": "pointer",
                    }),
                    html.Button("Save & Launch", id="setup-save-btn", n_clicks=0, style={
                        "flex": "2", "padding": "12px",
                        "background": COLORS["accent"], "border": "none",
                        "borderRadius": "6px", "color": "#fff",
                        "fontSize": "14px", "fontWeight": "700", "cursor": "pointer",
                    }),
                ]),
                html.Div(id="setup-status", style={
                    "marginTop": "12px", "fontSize": "13px",
                    "color": "#e05c5c",
                }),
            ]),
        ),
        # ────────────────────────────────────────────────────────────────────


        # Header: title left; settings gear pinned absolutely to the top-right
        html.Div(style={"position": "relative", "marginBottom": "24px"}, children=[
            # Right padding reserves the gear's corner on narrow windows
            html.Div(style={"paddingRight": "56px"}, children=[
                html.H1("FINANCE", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "48px",
                    "fontWeight": "800", "letterSpacing": "-2px",
                    "color": COLORS["text"], "display": "inline",
                }),
                html.Span(" DASHBOARD", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "48px",
                    "fontWeight": "800", "letterSpacing": "-2px", "color": COLORS["accent"],
                }),
                html.P(html.Span(id="data-updated"),
                       style={"color": COLORS["subtext"], "margin": "8px 0 0", "fontSize": "13px"}),
                # Unlabeled rows are ignored by every Summary total — surface
                # the count on its own line, in red
                html.P(html.Span(id="unlabeled-note", className="warn-text"),
                       style={"margin": "4px 0 0", "fontSize": "13px"}),
            ]),
            # Settings menu — gear button expands/collapses the panel
            html.Div(id="settings-menu-wrapper", children=[
                    html.Button(html.Span(className="gear-icon"), id="settings-menu-btn", n_clicks=0),
                    html.Div(id="settings-menu-panel", className="app-card", style={
                        "display": "none", "flexDirection": "column", "gap": "8px", "padding": "16px",
                    }, children=[
                        html.Div("DATA", className="settings-label",
                                 style={"fontSize": "9px", "letterSpacing": "2px", "fontWeight": "600"}),
                        html.Div(style={"display": "flex", "gap": "8px"}, children=[
                            dcc.Upload(
                                id="import-csv-upload",
                                children=html.Button("IMPORT CSV", className="btn-secondary",
                                                     style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px", "width": "100%"}),
                                accept=".csv",
                                multiple=False,
                                style={"flex": "1"},
                            ),
                            html.Button("EXPORT CSV", id="export-csv-btn", n_clicks=0,
                                        className="btn-secondary",
                                        style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px", "flex": "1"}),
                        ]),
                        dcc.Download(id="export-csv-download"),
                        html.Button("RELOAD DATA", id="reload-data-btn", n_clicks=0,
                                    className="btn-secondary",
                                    style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px"}),
                        html.Div(style={"height": "1px", "background": "var(--Dash-Stroke-Strong)", "margin": "4px 0"}),
                        html.Div("SOURCE", className="settings-label",
                                 style={"fontSize": "9px", "letterSpacing": "2px", "fontWeight": "600"}),
                        html.Button("CHANGE DATA FOLDER", id="open-setup-btn", n_clicks=0,
                                    className="btn-secondary",
                                    style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px"}),
                        html.Div(style={"height": "1px", "background": "var(--Dash-Stroke-Strong)", "margin": "4px 0"}),
                        html.Div("THEME", className="settings-label",
                                 style={"fontSize": "9px", "letterSpacing": "2px", "fontWeight": "600"}),
                        html.Div(style={"display": "flex", "gap": "8px"}, children=[
                            html.Button("LIGHT", id="theme-light-btn", n_clicks=0,
                                        className="btn-secondary",
                                        style={"fontSize": "11px", "padding": "8px 14px", "flex": "1"}),
                            html.Button("DARK", id="theme-dark-btn", n_clicks=0,
                                        className="btn-secondary",
                                        style={"fontSize": "11px", "padding": "8px 14px", "flex": "1"}),
                        ]),
                        # Single status slot at the bottom — reload + import messages
                        # land here. dcc.Loading tracks these spans (the slow
                        # callbacks output to them) and shows a fullscreen spinner
                        # while they run, so it never overlaps the menu buttons.
                        dcc.Loading(
                            id="data-op-loading", type="circle", color="#6c8aff",
                            fullscreen=True,
                            children=[
                                html.Span(id="reload-status", className="settings-status", style={"fontSize": "11px"}),
                                html.Span(id="import-status", className="settings-status", style={"fontSize": "11px"}),
                            ],
                        ),
                    ]),
            ]),
        ]),

        # ── SUMMARY content ───────────────────────────────────────────────────
        html.Div(id="summary-content", style={"paddingTop": "8px"}, children=[

                    # Summary — one YTD stat card per metric, each vs the same
                    # period last year. Cards wrap on narrow widths.
                    html.Div(id="performance-card", style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))",
                        "gap": "16px", "marginBottom": "24px",
                    }),

                    # Cash flow — monthly bars; metric selector by the title, range chips right
                    card([
                        html.Div(style={
                            "display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "12px",
                            "marginBottom": "16px",
                        }, children=[
                            # Metric selector doubles as the card title (left)
                            dcc.Dropdown(
                                id="cashflow-metric",
                                className="title-dropdown",
                                options=[
                                    {"label": "Net Cash Flow", "value": "net"},
                                    {"label": "Expenses",      "value": "expenses"},
                                    {"label": "Income",        "value": "income"},
                                ],
                                value="net",
                                clearable=False,
                                searchable=False,
                                style={"width": "190px"},
                            ),
                            # Right: time-range chips
                            dcc.RadioItems(
                                id="summary-range",
                                options=[
                                    {"label": "YTD", "value": "ytd"},
                                    {"label": "1Y",  "value": "1y"},
                                    {"label": "3Y",  "value": "3y"},
                                ],
                                value="ytd",
                                inline=True,
                                inputStyle={"display": "none"},
                                labelStyle={
                                    "padding": "6px 14px", "whiteSpace": "nowrap",
                                    "borderRadius": "6px", "cursor": "pointer", "fontSize": "12px",
                                    "fontWeight": "600", "letterSpacing": "1px",
                                },
                                style={"display": "flex", "flexWrap": "nowrap", "alignItems": "center", "gap": "6px"},
                            ),
                        ]),
                        dcc.Graph(id="net-position-chart", config={"displayModeBar": False}),
                    ]),

                    # Trends — same-month year-over-year, always all data
                    card([
                        html.Div(style={
                            "display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px",
                            "marginBottom": "16px",
                        }, children=[
                            html.Div(id="overview-chart-title", className="app-label", style={
                                "fontSize": "11px", "letterSpacing": "2px",
                            }),
                            dcc.RadioItems(
                                id="toggle-income-expenses",
                                options=[
                                    {"label": "Expenses", "value": "expenses"},
                                    {"label": "Income",   "value": "income"},
                                ],
                                value="expenses",
                                inline=True,
                                inputStyle={"display": "none"},
                                labelStyle={
                                    "padding": "6px 14px", "whiteSpace": "nowrap",
                                    "borderRadius": "6px", "cursor": "pointer", "fontSize": "12px",
                                    "fontWeight": "600", "letterSpacing": "1px",
                                },
                                style={"display": "flex", "flexWrap": "nowrap", "alignItems": "center", "gap": "6px"},
                            ),
                        ]),
                        dcc.Graph(id="overview-main-chart", config={"displayModeBar": False}),
                    ]),

                    # Categories — pie per year, with click drilldown
                    card([
                        html.Div(style={
                            "display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px",
                            "marginBottom": "16px",
                        }, children=[
                            html.Div([
                                html.Div(id="category-title", className="app-label", style={
                                    "fontSize": "11px", "letterSpacing": "2px",
                                }),
                                html.Div("click a slice to see its top merchants", style={
                                    "fontSize": "10px", "color": COLORS["subtext"], "marginTop": "3px",
                                }),
                            ]),
                            dcc.RadioItems(
                                id="category-year",
                                options=[{"label": str(y), "value": int(y)} for y in available_years(df)],
                                value=int(available_years(df)[-1]) if available_years(df) else None,
                                inline=True,
                                inputStyle={"display": "none"},
                                labelStyle={
                                    "padding": "6px 14px", "whiteSpace": "nowrap",
                                    "borderRadius": "6px", "cursor": "pointer", "fontSize": "12px",
                                    "fontWeight": "600", "letterSpacing": "1px",
                                },
                                style={"display": "flex", "flexWrap": "wrap", "alignItems": "center", "gap": "6px"},
                            ),
                        ]),
                        dcc.Graph(id="category-bar-chart", config={"displayModeBar": False}),
                        html.Div(id="category-drilldown"),
                    ]),

        ]),
    ]
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _range_window(rng: str):
    """Calendar-anchored month windows for the cash-flow range chips.
    Returns (start, end, label) — months as YYYY-MM."""
    now = pd.Timestamp.today().to_period("M")
    end = now.strftime("%Y-%m")
    if rng == "ytd":
        return f"{now.year}-01", end, "YTD"
    if rng == "1y":
        return (now - 11).strftime("%Y-%m"), end, "TRAILING 1Y"
    return (now - 35).strftime("%Y-%m"), end, "TRAILING 3Y"


# ── Callbacks ─────────────────────────────────────────────────────────────────

# ── Theme callbacks ───────────────────────────────────────────────────────────

@app.callback(
    Output("theme-store", "data"),
    Output("app-root",    "className"),
    Input("theme-light-btn", "n_clicks"),
    Input("theme-dark-btn",  "n_clicks"),
    prevent_initial_call=True,
)
def set_theme(_, __):
    from dash import ctx
    new = "light" if ctx.triggered_id == "theme-light-btn" else "dark"
    return new, f"{new}-theme"


# ── Settings menu callback ────────────────────────────────────────────────────

@app.callback(
    Output("settings-menu-open",  "data"),
    Output("settings-menu-panel", "style"),
    Input("settings-menu-btn",    "n_clicks"),
    State("settings-menu-open",   "data"),
    State("settings-menu-panel",  "style"),
    prevent_initial_call=True,
)
def toggle_settings_menu(_, is_open, style):
    new_open = not is_open
    new_style = dict(style)
    new_style["display"] = "flex" if new_open else "none"
    return new_open, new_style


@app.callback(
    Output("overview-main-chart",   "figure"),
    Output("overview-chart-title",  "children"),
    Output("category-bar-chart",    "figure"),
    Output("category-title",        "children"),
    Output("net-position-chart",    "figure"),
    Output("performance-card",      "children"),
    Input("summary-range",          "value"),
    Input("cashflow-metric",        "value"),
    Input("toggle-income-expenses", "value"),
    Input("category-year",          "value"),
    Input("theme-store",            "data"),
    Input("refresh-trigger",        "data"),
    State("selected-category",      "data"),
)
def update_overview(rng, cf_metric, metric, cat_year, theme, _refresh, sel_cat):
    import calendar
    tmpl = chart_template(theme)
    c    = _CHART[theme]

    metric    = metric if metric in ("expenses", "income") else "expenses"
    cf_metric = cf_metric if cf_metric in ("net", "expenses", "income") else "net"
    rng       = rng if rng in ("ytd", "1y", "3y") else "ytd"
    start, end, _ = _range_window(rng)
    data_df = df[(df["month_str"] >= start) & (df["month_str"] <= end)]

    # ── Trends: same-calendar-month year-over-year comparison (all data) ────
    metric_lbl = "EXPENSES" if metric == "expenses" else "INCOME"

    if metric == "expenses":
        series = monthly_expenses(df).rename(columns={"total_expenses": "val"})
    else:
        series = monthly_income(df).rename(columns={"total_income": "val"})
    val_map   = {(int(m[:4]), int(m[5:7])): v for m, v in zip(series["month_str"], series["val"])}
    years_all = sorted({yr for yr, _ in val_map})
    cur_year  = int(end[:4])

    hi_yr  = cur_year if cur_year in years_all else (years_all[-1] if years_all else None)
    x_lbls = [calendar.month_abbr[m_] for m_ in range(1, 13)]
    fig_main = go.Figure()
    for i, yr in enumerate(years_all):
        ys, cds = [], []
        for m_ in range(1, 13):
            v  = val_map.get((yr, m_))
            pv = val_map.get((yr - 1, m_))
            ys.append(v)
            if v is not None and pv:
                d = v - pv
                cds.append(f"{'+' if d >= 0 else '-'}${abs(d):,.0f} "
                           f"({'+' if d >= 0 else '-'}{abs(d / pv * 100):.0f}%) "
                           f"vs {calendar.month_abbr[m_]} {yr - 1}")
            else:
                cds.append("")
        is_hi = yr == hi_yr
        fig_main.add_trace(go.Scatter(
            x=x_lbls, y=ys, name=str(yr),
            mode="lines+markers",
            line=dict(color=PIE_COLORS[i % len(PIE_COLORS)], width=3.5 if is_hi else 1.5),
            marker=dict(size=8 if is_hi else 4),
            opacity=1.0 if is_hi else 0.55,
            customdata=cds,
            hovertemplate=("<b>%{x} " + str(yr) + "</b><br>"
                           + metric_lbl.title() + ": $%{y:,.2f}<br>%{customdata}<extra></extra>"),
        ))
    chart_title = f"{metric_lbl} BY CALENDAR MONTH"
    fig_main.update_layout(**tmpl, height=320)

    # ── Cash flow: monthly bars of the selected metric within the range ─────
    flow = (
        monthly_expenses(data_df).rename(columns={"total_expenses": "exp"})
        .merge(monthly_income(data_df).rename(columns={"total_income": "inc"}),
               on="month_str", how="outer")
        .fillna(0).sort_values("month_str")
    )
    flow["net"] = flow["inc"] - flow["exp"]

    flow_x = [pd.to_datetime(m).strftime("%b '%y") for m in flow["month_str"]]
    if cf_metric == "net":
        flow_vals   = flow["net"].tolist()
        flow_colors = [c["accent3"] if v >= 0 else c["accent2"] for v in flow_vals]
        flow_name   = "Net"
    elif cf_metric == "expenses":
        flow_vals   = flow["exp"].tolist()
        flow_colors = c["accent2"]
        flow_name   = "Expenses"
    else:
        flow_vals   = flow["inc"].tolist()
        flow_colors = c["accent3"]
        flow_name   = "Income"

    fig_pos = go.Figure()
    if flow_vals:
        fig_pos.add_trace(go.Bar(
            x=flow_x, y=flow_vals, name=flow_name,
            marker_color=flow_colors, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>" + flow_name + ": $%{y:,.2f}<extra></extra>",
        ))
        if cf_metric == "net":
            fig_pos.add_hline(y=0, line_color=c["border"], line_width=1)
    fig_pos.update_layout(**tmpl, height=280, showlegend=False)
    # ── Categories: pie of spend for the selected year ───────────────────────
    ydf = df[df["year"] == int(cat_year)] if cat_year else df.iloc[0:0]
    cat = expenses_by_category(ydf)
    top = cat.head(CAT_PIE_TOP_N).copy()
    if len(cat) > CAT_PIE_TOP_N:
        rest = cat.iloc[CAT_PIE_TOP_N:]
        top = pd.concat([top, pd.DataFrame([{
            "category": f"Other · {len(rest)} categories",
            "total_expenses": rest["total_expenses"].sum(),
        }])], ignore_index=True)

    fig_cat = go.Figure()
    if not top.empty:
        # Colours follow the category's all-time spend rank, not its rank
        # within the selected year, so a category keeps its colour when
        # flipping between year chips ("Other" is always grey)
        cat_rank = {name: i for i, name in enumerate(expenses_by_category(df)["category"])}
        slice_colors = ["#8a8fa8" if name.startswith("Other · ")
                        else PIE_COLORS[cat_rank.get(name, 0) % len(PIE_COLORS)]
                        for name in top["category"]]
        # Pop the selected slice out so it stands apart from the ring
        pulls = [0.08 if name == sel_cat else 0 for name in top["category"]]
        fig_cat.add_trace(go.Pie(
            labels=top["category"], values=top["total_expenses"],
            marker=dict(colors=slice_colors),
            pull=pulls,
            sort=False,
            textinfo="percent",
            # Fixed dark text on every slice — the fills are all bright, so
            # this reads on all of them and avoids Plotly's per-slice
            # black/white auto-contrast looking inconsistent
            insidetextfont=dict(color="#0a0a0f"),
            hovertemplate="<b>%{label}</b><br>$%{value:,.2f} · %{percent}<extra></extra>",
        ))
    # Ease the slice pop-out (pull change) instead of snapping
    fig_cat.update_layout(**tmpl, height=380,
                          transition={"duration": 450, "easing": "cubic-in-out"})
    cat_title = "SPEND BY CATEGORY"

    # ── Summary card: YTD totals with a same-period-last-year delta ─────────
    # Compares Jan→current month of this year against the same months last
    # year (apples-to-apples), with the change shown beneath each figure.
    def _dollar(v):
        return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"

    now_p     = pd.Timestamp.today()
    cur_year  = now_p.year
    ytd_start = f"{cur_year}-01"
    ytd_end   = f"{cur_year}-{now_p.month:02d}"
    ly_start  = f"{cur_year - 1}-01"
    ly_end    = f"{cur_year - 1}-{now_p.month:02d}"

    mexp = monthly_expenses(df)
    minc = monthly_income(df)

    def _window_sum(series, col, s, e):
        w = series[(series["month_str"] >= s) & (series["month_str"] <= e)]
        return w[col].sum()

    ytd_exp = _window_sum(mexp, "total_expenses", ytd_start, ytd_end)
    ytd_inc = _window_sum(minc, "total_income",   ytd_start, ytd_end)
    ly_exp  = _window_sum(mexp, "total_expenses", ly_start,  ly_end)
    ly_inc  = _window_sum(minc, "total_income",   ly_start,  ly_end)

    ytd_net   = ytd_inc - ytd_exp
    ly_net    = ly_inc - ly_exp
    rate      = (ytd_net / ytd_inc * 100) if ytd_inc > 0 else None
    ly_rate   = (ly_net / ly_inc * 100) if ly_inc > 0 else None

    def _delta(cur, prior):
        if not prior:
            return ""
        # Divide by |prior| so the arrow tracks the real direction of change:
        # a negative prior (e.g. last year's net was negative) must not flip
        # the sign of an improvement.
        p = (cur - prior) / abs(prior) * 100
        return f"{'▲' if p >= 0 else '▼'}{abs(p):.0f}%"

    def _delta_pt(cur, prior):
        # Savings rate is already a percentage — compare in points, not
        # relative % change, so the delta reads unambiguously.
        if cur is None or prior is None:
            return ""
        d = cur - prior
        return f"{'▲' if d >= 0 else '▼'}{abs(d):.0f}pt"

    def _stat_card(title, value, delta, higher_is_good):
        # Delta colour signals good/bad for THIS metric: an increase is green
        # when higher is better (income, net, savings) and red when higher is
        # worse (expenses); a decrease flips it.
        delta_color = c["subtext"]
        if delta.startswith("▲"):
            delta_color = c["accent3"] if higher_is_good else c["accent2"]
        elif delta.startswith("▼"):
            delta_color = c["accent2"] if higher_is_good else c["accent3"]
        return html.Div(style={
            "background": c["surface"], "border": f"1px solid {c['border']}",
            "borderRadius": "12px", "padding": "18px 20px",
            "display": "flex", "flexDirection": "column", "gap": "8px",
        }, children=[
            html.Div(title, style={
                "fontSize": "10px", "letterSpacing": "1.5px", "fontWeight": "600",
                "color": c["subtext"],
            }),
            html.Div(value, style={
                "fontSize": "26px", "fontWeight": "600", "color": c["text"],
                "fontFamily": "'Syne', sans-serif", "lineHeight": "1.1",
            }),
            # Coloured delta + a neutral "vs last year" so the number pops;
            # the non-breaking space keeps card heights aligned when it's blank.
            html.Div(
                [html.Span(delta, style={"color": delta_color, "fontWeight": "600"}),
                 html.Span(" vs last year", style={"color": c["subtext"]})]
                if delta else " ",
                style={"fontSize": "11px", "fontFamily": "IBM Plex Mono, monospace"},
            ),
        ])

    perf = [
        _stat_card("YTD INCOME",       _dollar(ytd_inc), _delta(ytd_inc, ly_inc), True),
        _stat_card("YTD EXPENSES",     _dollar(ytd_exp), _delta(ytd_exp, ly_exp), False),
        _stat_card("YTD NET",          _dollar(ytd_net), _delta(ytd_net, ly_net), True),
        _stat_card("YTD SAVINGS RATE",
                   f"{rate:.0f}%" if rate is not None else "—",
                   _delta_pt(rate, ly_rate), True),
    ]

    return (fig_main, chart_title, fig_cat, cat_title, fig_pos, perf)


@app.callback(
    Output("selected-category",  "data"),
    Output("category-bar-chart", "clickData"),
    Input("category-bar-chart",  "clickData"),
    Input("category-year",       "value"),
    State("selected-category",   "data"),
    prevent_initial_call=True,
)
def select_category(click_data, _cat_year, current):
    # Store the clicked slice's label. Always reset clickData to None afterwards
    # so re-clicking the SAME slice registers as a change (Dash only fires on a
    # changed input) — otherwise repeat clicks look unresponsive. A year change
    # clears the selection; clicking the current slice toggles it back off.
    from dash import ctx
    if ctx.triggered_id == "category-year":
        return None, None
    if not click_data:
        return dash.no_update, dash.no_update
    label = click_data["points"][0].get("label")
    new = None if label == current else label
    return new, None


@app.callback(
    Output("category-bar-chart", "figure", allow_duplicate=True),
    Input("selected-category",   "data"),
    State("category-bar-chart",  "figure"),
    prevent_initial_call=True,
)
def pop_slice(sel_cat, fig):
    # Patch only the pie's pull — a click shouldn't rebuild the whole dashboard.
    if not fig or not fig.get("data"):
        return dash.no_update
    labels = fig["data"][0].get("labels") or []
    patched = Patch()
    patched["data"][0]["pull"] = [0.08 if l == sel_cat else 0 for l in labels]
    return patched


@app.callback(
    Output("category-drilldown", "children"),
    Input("selected-category",   "data"),
    State("category-year",       "value"),
    State("theme-store",         "data"),
)
def category_drilldown(label, cat_year, theme):
    if not label:
        return []
    c = _CHART[theme]
    scope_lbl = f" · {cat_year}" if cat_year else ""

    filtered = df[df["year"] == int(cat_year)] if cat_year else df.iloc[0:0]
    expenses = filtered[filtered["master_category"] == "Expense"].copy()
    if expenses.empty:
        return []
    expenses["cat"] = expenses["category_display"].where(
        expenses["category_display"] != "", "Uncategorized")
    expenses["amount"] = -expenses["amount"]

    divider = {"height": "1px", "background": c["border"], "margin": "12px 0"}

    def _prop_row(name, amt, cnt, total, muted=False):
        frac = amt / total if total > 0 else 0
        return html.Div(style={"display": "flex", "alignItems": "center", "gap": "12px",
                               "marginBottom": "8px"}, children=[
            html.Span(name, className="muted-text" if muted else None,
                      style={"flex": "0 0 150px", "fontSize": "12px", "overflow": "hidden",
                             "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            html.Div(style={"flex": "1", "height": "8px", "background": c["border"],
                            "borderRadius": "4px"},
                     children=html.Div(style={
                         # clamp: a refund-heavy group can net negative, which
                         # would otherwise emit an invalid negative CSS width
                         "width": f"{max(frac, 0) * 100:.0f}%", "height": "8px", "borderRadius": "4px",
                         "background": c["subtext"] if muted else c["accent"],
                     })),
            html.Span(f"${amt:,.2f} · {frac * 100:.0f}% · {int(cnt)} txn{'s' if cnt != 1 else ''}",
                      className="muted-text",
                      style={"flex": "0 0 170px", "fontSize": "11px", "textAlign": "right"}),
        ])

    def _panel(title, right, section_label, rows, footer_txns):
        big = footer_txns.loc[footer_txns["amount"].idxmax()]
        return html.Div(style={"marginTop": "20px",
                               "borderTop": f"1px solid {c['border']}",
                               "paddingTop": "20px"}, children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center"}, children=[
                html.Span(title, className="muted-text",
                          style={"fontSize": "11px", "letterSpacing": "2px"}),
                html.Span(right, style={"fontSize": "12px", "fontWeight": "600"}),
            ]),
            html.Div(style=divider),
            html.Div(section_label, className="muted-text",
                     style={"fontSize": "10px", "letterSpacing": "2px", "marginBottom": "10px"}),
            *rows,
            html.Div(style=divider),
            html.Div([
                "Largest: ",
                html.Span(f"${big['amount']:,.2f}", className="warn-text", style={"fontWeight": "600"}),
                f" · {big['description']} · {pd.to_datetime(big['date']).strftime('%b %d')}",
            ], className="muted-text", style={"fontSize": "11px"}),
        ])

    # Merchant rollup: bank descriptions embed store numbers and ids, so strip
    # digits/punctuation to group "STARBUCKS #1234" with "STARBUCKS #98"
    def _merchant(desc):
        m = re.sub(r"[\d#*]+", "", str(desc).upper())
        m = re.sub(r"\s{2,}", " ", m).strip(" -.,/")
        return m or "UNKNOWN"

    def _top_merchants_panel(txns, title):
        total = txns["amount"].sum()
        count = len(txns)
        avg   = total / count
        g = (txns.assign(merchant=txns["description"].map(_merchant))
             .groupby("merchant")["amount"].agg(["sum", "count"])
             .sort_values("sum", ascending=False))
        rest = g.iloc[5:]
        rows = [_prop_row(name, r["sum"], r["count"], total) for name, r in g.head(5).iterrows()]
        if not rest.empty:
            rows.append(_prop_row(f"OTHER · {len(rest)} merchants",
                                  rest["sum"].sum(), rest["count"].sum(), total, muted=True))
        return _panel(title, f"${total:,.2f} · {count} txns · ${avg:,.2f} avg",
                      "TOP MERCHANTS", rows, txns)

    # ── "Other" slice: top merchants across the small categories it aggregates ─
    if str(label).startswith("Other · "):
        by_cat = expenses.groupby("cat")["amount"].sum().sort_values(ascending=False)
        other_txns = expenses[expenses["cat"].isin(by_cat.iloc[CAT_PIE_TOP_N:].index)]
        if other_txns.empty:
            return []
        return _top_merchants_panel(other_txns, f"OTHER CATEGORIES{scope_lbl}")

    # ── Real category: its top merchants ─────────────────────────────────────
    cat_txns = expenses[expenses["cat"] == label]
    if cat_txns.empty:
        return []
    return _top_merchants_panel(cat_txns, f"{label.upper()}{scope_lbl}")


@app.callback(
    Output("unlabeled-note", "children"),
    Input("refresh-trigger", "data"),
)
def update_unlabeled_note(_refresh):
    # Anything outside Expense / Income / Transfer (including blank) never
    # reaches a Summary total — Transfer is deliberate, the rest deserve a flag.
    n = int((~df["master_category"].isin(PREDEFINED_CATEGORIES)).sum())
    if n == 0:
        return ""
    return (f"⚠ {n} of {len(df)} transactions have no valid label "
            f"(Expense / Income / Transfer) and are ignored in all totals.")


@app.callback(
    Output("export-csv-download", "data"),
    Input("export-csv-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(_):
    cols = ["date", "description", "amount", "institution", "source", "card_last4", "original_category", "master_category", "sub_category"]
    export = df[cols].copy()
    export["date"] = export["date"].astype(str)
    export["master_category"] = export["master_category"].fillna("")
    export["sub_category"]    = export["sub_category"].fillna("")
    return dcc.send_data_frame(export.to_csv, "transactions_export.csv", index=False)


@app.callback(
    Output("import-status",   "children"),
    Output("refresh-trigger", "data",     allow_duplicate=True),
    Input("import-csv-upload", "contents"),
    State("import-csv-upload", "filename"),
    State("refresh-trigger",   "data"),
    prevent_initial_call=True,
)
def import_csv(contents, filename, trigger):
    if not contents:
        return "", dash.no_update

    import base64, io
    _, content_string = contents.split(",", 1)
    try:
        import_df = pd.read_csv(io.StringIO(base64.b64decode(content_string).decode("utf-8")))
    except Exception as e:
        return f"⚠ Could not parse CSV: {e}", dash.no_update

    required = {"description", "amount", "source", "master_category"}
    missing = required - set(import_df.columns)
    if missing:
        return f"⚠ Missing columns: {', '.join(sorted(missing))}", dash.no_update

    if not MASTER_PATH or not MASTER_PATH.exists():
        return "⚠ No data directory configured — use the setup screen first.", dash.no_update
    try:
        has_date    = "date"         in import_df.columns
        has_sub_cat = "sub_category" in import_df.columns
        full_df = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
        full_df["master_category"] = full_df["master_category"].fillna("")
        full_df["sub_category"]    = full_df["sub_category"].fillna("")
        full_df["card_last4"]      = full_df["card_last4"].fillna("")

        updated = 0
        full_amounts = pd.to_numeric(full_df["amount"], errors="coerce").round(4)
        for _, row in import_df.iterrows():
            cat = str(row["master_category"]).strip() if pd.notna(row["master_category"]) else ""
            sub = str(row["sub_category"]).strip() if has_sub_cat and pd.notna(row.get("sub_category")) else ""
            if not cat and not sub:
                continue
            try:
                row_amt = round(float(row["amount"]), 4)
            except (ValueError, TypeError):
                continue
            mask = (
                (full_df["description"] == str(row["description"])) &
                (full_amounts == row_amt) &
                (full_df["source"] == str(row["source"]))
            )
            if has_date and pd.notna(row.get("date")):
                mask = mask & (full_df["date"].astype(str).str[:10] == str(row["date"])[:10])
            if mask.any():
                if cat:
                    full_df.loc[mask, "master_category"] = cat
                if sub:
                    full_df.loc[mask, "sub_category"] = sub
                updated += int(mask.sum())

        full_df.to_csv(MASTER_PATH, index=False)
        global df
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)

        return f"Updated {updated} row(s) from {filename}", (trigger or 0) + 1
    except Exception as e:
        return f"Import error: {e}", dash.no_update


@app.callback(
    Output("reload-status",   "children"),
    Output("refresh-trigger", "data",     allow_duplicate=True),
    Input("reload-data-btn",  "n_clicks"),
    State("refresh-trigger",  "data"),
    prevent_initial_call=True,
)
def reload_data(_, trigger):
    global df
    if not MASTER_PATH:
        return "⚠ No data directory configured — use the setup screen first.", dash.no_update
    try:
        _run_ingest_pipeline()
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
        return "✓ Reloaded", (trigger or 0) + 1
    except Exception as e:
        return f"⚠ {e}", dash.no_update


@app.callback(
    Output("category-year", "options"),
    Output("category-year", "value"),
    Input("refresh-trigger", "data"),
    State("category-year", "value"),
)
def update_year_options(_refresh, current):
    """Regenerate the year chips after reloads/imports so a new year's data
    gets a chip without restarting the app; the selection is preserved."""
    years = [int(y) for y in available_years(df)]
    opts  = [{"label": str(y), "value": y} for y in years]
    value = current if current in years else (years[-1] if years else None)
    return opts, value


@app.callback(
    Output("data-updated", "children"),
    Input("refresh-trigger", "data"),
)
def update_data_note(_refresh):
    srcs  = sorted(df["source"].dropna().unique().tolist())
    parts = [f"{len(srcs)} sources: {', '.join(srcs)}"] if srcs else ["no data loaded"]
    last_txn = df["date"].dropna().max()
    if pd.notna(last_txn):
        parts.append(f"latest transaction {last_txn.strftime('%b %d, %Y')}")
    return " · ".join(parts)




# ── Setup overlay callbacks ───────────────────────────────────────────────────

def _pick_folder() -> str:
    """Open a native OS folder picker. Returns the selected path or ''."""
    import sys, subprocess
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                 "$d.Description = 'Select your Data folder'; "
                 "$d.ShowNewFolderButton = $true; "
                 "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
                 "{ $d.SelectedPath }"],
                capture_output=True, text=True, timeout=120,
            )
            return result.stdout.strip()
        except Exception:
            pass
    # macOS / Linux fallback
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select your Data folder")
        root.destroy()
        return path or ""
    except Exception:
        return ""


@app.callback(
    Output("setup-path-input", "value", allow_duplicate=True),
    Input("setup-browse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def browse_for_folder(n_clicks):
    if not n_clicks:
        return dash.no_update
    path = _pick_folder()
    return path if path else dash.no_update


@app.callback(
    Output("setup-overlay", "style", allow_duplicate=True),
    Output("setup-status", "children", allow_duplicate=True),
    Output("setup-path-input", "value", allow_duplicate=True),
    Input("open-setup-btn", "n_clicks"),
    prevent_initial_call=True,
)
def open_setup(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    current = str(MASTER_PATH.parent.parent) if MASTER_PATH else ""
    return _OVERLAY_VISIBLE, "", current


@app.callback(
    Output("setup-overlay", "style", allow_duplicate=True),
    Output("setup-status", "children", allow_duplicate=True),
    Input("setup-cancel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_setup(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return _OVERLAY_HIDDEN, ""


@app.callback(
    Output("setup-overlay", "style", allow_duplicate=True),
    Output("setup-status", "children", allow_duplicate=True),
    Input("setup-save-btn", "n_clicks"),
    State("setup-path-input", "value"),
    prevent_initial_call=True,
)
def save_setup(n_clicks, path):
    global df, MASTER_PATH

    if not path or not path.strip():
        return dash.no_update, "Please enter or browse to a folder path."

    data_dir = Path(path.strip())
    master   = get_master_path(data_dir)

    if not data_dir.exists():
        return dash.no_update, f"Folder not found: {data_dir}"

    if not master.exists():
        try:
            _run_ingest_pipeline(data_dir)
        except Exception as e:
            return dash.no_update, f"Failed to run ingest: {e}"
        if not master.exists():
            return dash.no_update, f"Ingest ran but master file was not created at {master}"

    save_data_dir(str(data_dir))
    MASTER_PATH = master
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception as e:
        return dash.no_update, f"Error loading data: {e}"

    return _OVERLAY_HIDDEN, ""


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
