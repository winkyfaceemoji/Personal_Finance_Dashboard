import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, dash_table, Input, Output, State
import plotly.graph_objects as go

from config import get_data_dir, save_data_dir
from Modules.transforms import (
    load_transactions,
    monthly_expenses,
    monthly_income,
    yearly_expenses,
    yearly_income,
    expenses_by_category,
    get_uncategorized,
    available_months,
    available_years,
    available_categories,
    available_sources,
    PREDEFINED_CATEGORIES,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
RULES_PATH  = BASE_DIR / "rules.csv"
EXCLUDED_CATEGORIES = {"Transfer"}

_data_dir   = get_data_dir()
MASTER_PATH = (_data_dir / "SORTED" / "edited_combined_transactions.csv") if _data_dir else None

# ── Load data ─────────────────────────────────────────────────────────────────
_EMPTY_DF = pd.DataFrame(columns=[
    "date", "post_date", "amount", "description", "source", "master_category",
    "sub_category", "original_category", "card_last4",
    "effective_category", "month", "month_str", "year",
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


def label(text):
    return html.Label(text, className="app-label", style={
        "fontSize": "11px", "letterSpacing": "2px", "marginBottom": "10px",
        "display": "block", "color": "#ffffff",
    })


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

app.index_string = '''
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
        .dark-theme #active-tab label,
        .dark-theme #overview-view-toggle label {
            color: #8a8fa8; background: #0a0a0f; border: 1px solid #252830;
            transition: all 0.15s;
        }
        .dark-theme #active-tab input[type="radio"]:checked + label,
        .dark-theme #overview-view-toggle input[type="radio"]:checked + label {
            color: #ffffff !important; border-color: #6c8aff !important;
            background: rgba(108,138,255,0.18) !important; font-weight: 600 !important;
        }
        .dark-theme .btn-primary { background: #6c8aff; color: #0a0a0f; }
        .dark-theme .btn-secondary { color: #6c8aff; border-color: #6c8aff; }
        .dark-theme #theme-toggle-btn { background: #111318; border-color: #252830; color: #ffffff; }

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
        .light-theme #active-tab label,
        .light-theme #overview-view-toggle label {
            color: #5c5f72; background: #ffffff; border: 1px solid #dcdee8;
            transition: all 0.15s;
        }
        .light-theme #active-tab input[type="radio"]:checked + label,
        .light-theme #overview-view-toggle input[type="radio"]:checked + label {
            color: #0a0a0f !important; border-color: #4a68e8 !important;
            background: rgba(74,104,232,0.12) !important; font-weight: 600 !important;
        }
        .light-theme .btn-primary { background: #4a68e8; color: #ffffff; }
        .light-theme .btn-secondary { color: #4a68e8; border-color: #4a68e8; }
        .light-theme #theme-toggle-btn { background: #f0f1f5; border-color: #dcdee8; color: #0a0a0f; }

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
        #theme-toggle-btn {
            position: fixed; bottom: 32px; right: 32px;
            width: 48px; height: 48px; border-radius: 50%;
            font-size: 20px; cursor: pointer; z-index: 9999;
            box-shadow: 0 4px 16px rgba(0,0,0,0.25); transition: all 0.2s;
            display: flex; align-items: center; justify-content: center;
            line-height: 1; padding: 0;
        }
        #theme-toggle-btn:hover { transform: scale(1.1); }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

# ── Layout ────────────────────────────────────────────────────────────────────
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

        # Floating theme toggle button (position:fixed via CSS)
        html.Button("☽", id="theme-toggle-btn", n_clicks=0),

        # ── Setup overlay (shown when no data directory is configured) ──────
        html.Div(
            id="setup-overlay",
            style={
                "display": "none" if (MASTER_PATH and MASTER_PATH.exists()) else "flex",
                "position": "fixed", "inset": "0", "zIndex": "9999",
                "background": "var(--bg, #111)", "alignItems": "center",
                "justifyContent": "center",
            },
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
                html.Button("Save & Launch", id="setup-save-btn", n_clicks=0, style={
                    "width": "100%", "padding": "12px",
                    "background": COLORS["accent"], "border": "none",
                    "borderRadius": "6px", "color": "#fff",
                    "fontSize": "14px", "fontWeight": "700", "cursor": "pointer",
                }),
                html.Div(id="setup-status", style={
                    "marginTop": "12px", "fontSize": "13px",
                    "color": "#e05c5c",
                }),
            ]),
        ),
        # ────────────────────────────────────────────────────────────────────


        # Header
        html.Div(style={"marginBottom": "32px"}, children=[
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

        # Nav + filters bar
        card([
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "20px", "flexWrap": "wrap"}, children=[

                # Tab navigation
                dcc.RadioItems(
                    id="active-tab",
                    options=[
                        {"label": "SUMMARY",         "value": "summary"},
                        {"label": "ALL TRANSACTIONS", "value": "editor"},
                    ],
                    value="summary",
                    inline=True,
                    inputStyle={"display": "none"},
                    labelStyle={
                        "marginRight": "6px", "padding": "7px 18px",
                        "borderRadius": "6px", "cursor": "pointer", "fontSize": "13px",
                        "fontWeight": "600", "letterSpacing": "1px",
                    },
                ),

                # Divider
                html.Div(style={"width": "1px", "height": "36px", "background": COLORS["border"], "flexShrink": "0"}),

                # Filters
                html.Div(style={"display": "flex", "gap": "24px", "alignItems": "flex-end", "flex": "1", "flexWrap": "wrap"}, children=[

                    html.Div([
                        label("SOURCE"),
                        dcc.Dropdown(
                            id="global-source-filter",
                            options=[{"label": "All Sources", "value": "all"}] +
                                    [{"label": s, "value": s} for s in available_sources(df)],
                            value="all",
                            clearable=False,
                            style={"width": "200px"},
                        ),
                    ]),

                    html.Div([
                        label("YEAR"),
                        dcc.Dropdown(
                            id="global-year-filter",
                            options=[{"label": "All Years", "value": "all"}] +
                                    [{"label": str(y), "value": y} for y in available_years(df)],
                            value="all",
                            clearable=False,
                            style={"width": "140px"},
                        ),
                    ]),

                    html.Div([
                        label("MONTH"),
                        dcc.Dropdown(
                            id="global-month-filter",
                            options=[{"label": "All Months", "value": "all"}],
                            value="all",
                            clearable=False,
                            style={"width": "160px"},
                        ),
                    ]),

                    html.Div([
                        label("SHOW ON CHARTS"),
                        dcc.Checklist(
                            id="toggle-income-expenses",
                            options=[
                                {"label": "  Expenses", "value": "expenses"},
                                {"label": "  Income",   "value": "income"},
                            ],
                            value=["expenses"],
                            inline=True,
                            style={"fontSize": "13px"},
                            inputStyle={"marginRight": "6px"},
                            labelStyle={"marginRight": "20px"},
                        ),
                    ]),

                    html.Div([
                        label("VIEW"),
                        dcc.RadioItems(
                            id="overview-view-toggle",
                            options=[
                                {"label": "MONTH BY MONTH", "value": "monthly"},
                                {"label": "ALL YEARS",      "value": "yearly"},
                            ],
                            value="monthly",
                            inline=True,
                            inputStyle={"display": "none"},
                            labelStyle={
                                "marginRight": "8px", "padding": "6px 16px",
                                "borderRadius": "6px", "cursor": "pointer", "fontSize": "13px",
                            },
                        ),
                    ]),

                    html.Div(style={"marginLeft": "auto", "display": "flex", "flexDirection": "column", "gap": "6px", "alignItems": "flex-end"}, children=[
                        html.Div(id="uncategorized-count", style={
                            "fontSize": "11px", "color": COLORS["subtext"], "letterSpacing": "1px",
                        }),
                        html.Div(style={"display": "flex", "alignItems": "center", "gap": "8px"}, children=[
                            html.Button("RELOAD DATA", id="reload-data-btn", n_clicks=0,
                                        className="btn-secondary",
                                        style={"fontSize": "11px", "padding": "6px 14px", "letterSpacing": "1px"}),
                            html.Span(id="reload-status", style={"fontSize": "11px", "color": COLORS["accent3"]}),
                        ]),
                    ]),
                ]),
            ]),
        ], style={"padding": "16px 24px", "marginBottom": "16px"}),

        # ── SUMMARY content ───────────────────────────────────────────────────
        html.Div(id="summary-content", style={"paddingTop": "8px"}, children=[

                    # Summary stat cards
                    html.Div(id="summary-stats", style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(3, 1fr)",
                        "gap": "16px",
                        "marginBottom": "16px",
                    }),

                    # Main chart (monthly or yearly)
                    card([
                        html.Div(id="overview-chart-title", className="app-label", style={
                            "fontSize": "11px", "letterSpacing": "2px", "marginBottom": "16px",
                        }),
                        dcc.Graph(id="overview-main-chart", config={"displayModeBar": False}),
                    ]),

                    # Net chart
                    card([
                        section_title("MONTHLY NET (INCOME − EXPENSES)"),
                        dcc.Graph(id="net-chart", config={"displayModeBar": False}),
                    ]),

                    # Category breakdown
                    card([
                        section_title("SPEND BY CATEGORY"),
                        dcc.Graph(id="category-bar-chart", config={"displayModeBar": False}),
                        html.Div(id="category-drilldown"),
                    ]),

        ]),

        # ── CATEGORY EDITOR content ───────────────────────────────────────────
        html.Div(id="editor-content", style={"display": "none", "paddingTop": "8px"}, children=[
                    card([
                        section_title("TRANSACTIONS"),

                        # Import / Export row
                        html.Div(style={"display": "flex", "gap": "12px", "marginBottom": "20px", "alignItems": "center"}, children=[
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
                        ]),

                        # Transactions table
                        dash_table.DataTable(
                            id="editor-table",
                            columns=[
                                {"name": "DATE",            "id": "date"},
                                {"name": "DESCRIPTION",     "id": "description"},
                                {"name": "AMOUNT",          "id": "amount"},
                                {"name": "SOURCE",          "id": "source"},
                                {"name": "CARD",            "id": "card_last4"},
                                {"name": "TYPE OF TRANSACTION", "id": "master_category"},
                                {"name": "CATEGORY",        "id": "category_display"},
                            ],
                            data=[],
                            page_size=25,
                            sort_action="native",
                            cell_selectable=False,
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
                                "padding": "10px 14px", "fontSize": "12px",
                                "fontFamily": "IBM Plex Mono, monospace",
                                "maxWidth": "280px", "overflow": "hidden",
                                "textOverflow": "ellipsis",
                            },
                            style_cell_conditional=[
                                {"if": {"column_id": "description"},       "maxWidth": "320px"},
                                {"if": {"column_id": "master_category"},   "color": COLORS["accent"]},
                                {"if": {"column_id": "category_display"},  "color": COLORS["accent"]},
                            ],
                            style_data_conditional=[
                                {"if": {"state": "active"},   "backgroundColor": COLORS["surface"], "border": f"1px solid {COLORS['border']}"},
                                {"if": {"state": "selected"}, "backgroundColor": COLORS["surface"], "border": f"1px solid {COLORS['border']}"},
                            ],
                        ),
                    ]),
        ]),
    ]
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def apply_global_filters(source: str, year, month: str = "all") -> pd.DataFrame:
    filtered = df.copy()
    if source != "all":
        filtered = filtered[filtered["source"] == source]
    if year != "all":
        filtered = filtered[filtered["year"] == int(year)]
    if month != "all":
        filtered = filtered[filtered["month_str"] == month]
    return filtered


# ── Callbacks ─────────────────────────────────────────────────────────────────

# ── Tab switching ─────────────────────────────────────────────────────────────

@app.callback(
    Output("summary-content", "style"),
    Output("editor-content",  "style"),
    Input("active-tab", "value"),
)
def switch_tab(active):
    show = {"paddingTop": "8px"}
    hide = {"display": "none"}
    return (show, hide) if active == "summary" else (hide, show)


# ── Theme callbacks ───────────────────────────────────────────────────────────

@app.callback(
    Output("theme-store",      "data"),
    Output("app-root",         "className"),
    Output("theme-toggle-btn", "children"),
    Input("theme-toggle-btn",  "n_clicks"),
    State("theme-store",       "data"),
    prevent_initial_call=True,
)
def toggle_theme(_, current):
    new = "light" if current == "dark" else "dark"
    icon = "☽" if new == "dark" else "☀"
    return new, f"{new}-theme", icon



@app.callback(
    Output("overview-main-chart",  "figure"),
    Output("overview-chart-title", "children"),
    Output("net-chart",            "figure"),
    Output("category-bar-chart",   "figure"),
    Output("summary-stats",        "children"),
    Input("global-source-filter",   "value"),
    Input("global-year-filter",     "value"),
    Input("global-month-filter",    "value"),
    Input("toggle-income-expenses", "value"),
    Input("overview-view-toggle",   "value"),
    Input("theme-store",            "data"),
    Input("refresh-trigger",        "data"),
)
def update_overview(source, year, month, toggles, view_mode, theme, _refresh):
    import calendar
    tmpl = chart_template(theme)
    c    = _CHART[theme]

    excluded      = EXCLUDED_CATEGORIES
    filtered      = apply_global_filters(source, year, month)
    source_df     = df if source == "all" else df[df["source"] == source]
    show_expenses = "expenses" in toggles
    show_income   = "income"   in toggles

    data_df = filtered

    # ── Main bar chart ─────────────────────────────────────────────────────
    fig_main = go.Figure()
    if view_mode == "monthly":
        chart_title = "MONTH BY MONTH"
        if show_expenses:
            me = monthly_expenses(filtered, excluded)
            xlabels = [calendar.month_abbr[int(m.split("-")[1])] if year != "all" else pd.to_datetime(m).strftime("%b '%y") for m in me["month_str"]]
            fig_main.add_trace(go.Bar(
                x=xlabels, y=me["total_expenses"], name="Expenses",
                marker_color=c["accent2"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
            ))
            if len(me) >= 2:
                rolling = me["total_expenses"].rolling(3, min_periods=1).mean()
                fig_main.add_trace(go.Scatter(
                    x=xlabels, y=rolling, name="3-mo avg",
                    mode="lines",
                    line=dict(color=c["accent2"], dash="dash", width=2),
                    opacity=0.7,
                    hovertemplate="<b>%{x}</b><br>3-mo avg: $%{y:,.2f}<extra></extra>",
                ))
        if show_income:
            mi = monthly_income(filtered, excluded)
            xlabels_i = [calendar.month_abbr[int(m.split("-")[1])] if year != "all" else pd.to_datetime(m).strftime("%b '%y") for m in mi["month_str"]]
            fig_main.add_trace(go.Bar(
                x=xlabels_i, y=mi["total_income"], name="Income",
                marker_color=c["accent3"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
            ))
    else:
        chart_title = "YEAR TO YEAR"
        if show_expenses:
            ye = yearly_expenses(source_df, excluded)
            fig_main.add_trace(go.Bar(
                x=ye["year"].astype(str), y=ye["total_expenses"], name="Expenses",
                marker_color=c["accent2"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
            ))
        if show_income:
            yi = yearly_income(source_df, excluded)
            fig_main.add_trace(go.Bar(
                x=yi["year"].astype(str), y=yi["total_income"], name="Income",
                marker_color=c["accent3"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
            ))
    fig_main.update_layout(**tmpl, barmode="group", height=320)

    # ── Net chart (income − expenses per period) ───────────────────────────
    me_net = monthly_expenses(data_df, excluded).rename(columns={"total_expenses": "exp"})
    mi_net = monthly_income(data_df, excluded).rename(columns={"total_income": "inc"})
    net    = me_net.merge(mi_net, on="month_str", how="outer").fillna(0).sort_values("month_str").reset_index(drop=True)
    net["net"] = net["inc"] - net["exp"]

    if view_mode == "monthly":
        net_x = [calendar.month_abbr[int(m.split("-")[1])] if year != "all" else pd.to_datetime(m).strftime("%b '%y") for m in net["month_str"]]
    else:
        net["year_str"] = net["month_str"].str[:4]
        net = net.groupby("year_str", as_index=False)["net"].sum()
        net_x = net["year_str"].tolist()

    bar_colors = [c["accent3"] if v >= 0 else c["accent2"] for v in net["net"]]
    fig_net = go.Figure(go.Bar(
        x=net_x, y=net["net"],
        marker_color=bar_colors, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Net: $%{y:,.2f}<extra></extra>",
    ))
    fig_net.add_hline(y=0, line_color=c["border"], line_width=1)
    fig_net.update_layout(**tmpl, height=240, showlegend=False)

    # ── Category horizontal bar ────────────────────────────────────────────
    cat = expenses_by_category(data_df, excluded=excluded)
    fig_cat = go.Figure(go.Bar(
        x=cat["total_expenses"], y=cat["category"],
        orientation="h",
        marker_color=PIE_COLORS[:len(cat)], marker_line_width=0,
        hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
    ))
    fig_cat.update_layout(**tmpl, height=max(300, len(cat) * 36))
    fig_cat.update_yaxes(autorange="reversed")

    # ── Summary stat cards ─────────────────────────────────────────────────
    me_s      = monthly_expenses(data_df, excluded)
    total_exp = me_s["total_expenses"].sum()
    total_inc = monthly_income(data_df, excluded)["total_income"].sum()

    # Previous-period totals for MoM / YoY delta
    prev_exp = prev_inc = None
    if month != "all":
        prev_m   = (pd.Period(month, "M") - 1).strftime("%Y-%m")
        _prev_df = apply_global_filters(source, "all", prev_m)
        prev_exp = monthly_expenses(_prev_df, excluded)["total_expenses"].sum()
        prev_inc = monthly_income(_prev_df, excluded)["total_income"].sum()
    elif year != "all":
        _prev_df = apply_global_filters(source, int(year) - 1, "all")
        prev_exp = monthly_expenses(_prev_df, excluded)["total_expenses"].sum()
        prev_inc = monthly_income(_prev_df, excluded)["total_income"].sum()

    if view_mode == "monthly":
        if month != "all":
            period_label = pd.to_datetime(month).strftime("%b %Y")
        elif year != "all":
            period_label = str(year)
        else:
            period_label = "ALL YEARS"
        avg_label    = "AVG MONTHLY SPEND"
        avg_val      = me_s["total_expenses"].mean() if not me_s.empty else 0
    else:
        period_label = str(year) if year != "all" else "ALL YEARS"
        avg_label    = "AVG YEARLY SPEND"
        ye_s         = yearly_expenses(data_df, excluded)
        avg_val      = ye_s["total_expenses"].mean() if not ye_s.empty else 0

    def _delta(current, prev, higher_is_bad=True):
        """Return (label_str, is_green) or (None, None) when no comparison is available."""
        if prev is None or prev == 0:
            return None, None
        delta = current - prev
        pct   = delta / prev * 100
        sign  = "+" if delta >= 0 else ""
        is_green = (delta < 0) if higher_is_bad else (delta >= 0)
        return f"{sign}${abs(delta):,.0f} ({sign}{pct:.0f}%) vs prior", is_green

    def stat_card(lbl, value, color, prev=None, higher_is_bad=True):
        delta_lbl, is_green = _delta(value, prev, higher_is_bad)
        children = [
            html.P(lbl, className="app-label", style={
                "fontSize": "10px", "letterSpacing": "2px", "marginBottom": "8px",
            }),
            html.P(f"${value:,.2f}", style={
                "fontSize": "22px", "fontWeight": "600",
                "fontFamily": "'Syne', sans-serif", "color": color,
            }),
        ]
        if delta_lbl:
            children.append(html.P(delta_lbl, style={
                "fontSize": "11px", "marginTop": "4px", "fontWeight": "500",
                "color": c["accent3"] if is_green else c["accent2"],
            }))
        return card(children, style={"padding": "20px 24px", "marginBottom": "0"})

    stats = [
        stat_card(f"TOTAL EXPENSES · {period_label}", total_exp, c["accent2"], prev=prev_exp, higher_is_bad=True),
        stat_card(f"TOTAL INCOME · {period_label}",   total_inc, c["accent3"], prev=prev_inc, higher_is_bad=False),
        stat_card(avg_label,                           avg_val,   _CHART[theme]["text"]),
    ]
    return fig_main, chart_title, fig_net, fig_cat, stats


@app.callback(
    Output("global-month-filter", "options"),
    Output("global-month-filter", "value"),
    Input("global-year-filter", "value"),
    Input("global-source-filter", "value"),
)
def update_month_options(year, source):
    filtered = df
    if source != "all":
        filtered = filtered[filtered["source"] == source]
    if year != "all":
        filtered = filtered[filtered["year"] == int(year)]
    months = sorted(filtered["month_str"].dropna().unique().tolist())
    options = [{"label": "All Months", "value": "all"}] + [
        {"label": pd.to_datetime(m).strftime("%b %Y"), "value": m}
        for m in months
    ]
    return options, "all"


@app.callback(
    Output("category-drilldown", "children"),
    Input("category-bar-chart",      "clickData"),
    Input("global-source-filter",    "value"),
    Input("global-year-filter",      "value"),
    Input("global-month-filter",     "value"),
    State("theme-store",             "data"),
)
def category_drilldown(click_data, source, year, month, theme):
    from dash import ctx
    if ctx.triggered_id != "category-bar-chart" or not click_data:
        return []

    category = click_data["points"][0]["y"]
    c = _CHART[theme]

    filtered = apply_global_filters(source, year, month)
    cat_txns = filtered[filtered["effective_category"] == category].copy()
    cat_txns = cat_txns[cat_txns["amount"] < 0]
    cat_txns["amount"] = cat_txns["amount"].abs()
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
            html.Span(f"TRANSACTIONS — {category.upper()}", style={
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
    Output("editor-table", "data"),
    Input("global-source-filter", "value"),
    Input("global-year-filter",   "value"),
    Input("global-month-filter",  "value"),
    Input("refresh-trigger",      "data"),
)
def update_editor_table(source, year, month, _refresh):
    return _build_table_data(source, year, month)


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
    Output("editor-table",    "data",     allow_duplicate=True),
    Output("import-status",   "children"),
    Output("refresh-trigger", "data",     allow_duplicate=True),
    Input("import-csv-upload", "contents"),
    State("import-csv-upload", "filename"),
    State("global-source-filter", "value"),
    State("global-year-filter",   "value"),
    State("global-month-filter",  "value"),
    State("refresh-trigger",      "data"),
    prevent_initial_call=True,
)
def import_csv(contents, filename, source, year, month, trigger):
    if not contents:
        return dash.no_update, "", dash.no_update

    import base64, io
    _, content_string = contents.split(",", 1)
    try:
        import_df = pd.read_csv(io.StringIO(base64.b64decode(content_string).decode("utf-8")))
    except Exception as e:
        return dash.no_update, f"⚠ Could not parse CSV: {e}", dash.no_update

    required = {"description", "amount", "source", "master_category"}
    missing = required - set(import_df.columns)
    if missing:
        return dash.no_update, f"⚠ Missing columns: {', '.join(sorted(missing))}", dash.no_update

    if not MASTER_PATH:
        return dash.no_update, "⚠ No data directory configured — use the setup screen first.", dash.no_update
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

        new_data = _build_table_data(source, year, month)
        return new_data, f"Updated {updated} row(s) from {filename}", (trigger or 0) + 1
    except Exception as e:
        return dash.no_update, f"Import error: {e}", dash.no_update


def _build_table_data(source: str, year, month: str) -> list[dict]:
    filtered = apply_global_filters(source, year, month)
    filtered = filtered.copy()
    filtered["date"]            = filtered["date"].astype(str)
    filtered["master_category"] = filtered["master_category"].fillna("")
    sub = filtered["sub_category"].fillna("").str.strip()
    orig = filtered["original_category"].fillna("").str.strip()
    filtered["category_display"] = sub.where(sub != "", orig)
    if "card_last4" in filtered.columns:
        filtered["card_last4"] = filtered["card_last4"].fillna("")
    cols = ["date", "description", "amount", "source", "card_last4", "master_category", "category_display"]
    return filtered[[c for c in cols if c in filtered.columns]].to_dict("records")


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
        from main import main as run_ingest
        run_ingest()
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
    Output("setup-path-input", "value"),
    Input("setup-browse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def browse_for_folder(n_clicks):
    if not n_clicks:
        return dash.no_update
    path = _pick_folder()
    return path if path else dash.no_update


_OVERLAY_HIDDEN  = {
    "display": "none", "position": "fixed", "inset": "0", "zIndex": "9999",
    "background": "var(--bg, #111)", "alignItems": "center", "justifyContent": "center",
}
_OVERLAY_VISIBLE = {**_OVERLAY_HIDDEN, "display": "flex"}


@app.callback(
    Output("setup-overlay", "style"),
    Output("setup-status", "children"),
    Input("setup-save-btn", "n_clicks"),
    State("setup-path-input", "value"),
    prevent_initial_call=True,
)
def save_setup(n_clicks, path):
    global df, MASTER_PATH

    if not path or not path.strip():
        return dash.no_update, "Please enter or browse to a folder path."

    data_dir = Path(path.strip())
    master   = data_dir / "SORTED" / "edited_combined_transactions.csv"

    if not data_dir.exists():
        return dash.no_update, f"Folder not found: {data_dir}"

    if not master.exists():
        try:
            from main import main as run_ingest
            run_ingest()
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
