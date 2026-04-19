import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, dash_table, Input, Output, State
import plotly.graph_objects as go

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
BASE_DIR   = Path(__file__).parent
MASTER_PATH = BASE_DIR / "Data" / "SORTED" / "edited_combined_transactions.csv"

# ── Load data ─────────────────────────────────────────────────────────────────
df = load_transactions(MASTER_PATH)

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

        # Floating theme toggle button (position:fixed via CSS)
        html.Button("☽", id="theme-toggle-btn", n_clicks=0),


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
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "20px"}, children=[

                # Tab navigation
                dcc.RadioItems(
                    id="active-tab",
                    options=[
                        {"label": "SUMMARY",         "value": "summary"},
                        {"label": "CATEGORY EDITOR", "value": "editor"},
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
                html.Div(style={"display": "flex", "gap": "24px", "alignItems": "flex-end", "flex": "1"}, children=[

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
                ]),
            ]),
        ], style={"padding": "16px 24px", "marginBottom": "16px"}),

        # ── SUMMARY content ───────────────────────────────────────────────────
        html.Div(id="summary-content", style={"paddingTop": "8px"}, children=[

                    # Controls row: view toggle
                    card([
                        html.Div(style={"display": "flex", "alignItems": "center", "justifyContent": "flex-end"}, children=[

                            # View toggle
                            html.Div(style={"display": "flex", "alignItems": "center", "gap": "12px"}, children=[
                                html.Span("VIEW", className="app-label", style={
                                    "fontSize": "11px", "letterSpacing": "2px", "whiteSpace": "nowrap",
                                }),
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

                        ]),
                    ], style={"padding": "16px 24px", "marginBottom": "16px"}),

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
                    ]),

        ]),

        # ── CATEGORY EDITOR content ───────────────────────────────────────────
        html.Div(id="editor-content", style={"display": "none", "paddingTop": "8px"}, children=[
                    card([
                        section_title("ASSIGN MASTER CATEGORIES TO TRANSACTIONS"),

                        # Controls row
                        html.Div(style={"display": "flex", "gap": "12px", "marginBottom": "20px", "alignItems": "flex-end", "flexWrap": "wrap"}, children=[

                            # Predefined category picker
                            html.Div([
                                label("SELECT CATEGORY"),
                                dcc.Dropdown(
                                    id="category-picker",
                                    options=[{"label": c, "value": c} for c in available_categories(df)],
                                    placeholder="Pick a category...",
                                    clearable=True,
                                    style={"width": "280px"},
                                ),
                            ]),

                            # Custom category input
                            html.Div([
                                label("OR CREATE NEW"),
                                dcc.Input(
                                    id="custom-category-input",
                                    type="text",
                                    placeholder="Type custom category...",
                                    debounce=False,
                                    style={
                                        "background": COLORS["bg"],
                                        "border": f"1px solid {COLORS['border']}",
                                        "borderRadius": "4px",
                                        "color": COLORS["text"],
                                        "padding": "8px 12px",
                                        "fontFamily": "IBM Plex Mono, monospace",
                                        "fontSize": "13px",
                                        "width": "240px",
                                        "height": "38px",
                                    },
                                ),
                            ]),

                            # Assign button
                            html.Div([
                                html.Div(style={"height": "21px"}),  # spacer to align with inputs
                                html.Button("ASSIGN TO SELECTED", id="assign-btn",
                                            n_clicks=0, className="btn-primary"),
                            ]),

                            # Clear button
                            html.Div([
                                html.Div(style={"height": "21px"}),
                                html.Button("CLEAR SELECTED", id="clear-btn",
                                            n_clicks=0, className="btn-secondary"),
                            ]),

                            # Status message
                            html.Span(id="save-status", style={
                                "fontSize": "12px", "color": COLORS["accent3"],
                                "alignSelf": "center", "marginLeft": "8px",
                            }),
                        ]),

                        # Import / Export row
                        html.Div(style={"display": "flex", "gap": "12px", "marginBottom": "20px", "alignItems": "center", "borderTop": f"1px solid {COLORS['border']}", "paddingTop": "16px"}, children=[
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

                        # Filter bar for the editor table
                        html.Div(style={"display": "flex", "gap": "16px", "marginBottom": "16px", "alignItems": "flex-end"}, children=[
                            html.Div([
                                label("FILTER TABLE BY SOURCE"),
                                dcc.Dropdown(
                                    id="editor-source-filter",
                                    options=[{"label": "All Sources", "value": "all"}] +
                                            [{"label": s, "value": s} for s in available_sources(df)],
                                    value="all",
                                    clearable=False,
                                    style={"width": "220px"},
                                ),
                            ]),
                            html.Div([
                                label("SHOW"),
                                dcc.Dropdown(
                                    id="editor-categorized-filter",
                                    options=[
                                        {"label": "Uncategorized only", "value": "uncategorized"},
                                        {"label": "All transactions",   "value": "all"},
                                    ],
                                    value="uncategorized",
                                    clearable=False,
                                    style={"width": "220px"},
                                ),
                            ]),
                        ]),

                        # Editor table
                        dash_table.DataTable(
                            id="editor-table",
                            columns=[
                                {"name": "DATE",              "id": "date"},
                                {"name": "DESCRIPTION",       "id": "description"},
                                {"name": "AMOUNT",            "id": "amount"},
                                {"name": "SOURCE",            "id": "source"},
                                {"name": "BANK CATEGORY",     "id": "category"},
                                {"name": "MASTER CATEGORY",   "id": "master_category"},
                            ],
                            data=[],
                            row_selectable="multi",
                            selected_rows=[],
                            page_size=25,
                            sort_action="native",
                            filter_action="native",
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
                                {"if": {"column_id": "description"}, "maxWidth": "320px"},
                                {"if": {"column_id": "master_category"}, "color": COLORS["accent"]},
                            ],
                            style_data_conditional=[{
                                "if": {"state": "selected"},
                                "backgroundColor": "var(--hover-bg)",
                                "border": f"1px solid {COLORS['accent']}",
                            }],
                        ),
                    ]),
        ]),
    ]
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def apply_global_filters(source: str, year) -> pd.DataFrame:
    """Filter the global df by source and year."""
    filtered = df.copy()
    if source != "all":
        filtered = filtered[filtered["source"] == source]
    if year != "all":
        filtered = filtered[filtered["year"] == int(year)]
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
    Input("toggle-income-expenses", "value"),
    Input("overview-view-toggle",   "value"),
    Input("theme-store",            "data"),
)
def update_overview(source, year, toggles, view_mode, theme):
    import calendar
    tmpl = chart_template(theme)
    c    = _CHART[theme]

    filtered      = apply_global_filters(source, year)
    source_df     = df if source == "all" else df[df["source"] == source]
    show_expenses = "expenses" in toggles
    show_income   = "income"   in toggles

    data_df = filtered if view_mode == "monthly" else source_df

    # ── Main bar chart ─────────────────────────────────────────────────────
    fig_main = go.Figure()
    if view_mode == "monthly":
        chart_title = "MONTH BY MONTH"
        if show_expenses:
            me = monthly_expenses(filtered)
            xlabels = [calendar.month_abbr[int(m.split("-")[1])] for m in me["month_str"]]
            fig_main.add_trace(go.Bar(
                x=xlabels, y=me["total_expenses"], name="Expenses",
                marker_color=c["accent2"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
            ))
        if show_income:
            mi = monthly_income(filtered)
            xlabels_i = [calendar.month_abbr[int(m.split("-")[1])] for m in mi["month_str"]]
            fig_main.add_trace(go.Bar(
                x=xlabels_i, y=mi["total_income"], name="Income",
                marker_color=c["accent3"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
            ))
    else:
        chart_title = "YEAR TO YEAR"
        if show_expenses:
            ye = yearly_expenses(source_df)
            fig_main.add_trace(go.Bar(
                x=ye["year"].astype(str), y=ye["total_expenses"], name="Expenses",
                marker_color=c["accent2"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
            ))
        if show_income:
            yi = yearly_income(source_df)
            fig_main.add_trace(go.Bar(
                x=yi["year"].astype(str), y=yi["total_income"], name="Income",
                marker_color=c["accent3"], marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
            ))
    fig_main.update_layout(**tmpl, barmode="group", height=320)

    # ── Net chart (income − expenses per period) ───────────────────────────
    me_net = monthly_expenses(data_df).rename(columns={"total_expenses": "exp"})
    mi_net = monthly_income(data_df).rename(columns={"total_income": "inc"})
    net    = me_net.merge(mi_net, on="month_str", how="outer").fillna(0)
    net["net"] = net["inc"] - net["exp"]

    if view_mode == "monthly":
        net_x = [calendar.month_abbr[int(m.split("-")[1])] for m in net["month_str"]]
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
    cat = expenses_by_category(data_df)
    fig_cat = go.Figure(go.Bar(
        x=cat["total_expenses"], y=cat["category"],
        orientation="h",
        marker_color=PIE_COLORS[:len(cat)], marker_line_width=0,
        hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
    ))
    fig_cat.update_layout(**tmpl, height=max(300, len(cat) * 36))
    fig_cat.update_yaxes(autorange="reversed")

    # ── Summary stat cards ─────────────────────────────────────────────────
    me_s      = monthly_expenses(data_df)
    total_exp = me_s["total_expenses"].sum()
    total_inc = monthly_income(data_df)["total_income"].sum()

    if view_mode == "monthly":
        period_label = str(year) if year != "all" else "ALL YEARS"
        avg_label    = "AVG MONTHLY SPEND"
        avg_val      = me_s["total_expenses"].mean() if not me_s.empty else 0
    else:
        period_label = "ALL YEARS"
        avg_label    = "AVG YEARLY SPEND"
        ye_s         = yearly_expenses(data_df)
        avg_val      = ye_s["total_expenses"].mean() if not ye_s.empty else 0

    def stat_card(lbl, value, color):
        return card([
            html.P(lbl, className="app-label", style={
                "fontSize": "10px", "letterSpacing": "2px", "marginBottom": "8px",
            }),
            html.P(f"${value:,.2f}", style={
                "fontSize": "22px", "fontWeight": "600",
                "fontFamily": "'Syne', sans-serif", "color": color,
            }),
        ], style={"padding": "20px 24px", "marginBottom": "0"})

    stats = [
        stat_card(f"TOTAL EXPENSES · {period_label}", total_exp, c["accent2"]),
        stat_card(f"TOTAL INCOME · {period_label}",   total_inc, c["accent3"]),
        stat_card(avg_label,                           avg_val,   _CHART[theme]["text"]),
    ]
    return fig_main, chart_title, fig_net, fig_cat, stats


@app.callback(
    Output("editor-table", "data"),
    Input("editor-source-filter",       "value"),
    Input("editor-categorized-filter",  "value"),
)
def update_editor_table(source, show):
    filtered = df.copy() if source == "all" else df[df["source"] == source]
    if show == "uncategorized":
        filtered = filtered[filtered["master_category"] == ""]

    cols = ["date", "description", "amount", "source", "category", "master_category"]
    filtered = filtered[cols].copy()
    filtered["date"] = filtered["date"].astype(str)
    filtered["master_category"] = filtered["master_category"].fillna("")
    return filtered.to_dict("records")


@app.callback(
    Output("editor-table",  "data",          allow_duplicate=True),
    Output("editor-table",  "selected_rows"),
    Output("save-status",   "children"),
    Output("category-picker", "options"),
    Input("assign-btn",  "n_clicks"),
    Input("clear-btn",   "n_clicks"),
    State("editor-table",           "selected_rows"),
    State("editor-table",           "data"),
    State("category-picker",        "value"),
    State("custom-category-input",  "value"),
    State("editor-source-filter",       "value"),
    State("editor-categorized-filter",  "value"),
    prevent_initial_call=True,
)
def handle_editor_actions(assign_clicks, clear_clicks, selected_rows, table_data,
                          picked_category, custom_category, source_filter, show_filter):
    from dash import ctx

    triggered = ctx.triggered_id

    # ── Clear master_category for selected rows ────────────────────────────
    if triggered == "clear-btn":
        if not selected_rows:
            return table_data, [], "⚠ No rows selected.", dash.no_update

        descriptions = [table_data[i]["description"] for i in selected_rows]
        amounts      = [float(table_data[i]["amount"])  for i in selected_rows]
        sources      = [table_data[i]["source"]         for i in selected_rows]

        full_df = pd.read_csv(MASTER_PATH)
        for desc, amt, src in zip(descriptions, amounts, sources):
            mask = (
                (full_df["description"] == desc) &
                (full_df["amount"] == amt) &
                (full_df["source"] == src)
            )
            full_df.loc[mask, "master_category"] = None
        full_df.to_csv(MASTER_PATH, index=False)

        # Reload and rebuild table
        global df
        df = load_transactions(MASTER_PATH)
        new_data = _build_table_data(source_filter, show_filter)
        return new_data, [], f"✓ Cleared {len(selected_rows)} row(s).", dash.no_update

    # ── Assign category to selected rows ───────────────────────────────────
    if triggered == "assign-btn":
        if not selected_rows:
            return table_data, selected_rows, "⚠ No rows selected.", dash.no_update

        # Custom input takes priority over dropdown
        new_category = (custom_category or "").strip() or (picked_category or "").strip()
        if not new_category:
            return table_data, selected_rows, "⚠ Enter or select a category first.", dash.no_update

        descriptions = [table_data[i]["description"] for i in selected_rows]
        amounts      = [float(table_data[i]["amount"])  for i in selected_rows]
        sources      = [table_data[i]["source"]         for i in selected_rows]

        full_df = pd.read_csv(MASTER_PATH)
        for desc, amt, src in zip(descriptions, amounts, sources):
            mask = (
                (full_df["description"] == desc) &
                (full_df["amount"] == amt) &
                (full_df["source"] == src)
            )
            full_df.loc[mask, "master_category"] = new_category
        full_df.to_csv(MASTER_PATH, index=False)

        # Reload global df so charts reflect new categories immediately
        df = load_transactions(MASTER_PATH)

        # Rebuild category options including any new custom category
        new_options = [{"label": c, "value": c} for c in available_categories(df)]

        new_data = _build_table_data(source_filter, show_filter)
        return new_data, [], f"✓ Assigned '{new_category}' to {len(selected_rows)} row(s).", new_options

    return table_data, selected_rows, "", dash.no_update


@app.callback(
    Output("export-csv-download", "data"),
    Input("export-csv-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(_):
    cols = ["date", "description", "amount", "source", "category", "master_category"]
    export = df[cols].copy()
    export["date"] = export["date"].astype(str)
    export["master_category"] = export["master_category"].fillna("")
    return dcc.send_data_frame(export.to_csv, "transactions_export.csv", index=False)


@app.callback(
    Output("editor-table",    "data",     allow_duplicate=True),
    Output("import-status",   "children"),
    Output("category-picker", "options",  allow_duplicate=True),
    Input("import-csv-upload", "contents"),
    State("import-csv-upload", "filename"),
    State("editor-source-filter",      "value"),
    State("editor-categorized-filter", "value"),
    prevent_initial_call=True,
)
def import_csv(contents, filename, source_filter, show_filter):
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

    full_df = pd.read_csv(MASTER_PATH)
    updated = 0
    for _, row in import_df.iterrows():
        cat = str(row["master_category"]).strip() if pd.notna(row["master_category"]) else ""
        if not cat:
            continue
        mask = (
            (full_df["description"] == row["description"]) &
            (full_df["amount"].astype(float) == float(row["amount"])) &
            (full_df["source"] == row["source"])
        )
        if mask.any():
            full_df.loc[mask, "master_category"] = cat
            updated += int(mask.sum())

    full_df.to_csv(MASTER_PATH, index=False)
    global df
    df = load_transactions(MASTER_PATH)

    new_options = [{"label": c, "value": c} for c in available_categories(df)]
    new_data = _build_table_data(source_filter, show_filter)
    return new_data, f"✓ Updated {updated} row(s) from {filename}", new_options


def _build_table_data(source: str, show: str) -> list[dict]:
    """Helper to rebuild editor table data after a save."""
    filtered = df.copy() if source == "all" else df[df["source"] == source]
    if show == "uncategorized":
        filtered = filtered[filtered["master_category"] == ""]
    cols = ["date", "description", "amount", "source", "category", "master_category"]
    filtered = filtered[cols].copy()
    filtered["date"] = filtered["date"].astype(str)
    filtered["master_category"] = filtered["master_category"].fillna("")
    return filtered.to_dict("records")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
