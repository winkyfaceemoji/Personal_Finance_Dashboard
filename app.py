import base64
import os
import re

import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, ctx, Input, Output, State, Patch
import plotly.graph_objects as go

from config import get_data_dir, get_master_path, save_data_dir
from Modules.transforms import (
    load_transactions,
    monthly_expenses,
    monthly_income,
    expenses_by_category,
    filter_period,
    period_label,
    period_short_label,
    period_summary,
    period_totals,
    source_freshness,
    to_period,
    unlabeled_summary,
    PERIOD_FREQS,
    TYPICAL_LOOKBACK,
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
    "date", "post_date", "amount", "description", "institution", "source",
    "master_category", "sub_category", "original_category", "card_last4",
    "effective_category", "category_display", "month", "month_str", "year",
]).astype({"date": "datetime64[ns]", "amount": float})
df = load_transactions(MASTER_PATH, rules_path=RULES_PATH) if (MASTER_PATH and MASTER_PATH.exists()) else _EMPTY_DF

# ── Theme tokens ──────────────────────────────────────────────────────────────
# The single source of colour. Plotly figures read these hex values directly;
# theme_css() turns the same dict into CSS custom properties (--bg, --accent,
# --accent-weak, …) on .dark-theme / .light-theme, which assets/app.css uses.
# Light-theme accents are darkened so small text on --surface passes WCAG AA.
_CHART = {
    "dark": {
        "bg": "#0a0a0f", "surface": "#111318", "chip": "#0a0a0f", "border": "#252830",
        "text": "#ffffff", "subtext": "#8a8fa8", "label": "#e0e2f0",
        "accent": "#6c8aff", "accent2": "#ff6c8a", "accent3": "#6cffd4",
        "accent_weak": "rgba(108,138,255,0.18)", "on_accent": "#0a0a0f",
        "muted_line": "#4a4f63", "overlay": "rgba(10,10,15,0.9)",
        "text_weak": "#c8cadb", "stroke_weak": "rgba(255,255,255,0.05)", "fill_active": "#2a2e3a",
        "shade_strong": "rgba(0,0,0,0.5)", "shade_weak": "rgba(0,0,0,0.3)",
    },
    "light": {
        "bg": "#ffffff", "surface": "#f0f1f5", "chip": "#ffffff", "border": "#dcdee8",
        "text": "#0a0a0f", "subtext": "#5c5f72", "label": "#5c5f72",
        "accent": "#3d5bd9", "accent2": "#c42a4f", "accent3": "#067a58",
        "accent_weak": "rgba(61,91,217,0.12)", "on_accent": "#ffffff",
        "muted_line": "#c3c7d6", "overlay": "rgba(255,255,255,0.9)",
        "text_weak": "#5c5f72", "stroke_weak": "rgba(0,0,0,0.05)", "fill_active": "#d0d2e0",
        "shade_strong": "rgba(0,0,0,0.2)", "shade_weak": "rgba(0,0,0,0.1)",
    },
}

# Dash 4 components theme themselves through --Dash-* variables; map them onto
# the tokens above so dropdowns and radio items follow the theme too.
_DASH_VARS = {
    "Fill-Inverse-Strong": "surface", "Stroke-Strong": "border", "Stroke-Weak": "stroke_weak",
    "Text-Primary": "text", "Text-Strong": "text", "Text-Weak": "text_weak",
    "Text-Disabled": "subtext", "Fill-Interactive-Strong": "accent",
    "Fill-Interactive-Weak": "accent_weak", "Fill-Primary-Hover": "border",
    "Fill-Primary-Active": "fill_active", "Fill-Disabled": "border",
    "Shading-Strong": "shade_strong", "Shading-Weak": "shade_weak",
}


def theme_css() -> str:
    blocks = [f':root {{ --gear-icon: url("{GEAR_ICON_URI}"); }}']
    for name, tokens in _CHART.items():
        decls = [f"--{k.replace('_', '-')}: {v};" for k, v in tokens.items()]
        decls += [f"--Dash-{k}: {tokens[v]};" for k, v in _DASH_VARS.items()]
        blocks.append(f".{name}-theme {{ {' '.join(decls)} }}")
    return "\n".join(blocks)


def chart_template(theme="dark"):
    c = _CHART[theme]
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=c["text"], family="IBM Plex Mono, monospace"),
        xaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"]),
        yaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"],
                   tickprefix="$", tickformat=",.0f"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=c["surface"], bordercolor=c["border"],
                        font=dict(color=c["text"], family="IBM Plex Mono, monospace")),
        margin=dict(l=48, r=20, t=24, b=40),
    )


def empty_figure(message: str, theme: str, height: int) -> go.Figure:
    """A blank chart that says why it's blank, instead of Plotly's bare grid."""
    c = _CHART[theme]
    fig = go.Figure()
    fig.update_layout(**chart_template(theme), height=height)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5,
                       xref="paper", yref="paper", font=dict(color=c["subtext"], size=13))
    return fig


# Categories beyond this rank collapse into one muted "Other" bar; the
# drilldown reuses it to reconstruct what that bar aggregates.
CAT_TOP_N = 9

# How many bars the spending-over-time chart shows per granularity (None = all).
CHART_PERIODS = {"week": 26, "month": 24, "year": None}

FREQ_NOUN = {"week": "week", "month": "month", "year": "year"}


