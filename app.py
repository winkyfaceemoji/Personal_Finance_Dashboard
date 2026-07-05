import base64

import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, dash_table, Input, Output, State
import plotly.graph_objects as go

from config import get_data_dir, get_master_path, save_data_dir
from Modules.transforms import (
    load_transactions,
    monthly_expenses,
    monthly_income,
    expenses_by_category,
    get_uncategorized,
    available_categories,
    available_sources,
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
        "text":   "#ffffff", "border": "#252830",
        "accent": "#6c8aff", "accent2": "#ff6c8a", "accent3": "#6cffd4",
    },
    "light": {
        "text":   "#0a0a0f", "border": "#dcdee8",
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
        .dark-theme #summary-range label {
            color: #8a8fa8; background: #0a0a0f; border: 1px solid #252830;
            transition: all 0.15s;
        }
        .dark-theme #summary-range input[type="radio"]:checked + label {
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
        .dark-theme #toggle-income-expenses label { color: #c8cadb !important; }
        .light-theme #toggle-income-expenses label { color: #5c5f72 !important; }
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
        .light-theme #summary-range label {
            color: #5c5f72; background: #ffffff; border: 1px solid #dcdee8;
            transition: all 0.15s;
        }
        .light-theme #summary-range input[type="radio"]:checked + label {
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
        #settings-menu-wrapper { position: relative; z-index: 9999; }
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


        # Header: title left; tab pills + settings gear docked right
        html.Div(style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center", "flexWrap": "wrap", "gap": "16px",
            "marginBottom": "24px",
        }, children=[
            html.Div([
                html.H1("FINANCE", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "48px",
                    "fontWeight": "800", "letterSpacing": "-2px",
                    "color": COLORS["text"], "display": "inline",
                }),
                html.Span(" DASHBOARD", style={
                    "fontFamily": "'Syne', sans-serif", "fontSize": "48px",
                    "fontWeight": "800", "letterSpacing": "-2px", "color": COLORS["accent"],
                }),
                html.P(
                    f"{len(df):,} transactions · {df['source'].nunique()} sources · "
                    f"{df['month_str'].nunique()} months",
                    style={"color": COLORS["subtext"], "marginTop": "8px", "fontSize": "13px"},
                ),
            ]),
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "12px"}, children=[
                # Settings menu — gear button expands/collapses the panel
                html.Div(id="settings-menu-wrapper", children=[
                    html.Button(html.Span(className="gear-icon"), id="settings-menu-btn", n_clicks=0),
                    html.Div(id="settings-menu-panel", className="app-card", style={
                        "display": "none", "flexDirection": "column", "gap": "10px", "padding": "16px",
                    }, children=[
                        html.Div(id="uncategorized-count", style={
                            "fontSize": "11px", "color": COLORS["subtext"], "letterSpacing": "1px",
                        }),
                        html.Button("CHANGE DATA FOLDER", id="open-setup-btn", n_clicks=0,
                                    className="btn-secondary",
                                    style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px"}),
                        html.Div(style={"display": "flex", "alignItems": "center", "gap": "8px"}, children=[
                            html.Button("RELOAD DATA", id="reload-data-btn", n_clicks=0,
                                        className="btn-secondary",
                                        style={"fontSize": "11px", "padding": "8px 14px", "letterSpacing": "1px", "flex": "1"}),
                        ]),
                        html.Span(id="reload-status", style={"fontSize": "11px", "color": COLORS["accent3"]}),
                        html.Div(style={"height": "1px", "background": "var(--Dash-Stroke-Strong)", "margin": "4px 0"}),
                        html.Div(style={"display": "flex", "gap": "8px"}, children=[
                            html.Button("LIGHT", id="theme-light-btn", n_clicks=0,
                                        className="btn-secondary", style={"fontSize": "11px", "padding": "8px 14px", "flex": "1"}),
                            html.Button("DARK", id="theme-dark-btn", n_clicks=0,
                                        className="btn-secondary", style={"fontSize": "11px", "padding": "8px 14px", "flex": "1"}),
                        ]),
                    ]),
                ]),
            ]),
        ]),

        # ── SUMMARY content ───────────────────────────────────────────────────
        html.Div(id="summary-content", style={"paddingTop": "8px"}, children=[

                    # 1. Graphs — view selector left, range chips + source right
                    card([
                        html.Div(style={
                            "display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "12px",
                            "marginBottom": "20px",
                        }, children=[
                            dcc.Dropdown(
                                id="chart-view-toggle",
                                options=[
                                    {"label": "Net",        "value": "position"},
                                    {"label": "Trends",     "value": "trends"},
                                    {"label": "Categories", "value": "categories"},
                                ],
                                value="position",
                                clearable=False,
                                style={"width": "180px"},
                            ),
                            html.Div(style={"display": "flex", "alignItems": "center", "gap": "12px", "flexWrap": "wrap"}, children=[
                                dcc.RadioItems(
                                    id="summary-range",
                                    options=[
                                        {"label": "1M",  "value": "1m"},
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
                                dcc.Dropdown(
                                    id="summary-source",
                                    options=[{"label": "All Sources", "value": "all"}] +
                                            [{"label": s, "value": s} for s in available_sources(df)],
                                    value="all",
                                    clearable=False,
                                    style={"width": "170px"},
                                ),
                            ]),
                        ]),

                        # Net view: per-period net bars
                        html.Div(id="chart-position-card", children=[
                            html.Div(id="net-position-header", className="app-label", style={
                                "fontSize": "11px", "letterSpacing": "2px", "marginBottom": "16px",
                            }),
                            dcc.Graph(id="net-position-chart", config={"displayModeBar": False}),
                        ]),

                        # Trends: same-month year-over-year
                        html.Div(id="chart-trends-card", style={"display": "none"}, children=[
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
                                        {"label": "  Expenses", "value": "expenses"},
                                        {"label": "  Income",   "value": "income"},
                                    ],
                                    value="expenses",
                                    inline=True,
                                    style={"fontSize": "12px"},
                                    inputStyle={"marginRight": "6px"},
                                    labelStyle={"marginRight": "16px"},
                                ),
                            ]),
                            dcc.Graph(id="overview-main-chart", config={"displayModeBar": False}),
                        ]),

                        # Category breakdown
                        html.Div(id="chart-categories-card", style={"display": "none"}, children=[
                            section_title("SPEND BY CATEGORY"),
                            dcc.Graph(id="category-bar-chart", config={"displayModeBar": False}),
                            html.Div(id="category-drilldown"),
                        ]),
                    ]),

                    # 2. Performance card — the metrics for the selected range
                    card([
                        html.Div(id="performance-title", className="app-label", style={
                            "fontSize": "11px", "letterSpacing": "2px", "marginBottom": "16px",
                        }),
                        html.Div(id="performance-card", style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(auto-fit, minmax(170px, 1fr))",
                            "gap": "20px",
                        }),
                    ]),

                    # Import / export + labeling status
                    card([
                        html.Div(style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap"}, children=[
                            html.Span("IMPORT / EXPORT", style={"fontSize": "11px", "letterSpacing": "2px", "color": COLORS["subtext"], "marginRight": "4px"}),
                            dcc.Upload(
                                id="import-csv-upload",
                                children=html.Button("IMPORT CSV", className="btn-secondary", style={"fontSize": "12px", "padding": "8px 16px"}),
                                accept=".csv",
                                multiple=False,
                            ),
                            html.Button("EXPORT CSV", id="export-csv-btn", n_clicks=0, className="btn-secondary", style={"fontSize": "12px", "padding": "8px 16px"}),
                            dcc.Download(id="export-csv-download"),
                            html.Span(id="import-status", style={"fontSize": "12px", "color": COLORS["accent3"], "marginLeft": "4px"}),
                            # Unlabeled rows are ignored by every Summary total — surface the count
                            html.Span(id="unlabeled-note", style={
                                "fontSize": "12px", "color": COLORS["subtext"], "marginLeft": "auto",
                            }),
                        ]),
                    ], style={"padding": "16px 24px"}),

        ]),
    ]
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _range_window(rng: str):
    """Calendar-anchored month windows for the summary range chips.
    Returns (start, end, prev_start, prev_end, label) — months as YYYY-MM,
    where the prev window is the equivalent span immediately before."""
    now = pd.Timestamp.today().to_period("M")
    end = now.strftime("%Y-%m")
    if rng == "1m":
        p = (now - 1).strftime("%Y-%m")
        return end, end, p, p, now.strftime("%b %Y").upper()
    if rng == "ytd":
        return (f"{now.year}-01", end,
                f"{now.year - 1}-01", (now - 12).strftime("%Y-%m"), f"YTD {now.year}")
    if rng == "1y":
        return ((now - 11).strftime("%Y-%m"), end,
                (now - 23).strftime("%Y-%m"), (now - 12).strftime("%Y-%m"), "TRAILING 1Y")
    return ((now - 35).strftime("%Y-%m"), end,
            (now - 71).strftime("%Y-%m"), (now - 36).strftime("%Y-%m"), "TRAILING 3Y")


