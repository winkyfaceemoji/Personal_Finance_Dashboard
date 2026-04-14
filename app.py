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
COLORS = {
    "bg":      "#0f1117",
    "surface": "#1a1d27",
    "border":  "#2a2d3a",
    "accent":  "#6c8aff",
    "accent2": "#ff6c8a",
    "accent3": "#6cffd4",
    "text":    "#e8eaf0",
    "subtext": "#7a7d8f",
}

CHART_TEMPLATE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=COLORS["text"], family="IBM Plex Mono, monospace"),
    xaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"]),
    yaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"]),
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
    base = {
        "background":   COLORS["surface"],
        "border":       f"1px solid {COLORS['border']}",
        "borderRadius": "12px",
        "padding":      "24px",
        "marginBottom": "24px",
    }
    if style:
        base.update(style)
    return html.Div(children, style=base)


def label(text):
    return html.Label(text, style={
        "fontSize": "11px", "color": COLORS["subtext"],
        "letterSpacing": "2px", "marginBottom": "10px", "display": "block",
    })


def section_title(text):
    return html.P(text, style={
        "fontSize": "11px", "letterSpacing": "2px",
        "color": COLORS["subtext"], "marginBottom": "16px",
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
        body { background: #0f1117; color: #e8eaf0; font-family: "IBM Plex Mono", monospace; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f1117; }
        ::-webkit-scrollbar-thumb { background: #2a2d3a; border-radius: 3px; }

        .tab-container .tab {
            background: #1a1d27 !important; border: 1px solid #2a2d3a !important;
            border-bottom: none !important; color: #7a7d8f !important;
            font-family: "IBM Plex Mono", monospace !important; font-size: 13px !important;
            padding: 12px 24px !important; border-radius: 8px 8px 0 0 !important;
        }
        .tab-container .tab--selected {
            background: #0f1117 !important; color: #6c8aff !important;
            border-bottom: 2px solid #6c8aff !important;
        }
        .tab-container .tab:hover { color: #e8eaf0 !important; }

        .Select-control { background: #1a1d27 !important; border-color: #2a2d3a !important; color: #e8eaf0 !important; }
        .Select-menu-outer { background: #1a1d27 !important; border-color: #2a2d3a !important; }
        .Select-option { color: #e8eaf0 !important; }
        .Select-option:hover { background: #2a2d3a !important; }
        .Select-value-label { color: #e8eaf0 !important; }
        .Select-placeholder { color: #7a7d8f !important; }

        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td,
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th {
            font-family: "IBM Plex Mono", monospace !important; font-size: 12px !important;
        }

        .btn-primary {
            background: #6c8aff; color: #0f1117; border: none; border-radius: 6px;
            padding: 10px 20px; font-family: "IBM Plex Mono", monospace; font-size: 12px;
            font-weight: 600; letter-spacing: 1px; cursor: pointer;
        }
        .btn-primary:hover { background: #8aa3ff; }
        .btn-secondary {
            background: transparent; color: #6c8aff;
            border: 1px solid #6c8aff; border-radius: 6px;
            padding: 10px 20px; font-family: "IBM Plex Mono", monospace; font-size: 12px;
            font-weight: 600; letter-spacing: 1px; cursor: pointer;
        }
        .btn-secondary:hover { background: rgba(108,138,255,0.1); }
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
    style={"minHeight": "100vh", "padding": "32px 40px"},
    children=[

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

        # Global filters bar
        card([
            html.Div(style={"display": "flex", "gap": "32px", "alignItems": "flex-end"}, children=[

                html.Div([
                    label("SOURCE"),
                    dcc.Dropdown(
                        id="global-source-filter",
                        options=[{"label": "All Sources", "value": "all"}] +
                                [{"label": s, "value": s} for s in available_sources(df)],
                        value="all",
                        clearable=False,
                        style={"width": "220px"},
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
                        style={"fontSize": "13px", "color": COLORS["text"]},
                        inputStyle={"marginRight": "6px", "accentColor": COLORS["accent"]},
                        labelStyle={"marginRight": "20px"},
                    ),
                ]),
            ]),
        ], style={"padding": "20px 24px", "marginBottom": "16px"}),

        # Tabs
        dcc.Tabs(className="tab-container", style={"marginBottom": "0"}, children=[

            # ── Tab 1: Overview ───────────────────────────────────────────────
            dcc.Tab(label="OVERVIEW", children=[
                html.Div(style={"paddingTop": "24px"}, children=[

                    # Summary stat cards
                    html.Div(id="summary-stats", style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(4, 1fr)",
                        "gap": "16px",
                        "marginBottom": "16px",
                    }),

                    # Month to month chart
                    card([
                        section_title("MONTH TO MONTH"),
                        dcc.Graph(id="monthly-chart", config={"displayModeBar": False}),
                    ]),

                    # Year to year chart
                    card([
                        section_title("YEAR TO YEAR"),
                        dcc.Graph(id="yearly-chart", config={"displayModeBar": False}),
                    ]),
                ]),
            ]),

            # ── Tab 2: Categories ─────────────────────────────────────────────
            dcc.Tab(label="CATEGORIES", children=[
                html.Div(style={"paddingTop": "24px"}, children=[

                    # Month filter for categories
                    card([
                        label("FILTER BY MONTH"),
                        dcc.Dropdown(
                            id="category-month-filter",
                            options=[{"label": "All Months", "value": "all"}] +
                                    [{"label": m, "value": m} for m in available_months(df)],
                            value="all",
                            clearable=False,
                            style={"width": "300px"},
                        ),
                    ], style={"padding": "16px 24px", "marginBottom": "16px"}),

                    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
                        card([
                            section_title("SPEND BY CATEGORY"),
                            dcc.Graph(id="category-pie-chart", config={"displayModeBar": False}),
                        ]),
                        card([
                            section_title("CATEGORY TOTALS"),
                            dcc.Graph(id="category-bar-chart", config={"displayModeBar": False}),
                        ]),
                    ]),
                ]),
            ]),

            # ── Tab 3: Category Editor ────────────────────────────────────────
            dcc.Tab(label="CATEGORY EDITOR", children=[
                html.Div(style={"paddingTop": "24px"}, children=[
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
                                "backgroundColor": "#1e2235",
                                "border": f"1px solid {COLORS['accent']}",
                            }],
                        ),
                    ]),
                ]),
            ]),
        ]),
    ],
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

@app.callback(
    Output("monthly-chart",  "figure"),
    Output("yearly-chart",   "figure"),
    Output("summary-stats",  "children"),
    Input("global-source-filter",    "value"),
    Input("global-year-filter",      "value"),
    Input("toggle-income-expenses",  "value"),
)
def update_overview(source, year, toggles):
    filtered = apply_global_filters(source, year)
    show_expenses = "expenses" in toggles
    show_income   = "income"   in toggles

    # ── Monthly chart ──────────────────────────────────────────────────────
    fig_monthly = go.Figure()
    if show_expenses:
        me = monthly_expenses(filtered)
        fig_monthly.add_trace(go.Bar(
            x=me["month_str"], y=me["total_expenses"],
            name="Expenses", marker_color=COLORS["accent2"], marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
        ))
    if show_income:
        mi = monthly_income(filtered)
        fig_monthly.add_trace(go.Bar(
            x=mi["month_str"], y=mi["total_income"],
            name="Income", marker_color=COLORS["accent3"], marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
        ))
    fig_monthly.update_layout(**CHART_TEMPLATE, barmode="group", height=340)

    # ── Yearly chart ───────────────────────────────────────────────────────
    fig_yearly = go.Figure()
    if show_expenses:
        ye = yearly_expenses(df if source == "all" else df[df["source"] == source])
        fig_yearly.add_trace(go.Bar(
            x=ye["year"].astype(str), y=ye["total_expenses"],
            name="Expenses", marker_color=COLORS["accent2"], marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Expenses: $%{y:,.2f}<extra></extra>",
        ))
    if show_income:
        yi = yearly_income(df if source == "all" else df[df["source"] == source])
        fig_yearly.add_trace(go.Bar(
            x=yi["year"].astype(str), y=yi["total_income"],
            name="Income", marker_color=COLORS["accent3"], marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Income: $%{y:,.2f}<extra></extra>",
        ))
    fig_yearly.update_layout(**CHART_TEMPLATE, barmode="group", height=280)

    # ── Summary stats ──────────────────────────────────────────────────────
    me_all = monthly_expenses(filtered)
    total_exp   = me_all["total_expenses"].sum()
    avg_monthly = me_all["total_expenses"].mean() if not me_all.empty else 0
    total_inc   = monthly_income(filtered)["total_income"].sum()
    max_month   = me_all.loc[me_all["total_expenses"].idxmax(), "month_str"] if not me_all.empty else "—"

    def stat_card(lbl, value, color=COLORS["text"], is_str=False):
        display = value if is_str else f"${value:,.2f}"
        return card([
            html.P(lbl, style={
                "fontSize": "10px", "letterSpacing": "2px",
                "color": COLORS["subtext"], "marginBottom": "8px",
            }),
            html.P(display, style={
                "fontSize": "22px", "fontWeight": "600",
                "fontFamily": "'Syne', sans-serif", "color": color,
            }),
        ], style={"padding": "20px 24px", "marginBottom": "0"})

    stats = [
        stat_card("TOTAL EXPENSES",    total_exp,   COLORS["accent2"]),
        stat_card("TOTAL INCOME",      total_inc,   COLORS["accent3"]),
        stat_card("AVG MONTHLY SPEND", avg_monthly, COLORS["text"]),
        stat_card("HIGHEST MONTH",     max_month,   COLORS["accent"], is_str=True),
    ]
    return fig_monthly, fig_yearly, stats


@app.callback(
    Output("category-pie-chart", "figure"),
    Output("category-bar-chart", "figure"),
    Input("global-source-filter",   "value"),
    Input("category-month-filter",  "value"),
)
def update_categories(source, month):
    filtered  = df.copy() if source == "all" else df[df["source"] == source]
    month_val = None if month == "all" else month
    cat = expenses_by_category(filtered, month_str=month_val)

    fig_pie = go.Figure(go.Pie(
        labels=cat["category"], values=cat["total_expenses"],
        hole=0.4, marker_colors=PIE_COLORS,
        textfont=dict(family="IBM Plex Mono, monospace", size=11),
        hovertemplate="<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>",
    ))
    fig_pie.update_layout(**CHART_TEMPLATE, height=420, showlegend=True)

    fig_bar = go.Figure(go.Bar(
        x=cat["total_expenses"], y=cat["category"],
        orientation="h",
        marker_color=PIE_COLORS[:len(cat)],
        marker_line_width=0,
        hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
    ))
    fig_bar.update_layout(**CHART_TEMPLATE, height=420)
    fig_bar.update_yaxes(autorange="reversed")

    return fig_pie, fig_bar


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