def card(children, **kwargs):
    return html.Div(children, className="app-card", **kwargs)


def _dollar(v: float) -> str:
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _dollar0(v: float) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


# ── Data-relative time ────────────────────────────────────────────────────────
# Periods are anchored to the latest transaction, not to today: with exports a
# few weeks old, "this month" would otherwise be empty and every card $0.

def _as_of() -> pd.Timestamp:
    dates = df["date"].dropna()
    return dates.max().normalize() if not dates.empty else pd.Timestamp.today().normalize()


def _period_bounds(freq: str) -> tuple[pd.Period, pd.Period]:
    dates = df["date"].dropna()
    if dates.empty:
        p = to_period(pd.Timestamp.today(), freq)
        return p, p
    return to_period(dates.min(), freq), to_period(dates.max(), freq)


def _selected_period(store) -> tuple[str, pd.Period]:
    freq = (store or {}).get("freq", "month")
    freq = freq if freq in PERIOD_FREQS else "month"
    start = (store or {}).get("start")
    return freq, (to_period(start, freq) if start else _period_bounds(freq)[1])


def _prev_name(p: pd.Period, freq: str) -> str:
    """How the previous period is named in a delta line."""
    if freq == "week":
        return "last week"
    return period_label(p - 1, freq)


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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
    <style>__THEME_CSS__</style>
    {%css%}
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''.replace("__THEME_CSS__", theme_css())

# ── Layout ────────────────────────────────────────────────────────────────────
_OVERLAY_HIDDEN  = {"display": "none"}
_OVERLAY_VISIBLE = {"display": "flex"}
_MENU_HIDDEN     = {"display": "none"}
_MENU_VISIBLE    = {"display": "flex"}

_PILL_INPUT = {"display": "none"}


def _settings_button(label, id_, **kwargs):
    return html.Button(label, id=id_, n_clicks=0, className="btn-secondary btn-small", **kwargs)