def _summary_window(rng: str, source: str):
    """Source-scoped frames for the selected range: (window df, prev-window df,
    source-only df, start, end, label, prior_ok).

    prior_ok is False when the prior window reaches back before the first month
    of data — a partially-covered prior would make every "vs prior" delta
    nonsense (e.g. a full 3Y window compared against a few months)."""
    start, end, p_start, p_end, label = _range_window(rng)
    src_df   = df if source == "all" else df[df["source"] == source]
    data_df  = src_df[(src_df["month_str"] >= start) & (src_df["month_str"] <= end)]
    prev_df  = src_df[(src_df["month_str"] >= p_start) & (src_df["month_str"] <= p_end)]
    months   = src_df["month_str"].dropna()
    prior_ok = (not months.empty) and p_start >= months.min()
    return data_df, prev_df, src_df, start, end, label, prior_ok


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
    Output("net-position-chart",    "figure"),
    Output("net-position-header",   "children"),
    Output("performance-title",     "children"),
    Output("performance-card",      "children"),
    Output("chart-position-card",   "style"),
    Output("chart-trends-card",     "style"),
    Output("chart-categories-card", "style"),
    Input("summary-range",          "value"),
    Input("summary-source",         "value"),
    Input("toggle-income-expenses", "value"),
    Input("theme-store",            "data"),
    Input("refresh-trigger",        "data"),
    Input("chart-view-toggle",      "value"),
)
def update_overview(rng, source, metric, theme, _refresh, chart_view):
    import calendar
    tmpl = chart_template(theme)
    c    = _CHART[theme]

    metric = metric if metric in ("expenses", "income") else "expenses"
    rng    = rng if rng in ("1m", "ytd", "1y", "3y") else "ytd"
    data_df, prev_df, src_df, start, end, period_label, prior_ok = _summary_window(rng, source)

    # ── Trends: same-calendar-month year-over-year comparison ──────────────
    # Inherently an all-years chart — it ignores the range chips (those drive
    # the NET and CATEGORIES views and the performance card).
    metric_lbl = "EXPENSES" if metric == "expenses" else "INCOME"

    if metric == "expenses":
        series = monthly_expenses(src_df).rename(columns={"total_expenses": "val"})
    else:
        series = monthly_income(src_df).rename(columns={"total_income": "val"})
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
    chart_title = f"{metric_lbl} BY CALENDAR MONTH · ONE LINE PER YEAR"
    fig_main.update_layout(**tmpl, height=320)

    # ── Totals for the window and its prior equivalent ──────────────────────
    me_s      = monthly_expenses(data_df)
    total_exp = me_s["total_expenses"].sum()
    total_inc = monthly_income(data_df)["total_income"].sum()
    net_val   = total_inc - total_exp
    # No deltas when the prior window predates the data — a partial prior
    # window would compare a full range against a sliver.
    prev_exp = prev_inc = prev_net = None
    if prior_ok:
        prev_exp = monthly_expenses(prev_df)["total_expenses"].sum()
        prev_inc = monthly_income(prev_df)["total_income"].sum()
        prev_net = prev_inc - prev_exp
    net_color = c["accent3"] if net_val >= 0 else c["accent2"]

    # ── Net view (per-period net bars) ──────────────────────────────────────
    net_m = (
        me_s.rename(columns={"total_expenses": "exp"})
        .merge(monthly_income(data_df).rename(columns={"total_income": "inc"}),
               on="month_str", how="outer")
        .fillna(0).sort_values("month_str")
    )
    net_m["net"] = net_m["inc"] - net_m["exp"]

    pos_xtitle = None
    if rng == "1m":
        # Daily resolution inside the current month
        rows  = data_df[data_df["master_category"].isin(["Expense", "Income"])]
        daily = rows.groupby(rows["date"].dt.day)["amount"].sum()
        if not daily.empty:
            daily = daily.reindex(range(1, int(daily.index.max()) + 1), fill_value=0)
        pos_x      = [str(d) for d in daily.index]
        net_vals   = daily.tolist()
        pos_xtitle = period_label + " · day of month"
    else:
        pos_x    = [pd.to_datetime(m).strftime("%b '%y") for m in net_m["month_str"]]
        net_vals = net_m["net"].tolist()

    fig_pos = go.Figure()
    if net_vals:
        fig_pos.add_trace(go.Bar(
            x=pos_x, y=net_vals, name="Net",
            marker_color=[c["accent3"] if v >= 0 else c["accent2"] for v in net_vals],
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Net: $%{y:,.2f}<extra></extra>",
        ))
        fig_pos.add_hline(y=0, line_color=c["border"], line_width=1)
    fig_pos.update_layout(**tmpl, height=280, showlegend=False)
    if pos_xtitle:
        fig_pos.update_xaxes(title_text=pos_xtitle, title_font=dict(size=11))
    pos_header = f"{'DAILY' if rng == '1m' else 'MONTHLY'} NET · {period_label}"

    # ── Categories view ─────────────────────────────────────────────────────
    if rng == "1m":
        # Snapshot: horizontal bars for the month (top N + Other, vs-prior deltas)
        TOP_N = 10
        cat = expenses_by_category(data_df)
        top = cat.head(TOP_N).copy()
        other_label = None
        if len(cat) > TOP_N:
            rest        = cat.iloc[TOP_N:]
            other_label = f"Other · {len(rest)} categories"
            top = pd.concat([top, pd.DataFrame([{
                "category": other_label, "total_expenses": rest["total_expenses"].sum(),
            }])], ignore_index=True)

        prev_cat_map = None
        if prior_ok:
            prev_cat = expenses_by_category(prev_df)
            if not prev_cat.empty:
                prev_cat_map = dict(zip(prev_cat["category"], prev_cat["total_expenses"]))

        top_names = set(cat.head(TOP_N)["category"])
        bar_texts = []
        for name, val in zip(top["category"], top["total_expenses"]):
            if prev_cat_map is None:
                bar_texts.append(f"${val:,.0f}")
                continue
            if name == other_label:
                prev_val = sum(v for k, v in prev_cat_map.items() if k not in top_names)
            else:
                prev_val = prev_cat_map.get(name, 0)
            d = val - prev_val
            bar_texts.append(f"${val:,.0f} · {'+' if d >= 0 else '-'}${abs(d):,.0f}")

        grand = cat["total_expenses"].sum()
        pcts  = (top["total_expenses"] / grand * 100) if grand else top["total_expenses"] * 0
        fig_cat = go.Figure(go.Bar(
            x=top["total_expenses"], y=top["category"],
            orientation="h",
            marker_color=PIE_COLORS[:len(top)], marker_line_width=0,
            text=bar_texts, textposition="outside", cliponaxis=False,
            textfont=dict(size=10),
            customdata=pcts,
            hovertemplate="<b>%{y}</b><br>$%{x:,.2f} · %{customdata:.0f}% of total<extra></extra>",
        ))
        fig_cat.update_layout(**tmpl, height=max(300, len(top) * 36))
        fig_cat.update_layout(margin=dict(l=40, r=120, t=40, b=40))
        fig_cat.update_yaxes(autorange="reversed")
    else:
        # Share trend lines: each category's % of that month's spending, so a
        # rising line = a category eating a growing share. Top 5 + Other keeps
        # it readable; months where nothing was spent show a gap.
        rows = data_df[data_df["master_category"] == "Expense"].copy()
        rows["cat"] = rows["category_display"].where(rows["category_display"] != "", "Uncategorized")
        fig_cat = go.Figure()
        if not rows.empty:
            pivot  = (-rows.pivot_table(index="month_str", columns="cat",
                                        values="amount", aggfunc="sum").fillna(0)).sort_index()
            totals = pivot.sum(axis=1)
            top5   = pivot.sum(axis=0).sort_values(ascending=False).head(5).index.tolist()
            others = [col for col in pivot.columns if col not in top5]
            names  = list(top5)
            if others:
                other_label = f"Other · {len(others)} categories"
                pivot[other_label] = pivot[others].sum(axis=1)
                names.append(other_label)

            x_lbls_c = [pd.to_datetime(m).strftime("%b '%y") for m in pivot.index]
            for i, name in enumerate(names):
                shares, cds = [], []
                prev_share = None
                for m, amt, tot in zip(pivot.index, pivot[name], totals):
                    share = (amt / tot * 100) if tot > 0 else None
                    shares.append(share)
                    if share is not None and prev_share is not None:
                        dpp = share - prev_share
                        pp_txt = f"{'+' if dpp >= 0 else '-'}{abs(dpp):.0f}pp vs prior month"
                    else:
                        pp_txt = ""
                    cds.append((f"${amt:,.0f}", pp_txt, name))
                    prev_share = share
                fig_cat.add_trace(go.Scatter(
                    x=x_lbls_c, y=shares, name=name,
                    mode="lines+markers",
                    line=dict(color=PIE_COLORS[i % len(PIE_COLORS)], width=2),
                    marker=dict(size=5),
                    customdata=cds,
                    hovertemplate=("<b>" + name + " · %{x}</b><br>"
                                   "%{y:.0f}% of spend · %{customdata[0]}<br>"
                                   "%{customdata[1]}<extra></extra>"),
                ))
        fig_cat.update_layout(**tmpl, height=340)
        fig_cat.update_yaxes(ticksuffix="%", rangemode="tozero",
                             title_text="% of monthly spend", title_font=dict(size=11))

    # ── Performance card ─────────────────────────────────────────────────────
    def _delta(current, prev, higher_is_bad=True):
        """Return (label_str, is_green) or (None, None) when no comparison is available."""
        if prev is None or prev == 0:
            return None, None
        delta = current - prev
        pct   = delta / abs(prev) * 100
        sign  = "+" if delta >= 0 else "-"
        is_green = (delta < 0) if higher_is_bad else (delta >= 0)
        return f"{sign}${abs(delta):,.0f} ({sign}{abs(pct):.0f}%) vs prior", is_green

    def perf_metric(lbl, value_str, color, delta_lbl=None, delta_green=None):
        children = [
            html.P(lbl, className="app-label", style={
                "fontSize": "10px", "letterSpacing": "2px", "marginBottom": "6px",
            }),
            html.P(value_str, style={
                "fontSize": "22px", "fontWeight": "600",
                "fontFamily": "'Syne', sans-serif", "color": color,
            }),
        ]
        if delta_lbl:
            children.append(html.P(delta_lbl, style={
                "fontSize": "11px", "marginTop": "4px", "fontWeight": "500",
                "color": c["accent3"] if delta_green else c["accent2"],
            }))
        return html.Div(children)

    def _dollar(v):
        return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"

    rate      = (net_val / total_inc * 100) if total_inc > 0 else None
    prev_rate = (prev_net / prev_inc * 100) if prev_inc and prev_inc > 0 else None
    exp_d, exp_g = _delta(total_exp, prev_exp, higher_is_bad=True)
    inc_d, inc_g = _delta(total_inc, prev_inc, higher_is_bad=False)
    net_d, net_g = _delta(net_val,  prev_net, higher_is_bad=False)
    rate_d = rate_g = None
    if rate is not None and prev_rate is not None:
        dpp    = rate - prev_rate
        rate_d = f"{'+' if dpp >= 0 else '-'}{abs(dpp):.0f}pp vs prior"
        rate_g = dpp >= 0

    perf_title = f"PERFORMANCE · {period_label}"
    perf = [
        perf_metric("TOTAL EXPENSES", _dollar(total_exp), c["accent2"], exp_d, exp_g),
        perf_metric("TOTAL INCOME",   _dollar(total_inc), c["accent3"], inc_d, inc_g),
        perf_metric("NET",            _dollar(net_val),   net_color,    net_d, net_g),
        perf_metric("SAVINGS RATE",   f"{rate:.0f}%" if rate is not None else "—", c["accent"], rate_d, rate_g),
    ]

    # One chart body visible at a time, driven by the selector. Styles are
    # emitted from this callback so the figure redraw and the unhide land in
    # the same render cycle (a Plotly graph drawn while display:none mis-sizes).
    hide = {"display": "none"}
    pos_style = {} if chart_view == "position"   else hide
    trd_style = {} if chart_view == "trends"     else hide
    cat_style = {} if chart_view == "categories" else hide

    return (fig_main, chart_title, fig_cat, fig_pos, pos_header, perf_title, perf,
            pos_style, trd_style, cat_style)