app.layout = html.Div(
    id="app-root",
    className="dark-theme",
    children=[
        # Theme choice survives page reloads (browser local storage)
        dcc.Store(id="theme-store", data="dark", storage_type="local"),

        # Data-freshness counter — incremented by any write operation so dependent
        # callbacks (charts, header notes) re-render automatically.
        dcc.Store(id="refresh-trigger", data=0),

        dcc.Store(id="settings-menu-open", data=False),

        # The selected period: {"freq": "week"|"month"|"year", "start": "YYYY-MM-DD"}.
        # Drives the stat cards, the spending chart highlight and the categories.
        dcc.Store(id="period-store"),

        # Clicked category bar — drives both the highlight and the drilldown.
        # A Store (not clickData directly) so rebuilding the chart doesn't
        # clear the selection.
        dcc.Store(id="selected-category"),

        # ── Setup overlay (shown when no data directory is configured) ──────
        html.Div(
            id="setup-overlay",
            style=_OVERLAY_HIDDEN if (MASTER_PATH and MASTER_PATH.exists()) else _OVERLAY_VISIBLE,
            children=html.Div(className="app-card setup-card", children=[
                html.H1(["FINANCE ", html.Span("DASHBOARD", className="accent")], className="wordmark"),
                html.P("Choose the folder that contains your RAW bank exports. "
                       "The dashboard keeps its SORTED output (and your labels) next to them.",
                       className="setup-copy"),
                html.Div(className="setup-row", children=[
                    dcc.Input(
                        id="setup-path-input",
                        type="text",
                        placeholder=r"e.g. C:\Users\you\Finance\Data",
                        debounce=False,
                        className="setup-input",
                    ),
                    html.Button("BROWSE", id="setup-browse-btn", n_clicks=0, className="btn-secondary"),
                ]),
                html.Div(className="setup-row", children=[
                    html.Button("CANCEL", id="setup-cancel-btn", n_clicks=0,
                                className="btn-secondary", style={"flex": "1"}),
                    html.Button("SAVE & LAUNCH", id="setup-save-btn", n_clicks=0,
                                className="btn-primary", style={"flex": "2"}),
                ]),
                html.Div(id="setup-status", className="setup-status"),
            ]),
        ),

        # Click-catcher behind the open settings menu (closes it)
        html.Div(id="settings-backdrop", n_clicks=0, style=_MENU_HIDDEN),

        # ── Header: wordmark, data freshness, unlabeled note; gear top-right ──
        html.Div(className="app-header", children=[
            html.H1(["FINANCE ", html.Span("DASHBOARD", className="accent")], className="wordmark"),
            html.P(id="data-updated", className="header-meta"),
            # Shown when the newest transaction is over a week old
            html.P(id="stale-note", className="notice"),
            # Unlabeled rows are ignored by every total — count and size them
            html.P(id="unlabeled-note", className="notice warn-text"),

            html.Div(id="settings-menu-wrapper", children=[
                html.Button(html.Span(className="gear-icon"), id="settings-menu-btn",
                            n_clicks=0, title="Settings"),
                html.Div(id="settings-menu-panel", className="app-card", style=_MENU_HIDDEN, children=[
                    html.Div("DATA", className="settings-label"),
                    html.Div(className="settings-row", children=[
                        dcc.Upload(
                            id="import-csv-upload",
                            children=html.Button("IMPORT CSV", className="btn-secondary btn-small",
                                                 style={"width": "100%"}),
                            accept=".csv",
                            multiple=False,
                        ),
                        _settings_button("EXPORT CSV", "export-csv-btn"),
                    ]),
                    dcc.Download(id="export-csv-download"),
                    _settings_button("RELOAD DATA", "reload-data-btn"),
                    html.Div(className="divider", style={"margin": "4px 0"}),
                    html.Div("SOURCE", className="settings-label"),
                    _settings_button("CHANGE DATA FOLDER", "open-setup-btn"),
                    html.Div(className="divider", style={"margin": "4px 0"}),
                    html.Div("THEME", className="settings-label"),
                    html.Div(className="settings-row", children=[
                        _settings_button("LIGHT", "theme-light-btn"),
                        _settings_button("DARK", "theme-dark-btn"),
                    ]),
                    # Single status slot at the bottom — reload + import messages
                    # land here. dcc.Loading tracks these spans (the slow
                    # callbacks output to them) and shows a fullscreen spinner
                    # while they run, so it never overlaps the menu buttons.
                    dcc.Loading(
                        id="data-op-loading", type="circle", color=_CHART["dark"]["accent"],
                        fullscreen=True,
                        children=[
                            html.Span(id="reload-status", className="settings-status"),
                            html.Span(id="import-status", className="settings-status"),
                        ],
                    ),
                ]),
            ]),
        ]),

        # ── Period bar: Week / Month / Year + ‹ period › stepper ─────────────
        html.Div(className="period-bar", children=[
            dcc.RadioItems(
                id="period-freq",
                className="pills",
                options=[
                    {"label": "WEEK",  "value": "week"},
                    {"label": "MONTH", "value": "month"},
                    {"label": "YEAR",  "value": "year"},
                ],
                value="month",
                inline=True,
                inputStyle=_PILL_INPUT,
                persistence=True, persistence_type="local",
            ),
            html.Div(className="stepper", children=[
                html.Button("‹", id="period-prev", n_clicks=0, className="step-btn", title="Previous period"),
                html.Div(className="period-text", children=[
                    html.Div(id="period-label", className="period-label"),
                    html.Div(id="period-sub", className="hint"),
                ]),
                html.Button("›", id="period-next", n_clicks=0, className="step-btn", title="Next period"),
                html.Button("LATEST", id="period-latest", n_clicks=0, className="btn-secondary btn-small",
                            title="Jump to the period with your newest transactions"),
            ]),
        ]),

        # ── Stat cards for the selected period ───────────────────────────────
        html.Div(id="period-stats", className="stats-grid"),

        # Pace: spending so far vs typical by this point (in-progress periods only)
        html.Div(id="pace-strip", className="app-card pace-card"),

        # ── Spending over time: one bar per week / month / year ───────────────
        card([
            html.Div(className="card-head", children=[
                # Metric selector doubles as the card title (left)
                dcc.Dropdown(
                    id="cashflow-metric",
                    className="title-dropdown",
                    options=[
                        {"label": "Expenses",      "value": "expenses"},
                        {"label": "Income",        "value": "income"},
                        {"label": "Net Cash Flow", "value": "net"},
                    ],
                    value="expenses",
                    clearable=False,
                    searchable=False,
                    style={"width": "190px"},
                ),
                html.Div(id="period-chart-range", className="hint"),
            ]),
            dcc.Graph(id="period-chart", config={"displayModeBar": False}),
        ]),

        # ── Categories for the selected period, with click drilldown ─────────
        card([
            html.Div(className="card-head", children=[
                html.Div([
                    html.Div(id="category-title", className="app-label"),
                    html.Div("click a bar to see its top merchants", className="hint"),
                ]),
            ]),
            dcc.Graph(id="category-chart", config={"displayModeBar": False}),
            html.Div(id="category-drilldown"),
        ]),

        # ── Seasonality: same calendar month, year over year ─────────────────
        card([
            html.Div(className="card-head", children=[
                html.Div([
                    html.Div(id="seasonality-title", className="app-label"),
                    html.Div("each line is a year · click a year in the legend to hide or show it",
                             className="hint"),
                ]),
                dcc.RadioItems(
                    id="seasonality-metric",
                    className="pills",
                    options=[
                        {"label": "EXPENSES", "value": "expenses"},
                        {"label": "INCOME",   "value": "income"},
                    ],
                    value="expenses",
                    inline=True,
                    inputStyle=_PILL_INPUT,
                ),
            ]),
            dcc.Graph(id="seasonality-chart", config={"displayModeBar": False}),
        ]),
    ]
)


# ── Callbacks ─────────────────────────────────────────────────────────────────

# ── Theme ─────────────────────────────────────────────────────────────────────

@app.callback(
    Output("theme-store", "data"),
    Input("theme-light-btn", "n_clicks"),
    Input("theme-dark-btn",  "n_clicks"),
    prevent_initial_call=True,
)
def set_theme(_, __):
    return "light" if ctx.triggered_id == "theme-light-btn" else "dark"


@app.callback(
    Output("app-root",        "className"),
    Output("theme-light-btn", "className"),
    Output("theme-dark-btn",  "className"),
    Input("theme-store",      "data"),
)
def apply_theme(theme):
    # Runs on load too, so a theme restored from local storage is applied
    theme = theme if theme in _CHART else "dark"
    base = "btn-secondary btn-small"
    return (f"{theme}-theme",
            f"{base} active" if theme == "light" else base,
            f"{base} active" if theme == "dark" else base)


# ── Settings menu ─────────────────────────────────────────────────────────────

@app.callback(
    Output("settings-menu-open",  "data"),
    Output("settings-menu-panel", "style"),
    Output("settings-backdrop",   "style"),
    Input("settings-menu-btn",    "n_clicks"),
    Input("settings-backdrop",    "n_clicks"),
    Input("theme-light-btn",      "n_clicks"),
    Input("theme-dark-btn",       "n_clicks"),
    Input("export-csv-btn",       "n_clicks"),
    Input("open-setup-btn",       "n_clicks"),
    State("settings-menu-open",   "data"),
    prevent_initial_call=True,
)
def toggle_settings_menu(*args):
    # The gear toggles; a click outside the panel (backdrop) or any action
    # that's finished at once closes it. Reload / import keep it open so their
    # status line stays visible.
    is_open  = args[-1]
    new_open = (not is_open) if ctx.triggered_id == "settings-menu-btn" else False
    style    = _MENU_VISIBLE if new_open else _MENU_HIDDEN
    return new_open, style, ({"display": "block"} if new_open else _MENU_HIDDEN)


# ── Header ────────────────────────────────────────────────────────────────────

@app.callback(
    Output("data-updated", "children"),
    Output("stale-note",   "children"),
    Input("refresh-trigger", "data"),
)
def update_data_note(_refresh):
    if df.empty:
        return "No data loaded", ""
    as_of = _as_of()
    fresh = source_freshness(df)
    parts = [f"{len(fresh)} source{'s' if len(fresh) != 1 else ''}: {', '.join(sorted(fresh.index))}",
             f"data through {as_of:%b} {as_of.day}, {as_of.year}"]
    # Name any source lagging the newest by over a week — its recent
    # transactions are missing, so recent totals undercount
    lagging = [f"{src} through {d:%b} {d.day}" for src, d in fresh.items()
               if (as_of - d.normalize()).days > 7]
    if lagging:
        parts.append("behind: " + ", ".join(lagging))

    stale = ""
    age = (pd.Timestamp.today().normalize() - as_of).days
    if age > 7:
        stale = (f"No transactions in the last {age} days. Download newer statements into "
                 f"your RAW folder and use Settings → Reload data to track the current week.")
    return " · ".join(parts), stale


@app.callback(
    Output("unlabeled-note", "children"),
    Input("refresh-trigger", "data"),
)
def update_unlabeled_note(_refresh):
    # Anything outside Expense / Income / Transfer (including blank) never
    # reaches a total — Transfer is deliberate, the rest deserve a flag.
    u = unlabeled_summary(df)
    if u["count"] == 0:
        return ""
    return (f"⚠ {u['count']:,} of {u['total']:,} transactions ({_dollar0(u['amount'])}) have no "
            f"Expense / Income / Transfer label and aren't counted. Label them with "
            f"Settings → Export CSV, then Import CSV.")


# ── Period navigation ─────────────────────────────────────────────────────────

@app.callback(
    Output("period-store", "data"),
    Output("period-chart", "clickData"),
    Input("period-freq",   "value"),
    Input("period-prev",   "n_clicks"),
    Input("period-next",   "n_clicks"),
    Input("period-latest", "n_clicks"),
    Input("period-chart",  "clickData"),
    Input("refresh-trigger", "data"),
    State("period-store",  "data"),
)
def navigate_period(freq, _prev, _next, _latest, click, _refresh, store):
    freq = freq if freq in PERIOD_FREQS else "month"
    first, last = _period_bounds(freq)

    cur = None
    if store and store.get("start"):
        old_freq = store.get("freq", freq)
        old = to_period(store["start"], old_freq)
        # Switching granularity keeps your place: Week of Dec 22 → Dec 2025
        cur = old if old_freq == freq else to_period(min(old.end_time.normalize(), _as_of()), freq)

    trig = ctx.triggered_id
    if cur is None or trig == "period-latest":
        cur = last
    elif trig == "period-prev":
        cur -= 1
    elif trig == "period-next":
        cur += 1
    elif trig == "period-chart" and click:
        cd = click["points"][0].get("customdata")
        if cd:
            cur = to_period(cd[0] if isinstance(cd, list) else cd, freq)

    cur = min(max(cur, first), last)
    # Reset clickData so clicking the same bar again still registers
    return {"freq": freq, "start": cur.start_time.strftime("%Y-%m-%d")}, None


@app.callback(
    Output("period-label",  "children"),
    Output("period-sub",    "children"),
    Output("period-prev",   "disabled"),
    Output("period-next",   "disabled"),
    Output("period-latest", "disabled"),
    Input("period-store",   "data"),
)
def update_period_header(store):
    freq, p = _selected_period(store)
    first, last = _period_bounds(freq)
    as_of = _as_of()
    start = p.start_time.normalize()
    end   = p.end_time.normalize()
    if start <= as_of < end:
        day   = (as_of - start).days + 1
        total = (end - start).days + 1
        sub = f"in progress · data through {as_of:%b} {as_of.day} · day {day} of {total}"
    elif p == last:
        sub = "latest complete " + FREQ_NOUN[freq]
    else:
        sub = ""
    return period_label(p, freq), sub, p <= first, p >= last, p >= last


# ── Stat cards + pace ─────────────────────────────────────────────────────────