@app.callback(
    Output("category-drilldown", "children"),
    Input("category-bar-chart",  "clickData"),
    Input("summary-range",       "value"),
    Input("summary-source",      "value"),
    State("theme-store",         "data"),
)
def category_drilldown(click_data, rng, source, theme):
    from dash import ctx
    if ctx.triggered_id != "category-bar-chart" or not click_data:
        return []

    # 1M snapshot bars carry the category on the y axis; the share-trend lines
    # carry it (plus the month) in customdata so a point click scopes to both.
    point = click_data["points"][0]
    cd    = point.get("customdata")
    month_scope = scope_lbl = None
    if isinstance(cd, (list, tuple)) and len(cd) == 3:
        category    = cd[2]
        month_scope = pd.to_datetime(point["x"], format="%b '%y").strftime("%Y-%m")
        scope_lbl   = str(point["x"]).upper()
    else:
        category = point["y"]
    if category.startswith("Other · "):  # aggregated tail, not a real category
        return []
    c = _CHART[theme]

    rng = rng if rng in ("1m", "ytd", "1y", "3y") else "ytd"
    filtered, _, _, _, _, _, _ = _summary_window(rng, source)
    if month_scope:
        filtered = filtered[filtered["month_str"] == month_scope]
    match_category = filtered["category_display"].where(filtered["category_display"] != "", "Uncategorized")
    cat_txns = filtered[match_category == category].copy()
    cat_txns = cat_txns[cat_txns["master_category"] == "Expense"]
    cat_txns["amount"] = -cat_txns["amount"]
    cat_txns = cat_txns.sort_values("date", ascending=False)
    cat_txns["date"] = cat_txns["date"].astype(str)
    display = cat_txns[["date", "description", "amount", "source"]].head(100)
    total = cat_txns["amount"].sum()

    return html.Div(style={
        "marginTop": "20px",
        "borderTop": f"1px solid {COLORS['border']}",
        "paddingTop": "20px",
    }, children=[
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "12px"}, children=[
            html.Span(f"TRANSACTIONS — {category.upper()}" + (f" · {scope_lbl}" if scope_lbl else ""), style={
                "fontSize": "11px", "letterSpacing": "2px", "color": COLORS["subtext"],
            }),
            html.Span(f"${total:,.2f} total · {len(cat_txns)} transactions", style={
                "fontSize": "12px", "color": c["accent2"], "fontWeight": "600",
            }),
        ]),
        dash_table.DataTable(
            data=display.to_dict("records"),
            columns=[
                {"name": "DATE",        "id": "date"},
                {"name": "DESCRIPTION", "id": "description"},
                {"name": "AMOUNT",      "id": "amount",  "type": "numeric", "format": {"specifier": ",.2f"}},
                {"name": "SOURCE",      "id": "source"},
            ],
            page_size=15,
            sort_action="native",
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": COLORS["bg"],
                "color": COLORS["subtext"],
                "border": f"1px solid {COLORS['border']}",
                "fontWeight": "600", "letterSpacing": "1px", "fontSize": "11px",
            },
            style_cell={
                "backgroundColor": COLORS["surface"],
                "color": COLORS["text"],
                "border": f"1px solid {COLORS['border']}",
                "padding": "8px 12px", "fontSize": "12px",
                "fontFamily": "IBM Plex Mono, monospace",
                "maxWidth": "300px", "overflow": "hidden", "textOverflow": "ellipsis",
            },
        ),
    ])


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
    cols = ["date", "description", "amount", "source", "card_last4", "original_category", "master_category", "sub_category"]
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
    Output("uncategorized-count", "children"),
    Input("refresh-trigger", "data"),
)
def update_uncategorized_count(_):
    n = int((df["master_category"] == "").sum())
    if n == 0:
        return ""
    return f"⚠ {n:,} uncategorized"




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