def _pct_delta(cur, prior):
    """Relative change, or None when either side is zero (a ▲/▼100% against
    nothing says more about missing data than about your money)."""
    if not prior or not cur:
        return None
    # Divide by |prior| so the arrow tracks the real direction of change: a
    # negative prior (e.g. last period's net was negative) must not flip the
    # sign of an improvement.
    return (cur - prior) / abs(prior) * 100


def _delta_line(change, suffix, higher_is_good, unit="%", tip=None):
    # Colour signals good/bad for THIS metric, not merely up/down: more
    # income is green, more spending is red.
    if change is None:
        body = [html.Span("—"), f" {suffix}"]
    else:
        up = change >= 0
        cls = "delta-good" if up == higher_is_good else "delta-bad"
        if unit == "$":
            amount = _dollar0(abs(change))
        elif unit == "%" and change >= 1000:
            # Past +1000% a multiple reads better: ▲21× rather than ▲1977%
            amount = f"{1 + change / 100:.0f}×"
        else:
            amount = f"{abs(change):.0f}{unit}"
        body = [html.Span(f"{'▲' if up else '▼'}{amount}", className=cls), f" {suffix}"]
    return html.Div(body, className="stat-delta", title=tip)


def _stat_card(title, value, lines):
    return html.Div(className="stat-card", children=[
        html.Div(title, className="stat-title"),
        html.Div(value, className="stat-value"),
        *lines,
    ])


@app.callback(
    Output("period-stats", "children"),
    Output("pace-strip",   "children"),
    Input("period-store",  "data"),
    Input("theme-store",   "data"),
    Input("refresh-trigger", "data"),
)
def update_stats(store, theme, _refresh):
    theme = theme if theme in _CHART else "dark"
    c = _CHART[theme]
    freq, p = _selected_period(store)
    s = period_summary(df, freq, p, _as_of())
    cur, prev, typ = s["cur"], s["prev"], s["typical"]

    n = s["n_typical"]
    lookback = TYPICAL_LOOKBACK[freq]
    if n:
        typ_tip = f"Median of the previous {n} {FREQ_NOUN[freq]}{'s' if n != 1 else ''}"
        if lookback:
            typ_tip += f" (looks back up to {lookback})"
    else:
        typ_tip = "No earlier periods in your data to compare against"
    if s["partial"]:
        prev_sfx = f"vs same point {_prev_name(p, freq)}" if freq == "week" else \
                   f"vs same point in {_prev_name(p, freq)}"
        typ_sfx  = "vs typical by now"
        if n:
            typ_tip += f", over their first {s['days_elapsed']} days"
    else:
        prev_sfx = f"vs {_prev_name(p, freq)}"
        typ_sfx  = f"vs typical {FREQ_NOUN[freq]}"

    def _lines(key, higher_is_good):
        return [
            _delta_line(_pct_delta(cur[key], prev[key]) if prev else None, prev_sfx, higher_is_good),
            _delta_line(_pct_delta(cur[key], typ[key]) if typ else None, typ_sfx, higher_is_good,
                        tip=typ_tip),
        ]

    def _net_lines():
        # Net often sits near zero or flips sign, where a % change explodes
        # (▼9205%) — compare it in dollars instead
        return [
            _delta_line(cur["net"] - prev["net"] if prev else None, prev_sfx, True, unit="$"),
            _delta_line(cur["net"] - typ["net"] if typ else None, typ_sfx, True, unit="$",
                        tip=typ_tip),
        ]

    def _pt(a, b):
        return a - b if a is not None and b is not None else None

    so_far = " SO FAR" if s["partial"] else ""
    cards = [
        _stat_card("SPENT" + so_far,  _dollar(cur["exp"]), _lines("exp", False)),
        _stat_card("INCOME" + so_far, _dollar(cur["inc"]), _lines("inc", True)),
        _stat_card("NET" + so_far,    _dollar(cur["net"]), _net_lines()),
        # Savings rate is already a percentage: compare in points, not %
        _stat_card("SAVINGS RATE",
                   f"{s['rate']:.0f}%" if s["rate"] is not None else "—",
                   [_delta_line(_pt(s["rate"], s["prev_rate"]), prev_sfx, True, unit="pt"),
                    _delta_line(_pt(s["rate"], s["typical_rate"]), typ_sfx, True, unit="pt",
                                tip=typ_tip)]),
    ]

    # ── Pace: only while the period is still in progress ──
    pace = []
    if s["partial"]:
        spent   = cur["exp"]
        by_now  = typ["exp"] if typ else None
        full    = s["typical_full"]["exp"] if s["typical_full"] else None
        noun    = FREQ_NOUN[freq]
        if by_now is not None and full is not None:
            diff   = spent - by_now
            ahead  = diff > 0
            status = (f"{_dollar0(abs(diff))} {'over' if ahead else 'under'} your typical pace"
                      if abs(diff) >= 1 else "Right on your typical pace")
            scale  = max(full, spent, by_now) * 1.05 or 1
            fill_c = c["accent2"] if ahead else c["accent3"]
            pace = [
                html.Div(className="pace-head", children=[
                    html.Div([html.Div(f"PACE · DAY {s['days_elapsed']} OF {s['days_total']}",
                                       className="app-label"),
                              html.Div(f"spending so far vs a typical {noun} at the same point",
                                       className="hint")]),
                    html.Div(status, className="pace-status",
                             style={"color": fill_c}),
                ]),
                html.Div(className="pace-track", children=[
                    html.Div(className="pace-fill",
                             style={"width": f"{min(spent / scale, 1) * 100:.1f}%", "background": fill_c}),
                    html.Div(className="pace-marker", title="Typical spending by now",
                             style={"left": f"{min(by_now / scale, 1) * 100:.1f}%"}),
                ]),
                html.Div(className="pace-legend", children=[
                    html.Span(f"Spent {_dollar0(spent)}"),
                    html.Span(f"│ typical by now {_dollar0(by_now)}"),
                    html.Span(f"typical full {noun} {_dollar0(full)}"),
                ]),
            ]
        else:
            pace = [html.Div(className="pace-head", children=[
                html.Div(f"PACE · DAY {s['days_elapsed']} OF {s['days_total']}", className="app-label"),
                html.Div(f"Not enough history yet to compare this {noun} against.", className="hint"),
            ])]
    return cards, pace


# ── Spending over time ────────────────────────────────────────────────────────

@app.callback(
    Output("period-chart",       "figure"),
    Output("period-chart-range", "children"),
    Input("period-store",    "data"),
    Input("cashflow-metric", "value"),
    Input("theme-store",     "data"),
    Input("refresh-trigger", "data"),
)
def update_period_chart(store, metric, theme, _refresh):
    theme  = theme if theme in _CHART else "dark"
    c      = _CHART[theme]
    metric = metric if metric in ("net", "expenses", "income") else "expenses"
    freq, p = _selected_period(store)
    noun = FREQ_NOUN[freq]

    totals = period_totals(df, freq)
    if totals.empty:
        return empty_figure("No transactions yet", theme, 300), ""

    # Window: the latest N periods — or, when the selected period is older
    # than that, a window that keeps it on screen
    n = CHART_PERIODS[freq]
    last_i = len(totals) - 1
    sel_i  = totals.index.get_loc(p) if p in totals.index else last_i
    if n is None:
        lo, hi = 0, last_i
    else:
        hi = last_i if sel_i > last_i - n else min(last_i, sel_i + n // 4)
        lo = max(0, hi - n + 1)
    win = totals.iloc[lo:hi + 1]

    col, name = {"expenses": ("exp", "Spent"), "income": ("inc", "Income"), "net": ("net", "Net")}[metric]
    vals = win[col].tolist()
    if metric == "net":
        colors = [c["accent3"] if v >= 0 else c["accent2"] for v in vals]
    else:
        colors = [c["accent2"] if metric == "expenses" else c["accent3"]] * len(vals)

    # The in-progress period gets a hatch so a short bar reads as "not over yet"
    as_of = _as_of()
    in_progress = [q.start_time.normalize() <= as_of < q.end_time.normalize() for q in win.index]
    labels = [period_label(q, freq) + (" (in progress)" if ip else "")
              for q, ip in zip(win.index, in_progress)]

    fig = go.Figure(go.Bar(
        x=[period_short_label(q, freq) for q in win.index],
        y=vals,
        marker=dict(
            color=colors,
            opacity=[1.0 if q == p else 0.6 for q in win.index],
            line=dict(width=[2 if q == p else 0 for q in win.index], color=c["text"]),
            pattern=dict(shape=["/" if ip else "" for ip in in_progress],
                         fgcolor=c["surface"], fillmode="overlay", solidity=0.3),
        ),
        customdata=[[q.start_time.strftime("%Y-%m-%d"), lbl] for q, lbl in zip(win.index, labels)],
        hovertemplate="<b>%{customdata[1]}</b><br>" + name + ": $%{y:,.2f}<extra></extra>",
    ))

    # Typical level: median of the complete periods on screen
    complete = [v for v, ip in zip(vals, in_progress) if not ip]
    if len(complete) >= 3:
        typical = float(pd.Series(complete).median())
        fig.add_hline(y=typical, line_dash="dash", line_color=c["subtext"], line_width=1,
                      annotation_text=f"typical {_dollar0(typical)}", annotation_position="top left",
                      annotation_font=dict(color=c["subtext"], size=11))
    if metric == "net":
        fig.add_hline(y=0, line_color=c["border"], line_width=1)

    fig.update_layout(**chart_template(theme), height=300, showlegend=False, bargap=0.25)
    fig.update_xaxes(type="category", showgrid=False)

    span = f"{len(win)} {noun}{'s' if len(win) != 1 else ''}"
    return fig, f"{span} · click a bar to open that {noun}"


# ── Categories ────────────────────────────────────────────────────────────────

def _category_split(pdf: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Top-N categories by spend in a slice of rows, plus the names that roll
    up into "Other". Shared by the chart and the drilldown so both agree."""
    cat = expenses_by_category(pdf)
    cat = cat[cat["total_expenses"] > 0]   # refund-only categories have no bar
    top = cat.head(CAT_TOP_N).copy()
    rest = cat.iloc[CAT_TOP_N:]
    if not rest.empty:
        top = pd.concat([top, pd.DataFrame([{
            "category": f"Other · {len(rest)} categories",
            "total_expenses": rest["total_expenses"].sum(),
        }])], ignore_index=True)
    return top, rest["category"].tolist()


@app.callback(
    Output("category-chart", "figure"),
    Output("category-title", "children"),
    Input("period-store",    "data"),
    Input("theme-store",     "data"),
    Input("refresh-trigger", "data"),
    State("selected-category", "data"),
)
def update_category_chart(store, theme, _refresh, sel_cat):
    theme = theme if theme in _CHART else "dark"
    c = _CHART[theme]
    freq, p = _selected_period(store)
    label = period_label(p, freq)
    title = f"SPEND BY CATEGORY · {label}"
    if ctx.triggered_id == "period-store":
        # select_category clears the selection on a period change; don't dim
        # the new period's bars with the stale one it's about to clear
        sel_cat = None

    top, _ = _category_split(filter_period(df, p))
    if top.empty:
        return empty_figure(f"No labeled expenses in {label}", theme, 160), title

    total = top["total_expenses"].sum()
    names = top["category"].tolist()
    fig = go.Figure(go.Bar(
        orientation="h",
        y=names,
        x=top["total_expenses"],
        marker=dict(
            color=[c["subtext"] if n_.startswith("Other · ") else c["accent"] for n_ in names],
            opacity=[0.35 if sel_cat and n_ != sel_cat else 1.0 for n_ in names],
        ),
        text=[f"{_dollar0(v)} · {v / total * 100:.0f}%" for v in top["total_expenses"]],
        textposition="outside",
        textfont=dict(color=c["text"], size=11),
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**chart_template(theme), height=max(100, 24 + 40 * len(names)),
                      showlegend=False, bargap=0.3)
    fig.update_layout(margin=dict(l=8, r=110, t=8, b=8))
    fig.update_yaxes(autorange="reversed", automargin=True, showgrid=False,
                     tickprefix="", ticksuffix="  ")
    fig.update_xaxes(visible=False)
    return fig, title


@app.callback(
    Output("selected-category", "data"),
    Output("category-chart",    "clickData"),
    Input("category-chart",     "clickData"),
    Input("period-store",       "data"),
    State("selected-category",  "data"),
    prevent_initial_call=True,
)
def select_category(click_data, _store, current):
    # Store the clicked bar's label. Always reset clickData to None afterwards
    # so re-clicking the SAME bar registers as a change (Dash only fires on a
    # changed input). A period change clears the selection; clicking the
    # selected bar again toggles it off.
    if ctx.triggered_id == "period-store":
        return None, None
    if not click_data:
        return dash.no_update, dash.no_update
    label = click_data["points"][0].get("y")
    return (None if label == current else label), None


@app.callback(
    Output("category-chart", "figure", allow_duplicate=True),
    Input("selected-category", "data"),
    State("category-chart",    "figure"),
    prevent_initial_call=True,
)
def highlight_category(sel_cat, fig):
    # Patch only the bar opacities — a click shouldn't rebuild the chart
    if not fig or not fig.get("data") or "y" not in fig["data"][0]:
        return dash.no_update
    names = fig["data"][0].get("y") or []
    patched = Patch()
    patched["data"][0]["marker"]["opacity"] = [0.35 if sel_cat and n_ != sel_cat else 1.0 for n_ in names]
    return patched


@app.callback(
    Output("category-drilldown", "children"),
    Input("selected-category",   "data"),
    Input("theme-store",         "data"),
    State("period-store",        "data"),
)
def category_drilldown(label, _theme, store):
    if not label:
        return []
    freq, p = _selected_period(store)
    scope_lbl = f" · {period_label(p, freq)}"

    pdf = filter_period(df, p)
    expenses = pdf[pdf["master_category"] == "Expense"].copy()
    if expenses.empty:
        return []
    expenses["cat"] = expenses["category_display"].where(
        expenses["category_display"] != "", "Uncategorized")
    expenses["amount"] = -expenses["amount"]

    def _prop_row(name, amt, cnt, total, muted=False):
        frac = amt / total if total > 0 else 0
        return html.Div(className="drill-row", children=[
            html.Span(name, title=name, className="drill-name" + (" muted-text" if muted else "")),
            html.Div(className="drill-track", children=html.Div(
                className="drill-fill" + (" muted" if muted else ""),
                # clamp: a refund-heavy group can net negative, which would
                # otherwise emit an invalid negative CSS width
                style={"width": f"{max(frac, 0) * 100:.0f}%"},
            )),
            html.Span(f"${amt:,.2f} · {frac * 100:.0f}% · {int(cnt)} txn{'s' if cnt != 1 else ''}",
                      className="drill-stat"),
        ])

    def _panel(title, right, rows, txns):
        big = txns.loc[txns["amount"].idxmax()]
        big_date = pd.to_datetime(big["date"])
        return html.Div(className="drilldown", children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px"}, children=[
                html.Span(title, className="app-label"),
                html.Span(right, style={"fontSize": "12px", "fontWeight": "600"}),
            ]),
            html.Div(className="divider"),
            html.Div("TOP MERCHANTS", className="settings-label", style={"marginBottom": "10px"}),
            *rows,
            html.Div(className="divider"),
            html.Div([
                "Largest: ",
                html.Span(f"${big['amount']:,.2f}", className="warn-text", style={"fontWeight": "600"}),
                f" · {big['description']} · {big_date:%b} {big_date.day}",
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
        g = (txns.assign(merchant=txns["description"].map(_merchant))
             .groupby("merchant")["amount"].agg(["sum", "count"])
             .sort_values("sum", ascending=False))
        rest = g.iloc[5:]
        rows = [_prop_row(name, r["sum"], r["count"], total) for name, r in g.head(5).iterrows()]
        if not rest.empty:
            rows.append(_prop_row(f"OTHER · {len(rest)} merchants",
                                  rest["sum"].sum(), rest["count"].sum(), total, muted=True))
        return _panel(title, f"${total:,.2f} · {count} txns · ${total / count:,.2f} avg", rows, txns)

    # ── "Other" bar: top merchants across the small categories it aggregates ─
    if str(label).startswith("Other · "):
        _, rest_names = _category_split(pdf)
        other_txns = expenses[expenses["cat"].isin(rest_names)]
        if other_txns.empty:
            return []
        return _top_merchants_panel(other_txns, f"OTHER CATEGORIES{scope_lbl}")

    # ── Real category: its top merchants ─────────────────────────────────────
    cat_txns = expenses[expenses["cat"] == label]
    if cat_txns.empty:
        return []
    return _top_merchants_panel(cat_txns, f"{label.upper()}{scope_lbl}")


# ── Seasonality ───────────────────────────────────────────────────────────────

@app.callback(
    Output("seasonality-chart", "figure"),
    Output("seasonality-title", "children"),
    Input("seasonality-metric", "value"),
    Input("period-store",       "data"),
    Input("theme-store",        "data"),
    Input("refresh-trigger",    "data"),
)
def update_seasonality(metric, store, theme, _refresh):
    import calendar
    theme  = theme if theme in _CHART else "dark"
    c      = _CHART[theme]
    metric = metric if metric in ("expenses", "income") else "expenses"
    metric_lbl = "EXPENSES" if metric == "expenses" else "INCOME"
    title = f"{metric_lbl} BY CALENDAR MONTH"

    if metric == "expenses":
        series = monthly_expenses(df).rename(columns={"total_expenses": "val"})
    else:
        series = monthly_income(df).rename(columns={"total_income": "val"})
    val_map   = {(int(m[:4]), int(m[5:7])): v for m, v in zip(series["month_str"], series["val"])}
    years_all = sorted({yr for yr, _ in val_map})
    if not years_all:
        return empty_figure(f"No labeled {metric} yet", theme, 320), title

    # The highlighted year follows the selected period
    _, p = _selected_period(store)
    hi_yr = p.start_time.year if p.start_time.year in years_all else years_all[-1]

    x_lbls = [calendar.month_abbr[m_] for m_ in range(1, 13)]
    fig = go.Figure()
    # Highlighted year drawn last so it sits on top of the muted ones
    for yr in [y for y in years_all if y != hi_yr] + [hi_yr]:
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
        fig.add_trace(go.Scatter(
            x=x_lbls, y=ys, name=str(yr),
            mode="lines+markers",
            line=dict(color=c["accent"] if is_hi else c["muted_line"], width=3.5 if is_hi else 1.5),
            marker=dict(size=8 if is_hi else 4),
            legendrank=yr,  # legend stays chronological whatever the draw order
            customdata=cds,
            hovertemplate=("<b>%{x} " + str(yr) + "</b><br>"
                           + metric_lbl.title() + ": $%{y:,.2f}<br>%{customdata}<extra></extra>"),
        ))
    fig.update_layout(**chart_template(theme), height=320)
    return fig, title


# ── Import / export / reload ──────────────────────────────────────────────────

@app.callback(
    Output("export-csv-download", "data"),
    Input("export-csv-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(_):
    cols = ["date", "description", "amount", "institution", "source", "card_last4", "original_category", "master_category", "sub_category"]
    export = df[cols].copy()
    export["date"] = export["date"].dt.strftime("%Y-%m-%d")
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

    import io
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
        # Rebuild the folder that's on screen — not whatever get_data_dir()
        # resolves, which differs when FINANCE_DATA_DIR is set
        _run_ingest_pipeline(MASTER_PATH.parent.parent)
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
        return "✓ Reloaded", (trigger or 0) + 1
    except Exception as e:
        return f"⚠ {e}", dash.no_update


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
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("setup-save-btn", "n_clicks"),
    State("setup-path-input", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def save_setup(n_clicks, path, trigger):
    global df, MASTER_PATH

    if not path or not path.strip():
        return dash.no_update, "Please enter or browse to a folder path.", dash.no_update

    data_dir = Path(path.strip())
    master   = get_master_path(data_dir)

    if not data_dir.exists():
        return dash.no_update, f"Folder not found: {data_dir}", dash.no_update

    if not master.exists():
        try:
            _run_ingest_pipeline(data_dir)
        except Exception as e:
            return dash.no_update, f"Failed to run ingest: {e}", dash.no_update
        if not master.exists():
            return dash.no_update, f"Ingest ran but master file was not created at {master}", dash.no_update

    save_data_dir(str(data_dir))
    MASTER_PATH = master
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception as e:
        return dash.no_update, f"Error loading data: {e}", dash.no_update

    # Bump the refresh counter so every card re-renders from the new folder
    return _OVERLAY_HIDDEN, "", (trigger or 0) + 1


if __name__ == "__main__":
    # Local-only and debug-off by default: the dashboard has no login, so
    # binding to every interface would expose your finances (export, import,
    # change-folder) to anyone on the same network. Docker sets
    # FINANCE_HOST=0.0.0.0 inside the container — see the Dockerfile.
    host  = os.environ.get("FINANCE_HOST", "127.0.0.1")
    debug = os.environ.get("FINANCE_DEBUG", "0") == "1"
    app.run(debug=debug, host=host, port=8050)
