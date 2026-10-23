import base64
import hashlib
import os
import re
import threading
from datetime import date

import pandas as pd
from pathlib import Path

import dash
from dash import dcc, html, ctx, ALL, Input, Output, State, Patch
import plotly.graph_objects as go

from config import get_data_dir, get_master_path, get_rules_path, save_data_dir
from Modules.labels import (
    apply_label_import, read_import_csv, row_ids, last_import_ids,
    unlabeled_groups, read_rules, label_rows, merchant_key,
    TRANSFER_PAIR_DAYS, pair_lists, not_transfer_keys, add_not_transfer,
)
from Modules.linked_cards import (
    answer_link, answered_links, links_unreadable, month_span, pending_duplicates, pending_links,
)
from Modules.chat import health, llm_url, run_turn
from Modules.chat_tools import all_categories, call_tool, tool_schemas, unverified_amounts
from Modules.merchants import (
    ALIASES_NAME, MERCHANTS_NAME, apply_conversion, convert_proposals, describe_label, dismiss, display_name,
    freeze_keyword_labels, keep_past, review_choices, spend_by_spelling, valid_keywords,
    find_merchant, label_changes, merchant_list, merchant_of, merchant_overview, merchants_from, merge, names_in_use,
    pattern_suggestions, read_merchants, remember, remember_check, rename, restore_files, rule_labels, save_change,
    save_merchants, set_patterns, snapshot_files, sort_merchants, split,
)
from Modules.recurring import recurring_charges
from Modules.similar import http_embedder, similar_merchants
from Modules.safety import (
    BACKUP_DIRNAME, MASTER_LOCK, atomic_write_csv, backup_master, orphan_count, read_exported_through, read_overlap_only,
    read_skipped, restore_backup, snapshot_master,
)
from Modules.transforms import (
    UNLABELED_BLOCK,
    unlabeled_share,
    load_transactions,
    category_split,
    filter_period,
    is_covered,
    period_label,
    period_short_label,
    previous_periods,
    period_summary,
    period_totals,
    source_freshness,
    to_period,
    unlabeled_summary,
    PERIOD_FREQS,
    filter_window,
    PREDEFINED_CATEGORIES,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
# FINANCE_RULES_PATH lets tests and scripted checks use a copy, so they never
# rewrite the real rules.csv now that the app can add and delete rules
RULES_PATH  = get_rules_path(get_data_dir())

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
    with MASTER_LOCK:
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
# Neutral and monochrome: white / near-black surfaces, grey text, black or
# white primary actions. Colour is reserved for meaning — red is bad (over
# typical), green is good — and charts are drawn in ink (`bar`). `control`
# outlines buttons and inputs: 3:1 against bg and surface, so they read as
# controls (card borders don't need to). Every text colour passes WCAG AA
# (4.5:1) on bg and surface; see .claude/rules/dashboard-ui.md.
_CHART = {
    "dark": {
        "bg": "#111111", "surface": "#1a1a1a", "chip": "#111111", "border": "#2e2e2e",
        "text": "#ececec", "subtext": "#a3a3a3", "label": "#a3a3a3",
        "accent": "#ececec", "accent2": "#f87171", "accent3": "#4fbf7f",
        "accent_weak": "#2a2a2a", "on_accent": "#111111", "bar": "#ececec", "control": "#737373",
        "overlay": "rgba(17,17,17,0.9)",
        "text_weak": "#c4c4c4", "stroke_weak": "rgba(255,255,255,0.06)", "fill_active": "#333333",
        "shade_strong": "rgba(0,0,0,0.5)", "shade_weak": "rgba(0,0,0,0.3)",
    },
    "light": {
        "bg": "#ffffff", "surface": "#ffffff", "chip": "#ffffff", "border": "#e5e5e5",
        "text": "#0d0d0d", "subtext": "#5d5d5d", "label": "#5d5d5d",
        "accent": "#0d0d0d", "accent2": "#c62828", "accent3": "#1a7f37",
        "accent_weak": "#f2f2f2", "on_accent": "#ffffff", "bar": "#0d0d0d", "control": "#858585",
        "overlay": "rgba(255,255,255,0.9)",
        "text_weak": "#5d5d5d", "stroke_weak": "rgba(0,0,0,0.06)", "fill_active": "#e8e8e8",
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


_FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"


def chart_template(theme="dark"):
    c = _CHART[theme]
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=c["text"], family=_FONT),
        xaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"]),
        yaxis=dict(gridcolor=c["border"], zerolinecolor=c["border"],
                   tickprefix="$", tickformat=",.0f"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=c["surface"], bordercolor=c["border"],
                        font=dict(color=c["text"], family=_FONT)),
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


# How many bars the spending-over-time chart shows per granularity (None = all).
CHART_PERIODS = {"week": 26, "month": 24, "year": None}

# The labeling panel shows the biggest merchants only — the top 25 cover ~90%
# of unlabeled dollars on real data; the rest wait for the next session.
LABEL_TOP_N = 25

# "Remember for future statements" starts ticked only for a merchant seen in
# at least this many different months: a regular, the kind worth labeling
# automatically. Two charges on one trip are thin evidence for a rule that
# labels every future match — those start unticked, the user's call.
REMEMBER_MONTHS = 3

LABEL_GUIDE = """
**Ask one question: did money enter or leave *you* — all your accounts counted as one pot?**

- **Expense** — it left you for someone else (groceries, rent, a Zelle to a friend for dinner).
- **Income** — it came to you from someone else (paycheck, client payment, tax refund).
- **Transfer** — it moved between your own accounts (credit-card payment, savings or investments, Venmo cash-out). Card purchases were already counted, so the bill payment must not count again.

**Tricky cases** — card payment ("AUTOPAY", "PAYMENT THANK YOU"): Transfer, on both sides ·
refund: Expense (it reduces spending) · friend paying you back: Expense · Venmo / Zelle / PayPal:
depends who's on the other end — expand and label row by row · ATM cash: Expense ·
loan or mortgage payment: Expense.
"""

FREQ_NOUN = {"week": "week", "month": "month", "year": "year"}

# The headline won't call a period when the newest data is over STALE_DAYS
# old (for the period holding it) or over UNLABELED_BLOCK (transforms.py) of
# its money out is unlabeled; nor before EARLY_SHARE of an in-progress period has passed, when
# "typical by now" is a day or two of spending. Within IN_LINE_SHARE of
# typical reads as in line.
STALE_DAYS      = 14
EARLY_SHARE     = 0.15
IN_LINE_SHARE   = 0.05


def card(children, **kwargs):
    return html.Div(children, className="app-card", **kwargs)


def _dollar(v: float) -> str:
    # Round first (+ 0.0 turns -0.0 into 0.0): an empty period's spending is
    # -0.0, and -0.001 rounds to zero — both must read "$0.00", not "$-0.00"
    v = round(float(v), 2) + 0.0
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _dollar0(v: float) -> str:
    v = round(float(v)) + 0.0
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


def unreviewed_amounts(pdf: pd.DataFrame) -> tuple[float, float]:
    """Unlabeled money out and money in for a slice of rows — shown on the stat
    cards so incomplete totals look incomplete instead of quietly short."""
    un = pdf[~pdf["master_category"].isin(PREDEFINED_CATEGORIES)]
    return (float(-un.loc[un["amount"] < 0, "amount"].sum()),
            float(un.loc[un["amount"] > 0, "amount"].sum()))


def skipped_text(skipped: list[tuple[str, str]]) -> str:
    """Attention-line item for RAW files the last import skipped. A new bank
    format (or a changed export) is otherwise only a console line, while a
    whole account's spending quietly drops out of every total."""
    if not skipped:
        return ""
    n = len(skipped)
    shown = ", ".join(f"{f} ({why})" for f, why in skipped[:3])
    more = f", and {n - 3} more" if n > 3 else ""
    return f"{n} RAW file{'s' if n != 1 else ''} not imported: {shown}{more}"


def data_age(frame: pd.DataFrame, today=None) -> int | None:
    """Days from the newest transaction to today (None without data)."""
    dates = frame["date"].dropna()
    if dates.empty:
        return None
    today = pd.Timestamp(today if today is not None else pd.Timestamp.today()).normalize()
    return (today - dates.max().normalize()).days


def overlap_text(left_out: pd.DataFrame | None) -> str:
    """Attention-line item for transactions the import left out where two
    exports of one account overlap: the export that owns those dates doesn't
    have them (e.g. a charge pending when the last Discover export was taken,
    which only a Capital One export has)."""
    if left_out is None or left_out.empty:
        return ""
    n = len(left_out)
    return (f"{n} transaction{'s' if n != 1 else ''} ({_dollar0(left_out['amount'].abs().sum())}) "
            f"left out where two exports overlap — listed in SORTED/overlap_only.csv")


def attention_parts(frame: pd.DataFrame, suspects: list[dict], import_ids, orphans: int,
                    skipped: list[tuple[str, str]], today=None,
                    left_out: pd.DataFrame | None = None,
                    exported: dict | None = None, links_broken: bool = False,
                    uncounted_ids: set | None = None,
                    merchant_problems: list[str] | None = None, keywords_left: int = 0) -> dict[str, str]:
    """
    The header's one attention line, item by item — each "" when it doesn't
    fire, so a healthy dashboard shows no line at all. unlabeled / review /
    transfers each come with a button; other is what has no in-app fix.
    exported: {source: date} its exports are known to reach (from their file
    names), so a quiet card with a recent download isn't "behind".
    links_broken: SORTED/linked_cards.csv can't be read, so imports are
    stopped (a confirmed replacement card would otherwise count twice).
    uncounted_ids: row ids the headline doesn't count as unreviewed (sides
    of certain transfer pairs), left out of the unlabeled count too — the
    line and the headline mustn't disagree.
    merchant_problems: why aliases were ignored (read_merchants), shown so a
    damaged merchant file is visible; the reader already fell back safely.
    """
    u = unlabeled_summary(frame[~row_ids(frame).isin(uncounted_ids)] if uncounted_ids else frame)
    unlabeled = (f"{u['count']:,} unlabeled ({_dollar0(u['amount'])}) not counted"
                 if u["count"] else "")
    _, need = last_import_text(frame, import_ids)
    review = f"{need} new from the last import need a label" if need else ""

    other = []
    if links_broken:
        other.append("SORTED/linked_cards.csv can't be read — imports are paused so your card totals "
                     "stay right. Fix or close it, then Reload")
    age = data_age(frame, today)
    if age is not None and age > STALE_DAYS:
        other.append(f"no transactions in {age} days — add newer statements and reload")
    if not frame.empty:
        newest = frame["date"].max().normalize()
        # A source lagging the newest by over a week: its recent spending is
        # missing — unless an export named after a later date says it was quiet
        exported = exported or {}
        for src, d in source_freshness(frame).items():
            through = max(d.normalize(), exported.get(src, d).normalize())
            if (newest - through).days > 7:
                other.append(f"{src} only through {d:%b} {d.day}")
    if orphans:
        other.append(f"{orphans} label{'s' if orphans != 1 else ''} match no transaction "
                     f"(kept in SORTED/orphaned_labels.csv)")
    if skipped:
        other.append(skipped_text(skipped))
    if overlap_text(left_out):
        other.append(overlap_text(left_out))
    if merchant_problems:
        other.append(f"SORTED/merchants.csv and merchant_aliases.csv disagree ({'; '.join(merchant_problems)})"
                     " — those spellings count as their own merchants")
    convert = (f"{keywords_left} rules.csv keyword{'s' if keywords_left != 1 else ''} "
               f"{'aren' if keywords_left != 1 else 'isn'}'t a merchant yet" if keywords_left else "")
    return {"unlabeled": unlabeled, "review": review, "transfers": transfer_check_text(suspects),
            "convert": convert, "other": " · ".join(other)}


def _track(spent: float, ref: float, c: dict, over: bool, marker_title: str) -> html.Div:
    """Spending as a bar, with the typical level as a marker. Spending up to
    typical is ordinary, so it's grey; only the part past typical is red, and
    only when the headline calls it over. Refunds can push a period's
    spending below zero; the bar then stays empty."""
    scale = max(spent, ref, 0) * 1.05 or 1

    def _pct(v):
        return f"{min(max(v / scale, 0), 1) * 100:.1f}%"

    fills = [html.Div(className="pace-fill",
                      style={"left": "0%", "width": _pct(min(spent, ref) if over else spent),
                             "background": c["subtext"]})]
    if over:
        fills.append(html.Div(className="pace-fill pace-over",
                              style={"left": _pct(ref), "width": _pct(spent - ref),
                                     "background": c["accent2"]}))
    return html.Div(className="pace-track", children=[
        *fills, html.Div(className="pace-marker", title=marker_title, style={"left": _pct(ref)}),
    ])


def cant_say_reasons(spent: float, freq: str, health: dict) -> tuple[list[str], bool]:
    """Why the page won't compare this period (headline and cards alike):
    the newest data is stale, too much of its money out is unlabeled, or a
    card question is waiting (health["card_question"]). Returns (reasons,
    whether unlabeled money is one of them)."""
    reasons = []
    if health.get("card_question"):
        reasons.append(health["card_question"])
    if health["current"] and health["age"] is not None and health["age"] > STALE_DAYS:
        d = health["as_of"]
        reasons.append(f"your data ends {d:%b} {d.day}, {d.year} — {health['age']} days ago")
    unlabeled = unlabeled_share(spent, health["unlabeled_out"]) > UNLABELED_BLOCK
    if unlabeled:
        n = health["unlabeled_n"]
        reasons.append(f"{_dollar0(health['unlabeled_out'])} of this {FREQ_NOUN[freq]}'s money out "
                       f"({n} transaction{'s' if n != 1 else ''}) isn't labeled")
    return reasons, unlabeled


def card_question_reason(pending: list[dict], freq: str, p: pd.Period, first) -> str | None:
    """A replacement-card question still waiting whose overlap falls in this
    period or in the periods its "typical" is measured over: those charges
    may be counted twice in either, so the page won't compare until the
    user answers (one tap)."""
    if not pending:
        return None
    prev = previous_periods(p, freq, first) if first is not None else []
    lo, hi = (prev[-1] if prev else p).start_time, p.end_time
    for q in pending:
        if pd.notna(q["from"]) and pd.notna(q["to"]) and q["from"] <= hi and q["to"] >= lo:
            return (f"{q['n']} charges ({_dollar0(q['out'])}) may be counted twice — "
                    f"answer the card question above")
    return None


def card_question_items(pending: list[dict], answered: list[dict], confirm: str | None) -> list:
    """The attention line's replacement-card questions, first on the line:
    asked about what happened (a new card), with the money it decides. NO on
    a pair this alike asks once more. `answered`: the pair just answered,
    confirmed once with UNDO — gone on the next load; Settings → CARDS can
    switch it later (Modules/linked_cards)."""
    def _buttons(pid, buttons):
        return html.Span(className="q-buttons", children=[
            html.Button(label, id={"type": "card-ans", "pair": pid, "act": act}, n_clicks=0,
                        className="btn-secondary btn-small") for label, act in buttons])

    items = []
    for q in pending:
        span = month_span(q["from"], q["to"])
        if confirm == q["id"]:
            text = f"Then {_dollar0(q['out'])} in {span} stays counted twice."
            buttons = [("KEEP BOTH", "keep"), ("GO BACK", "back")]
        else:
            text = (f"Did {q['institution'] or q['source']} replace your card ending {q['old_card']} "
                    f"with {q['new_card']}? {q['n']} charges ({_dollar0(q['out'])}, {span}) are on both "
                    f"and count twice until you answer.")
            buttons = [("YES, REPLACED", "yes"), ("NO, I HAVE BOTH", "no")]
        items.append(html.Span(className="attention-item attention-question",
                               children=[html.Span(text), _buttons(q["id"], buttons)]))
    for a in answered:
        span = month_span(a["from"], a["to"])
        text = (f"{a['new_card']} counted as a replacement for {a['old_card']} — {span} no longer "
                f"counts {_dollar0(a['out'])} twice." if a["status"] == "same" else
                f"{a['old_card']} and {a['new_card']} kept apart — {_dollar0(a['out'])} in {span} "
                f"stays counted twice.") + " You can change this in Settings → Cards."
        items.append(html.Span(className="attention-item attention-note",
                               children=[html.Span(text), _buttons(a["id"], [("UNDO", "undo")])]))
    return items


def headline_view(s: dict, freq: str, health: dict, c: dict) -> tuple[list, bool]:
    """
    The one answer at the top: this period's spending against a typical one
    (the median of earlier periods; while in progress, at the same point).

    It refuses to answer when the data can't support one — the period holds
    the newest data and that's over STALE_DAYS old, or over UNLABELED_BLOCK
    of the money out is unlabeled. A confident verdict over missing data is
    worse than none. health: {"current", "age", "as_of", "unlabeled_out",
    "unlabeled_n"}. Returns (children, whether labeling is the fix).
    """
    noun = FREQ_NOUN[freq]
    spent = s["cur"]["exp"]
    t = s.get("through")
    by = f"{t:%b} {t.day}" if t is not None else ""   # "Oct 8": where the data stops
    title = f"SPENDING THROUGH {by.upper()}" if s["partial"] else "SPENDING"

    def _view(status, colour, legend, track=None):
        return [
            html.Div(title, className="app-label"),
            html.Div(status, className="headline-status", style={"color": colour}),
            track,
            html.Div(className="pace-legend", children=[html.Span(t) for t in legend if t]),
        ]

    reasons, unlabeled = cant_say_reasons(spent, freq, health)
    if reasons:
        # Missing data isn't overspending: ink, not the "over" red
        return _view("Can't say yet", c["text"], ["; ".join(reasons)]), unlabeled

    typ, full = s["typical"], s["typical_full"]
    # Earlier periods too unlabeled to count toward typical (they'd read short)
    k = s.get("left_out_unlabeled", 0)
    left_out = f"{k} earlier {noun}{'s' if k != 1 else ''} not fully labeled, left out" if k else None
    if not typ or not full:
        return _view(f"{_dollar0(spent)} spent", c["text"],
                     [left_out or f"No full earlier {noun} to compare against"]), False
    # One full earlier period isn't a "typical" one: name it instead
    only = s.get("typical_periods") or []
    one = period_label(only[0], freq) if len(only) == 1 else None
    full_name = f"all of {one}" if one else f"typical full {noun}"
    if s["partial"] and s["days_elapsed"] / s["days_total"] < EARLY_SHARE:
        return _view(f"Too early to call — {_dollar0(spent)} spent", c["text"],
                     [f"{full_name} {_dollar0(full['exp'])}", left_out]), False

    ref = typ["exp"]                   # the same point in a typical period, or a full one
    diff = spent - ref
    over = False
    against = one or f"a typical {noun}"
    if abs(diff) <= max(1.0, IN_LINE_SHARE * ref):
        status, colour = f"In line with {against}", c["accent3"]
    else:
        status = f"{_dollar0(abs(diff))} {'over' if diff > 0 else 'under'} {against}"
        colour = c["accent2"] if diff > 0 else c["accent3"]
        over = diff > 0
    if s["partial"]:
        legend = [f"Spent {_dollar0(spent)}", f"│ {one or 'typical'} by {by} {_dollar0(ref)}",
                  f"{full_name} {_dollar0(full['exp'])}"]
        marker = f"{one or 'Typical spending'} by {by}"
    else:
        legend = [f"Spent {_dollar0(spent)}", f"│ {one or 'typical ' + noun} {_dollar0(ref)}"]
        marker = one or f"Typical {noun}"
    legend.append(left_out)
    return _view(status, colour, legend, _track(spent, ref, c, over, marker)), False


def recurring_view(items: list[dict], as_of=None) -> tuple[list, str]:
    """(rows for the Recurring charges card, the one-line summary its closed
    fold shows). Each row: the name and what it costs a year, then in grey
    the price, how often and when it last charged. Active charges first;
    ones that stopped are folded away — worth a glance when a subscription
    you cancelled may still be billing elsewhere."""
    note = html.Div("Repeat charges found across all your history, not just this period.",
                    className="hint rc-note")
    if not items:
        return [note, html.Div("None found yet — a charge needs to repeat at least 3 times, "
                               "monthly to yearly, at a steady amount.", className="hint")], \
            " · none found yet"
    year = pd.Timestamp(as_of).year if as_of is not None else None

    def _row(r):
        d = r["last"]
        when = f"{d:%b} {d.day}" + ("" if d.year == year else f", {d.year}")
        return html.Div(className="recurring-row", children=[
            html.Span(r["merchant"], className="rc-name", title=f"{r['count']} charges since "
                      f"{r['first']:%b} {r['first'].day}, {r['first'].year}"),
            html.Span(f"{_dollar0(r['yearly'])} / yr", className="rc-year"),
            html.Span(f"{_dollar(r['amount'])} {r['cadence']} · last {when}", className="rc-detail"),
        ])

    active = [r for r in items if r["active"]]
    stopped = [r for r in items if not r["active"]]
    rows = [note, *[_row(r) for r in active]] if active else \
        [note, html.Div("None active right now.", className="hint")]
    if stopped:
        rows.append(html.Details(className="lg-rows", children=[
            html.Summary(f"No longer charging ({len(stopped)})"), *[_row(r) for r in stopped]]))
    return rows, f" · {len(active)} · {_dollar0(sum(r['yearly'] for r in active))} a year"


def last_import_text(frame: pd.DataFrame, ids) -> tuple[str, int]:
    """'Last import: 31 new · 27 labeled · 4 need you', and the need-you count."""
    if not ids:
        return "", 0
    rows = frame[row_ids(frame).isin(set(ids))]
    labeled = int(rows["master_category"].isin(PREDEFINED_CATEGORIES).sum())
    need = len(rows) - labeled
    return f"Last import: {len(ids)} new · {labeled} labeled · {need} need you", need


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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
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
_HIDDEN          = {"display": "none"}
_SHOWN_INLINE    = {"display": "inline-block"}

# Visually hidden, not display:none — the radios stay focusable, so the pills
# work from the keyboard (app.css shows a focus ring)
_PILL_INPUT = {"position": "absolute", "opacity": 0, "width": "1px", "height": "1px",
               "margin": 0, "pointerEvents": "none"}


def _attention_item(id_, button, button_id):
    return html.Span(id=f"{id_}-item", className="attention-item", style=_HIDDEN, children=[
        html.Span(id=id_),
        html.Button(button, id=button_id, n_clicks=0, className="btn-secondary btn-small"),
    ])


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
        # Replacement-card question: {"confirm": pair awaiting NO's second
        # tap, "just": pair just answered (confirmed once — memory storage,
        # so a reload clears it), "error": a failed answer's message}
        dcc.Store(id="card-ui", data={}),

        dcc.Store(id="settings-menu-open", data=False),

        # The selected period: {"freq": "week"|"month"|"year", "start": "YYYY-MM-DD"}.
        # Drives the stat cards, the spending chart highlight and the categories.
        dcc.Store(id="period-store"),

        # Clicked category bar — drives both the highlight and the drilldown.
        # A Store (not clickData directly) so rebuilding the chart doesn't
        # clear the selection.
        dcc.Store(id="selected-category"),

        # Labeling panel: which list it shows, the last action (for Undo), and a
        # counter bumped after every write so the list re-renders
        dcc.Store(id="label-filter", data="all"),
        dcc.Store(id="label-undo"),
        dcc.Store(id="merchant-pending"),       # a merge / split / rename waiting for CONFIRM
        dcc.Store(id="label-version", data=0),

        # AI chat: the conversation (memory storage, so a reload clears it),
        # this tab's id for the status poll, and the poll itself (on only
        # while a turn runs)
        dcc.Store(id="chat-history", data=[]),
        dcc.Store(id="chat-id"),
        dcc.Interval(id="chat-poll", interval=400, disabled=True),

        # ── AI chat panel (right side; the page moves left while it's open) ──
        html.Aside(id="chat-panel", className="chat-panel", children=[
            html.Div(className="chat-head", children=[
                html.Div("CHAT", className="app-label"),
                html.Button("CLOSE", id="chat-close", n_clicks=0, className="btn-secondary btn-small"),
            ]),
            html.P("Answers cover the period picked on the page, from labeled transactions only.",
                   className="hint"),
            html.Div(id="chat-health", className="chat-health"),
            html.Div(id="chat-log", className="chat-log"),
            html.Div(id="chat-pending", className="chat-msg chat-user"),
            html.Div(id="chat-status", className="hint chat-status"),
            html.Div(className="chat-input-row", children=[
                dcc.Input(id="chat-input", type="text", placeholder="Ask about this period's money",
                          debounce=False, n_submit=0, className="chat-input", autoComplete="off"),
                html.Button("SEND", id="chat-send", n_clicks=0, className="btn-primary btn-small"),
            ]),
        ]),

        # ── Setup overlay (shown when no data directory is configured) ──────
        html.Div(
            id="setup-overlay",
            style=_OVERLAY_HIDDEN if (MASTER_PATH and MASTER_PATH.exists()) else _OVERLAY_VISIBLE,
            children=html.Div(className="app-card setup-card", children=[
                html.H1(["Finance ", html.Span("Dashboard", className="accent")], className="wordmark"),
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

        # ── Labeling panel (full-screen; opened from the header) ─────────────
        html.Div(id="label-panel", style=_HIDDEN, children=html.Div(className="label-panel-inner", children=[
            html.Div(className="label-head", children=[
                html.Div([html.Div("LABEL TRANSACTIONS", className="app-label"),
                          html.Div(className="label-summary-row", children=[
                              html.Span(id="label-summary", className="hint"),
                              # Opened on a subset (REVIEW →, LABEL THEM →): the way to everything
                              html.Button("SHOW ALL", id="label-show-all", n_clicks=0,
                                          className="btn-secondary btn-small", style=_HIDDEN),
                              # All merchants only: biggest spend first, or what needs a look
                              dcc.RadioItems(id="merchant-sort", className="pills", value="spend", inline=True,
                                             inputStyle=_PILL_INPUT, style=_HIDDEN,
                                             options=[{"label": "BY SPEND", "value": "spend"},
                                                      {"label": "NEEDS ATTENTION", "value": "attention"}]),
                              # Convert rules only: turns every reviewed keyword into a merchant (previewed)
                              html.Button("CONVERT ALL", id="cv-go", n_clicks=0, className="btn-primary btn-small",
                                          style=_HIDDEN),
                          ])]),
                dcc.RadioItems(
                    id="label-tab", className="pills", value="todo", inline=True,
                    inputStyle=_PILL_INPUT,
                    options=[{"label": "TO LABEL", "value": "todo"},
                             {"label": "ALL MERCHANTS", "value": "merchants"},
                             {"label": "TRANSFER PAIRS", "value": "pairs"},
                             {"label": "CONVERT RULES", "value": "rules"}],
                ),
                html.Button("DONE", id="close-label-panel", n_clicks=0, className="btn-primary"),
            ]),
            html.Details(className="label-guide", children=[
                html.Summary("How to choose a label"),
                dcc.Markdown(LABEL_GUIDE),
            ]),
            html.Div(className="label-status-row", children=[
                html.Span(id="label-status", className="settings-status"),
                html.Button("UNDO", id="label-undo-btn", n_clicks=0,
                            className="btn-secondary btn-small", style=_HIDDEN),
            ]),
            # A merchant change shows what it would relabel, and waits for CONFIRM
            html.Div(id="merchant-preview", className="label-status-row", style=_HIDDEN, children=[
                html.Span(id="merchant-preview-text", className="hint"),
                html.Button("CONFIRM", id="merchant-confirm", n_clicks=0, className="btn-primary btn-small"),
                html.Button("CANCEL", id="merchant-cancel", n_clicks=0, className="btn-secondary btn-small"),
            ]),
            html.Div(id="label-list"),
        ])),

        # Click-catcher behind the open settings menu (closes it)
        html.Div(id="settings-backdrop", n_clicks=0, style=_MENU_HIDDEN),

        # ── Header: wordmark, data freshness, attention line; gear top-right ──
        html.Div(className="app-header", children=[
            html.H1(["Finance ", html.Span("Dashboard", className="accent")], className="wordmark"),
            html.P(id="data-updated", className="header-meta"),
            # One red line for everything that needs you — shown only when
            # something fires. Buttons stay in the layout (callbacks listen to
            # them) and hide with their item.
            html.Div(id="attention", className="attention", style=_HIDDEN, children=[
                html.Span(id="att-cards", className="attention-cards"),
                _attention_item("att-unlabeled", "LABEL →", "open-label-panel"),
                _attention_item("att-review", "REVIEW →", "open-label-review"),
                _attention_item("att-transfers", "CHECK →", "open-transfer-check"),
                _attention_item("att-convert", "CONVERT →", "open-convert"),
                html.Span(id="att-other", className="attention-item"),
            ]),

            html.Button("CHAT", id="chat-toggle", n_clicks=0, className="btn-secondary btn-small",
                        title="Ask about this period in plain English"),

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
                    # The panel is otherwise reached only while something is unlabeled
                    _settings_button("LABELS & MERCHANTS", "open-merchants-btn"),
                    html.Div(className="divider", style={"margin": "4px 0"}),
                    html.Div("SOURCE", className="settings-label"),
                    _settings_button("CHANGE DATA FOLDER", "open-setup-btn"),
                    # Replacement-card answers, switchable (filled when any exist)
                    html.Div(id="settings-cards", className="settings-cards"),
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
                        id="data-op-loading", type="circle", color=_CHART["light"]["subtext"],  # visible on either overlay
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


        # ── Headline: this period's spending against a typical one ───────────
        html.Div(className="app-card pace-card", children=[
            html.Div(id="headline"),
            html.Button("LABEL THEM →", id="headline-label", n_clicks=0,
                        className="btn-secondary btn-small", style=_HIDDEN),
        ]),

        # ── Spent / income / net for the selected period ─────────────────────
        html.Div(id="period-stats", className="stats-grid"),

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
            ]),
            dcc.Graph(id="period-chart", config={"displayModeBar": False}),
        ]),

        # ── Categories for the selected period, with click drilldown ─────────
        card([
            html.Div(className="card-head", children=[
                html.Div(id="category-title", className="app-label"),
            ]),
            dcc.Graph(id="category-chart", config={"displayModeBar": False}),
            html.Div(id="category-drilldown"),
        ]),

        # ── Recurring charges: all history, not the period — folded away, its
        # one-line answer on the fold ("RECURRING CHARGES · 7 · $3,149 a year")
        html.Details(className="app-card recurring", children=[
            html.Summary([html.Span("RECURRING CHARGES", className="app-label"),
                          html.Span(id="recurring-sub", className="rc-summary")]),
            html.Div(id="recurring-list"),
        ]),
    ]
)


# ── Labeling panel cards ──────────────────────────────────────────────────────

def _span_text(g) -> str:
    a, b = pd.Timestamp(g["first"]), pd.Timestamp(g["last"])
    if a.date() == b.date():
        return f"{a:%b} {a.day}, {a.year}"
    return f"{a:%b} {a.day}, {a.year} – {b:%b} {b.day}, {b.year}"


def _suggestion_line(mkey: str, target: str):
    """"Same as <merchant>?" with YES and NO: both only preview; CONFIRM
    above the list applies them (ADR 0025: never joined on its own)."""
    return html.Div(className="lg-text", children=[
        html.Span(f"Same as {display_name(target)}?", className="lg-example"),
        html.Button("YES", id={"type": "mer-act", "merchant": mkey, "act": "accept"}, n_clicks=0,
                    className="btn-secondary btn-small"),
        html.Button("NO", id={"type": "mer-act", "merchant": mkey, "act": "dismiss"}, n_clicks=0,
                    className="btn-secondary btn-small"),
    ])


def _group_card(g: dict, chk: dict, kept: dict | None = None, suggested: str = ""):
    """One merchant group: three label buttons, subcategory, remember, rows.
    kept: what the user had set on this card before the list re-rendered
    ({"sub", "remember", "open"}), so a click elsewhere doesn't wipe it."""
    key = g["key"]
    kept = kept or {}

    # Bulk buttons only when one click is safe: never on a nameless (fallback)
    # group or one with money both in and out — those are labeled row by row
    bulk = not g["fallback"] and not g["mixed"]

    def _btn(cat, row=None):
        id_ = ({"type": "lbl-group", "group": key, "sig": g["sig"], "cat": cat} if row is None
               else {"type": "lbl-row", "group": key, "row": row, "cat": cat})
        cls = "btn-secondary btn-small"
        text = cat.upper()
        if cat == "Transfer" and g["suggest_transfer"]:
            # Filled and starred: every button is already outlined in the
            # accent, so colour alone didn't stand out
            cls += " suggested"
            text = "★ " + text
        return html.Button(text, id=id_, n_clicks=0, className=cls,
                           title="Suggested: looks like a card payment or transfer"
                           if "suggested" in cls else None)

    months = chk["months"]                         # every row of the merchant, not just those shown
    if chk["ok"]:
        note = (f'labels every {g["merchant"]} row from now on ({chk["direction"]}) · {chk["rows_now"]} row'
                f'{"s" if chk["rows_now"] != 1 else ""} ({_dollar0(chk["dollars_now"])}) now')
        if g["count"] < 2:
            note += " · only one transaction — tick to remember anyway"
        elif months < REMEMBER_MONTHS:
            note += f" · seen in {months} month{'s' if months != 1 else ''} — tick to remember anyway"
    else:
        note = chk["reason"]
    # Remember only acts on a group-button click, so it is disabled where there
    # are none; and it starts ticked only for a regular (REMEMBER_MONTHS)
    can_remember = bulk and not chk["blocking"]
    ticked = can_remember and chk["ok"] and months >= REMEMBER_MONTHS
    remember = ["yes"] if ticked else []
    if can_remember and kept.get("remember") is not None:
        remember = kept["remember"]

    # A nameless card's rows mostly repeat the transaction text shown above
    # them: show a row's text only where it differs
    def _row_text(r):
        return "" if g["fallback"] and r["description"] == g["example"] else r["description"]

    rows = [html.Div(className="lg-row", children=[
                html.Span(f"{pd.Timestamp(r['date']):%b} {pd.Timestamp(r['date']).day}", className="lg-date"),
                html.Span(_row_text(r) + (f"  ×{r['count']}" if r["count"] > 1 else ""),
                          className="lg-desc" + ("" if _row_text(r) else " lg-desc-same"),
                          title=r["description"]),
                html.Span(_dollar(r["amount"]), className="lg-amt"),
                html.Div(className="lg-buttons", children=[_btn(c, r["row_id"]) for c in PREDEFINED_CATEGORIES]),
            ]) for r in g["rows"]]

    others = len({r["description"] for r in g["rows"]}) - 1     # the bank's other wordings
    return html.Div(className="app-card label-group", children=[
        html.Div(className="lg-main", children=[
            html.Div(className="lg-info", children=[
                # Who it's with (the name rows are grouped under) as the title,
                # and under it, verbatim and tagged, what the bank wrote
                html.Div(className="lg-title", children=[
                    # A nameless (fallback) group has no merchant to show — its
                    # title would only repeat the transaction text below
                    html.Span("No clear merchant", className="lg-name lg-unclear",
                              title="Label each row by what its transaction text says")
                    if g["fallback"] else html.Span(g["merchant"], className="lg-name", title="Merchant"),
                    html.Span("MIXED", className="lg-badge",
                              title="Has money in and out — check the rows") if g["mixed"] else None,
                ]),
                html.Div(className="lg-text", children=[
                    html.Span("Transaction text", className="lg-tag"),
                    html.Span(g["example"], className="lg-example"),
                    html.Span(f"+{others} other wording{'s' if others != 1 else ''}", className="lg-more")
                    if others else None,
                ]),
                html.Div(f'{g["count"]} txn{"s" if g["count"] != 1 else ""} · '
                         f'{_dollar(g["total"])} · {_span_text(g)}', className="hint"),
            ]),
            html.Div(className="lg-buttons", children=[_btn(c) for c in PREDEFINED_CATEGORIES]) if bulk
            else html.Div("Label these one at a time below", className="hint"),
        ]),
        _suggestion_line(g["mkey"], suggested) if suggested else None,
        html.Div(className="lg-options", children=[
            dcc.Input(id={"type": "lbl-sub", "group": key}, placeholder="Subcategory (optional)",
                      className="setup-input lg-sub", list="lbl-sub-options", debounce=False,
                      value=kept.get("sub") or ""),
            # Hidden, not left out, on a nameless card: it can never be ticked
            # there, and the label callbacks read every card's checkbox
            dcc.Checklist(
                id={"type": "lbl-remember", "group": key}, className="lg-remember",
                options=[{"label": " Remember for future statements", "value": "yes",
                          "disabled": not can_remember}],
                value=remember, style={"display": "none"} if g["fallback"] else None,
            ),
            html.Span(note, className="hint") if not g["fallback"] else None,
        ]),
        # Row-by-row groups start open; any group the user opened stays open.
        # Dash doesn't report a <details> toggle, so the summary counts clicks
        # and render_label_list works out the current state from the parity
        html.Details(id={"type": "lbl-rows", "group": key}, className="lg-rows",
                     open=bool(kept["open"]) if kept.get("open") is not None else not bulk,
                     children=[html.Summary(f"Label rows one at a time ({g['count']})",
                                            id={"type": "lbl-rows-sum", "group": key}, n_clicks=0),
                               *rows]),
    ])


def _merchant_card(i: dict):
    """One merchant in the All merchants view, read-only: its rule, its
    spellings, and its money over all time."""
    rule = " · ".join(x for x in (i["label"], i["category"]) if x) or "No rule"
    shown = ", ".join(i["spellings"][:5]) + (f" +{len(i['spellings']) - 5} more" if len(i["spellings"]) > 5 else "")

    def _line(tag, text):
        return html.Div(className="lg-text", children=[html.Span(tag, className="lg-tag"),
                                                        html.Span(text, className="lg-example")])
    return html.Div(className="app-card label-group", children=[
        html.Div(className="lg-title", children=[
            html.Span(i["name"], className="lg-name", title="Merchant"),
            html.Span("LABELS DIFFER", className="lg-badge", title="Its rows carry different labels")
            if len(i["labels"]) > 1 else None,
        ]),
        _suggestion_line(i["mkey"], i["suggested"]) if i["suggested"] else None,
        _line("Rule", rule),
        # What its rows carry now, whatever labeled them (a hand label, its
        # rule, or a rules.csv keyword until those are converted)
        _line("Labeled", ", ".join(i["labels"]) or "Not labeled"),
        html.Div(className="lg-text", title=", ".join(i["spellings"]), children=[
            html.Span("Spellings", className="lg-tag"), html.Span(shown, className="lg-example")]),
        _line("Patterns", i["patterns"]) if i["patterns"] else None,
        html.Div(f"{_dollar(i['out'])} out · {_dollar(i['inn'])} in · {i['rows']} txn{'s' if i['rows'] != 1 else ''}"
                 f" · {_span_text(i) if pd.notna(i['first']) else 'no dates'}", className="hint"),
        _merchant_changes(i),
    ])


def _merchant_changes(i: dict):
    """Rename, merge into another merchant, split a spelling out. Each click
    only previews; CONFIRM above the list applies it."""
    key = i["mkey"]

    def _act(text, act, **extra):
        return html.Button(text, id={"type": "mer-act", "merchant": key, "act": act, **extra}, n_clicks=0,
                           className="btn-secondary btn-small")
    return html.Details(className="lg-rows", children=[
        html.Summary("Change this merchant"),
        html.Div(className="lg-options", children=[
            dcc.Input(id={"type": "mer-name", "merchant": key}, value=i["name"], className="setup-input lg-sub"),
            _act("RENAME", "rename"),
        ]),
        html.Div(className="lg-options", children=[
            dcc.Input(id={"type": "mer-into", "merchant": key}, placeholder="Merge into… (a merchant's name)",
                      className="setup-input lg-sub", list="mer-names"),
            _act("MERGE", "merge"),
        ]),
        # One spelling of a merged merchant: on its own, or moved to another merchant
        *[html.Div(className="lg-options", children=[
              html.Span(s, className="lg-example"),
              _act("SPLIT OUT", "split", spelling=s),
              dcc.Input(id={"type": "mer-move", "merchant": key, "spelling": s}, placeholder="Move to…",
                        className="setup-input lg-sub", list="mer-names"),
              _act("MOVE", "move", spelling=s)])
          for s in (i["spellings"] if len(i["spellings"]) > 1 else [])],
        # What new spellings it should be suggested for ("a | b")
        html.Div(className="lg-options", children=[
            dcc.Input(id={"type": "mer-pat", "merchant": key}, value=i["patterns"],
                      placeholder="Patterns, e.g. zelle payment from | zelle from", className="setup-input lg-sub"),
            _act("SAVE PATTERNS", "patterns"),
        ]),
        # Fixes a past call: its hand-labeled rows and its rule, after a preview
        html.Div(className="lg-options", children=[
            html.Span("Relabel every row", className="lg-tag"),
            *[_act(c.upper(), "relabel", cat=c) for c in PREDEFINED_CATEGORIES],
            dcc.Input(id={"type": "mer-cat", "merchant": key}, placeholder="Subcategory (optional)",
                      className="setup-input lg-sub", list="lbl-sub-options"),
        ]),
    ])


def _merchants_view(sort: str):
    """Every merchant, all time (the period bar doesn't apply), top
    LABEL_TOP_N in the chosen order and the rest folded into one line."""
    # Copies waiting on a replacement-card question count nowhere else either
    frame, m = _without_pending_dups(df), _merchants()
    items, nameless = merchant_overview(frame, m, suggested=_suggestions(m, frame))
    # The biggest merchants by spend always get a card, in the chosen order;
    # "Other" always holds the smallest, so no sort can fold a big one away
    by_spend = sort_merchants(items, "spend")
    shown, rest = sort_merchants(by_spend[:LABEL_TOP_N], sort), by_spend[LABEL_TOP_N:]
    out = [html.Datalist(id="mer-names", children=[html.Option(value=i["name"]) for i in by_spend]),
           *[_merchant_card(i) for i in shown]]
    if rest:
        out.append(html.Div(f"Other · {len(rest)} merchant{'s' if len(rest) != 1 else ''} · "
                            f"{_dollar0(sum(i['out'] for i in rest))} out · "
                            f"{_dollar0(sum(i['inn'] for i in rest))} in", className="hint lg-other"))
    if nameless["rows"]:
        n = nameless["rows"]
        out.append(html.Div(f"No merchant name · {n} row{'s' if n != 1 else ''} · {_dollar0(nameless['out'])} out"
                            f" · {_dollar0(nameless['inn'])} in — they belong to no merchant",
                            className="hint lg-other"))
    summary = (f"{len(items)} merchant{'s' if len(items) != 1 else ''} · "
               f"{_dollar0(sum(i['out'] for i in items))} out · {_dollar0(sum(i['inn'] for i in items))} in, all time")
    if not items:
        out.insert(1, html.Div("No merchants yet", className="hint"))
    return out, summary


def _pair_side(r: dict, direction: str):
    acct = r["source"] + (f" ···{r['card_last4']}" if r["card_last4"] else "")
    return html.Div(className="lg-row", children=[
        html.Span(f"{pd.Timestamp(r['date']):%b} {pd.Timestamp(r['date']).day}", className="lg-date"),
        html.Span(direction, className="pair-dir"),
        html.Span(acct, className="pair-acct"),
        html.Span(r["description"], className="lg-desc", title=r["description"]),
        html.Span(r["label"] or "unlabeled", className="pair-label" + ("" if r["label"] else " open")),
        html.Span(_dollar(r["amount"]), className="lg-amt"),
    ])


def _pair_card(p: dict):
    """One likely transfer: the row out, the row in, one button for both."""
    n = len(p["to_label"])
    return html.Div(className="app-card label-group", children=[
        html.Div(className="lg-main", children=[
            html.Div(className="lg-info", children=[
                html.Span(f"{_dollar(p['amount'])} moved between your accounts", className="lg-name"),
                html.Div(f"{p['gap']} day{'s' if p['gap'] != 1 else ''} apart", className="hint"),
            ]),
            html.Button("LABEL BOTH TRANSFER" if n == 2 else "LABEL AS TRANSFER",
                        id={"type": "lbl-pair", "pair": p["key"], "sig": p["key"]}, n_clicks=0,
                        className="btn-secondary btn-small suggested"),
        ]),
        _pair_side(p["out"], "OUT"),
        _pair_side(p["in"], "IN"),
    ])


_PAIRS_CACHE: dict = {}


def _pair_lists() -> tuple[list[dict], list[dict]]:
    """(transfer_pairs, suspect_transfers) for the current df, computed once per
    load: the header, the TO LABEL hint and the pairs tab all ask for them."""
    if _PAIRS_CACHE.get("df") is not df:
        _PAIRS_CACHE.update(df=df, lists=pair_lists(df))
    return _PAIRS_CACHE["lists"]


def _shown_pairs(filt) -> tuple[list[dict], int]:
    """(the pairs the TRANSFER PAIRS tab shows, how many exist). Opened from
    REVIEW, only pairs touching the last import's rows; at most LABEL_TOP_N,
    and LABEL ALL acts on exactly these — never on pairs the user didn't see."""
    pairs = _pair_lists()[0]
    only, _ = _filter_ids(filt, pairs=True)
    if only is not None:
        pairs = [p for p in pairs if p["out"]["row_id"] in only or p["in"]["row_id"] in only]
    return pairs[:LABEL_TOP_N], len(pairs)


def _suspects(filt=None) -> list[dict]:
    """Likely transfers labeled Expense/Income that the user hasn't dismissed
    (REVIEW: only those touching the last import), biggest first."""
    dismissed = not_transfer_keys(MASTER_PATH) if MASTER_PATH else set()
    out = [p for p in _pair_lists()[1] if p["key"] not in dismissed]
    only, _ = _filter_ids(filt, pairs=True)
    if only is not None:
        out = [p for p in out if p["out"]["row_id"] in only or p["in"]["row_id"] in only]
    return out


def transfer_check_text(suspects: list[dict]) -> str:
    """Header warning: money counted as spending or income that most likely
    just moved between your own accounts."""
    if not suspects:
        return ""
    n = len(suspects)
    return (f"⚠ {n} likely transfer{'s' if n != 1 else ''} between your accounts "
            f"{'are' if n != 1 else 'is'} labeled Expense or Income — "
            f"{_dollar0(sum(p['counted'] for p in suspects))} counted that probably shouldn't be.")


def _suspect_card(p: dict):
    """A likely transfer labeled Expense/Income: fix it, or say it isn't one."""
    return html.Div(className="app-card label-group", children=[
        html.Div(className="lg-main", children=[
            html.Div(className="lg-info", children=[
                html.Span(f"{_dollar(p['amount'])} moved between your accounts?", className="lg-name"),
                html.Div(f"{p['gap']} day{'s' if p['gap'] != 1 else ''} apart · "
                         f"{_dollar0(p['counted'])} of it is in your totals", className="hint"),
            ]),
            html.Div(className="lg-buttons", children=[
                html.Button("RELABEL AS TRANSFER",
                            id={"type": "lbl-fix", "pair": p["key"], "act": "fix"}, n_clicks=0,
                            className="btn-secondary btn-small suggested"),
                html.Button("NOT A TRANSFER",
                            id={"type": "lbl-fix", "pair": p["key"], "act": "dismiss"}, n_clicks=0,
                            className="btn-secondary btn-small",
                            title="Keep the labels and stop flagging this pair"),
            ]),
        ]),
        _pair_side(p["out"], "OUT"),
        _pair_side(p["in"], "IN"),
    ])


def _pairs_sig(pairs: list[dict]) -> str:
    """Signature of the whole pairs list, checked again when LABEL ALL is clicked."""
    return hashlib.sha1("|".join(p["key"] for p in pairs).encode()).hexdigest()[:10]


def _pairs_view(pairs: list[dict], suspects: list[dict] | None = None) -> list:
    suspects = suspects or []
    check = [
        html.Div("CHECK THESE — LABELED EXPENSE OR INCOME", className="settings-label"),
        html.Div("Same amount out of one account and into another, but counted as spending or "
                 "income. A card payment labeled Expense counts that card's purchases twice.",
                 className="hint"),
        *[_suspect_card(p) for p in suspects[:LABEL_TOP_N]],
        html.Div("TO LABEL", className="settings-label", style={"marginTop": "20px"}),
    ] if suspects else []
    if not pairs:
        return [*check, html.Div("No likely transfer pairs to label ✓", className="hint")]
    rows = sum(len(p["to_label"]) for p in pairs)
    return [*check,
        html.Div(className="label-status-row", children=[
            html.Span(f"The same amount left one of your accounts and arrived in another within "
                      f"{TRANSFER_PAIR_DAYS} days — a card payment or a move between your own accounts. "
                      f"Only certain matches are shown.", className="hint"),
            html.Button(f"LABEL ALL {len(pairs)} SHOWN",
                        id={"type": "lbl-pair", "pair": "__all__", "sig": _pairs_sig(pairs)},
                        n_clicks=0, className="btn-secondary btn-small pairs-all",
                        title=f"Label the {rows} unlabeled rows of the pairs below as Transfer"),
        ]),
        *[_pair_card(p) for p in pairs],
    ]


def _convert_proposals():
    return convert_proposals(_without_pending_dups(df), read_rules(RULES_PATH), _merchants())


def _convert_view():
    """The one-time review that turns rules.csv keywords into merchants:
    each keyword's proposed merchant, editable, then CONVERT ALL (previewed;
    CONFIRM applies all at once; UNDO takes it back)."""
    props = _convert_proposals()
    if not props:
        return (html.Div("No rules.csv keywords left: every rule belongs to a merchant.", className="hint"),
                "Nothing to convert")

    def _card(i, p):
        return html.Div(className="app-card label-group", children=[
            html.Div(className="lg-text", children=[html.Span("Keyword", className="lg-tag"),
                                                    html.Span(p["keyword"], className="lg-example")]),
            html.Div(className="lg-options", children=[
                dcc.Input(id={"type": "cv-name", "rule": i}, value=p["name"], className="setup-input lg-sub"),
                dcc.Dropdown(id={"type": "cv-label", "rule": i}, value=p["label"], clearable=False,
                             className="lg-sub", options=[{"label": c, "value": c} for c in PREDEFINED_CATEGORIES]
                             + [{"label": "No label (category only)", "value": ""}]),
                dcc.Input(id={"type": "cv-cat", "rule": i}, value=p["category"], placeholder="Subcategory (optional)",
                          className="setup-input lg-sub", list="lbl-sub-options"),
            ]),
            dcc.Checklist(id={"type": "cv-pat", "rule": i}, className="lg-remember", value=["keep"],
                          options=[{"label": f" Keep \"{p['pattern']}\" as a pattern (suggests new spellings)",
                                    "value": "keep"}], style=None if p["pattern"] else {"display": "none"}),
            dcc.Checklist(id={"type": "cv-spell", "rule": i}, className="lg-remember", value=p["spellings"],
                          options=[{"label": f" {s}", "value": s} for s in p["spellings"]])
            if p["spellings"] else html.Div("Matches nothing today: kept as a pattern only", className="hint"),
        ])
    subs = sorted(s for s in df["sub_category"].unique() if s)
    return ([html.Datalist(id="lbl-sub-options", children=[html.Option(value=s) for s in subs]),
             html.Div("Each keyword becomes a merchant with its rule. Untick a spelling that isn't that merchant, "
                      "then convert them all at once: you'll see what changes first, and UNDO takes it back.",
                      className="hint"),
             *[_card(i, p) for i, p in enumerate(props)]],
            f"{len(props)} rules.csv keyword{'s' if len(props) != 1 else ''} to turn into merchants")


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
    Input("refresh-trigger", "data"),
)
def update_data_note(_refresh):
    if df.empty:
        return "No data loaded"
    as_of = _as_of()
    return f"Data through {as_of:%b} {as_of.day}, {as_of.year}"


_ATTENTION_ITEMS = ("unlabeled", "review", "transfers", "convert")


def _pending() -> list[dict]:
    return pending_links(MASTER_PATH) if MASTER_PATH else []


def _without_pending_dups(frame: pd.DataFrame, pending: list[dict] | None = None) -> pd.DataFrame:
    """frame without the new card's copies of charges in a replacement-card
    pair still awaiting an answer: nobody should be asked to label a charge
    that may be a duplicate (YES merges them; NO brings them back)."""
    pending = _pending() if pending is None else pending
    return frame[~pending_duplicates(frame, pending)] if pending else frame


@app.callback(
    Output("attention", "style"),
    *[Output(f"att-{k}-item", "style") for k in _ATTENTION_ITEMS],
    *[Output(f"att-{k}", "children") for k in _ATTENTION_ITEMS],
    Output("att-other", "children"),
    Output("att-cards", "children"),
    Input("refresh-trigger", "data"),
    Input("card-ui", "data"),
)
def update_attention(_refresh, card_ui):
    card_ui = card_ui or {}
    pending = _pending()
    just = [a for a in (answered_links(MASTER_PATH) if MASTER_PATH else [])
            if a["id"] == card_ui.get("just")]
    cards = card_question_items(pending, just, card_ui.get("confirm"))
    if card_ui.get("error"):
        cards.append(html.Span(card_ui["error"], className="attention-item"))
    parts = attention_parts(
        _without_pending_dups(df, pending), _suspects(), last_import_ids(MASTER_PATH),
        orphan_count(MASTER_PATH) if MASTER_PATH else 0,
        read_skipped(MASTER_PATH) if MASTER_PATH else [],
        left_out=read_overlap_only(MASTER_PATH) if MASTER_PATH else None,
        exported=read_exported_through(MASTER_PATH) if MASTER_PATH else None,
        links_broken=links_unreadable(MASTER_PATH) if MASTER_PATH else False,
        uncounted_ids=_pair_row_ids(),
        merchant_problems=read_merchants(MASTER_PATH.parent).problems if MASTER_PATH else None,
        keywords_left=len(valid_keywords(read_rules(RULES_PATH))),
    )
    shown = {"display": "flex"} if any(parts.values()) or cards else _HIDDEN
    return (shown,
            *[_SHOWN_INLINE if parts[k] else _HIDDEN for k in _ATTENTION_ITEMS],
            *[parts[k] for k in _ATTENTION_ITEMS],
            parts["other"], cards)


@app.callback(
    Output("card-ui",         "data"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input({"type": "card-ans", "pair": ALL, "act": ALL}, "n_clicks"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def card_answer(_clicks, trigger):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return dash.no_update, dash.no_update
    return _do_card_answer(ctx.triggered_id["pair"], ctx.triggered_id["act"], trigger)


def _do_card_answer(pid: str, act: str, trigger) -> tuple[dict, int]:
    """Answer, undo or switch a replacement-card answer (attention line or
    Settings → CARDS). Writes only if the pair is still in the state the
    button was drawn for — a double tap or a stale page is a no-op. Anything
    that makes or breaks a "same" re-runs the import like Reload. Returns
    (card-ui, refresh); card-ui {"just": pair} shows the answer once."""
    global df
    bump = (trigger or 0) + 1
    if act == "no":
        return {"confirm": pid}, dash.no_update   # a pair this alike: ask once more
    if act == "back" or not MASTER_PATH:
        return {}, dash.no_update
    was = {a["id"]: a["status"] for a in answered_links(MASTER_PATH)}.get(pid)
    if act == "undo":
        expect, status = (was, "proposed") if was else (None, None)
    elif act == "switch":
        expect, status = (was, {"same": "different", "different": "same"}[was]) if was else (None, None)
    else:
        expect, status = {"yes": ("proposed", "same"), "keep": ("proposed", "different")}.get(act, (None, None))
    if expect is None:
        return {}, bump
    try:
        with MASTER_LOCK:
            changed = answer_link(MASTER_PATH, pid, expect, status)
    except PermissionError:
        return {"error": "SORTED/linked_cards.csv is open in another program (Excel?) — close it and "
                         "answer again."}, bump
    if changed and "same" in (expect, status):
        try:
            _run_ingest_pipeline(MASTER_PATH.parent.parent)
            df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
        except Exception as e:
            return {"error": f"Answer saved, but the reload failed ({e}) — close any open data file "
                             f"and press Reload."}, bump
    return ({"just": pid} if changed and status != "proposed" else {}), bump


def settings_card_rows(answered: list[dict]) -> list:
    """Settings → CARDS: every replacement-card answer, each switchable."""
    if not answered:
        return []
    rows = []
    for a in answered:
        if a["status"] == "same":
            text, button = f"{a['old_card']} → {a['new_card']} · counted as one card", "KEEP APART"
        else:
            text = (f"{a['old_card']} / {a['new_card']} · kept apart "
                    f"({_dollar0(a['out'])} counted twice)")
            button = "COUNT AS ONE"
        rows.append(html.Div(className="settings-card-row", children=[
            html.Span(f"{a['source']} {text}", className="settings-card-text"),
            html.Button(button, id={"type": "card-ans", "pair": a["id"], "act": "switch"}, n_clicks=0,
                        className="btn-secondary btn-small"),
        ]))
    return [html.Div(className="divider", style={"margin": "4px 0"}),
            html.Div("CARDS", className="settings-label"), *rows]


@app.callback(
    Output("settings-cards", "children"),
    Input("refresh-trigger", "data"),
)
def update_settings_cards(_refresh):
    return settings_card_rows(answered_links(MASTER_PATH) if MASTER_PATH else [])


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
    data_start = df["date"].min() if df["date"].notna().any() else pd.NaT
    if start <= as_of < end:
        # Where the data stops — the same words whether the period is still
        # running or ended after the last export (never today's date)
        sub = f"through {as_of:%b} {as_of.day}"
    elif p == first and not is_covered(p, data_start):
        sub = f"data starts {data_start:%b} {data_start.day}"
    elif p == last:
        sub = "latest complete " + FREQ_NOUN[freq]
    else:
        sub = ""
    return period_label(p, freq), sub, p <= first, p >= last, p >= last


# ── Headline + stat cards ─────────────────────────────────────────────────────

# How each card words a change against last year: (more, less) and whether
# more is good. Net reads better / worse — "more" of a negative net is unclear.
_LAST_YEAR_WORDS = {"exp": ("more", "less", False), "inc": ("more", "less", True),
                    "net": ("better", "worse", True)}


def last_year_lines(s: dict, freq: str, last_year_unlabeled: float | None) -> dict:
    """
    The stat cards' comparison: each total against the same month last year,
    or last year (while in progress, up to the same date). In dollars and
    words, with last year's figure in brackets so it can be checked:
    "$450 more than Oct 2024 ($2,420)". Colour means good or bad for that
    card. {"exp"|"inc"|"net": line or None}.

    It says why instead of showing a number when there's no data for last
    year's period, or when over UNLABELED_BLOCK of that period's money out
    is unlabeled (last_year_unlabeled is that share). Weeks get no line.
    """
    q = s["last_year_period"]
    if q is None:
        return dict.fromkeys(_LAST_YEAR_WORDS)
    name = period_label(q, freq)

    def _note(text):
        return dict.fromkeys(_LAST_YEAR_WORDS, html.Div(text, className="stat-delta"))

    if s.get("last_year_partial"):
        return _note(f"{name} only partly covered")
    if s["last_year"] is None:
        return _note(f"No data for {name}")
    if last_year_unlabeled is not None and last_year_unlabeled > UNLABELED_BLOCK:
        return _note(f"{name} isn't fully labeled")
    if s["partial"]:
        end = s["last_year_window"][1]
        name += f" through {end:%b} {end.day}"

    out = {}
    for k, (up, down, up_is_good) in _LAST_YEAR_WORDS.items():
        was = s["last_year"][k]
        change = s["cur"][k] - was
        if abs(change) < 0.5:
            out[k] = html.Div(f"Same as {name} ({_dollar0(was)})", className="stat-delta")
            continue
        good = (change > 0) == up_is_good
        out[k] = html.Div([
            html.Span(f"{_dollar0(abs(change))} {up if change > 0 else down}",
                      className="delta-good" if good else "delta-bad"),
            f" than {name} ({_dollar0(was)})",
        ], className="stat-delta")
    return out


def _stat_card(title, value, lines):
    return html.Div(className="stat-card", children=[
        html.Div(title, className="stat-title"),
        html.Div(value, className="stat-value"),
        *[l for l in lines if l is not None],
    ])


def _pair_row_ids() -> set:
    """Rows on either side of a certain transfer pair. Unlabeled ones are
    almost surely transfers, so they don't count as unreviewed spending —
    an unlabeled card payment would otherwise look like a missing expense."""
    return {r["row_id"] for p in _pair_lists()[0] for r in p["to_label"]}


def _counted_rows(rows: pd.DataFrame, pending: list[dict] | None = None) -> pd.DataFrame:
    """Rows that can count, leaving out the sides of certain transfer pairs
    (an unlabeled card payment isn't missing spending) and a replacement
    card's copies awaiting the card question."""
    rows = _without_pending_dups(rows, pending)
    return rows[~row_ids(rows).isin(_pair_row_ids())] if not rows.empty else rows


def _blocking_rows(freq: str, p: pd.Period) -> pd.DataFrame:
    """The rows the headline's unlabeled test counts for a period —
    unlabeled money out that can count. Labeling exactly these clears its
    "Can't say yet"; LABEL THEM → opens the panel on them."""
    rows = _counted_rows(filter_period(df, p))
    return rows[~rows["master_category"].isin(PREDEFINED_CATEGORIES) & (rows["amount"] < 0)]


def _period_filter(filt) -> tuple[str, pd.Period] | None:
    """(freq, period) from a "period|month|2026-10-01" label filter."""
    if not isinstance(filt, str) or not filt.startswith("period|"):
        return None
    try:
        _, freq, start = filt.split("|")
        return (freq, to_period(start, freq)) if freq in PERIOD_FREQS else None
    except ValueError:
        return None


def _filter_ids(filt, pairs: bool = False) -> tuple[set | None, str]:
    """(row ids the labeling panel is limited to — None for all — and the
    summary's note). "last": the last import's rows (REVIEW →); a period
    filter: the rows holding back that period's headline (LABEL THEM →) —
    those have no transfer pairs, so the pairs tab ignores it."""
    if filt == "last":
        ids = last_import_ids(MASTER_PATH)
        return (set(ids), " · from the last import") if ids is not None else (None, "")
    fp = None if pairs else _period_filter(filt)
    if fp:
        freq, q = fp
        return set(row_ids(_blocking_rows(freq, q))), f" · in {period_label(q, freq)}"
    return None, ""


@app.callback(
    Output("period-stats",   "children"),
    Output("headline",       "children"),
    Output("headline-label", "style"),
    Input("period-store",  "data"),
    Input("theme-store",   "data"),
    Input("refresh-trigger", "data"),
)
def update_stats(store, theme, _refresh):
    theme = theme if theme in _CHART else "dark"
    c = _CHART[theme]
    freq, p = _selected_period(store)
    as_of = _as_of()
    pending = _pending()

    def _counted(rows):
        return _counted_rows(rows, pending)

    s = period_summary(df, freq, p, as_of, unlabeled_out=lambda rows: unreviewed_amounts(_counted(rows))[0])
    cur = s["cur"]

    rows = _counted(filter_period(df, p))
    out_unrev, in_unrev = unreviewed_amounts(rows)

    def _unreviewed(amount):
        if amount < 0.5:
            return None
        return html.Div(f"+ {_dollar0(amount)} unreviewed", className="stat-delta unreviewed",
                        title="Unlabeled transactions in this period — not counted above")

    un = _blocking_rows(freq, p)
    first = to_period(df["date"].min(), freq) if df["date"].notna().any() else None
    health = {"current": p == to_period(as_of, freq), "age": data_age(df), "as_of": as_of,
              "unlabeled_out": out_unrev, "unlabeled_n": int(len(un)),
              "card_question": card_question_reason(pending, freq, p, first)}

    # Against last year — unless the page won't compare this period at all
    # (the headline says "Can't say yet"), so the cards never contradict it
    if cant_say_reasons(cur["exp"], freq, health)[0]:
        vs = dict.fromkeys(("exp", "inc", "net"))
    else:
        ly_share = None
        if s["last_year_window"] is not None:
            ly_rows = _counted(filter_window(df, *s["last_year_window"]))
            if ly_rows.empty:
                s = dict(s, last_year=None)            # nothing recorded then
            else:
                ly_share = unlabeled_share(s["last_year"]["exp"], unreviewed_amounts(ly_rows)[0])
        vs = last_year_lines(s, freq, ly_share)

    so_far = f" THROUGH {s['through']:%b} {s['through'].day}".upper() if s["partial"] else ""
    cards = [
        _stat_card("SPENT" + so_far, _dollar(cur["exp"]), [vs["exp"], _unreviewed(out_unrev)]),
        _stat_card("INCOME" + so_far, _dollar(cur["inc"]), [vs["inc"], _unreviewed(in_unrev)]),
        _stat_card("NET" + so_far, _dollar(cur["net"]), [vs["net"]]),
    ]

    headline, label_fix = headline_view(s, freq, health, c)
    return cards, headline, (_SHOWN_INLINE if label_fix else _HIDDEN)


# ── Spending over time ────────────────────────────────────────────────────────

@app.callback(
    Output("period-chart", "figure"),
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

    totals = period_totals(df, freq)
    if totals.empty:
        return empty_figure("No transactions yet", theme, 300)

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
        # Spending isn't "bad" and income isn't "good" — both are drawn in ink
        colors = [c["bar"]] * len(vals)

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
            opacity=[1.0 if q == p else 0.45 for q in win.index],
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
        # "median", not "typical": the headline's typical is a different measure
        # (the previous 12 periods), and two different "typical" numbers on one
        # screen read as an error
        fig.add_hline(y=typical, line_dash="dash", line_color=c["subtext"], line_width=1,
                      annotation_text=f"median {_dollar0(typical)}", annotation_position="top right",
                      annotation_font=dict(color=c["subtext"], size=11))
    if metric == "net":
        fig.add_hline(y=0, line_color=c["border"], line_width=1)

    fig.update_layout(**chart_template(theme), height=300, showlegend=False, bargap=0.25)
    fig.update_xaxes(type="category", showgrid=False)

    return fig


# ── Categories ────────────────────────────────────────────────────────────────

def _category_split(pdf: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Top-N categories by spend in a slice of rows, plus the names that roll
    up into "Other". Shared by the chart, the drilldown and the AI chat so
    all three agree."""
    top, rest = category_split(pdf, "out")
    return top.rename(columns={"total": "total_expenses"}), rest


def _category_opacity(names: list[str], selected) -> list[float]:
    """Bars are grey ink; the clicked one is full ink, "Other" lighter still."""
    return [1.0 if n_ == selected else 0.25 if n_.startswith("Other · ") else 0.45 for n_ in names]


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
            color=c["bar"],
            opacity=_category_opacity(names, sel_cat),
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
    patched["data"][0]["marker"]["opacity"] = _category_opacity(names, sel_cat)
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
                html.Span(f"${big['amount']:,.2f}", style={"fontWeight": "600"}),
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


# ── Recurring charges ─────────────────────────────────────────────────────────

@app.callback(
    Output("recurring-list", "children"),
    Output("recurring-sub",  "children"),
    Input("refresh-trigger", "data"),
)
def update_recurring(_refresh):
    # Not tied to the period bar: a subscription is a standing commitment,
    # judged over all your history and "active" as of your newest data. The
    # sides of likely transfers (a fixed monthly move to savings) aren't charges
    pairs, suspects = _pair_lists()
    transfer_ids = {s["row_id"] for p in pairs + suspects for s in (p["out"], p["in"])}
    return recurring_view(recurring_charges(df, exclude_row_ids=transfer_ids), as_of=_as_of())


# ── AI chat (ADR 0021, spec docs/specs/ai-chat.md) ────────────────────────────
# The model only picks tools; every number comes from Modules/chat_tools.py.
# One ordinary callback runs a whole turn (no background callbacks, ADR 0010)
# and records its status here; chat_poll reads it while the turn runs.

_CHAT_PROGRESS: dict[str, str] = {}
_CHAT_PROGRESS_LOCK = threading.Lock()
_CHAT_HISTORY_SENT = 12            # earlier messages the model sees, newest last

_CHAT_DOWN = "The chat model isn't running. Start it with start_llm.ps1, then reopen this panel."
_CHAT_LOADING = "The chat model is still loading. Try again in a moment."


def _set_progress(chat_id: str, text: str | None) -> None:
    with _CHAT_PROGRESS_LOCK:
        if text is None:
            _CHAT_PROGRESS.pop(chat_id, None)
        else:
            _CHAT_PROGRESS[chat_id] = text


def _chat_period(freq: str, p: pd.Period) -> str:
    """'Oct 2026 (Oct 1 – Oct 21, 2026)': the period and the dates its numbers
    cover, which stop at the newest transaction for a period still running."""
    s, e = p.start_time, min(p.end_time.normalize(), _as_of())
    span = (f"{s:%b} {s.day} – {e:%b} {e.day}, {e.year}" if s.year == e.year
            else f"{s:%b} {s.day}, {s.year} – {e:%b} {e.day}, {e.year}")
    return f"{period_label(p, freq)} ({span})"


def _unreviewed_note(out: float, inn: float) -> str:
    """The stat cards' unreviewed money, under every answer: a fact the code
    states rather than trusting the model to mention it."""
    parts = [f"{_dollar0(v)} money {way}" for v, way in ((out, "out"), (inn, "in")) if v >= 0.5]
    return f"+ {' and '.join(parts)} unreviewed, not counted" if parts else ""


def _chat_system(period: str) -> str:
    return (
        f"You answer questions about the user's own transactions for one period: {period}. "
        "Use the tools for every number. Quote dollar amounts exactly as the tools give them; "
        "never add, subtract, average or estimate amounts yourself. Totals count labeled "
        "transactions only, so mention the unreviewed amount when it isn't $0.00. "
        "If the tools can't answer something (other periods, comparisons, recurring charges, "
        "single transactions), say you can't answer that yet. If asked what you should do or "
        "whether to spend less, give the facts and say recommendations aren't available yet; "
        "don't advise. Keep answers short."
    )


@app.callback(
    Output("chat-panel",  "className"),
    Output("chat-health", "children"),
    Output("chat-id",     "data"),
    Input("chat-toggle",  "n_clicks"),
    Input("chat-close",   "n_clicks"),
    State("chat-panel",   "className"),
    prevent_initial_call=True,
)
def toggle_chat(_open, _close, cls):
    # Both buttons toggle (CLOSE only shows while open). Opening checks the
    # model server, so a stopped server is said up front, not after a question
    if "open" in (cls or ""):
        return "chat-panel", dash.no_update, dash.no_update
    state = health(llm_url())
    note = "" if state == "ok" else _CHAT_LOADING if state == "loading" else _CHAT_DOWN
    return "chat-panel open", note, os.urandom(8).hex()


@app.callback(
    Output("chat-history",      "data"),
    Output("chat-input",        "value"),
    Output("selected-category", "data", allow_duplicate=True),
    Output("chat-pending",      "children", allow_duplicate=True),
    Output("chat-status",       "children", allow_duplicate=True),
    Input("chat-send",          "n_clicks"),
    Input("chat-input",         "n_submit"),
    State("chat-input",         "value"),
    State("chat-history",       "data"),
    State("period-store",       "data"),
    State("chat-id",            "data"),
    prevent_initial_call=True,
    running=[(Output("chat-poll", "disabled"), False, True),
             (Output("chat-send", "disabled"), True, False)],
)
def chat_send(_n, _submit, text, history, store, chat_id):
    question = (text or "").strip()
    if not question:
        raise dash.exceptions.PreventUpdate
    turn, period, rows, unreviewed = _chat_turn(question, history, store, chat_id or "chat")
    history = list(history or [])
    history.append({"role": "user", "text": question})
    if turn["error"]:
        history.append({"role": "assistant", "error": turn["error"]})
        return history, "", dash.no_update, "", ""
    history.append({"role": "assistant", "text": turn["reply"], "period": period,
                    "unreviewed": _unreviewed_note(*unreviewed),
                    "unverified": unverified_amounts(turn["reply"], turn["results"])})

    # One category of spending asked about → select its bar, like a click
    # (ADR 0011). Only a bar on the chart: a folded category has none.
    asked = {a.get("category") for n, a in turn["calls"] if a.get("direction") == "out"} - {None}
    bars = set(_category_split(rows)[0]["category"])
    selected = asked.pop() if len(asked) == 1 and asked <= bars else dash.no_update
    return history, "", selected, "", ""


def _chat_turn(question: str, history: list | None, store, chat_id: str
               ) -> tuple[dict, str, pd.DataFrame, tuple[float, float]]:
    """One question to an answer for the selected period: (the turn from
    run_turn, the period wording, the period's rows, its unreviewed money out
    and in, counted as the stat cards count it). ai_eval.py calls this
    too, so the question set tests exactly what the panel runs."""
    freq, p = _selected_period(store)
    period = _chat_period(freq, p)
    rows = filter_period(df, p)
    unreviewed = unreviewed_amounts(_counted_rows(rows, _pending()))
    merchants = read_merchants(MASTER_PATH.parent if MASTER_PATH else BASE_DIR / "no data folder")
    categories = all_categories(df)
    wording = {"period": period_label(p, freq), "dates": period}

    def _tool(name, args):
        return call_tool(name, args, rows=rows, period=wording, unreviewed=unreviewed,
                         merchants=merchants, categories=categories)

    earlier = [{"role": m["role"], "content": m["text"]} for m in history or [] if m.get("text")]
    messages = ([{"role": "system", "content": _chat_system(period)}]
                + earlier[-_CHAT_HISTORY_SENT:] + [{"role": "user", "content": question}])
    _set_progress(chat_id, "Thinking…")
    try:
        turn = run_turn(llm_url(), messages, tool_schemas(categories), _tool,
                        progress=lambda s: _set_progress(chat_id, s))
    finally:
        _set_progress(chat_id, None)
    return turn, period, rows, unreviewed


# The question shows as soon as it's sent; chat_send clears it with the answer
app.clientside_callback(
    "function(_n, _s, text) { return (text || '').trim(); }",
    Output("chat-pending", "children"),
    Input("chat-send",     "n_clicks"),
    Input("chat-input",    "n_submit"),
    State("chat-input",    "value"),
    prevent_initial_call=True,
)


@app.callback(
    Output("chat-status", "children"),
    Input("chat-poll",    "n_intervals"),
    State("chat-id",      "data"),
)
def chat_poll(_n, chat_id):
    with _CHAT_PROGRESS_LOCK:
        return _CHAT_PROGRESS.get(chat_id or "chat", "")


@app.callback(
    Output("chat-log",     "children"),
    Input("chat-history",  "data"),
)
def render_chat(history):
    out = []
    for m in history or []:
        if m["role"] == "user":
            out.append(html.Div(m["text"], className="chat-msg chat-user"))
        elif m.get("error"):
            out.append(html.Div(m["error"], className="chat-msg chat-answer warn-text"))
        else:
            parts = [dcc.Markdown(m["text"], className="chat-text"),
                     html.Div(" · ".join(filter(None, [m["period"], m.get("unreviewed")])), className="hint")]
            if m.get("unverified"):
                parts.append(html.Div("⚠ Not from a tool, so check before trusting: "
                                      + ", ".join(m["unverified"]), className="chat-unverified"))
            out.append(html.Div(parts, className="chat-msg chat-answer"))
    return out


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
    # UTF-8 with a BOM: without it Excel reads the file as Windows-1252, and
    # non-ASCII descriptions come back mangled and match nothing on import.
    # send_bytes, because send_data_frame writes to text and drops the BOM.
    return dcc.send_bytes(export.to_csv(index=False).encode("utf-8-sig"), "transactions_export.csv")


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

    _, content_string = contents.split(",", 1)
    try:
        import_df = read_import_csv(base64.b64decode(content_string))
    except Exception as e:
        return f"⚠ Could not read CSV: {e}", dash.no_update

    required = {"description", "amount", "source", "master_category"}
    missing = required - set(import_df.columns)
    if missing:
        return f"⚠ Missing columns: {', '.join(sorted(missing))}", dash.no_update

    if not MASTER_PATH or not MASTER_PATH.exists():
        return "⚠ No data directory configured — use the setup screen first.", dash.no_update
    try:
        with MASTER_LOCK:
            full_df = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
            full_df, updated, skipped = apply_label_import(full_df, import_df)
            # Versioned backup, then an atomic write: a bad import can be rolled
            # back from SORTED/backups/, and a crash never truncates the master
            backup_master(MASTER_PATH)
            atomic_write_csv(full_df, MASTER_PATH)
        global df
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)

        note = f" · {skipped} row(s) matched nothing" if skipped else ""
        return f"Updated {updated} row(s) from {filename}{note}", (trigger or 0) + 1
    except PermissionError:
        return "⚠ The master file is open in another program (Excel?) — close it and import again.", dash.no_update
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
        if links_unreadable(MASTER_PATH):
            return ("⚠ Nothing imported: SORTED/linked_cards.csv can't be read — fix or close it, "
                    "then reload."), (trigger or 0) + 1
        return "✓ Reloaded", (trigger or 0) + 1
    except PermissionError:
        return "⚠ A data file is open in another program (Excel?) — close it and reload again.", dash.no_update
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
    global df, MASTER_PATH, RULES_PATH

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
    RULES_PATH = get_rules_path(data_dir)
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception as e:
        return dash.no_update, f"Error loading data: {e}", dash.no_update

    # Bump the refresh counter so every card re-renders from the new folder
    return _OVERLAY_HIDDEN, "", (trigger or 0) + 1


# ── Labeling panel ────────────────────────────────────────────────────────────

@app.callback(
    Output("label-panel",     "style"),
    Output("label-filter",    "data"),
    Output("label-tab",       "value"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("open-label-panel",  "n_clicks"),
    Input("open-label-review", "n_clicks"),
    Input("open-transfer-check", "n_clicks"),
    Input("headline-label",    "n_clicks"),
    Input("open-merchants-btn", "n_clicks"),
    Input("open-convert",      "n_clicks"),
    Input("close-label-panel", "n_clicks"),
    State("refresh-trigger",   "data"),
    State("period-store",      "data"),
    prevent_initial_call=True,
)
def toggle_label_panel(_open, _review, _check, _headline, _merchants_btn, _convert, _close, trigger, store=None):
    # Closing refreshes every card: labels written while the panel was open
    # change totals, the header notes and the period bar
    if ctx.triggered_id == "close-label-panel":
        return _HIDDEN, dash.no_update, dash.no_update, (trigger or 0) + 1
    filt = "last" if ctx.triggered_id == "open-label-review" else "all"
    if ctx.triggered_id == "headline-label":
        freq, p = _selected_period(store)
        filt = f"period|{freq}|{p.start_time:%Y-%m-%d}"   # the rows holding back its headline
    tab = _opening_tab(ctx.triggered_id)
    _snapshot_before_labeling()
    return {"display": "block"}, filt, tab, dash.no_update


def _opening_tab(trigger) -> str:
    """Which view the panel opens on: the pairs for CHECK →, and for the
    MERCHANTS menu entry, To label while anything is unlabeled, otherwise
    All merchants."""
    if trigger == "open-transfer-check":
        return "pairs"
    if trigger == "open-convert":
        return "rules"
    if trigger == "open-merchants-btn" and not _todo_groups("all"):
        return "merchants"
    return "todo"


@app.callback(
    Output("merchant-sort", "style"),
    Input("label-tab", "value"),
)
def show_merchant_sort(tab):
    return _SHOWN_INLINE if tab == "merchants" else _HIDDEN


@app.callback(
    Output("cv-go", "style"),
    Input("label-tab", "value"),
    Input("label-version", "data"),
)
def show_convert_all(tab, _version):
    return _SHOWN_INLINE if tab == "rules" and valid_keywords(read_rules(RULES_PATH)) else _HIDDEN


@app.callback(
    Output("label-version", "data", allow_duplicate=True),
    Input("merchant-sort", "value"),
    State("label-version", "data"),
    prevent_initial_call=True,
)
def resort_merchants(_sort, version):
    return (version or 0) + 1                     # re-renders the list in the new order


@app.callback(
    Output("label-show-all", "style"),
    Input("label-filter", "data"),
    Input("label-tab",    "value"),
)
def show_all_button(filt, tab):
    return _SHOWN_INLINE if tab == "todo" and filt not in (None, "all") else _HIDDEN


@app.callback(
    Output("label-filter",  "data",  allow_duplicate=True),
    Output("label-version", "data",  allow_duplicate=True),
    Input("label-show-all", "n_clicks"),
    State("label-version",  "data"),
    prevent_initial_call=True,
)
def show_all_unlabeled(n_clicks, version):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return "all", (version or 0) + 1


def _snapshot_before_labeling() -> None:
    """Keep the state from before today's labeling outside the backup rotation
    (each click takes a rotating backup). A failed copy — disk full, read-only
    folder — must not keep the panel shut: every click still backs up."""
    if not (MASTER_PATH and MASTER_PATH.exists()):
        return
    try:
        with MASTER_LOCK:
            snapshot_master(MASTER_PATH)
    except OSError as e:
        print(f"Warning: pre-labeling snapshot failed: {e}")


@app.callback(
    Output("label-list",    "children"),
    Output("label-summary", "children"),
    Input("label-panel",   "style"),
    Input("label-version", "data"),
    Input("label-tab",     "value"),
    State("label-filter",  "data"),
    # What the user set on the cards, carried across the re-render
    State({"type": "lbl-sub", "group": ALL}, "value"),
    State({"type": "lbl-sub", "group": ALL}, "id"),
    State({"type": "lbl-remember", "group": ALL}, "value"),
    State({"type": "lbl-remember", "group": ALL}, "id"),
    State({"type": "lbl-rows", "group": ALL}, "open"),
    State({"type": "lbl-rows", "group": ALL}, "id"),
    State({"type": "lbl-rows-sum", "group": ALL}, "n_clicks"),
    State({"type": "lbl-rows-sum", "group": ALL}, "id"),
    State("merchant-sort", "value"),
)
def render_label_list(style, _version, tab, filt, subs_in, sub_ids, rems_in, rem_ids,
                      opens, open_ids, toggles, toggle_ids, merchant_sort="spend"):
    if not style or style.get("display") == "none":
        return dash.no_update, dash.no_update
    if tab == "merchants":
        return _merchants_view(merchant_sort)
    if tab == "rules":
        return _convert_view()
    shown, n_pairs = _shown_pairs(filt)
    if tab == "pairs":
        summary = f"{n_pairs} likely transfer pair{'s' if n_pairs != 1 else ''}" + _filter_ids(filt, pairs=True)[1]
        if n_pairs > len(shown):
            summary += f" · showing the top {len(shown)}"
        suspects = _suspects(filt)
        if suspects:
            summary += f" · {len(suspects)} to check"
        return _pairs_view(shown, suspects), summary
    only, note = _filter_ids(filt)
    merchants = _merchants()
    groups = unlabeled_groups(_without_pending_dups(df), only_row_ids=only, merchants=merchants)
    n_rows = sum(g["count"] for g in groups)
    summary = (f"{n_rows:,} row{'s' if n_rows != 1 else ''} · "
               f"{_dollar0(sum(g['abs_total'] for g in groups))} · "
               f"{len(groups)} merchant{'s' if len(groups) != 1 else ''}" + note)
    if not groups:
        return html.Div("Everything is labeled ✓", className="hint"), summary
    subs = sorted(s for s in df["sub_category"].unique() if s)
    kept: dict[str, dict] = {}
    for field, values, ids in (("sub", subs_in, sub_ids), ("remember", rems_in, rem_ids),
                               ("open", opens, open_ids)):
        for i, v in zip(ids or [], values or []):
            kept.setdefault(i["group"], {})[field] = v
    # "open" above is what the server last rendered; each summary click flipped it
    for i, n in zip(toggle_ids or [], toggles or []):
        k = kept.setdefault(i["group"], {})
        if n and n % 2 and k.get("open") is not None:
            k["open"] = not k["open"]
    named = [g for g in groups if not g["fallback"]]
    nameless = [g for g in groups if g["fallback"]]
    suggested = _suggestions(merchants)
    cards = [_group_card(g, remember_check(df, g, merchants), kept.get(g["key"]), suggested.get(g["mkey"], ""))
             for g in named[:LABEL_TOP_N]]
    if nameless:
        n_nameless = sum(g["count"] for g in nameless)
        cards += [html.Div(className="lg-section", children=[
                      html.Span("NO MERCHANT NAME", className="app-label"),
                      html.Span(f" · {n_nameless} row{'s' if n_nameless != 1 else ''}, labeled one at a time",
                                className="hint")]),
                  *[_group_card(g, remember_check(df, g, merchants), kept.get(g["key"]))
                    for g in nameless[:LABEL_TOP_N]]]
    datalist = html.Datalist(id="lbl-sub-options", children=[html.Option(value=s) for s in subs])
    if len(named) > LABEL_TOP_N or len(nameless) > LABEL_TOP_N:
        summary += f" · showing the top {LABEL_TOP_N}"
    if n_pairs:
        summary += f" · {n_pairs} transfer pair{'s' if n_pairs != 1 else ''} found (TRANSFER PAIRS tab)"
    return [datalist, *cards], summary


_LOCKED_MSG = "⚠ The data file is open in another program (Excel?) — close it and try again."


def _is_real_click(triggered) -> bool:
    """Re-rendering the list adds buttons with n_clicks=0 (or None), which fires
    pattern-matching callbacks too — only a real click may write anything."""
    return bool(triggered) and bool(triggered[0].get("value"))


def _mtime(path) -> str:
    """A file's mtime as a string: st_mtime_ns is past 2^53, and the undo record
    goes through the browser's JSON, which would round an int."""
    return str(Path(path).stat().st_mtime_ns) if path and Path(path).exists() else "0"


def _undo_files() -> list:
    """The files a label action may have written. UNDO restores only while
    none of them has changed since the click."""
    merchant_files = [MASTER_PATH.parent / MERCHANTS_NAME, MASTER_PATH.parent / ALIASES_NAME] if MASTER_PATH else []
    return [MASTER_PATH, RULES_PATH, *merchant_files]


def _first_locked(paths) -> str | None:
    """The first of `paths` another program holds open for writing (Excel on
    Windows), or None. Checked before an UNDO or a merchant change so it
    changes nothing at all, and the user can close the file and try again."""
    for path in paths:
        if path and Path(path).exists():
            try:
                with open(path, "r+b"):
                    pass
            except PermissionError:
                return Path(path).name
    return None


# Name-similarity suggestions need the app's embedding server (ADR 0023),
# set up separately. Until it exists, FINANCE_EMBED_URL names one; without
# it they stay off. A server that stops answering isn't asked again until
# the app restarts (ADR 0023: no retry), so a down server never slows pages.
_EMBED = http_embedder(os.environ["FINANCE_EMBED_URL"]) if os.environ.get("FINANCE_EMBED_URL") else None
_EMBED_DOWN = False


def _embedder():
    return None if _EMBED_DOWN else _EMBED


def _suggestions(m, frame: pd.DataFrame | None = None) -> dict[str, str]:
    """{spelling: merchant} to offer as "Same as …?": pattern matches first,
    then, for spellings no pattern names, the merchant whose spelling looks
    most alike (when the embedding server answers). Never applied on its own."""
    frame = _without_pending_dups(df) if frame is None else frame
    spellings = frame["description"].map(merchant_key)
    out = pattern_suggestions(spellings, m)
    embed = _embedder()
    if embed is None:
        return out

    def asked(texts):
        global _EMBED_DOWN
        vectors = embed(texts)
        if vectors is None:
            _EMBED_DOWN = True
        return vectors
    aliases = m.aliases
    dismissed = set(zip(aliases.loc[aliases["status"] == "dismissed", "spelling"],
                        aliases.loc[aliases["status"] == "dismissed", "merchant"]))
    open_ = sorted(set(spellings) - {""} - set(m.alias_of) - set(out))
    alike = similar_merchants(open_, merchant_list(spellings, m), asked, dismissed)
    return out | {s: target for s, (target, _) in alike.items()}


def _merchants():
    """The merchant files beside the master (none without a data folder)."""
    return read_merchants(MASTER_PATH.parent if MASTER_PATH else None)


def _todo_groups(filt):
    """The To label groups, exactly as the list draws them: a click must find
    its group the same way, or it is stale."""
    only, _ = _filter_ids(filt)
    return unlabeled_groups(_without_pending_dups(df), only_row_ids=only, merchants=_merchants())


def _stamps() -> dict[str, str]:
    """Each tracked file's mtime, keyed by its path, for the undo record."""
    return {str(p): _mtime(p) for p in _undo_files()}


def _write_labels(rows: list[dict], cat: str, sub: str = "", relabel: bool = False):
    """The master write every label action shares; call it holding MASTER_LOCK.
    Labels exactly these rows — unlabeled ones only, or with relabel (an
    explicit fix) each row whose label on disk is still the one shown (its
    "label") — backup first, atomic write. Returns (rows labeled, backup), or
    None — with nothing written and df reloaded — when the master no longer
    matches what the user saw. PermissionError (file open in Excel)
    propagates: nothing was written."""
    global df
    expected = sum(r["count"] for r in rows)
    master = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
    if relabel:
        # Row by row, each checked on its own: a combined count could hide one
        # side matching nothing while another matches an unseen row
        n = 0
        for r in rows:
            master, k = label_rows(master, [r], cat, sub, relabel_from={r["label"]} if r.get("label") else None)
            if k != r["count"]:
                n = -1
                break
            n += k
    else:
        master, n = label_rows(master, rows, cat, sub)
    if n != expected:
        # Something relabeled or removed these rows since the list was drawn —
        # write nothing rather than a partial label, and reload so the next
        # draw (and click) sees what is on disk now
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
        return None
    backup = backup_master(MASTER_PATH)
    atomic_write_csv(master, MASTER_PATH)
    return n, backup


def _do_label(trig: dict, sub: str, keep_rule: bool, version, filt):
    """Label a group (or one row of it): master write under the lock with a
    backup first, then — only if that succeeded — the merchant's rule (in the
    merchant files, ADR 0025). Once the master is written, nothing after it
    may lose the Undo. Returns
    (status, undo, undo-button style, version)."""
    global df
    cat = trig["cat"]
    if cat not in PREDEFINED_CATEGORIES:            # a forged or stale button id
        return f'"{cat}" isn\'t a label — nothing was changed.', dash.no_update, dash.no_update, dash.no_update
    bumped = (version or 0) + 1
    stale = ("The list changed — it has been refreshed.", dash.no_update, dash.no_update, bumped)
    groups = _todo_groups(filt)
    group = next((g for g in groups if g["key"] == trig["group"]), None)
    if trig["type"] == "lbl-group":
        if group is None or group["sig"] != trig.get("sig"):
            return stale                           # never label rows the user didn't see
        if group["fallback"] or group["mixed"]:
            return ("Label these one at a time — the rows don't all look alike.",
                    dash.no_update, dash.no_update, bumped)
        rows = group["rows"]
    else:
        # A row is found by its id anywhere in the list, so it still works after
        # another click regrouped things
        row = next((r for g in groups for r in g["rows"] if r["row_id"] == trig.get("row")), None)
        if row is None:
            return stale
        rows, group = [row], group or {"merchant": row["description"]}
    with MASTER_LOCK:
        # Only failures before the master write mean "nothing happened"
        try:
            written = _write_labels(rows, cat, sub)
        except PermissionError:
            return _LOCKED_MSG, dash.no_update, dash.no_update, dash.no_update
        if written is None:
            return stale
        n, backup = written
        # The master is written: Undo is offered whatever happens to the rule
        undo = {"backup": str(backup)}
        rule_note, remembered = "", ""
        if keep_rule and trig["type"] == "lbl-group":
            folder = MASTER_PATH.parent
            try:
                saved = snapshot_files(folder)
                table, aliases = remember(read_merchants(folder), group["mkey"], group["spellings"], cat, sub,
                                          date.today().isoformat())
                save_merchants(folder, table, aliases, adding=True)
                undo["merchant_files"], remembered = saved, group["merchant"]
            except PermissionError:
                rule_note = " · not remembered: a merchant file is open in another program"
            except Exception:
                rule_note = " · not remembered: the merchant files couldn't be read or written"
        undo["stamps"] = _stamps()
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception:
        rule_note += " · couldn't reload the data — use RELOAD DATA"
    status = (f"Labeled {n} {group['merchant']} row{'s' if n != 1 else ''} as {cat}"
              + (f" · remembered: {remembered} is {cat}" if remembered else "") + rule_note)
    return status, undo, _SHOWN_INLINE, bumped


def _hand_labels() -> pd.DataFrame:
    """The master as saved: hand labels only, before any rule."""
    master = pd.read_csv(MASTER_PATH, dtype=str, keep_default_na=False)
    master["amount"] = pd.to_numeric(master["amount"], errors="coerce")
    return master.dropna(subset=["amount"])          # as load_transactions does


def _merchant_change(m, pending: dict):
    """((table, aliases), preview wording, status wording) for a pending
    rename, merge, move, split, pattern change, or accepted or dismissed
    suggestion. ValueError when it can't be done (a name in use, no target)."""
    frame = _without_pending_dups(df)
    items, _ = merchant_overview(frame, m)
    act, key, value = pending["act"], pending["mkey"], (pending.get("value") or "").strip()
    if act == "rename":
        in_use = names_in_use(m, frame["description"].map(merchant_key))
        return rename(m, key, value, in_use), f"Rename {display_name(key)} to {value}", "Renamed"
    if act in ("merge", "move"):
        target = find_merchant(value, {i["name"]: i["mkey"] for i in items} | {i["mkey"]: i["mkey"] for i in items})
        if target is None or target == key:
            raise ValueError("Pick another merchant (start typing its name)")
        spend = spend_by_spelling(frame)
        source = pending["spelling"] if act == "move" else key
        what = (f"Move {source} to {display_name(target)}" if act == "move"
                else f"Merge {display_name(key)} into {display_name(target)}")
        done = (f"Moved {source} to {display_name(target)}" if act == "move"
                else f"Merged {display_name(key)} into {display_name(target)}")
        return merge(m, source, target, spend), what, done
    if act in ("accept", "dismiss"):
        target = _suggestions(m, frame).get(key)
        if target is None:
            raise ValueError("That suggestion no longer applies — nothing was changed")
        if act == "dismiss":
            return (dismiss(m, key, target), f"Stop suggesting {display_name(key)} as {display_name(target)}",
                    f"Won't suggest {display_name(key)} as {display_name(target)} again")
        return (merge(m, key, target, spend_by_spelling(frame)), f"Join {display_name(key)} to {display_name(target)}",
                f"Joined {display_name(key)} to {display_name(target)}")
    if act == "patterns":
        table, aliases = set_patterns(m, key, value)
        cell = table.set_index("merchant").loc[key, "patterns"]
        return ((table, aliases), f"Patterns for {display_name(key)}: {cell or 'none'}",
                f"Saved the patterns for {display_name(key)}")
    what = f"Split {pending['spelling']} out of {display_name(key)}"
    return split(m, pending["spelling"]), what, what


def _relabel_plan(m, pending: dict):
    """A relabel's parts: the merchant's hand-labeled rows whose label (or,
    with a subcategory, whose subcategory) differs, as row dicts carrying the
    label seen; the hand labels with those rewritten; and both merchant files
    with the merchant's rule set to the new label."""
    key, cat, sub = pending["mkey"], pending["cat"], (pending.get("value") or "").strip()
    if cat not in PREDEFINED_CATEGORIES:
        raise ValueError(f"{cat} isn't a label")
    hand = _hand_labels()
    mine = (merchant_of(hand["description"], m) == key) & hand["master_category"].isin(PREDEFINED_CATEGORIES)
    change = mine & ((hand["master_category"] != cat) | ((sub != "") & (hand["sub_category"] != sub)))
    ids = ["date", "description", "amount", "source", "card_last4"]
    # label_rows also takes an identical twin that has no label, so a row's
    # expected count includes those (else CONFIRM would wrongly skip it)
    open_twins = hand[~hand["master_category"].isin(PREDEFINED_CATEGORIES)].groupby(ids).size()
    rows = [{**dict(zip(ids, k[:-1])), "amount": float(k[2]), "label": k[-1],
             "count": int(n) + int(open_twins.get(k[:-1], 0))}
            for k, n in hand[change].groupby(ids + ["master_category"], sort=False).size().items()]
    rewritten = hand.copy()
    rewritten.loc[change, "master_category"] = cat
    if sub:
        rewritten.loc[change, "sub_category"] = sub
    items, _ = merchant_overview(_without_pending_dups(df), m)
    spellings = next((i["spellings"] for i in items if i["mkey"] == key), [key])
    files = remember(m, key, spellings, cat, sub, date.today().isoformat())
    return rows, hand, rewritten, files


def _relabel_preview(m, pending: dict):
    """The preview text. It also stores in `pending` the rows it showed, with
    the label seen on each: CONFIRM rewrites exactly those, never a row whose
    label changed since."""
    rows, hand, rewritten, (table, aliases) = _relabel_plan(m, pending)
    pending["rows"] = rows
    was = rule_labels(hand, m, RULES_PATH)
    now = rule_labels(rewritten, merchants_from(table, aliases), RULES_PATH)
    changed = (was != now).any(axis=1)
    moved = pd.DataFrame({"from": [describe_label(*x) for x in was[changed].itertuples(index=False)],
                          "to": [describe_label(*x) for x in now[changed].itertuples(index=False)],
                          "amount": hand.loc[changed, "amount"].to_numpy()})
    effect = "; ".join(f"{len(g)} row{'s' if len(g) != 1 else ''} ({_dollar0(g['amount'].abs().sum())}) "
                       f"{f} → {t}" for (f, t), g in moved.groupby(["from", "to"])) or "no labels change"
    refunds = moved[moved["amount"] > 0] if (moved["amount"] < 0).any() else moved.iloc[0:0]
    if len(refunds):
        effect += (f" · includes {len(refunds)} refund{'s' if len(refunds) != 1 else ''} "
                   f"({_dollar0(refunds['amount'].sum())}), also labeled {pending['cat']}")
    sub = (pending.get("value") or "").strip()
    return f"Relabel {display_name(pending['mkey'])} as {pending['cat']}{' · ' + sub if sub else ''}: {effect}"


def _do_relabel(pending: dict, version):
    """Rewrite the merchant's hand labels that still show the label seen
    (others are left and counted), then save its rule. Master first, as every
    label write; a rule that can't be saved keeps the labels and UNDO."""
    global df
    with MASTER_LOCK:
        m = _merchants()
        if m.version != pending["version"]:
            return ("The merchants changed since the preview — nothing was changed.",
                    dash.no_update, dash.no_update, (version or 0) + 1)
        _, _, _, (table, aliases) = _relabel_plan(m, pending)
        rows = pending["rows"]                      # as previewed, with the label seen on each
        cat, sub = pending["cat"], (pending.get("value") or "").strip()
        master = pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})
        done = skipped = 0
        for r in rows:
            new, k = label_rows(master, [r], cat, sub, relabel_from={r["label"]})
            if k == r["count"]:
                master, done = new, done + k
            else:                                   # its label changed since: leave it
                skipped += r["count"]
        undo = {}
        try:
            if done:
                undo["backup"] = str(backup_master(MASTER_PATH))
                atomic_write_csv(master, MASTER_PATH)
        except PermissionError:
            return _LOCKED_MSG, dash.no_update, dash.no_update, dash.no_update
        folder, note = MASTER_PATH.parent, " · rule saved"
        try:
            saved = snapshot_files(folder)
            save_change(folder, m, table, aliases)
            undo["merchant_files"] = saved
        except PermissionError:
            note = " · rule not saved: a merchant file is open in another program"
        except Exception:
            note = " · rule not saved: the merchant files couldn't be read or written"
        undo["stamps"] = _stamps()
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception:
        note += " · couldn't reload the data — use RELOAD DATA"
    rewritten = f" · {done} hand label{'s' if done != 1 else ''} rewritten" if done else ""
    left = f" · {skipped} row{'s' if skipped != 1 else ''} left as it was (its label changed since)" if skipped else ""
    return (f"Relabeled {display_name(pending['mkey'])} as {describe_label(cat, sub)}{rewritten}{note}{left}",
            undo, _SHOWN_INLINE, (version or 0) + 1)


def _rules_hash() -> str:
    path = Path(RULES_PATH) if RULES_PATH else None
    return hashlib.sha1(path.read_bytes() if path and path.exists() else b"").hexdigest()


def _master_for_freeze() -> pd.DataFrame:
    """The master as stored, read as every label write reads it."""
    return pd.read_csv(MASTER_PATH, dtype={"card_last4": str, "master_category": str, "sub_category": str})


def _conversion(m, reviewed: list[dict]):
    """(props, frozen master, rows stored, moves, rules dropped) for
    converting the reviewed keywords: every label and category the keywords
    give a row today is stored on it, unless the review chose otherwise for
    its spelling (so only the review moves the past), and a proposal whose
    rule would still move a past row keeps no rule."""
    master = _master_for_freeze()
    choices = review_choices(_convert_proposals(), reviewed)
    shown = rule_labels(master, m, RULES_PATH)
    frozen, kept, stored = freeze_keyword_labels(master, m, RULES_PATH, choices)
    props, dropped = keep_past(frozen, kept, m, reviewed)
    after = merchants_from(*apply_conversion(m, props))
    now = rule_labels(frozen, after, None)
    moved = (now != shown).any(axis=1)
    moves = [f"{int(g.size)} row{'s' if g.size != 1 else ''} ({_dollar0(g.abs().sum())}) {f} → {t}"
             for (f, t), g in master.loc[moved, "amount"].groupby(
                 [[describe_label(*x) for x in shown[moved].itertuples(index=False)],
                  [describe_label(*x) for x in now[moved].itertuples(index=False)]])]
    return props, frozen, int(stored.sum()), moves, dropped


def _convert_preview(reviewed: list[dict]):
    """(pending, text) for converting the reviewed keywords. Every label
    the keywords give today is kept as a stored label, so the preview's
    first part is "no labels change" unless the review changed one. The
    pending change holds the review as made (CONFIRM recomputes from it)."""
    m = _merchants()
    try:
        _, _, kept, moves, dropped = _conversion(m, reviewed)
    except ValueError as e:
        return None, str(e)
    n = len(reviewed)
    text = (f"Convert {n} rules.csv keyword{'s' if n != 1 else ''} into merchants: "
            f"{'; '.join(moves) or 'no labels change'}")
    if kept:
        text += f" · {kept} row{'s' if kept != 1 else ''} keep their label as a stored label"
    if dropped:
        text += (f" · {dropped} merchant{'s' if dropped != 1 else ''} get no rule (it would relabel past rows): "
                 "new rows of them wait for you")
    return ({"act": "convert", "props": reviewed, "version": m.version, "rules": _rules_hash(),
             "master": _mtime(MASTER_PATH)}, text)


def _retired_rules_path(backups: Path) -> Path:
    """rules-converted-<date>.csv, numbered when one already exists, so a
    second conversion (after an UNDO) never overwrites the first backup."""
    backups.mkdir(parents=True, exist_ok=True)
    stem = f"rules-converted-{date.today().isoformat()}"
    return next(backups / f"{stem}{suffix}.csv" for suffix in [""] + [f"-{i}" for i in range(2, 1000)]
                if not (backups / f"{stem}{suffix}.csv").exists())


def _do_convert(pending: dict, version):
    """Store the keywords' labels on the master, write the merchants, then
    retire rules.csv to a dated backup — all three, or (on a refusal) none.
    One UNDO puts the master, both merchant files and rules.csv back."""
    global df
    with MASTER_LOCK:
        m = _merchants()
        if (m.version != pending["version"] or _rules_hash() != pending["rules"]
                or _mtime(MASTER_PATH) != pending.get("master")):
            return ("The data, the merchants or rules.csv changed since the preview — nothing was changed.",
                    dash.no_update, dash.no_update, (version or 0) + 1)
        folder, rules_path = MASTER_PATH.parent, Path(RULES_PATH)
        locked = _first_locked([MASTER_PATH, folder / MERCHANTS_NAME, folder / ALIASES_NAME, rules_path])
        if locked:
            return (f"⚠ Nothing changed: {locked} is open in another program (Excel?) — close it and try again.",
                    dash.no_update, dash.no_update, dash.no_update)
        try:
            props, frozen, kept, _, _ = _conversion(m, pending["props"])
        except ValueError as e:
            return str(e), dash.no_update, dash.no_update, (version or 0) + 1
        table, aliases = apply_conversion(m, props)
        rules = rules_path.read_bytes()
        undo, saved, retired = {}, snapshot_files(folder), None
        try:
            if kept:
                undo["backup"] = str(backup_master(MASTER_PATH))
                atomic_write_csv(frozen, MASTER_PATH)
            save_change(folder, m, table, aliases)
            retired = _retired_rules_path(folder / BACKUP_DIRNAME)
            retired.write_bytes(rules)
            rules_path.unlink()
        except OSError as e:                         # Excel got a file after the check: put everything back
            if retired is not None:
                retired.unlink(missing_ok=True)
            restore_files(folder, saved)
            if undo.get("backup"):
                restore_backup(Path(undo["backup"]), MASTER_PATH)
            return (f"⚠ Nothing changed: {e} — close the file and try again.",
                    dash.no_update, dash.no_update, dash.no_update)
        undo.update({"merchant_files": saved, "rules_file": rules.decode("latin-1"), "stamps": _stamps()})
    df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    n = len(pending["props"])
    return (f"Converted {n} keyword{'s' if n != 1 else ''} into merchants · rules.csv kept as "
            f"SORTED/backups/{retired.name}", undo, _SHOWN_INLINE, (version or 0) + 1)


@app.callback(
    Output("merchant-pending",      "data",     allow_duplicate=True),
    Output("merchant-preview",      "style",    allow_duplicate=True),
    Output("merchant-preview-text", "children", allow_duplicate=True),
    Output("label-status",          "children", allow_duplicate=True),
    Input("cv-go", "n_clicks"),
    State({"type": "cv-name", "rule": ALL}, "value"),
    State({"type": "cv-label", "rule": ALL}, "value"),
    State({"type": "cv-cat", "rule": ALL}, "value"),
    State({"type": "cv-pat", "rule": ALL}, "value"),
    State({"type": "cv-spell", "rule": ALL}, "value"),
    State({"type": "cv-spell", "rule": ALL}, "id"),
    prevent_initial_call=True,
)
def convert_click(_n, names, labels, cats, pats, spells, spell_ids):
    props = _convert_proposals()
    if not props or len(props) != len(names):
        return None, _HIDDEN, "", "The list changed — reopen CONVERT RULES to see it again."
    ticked = {i["rule"]: v for i, v in zip(spell_ids, spells)}
    reviewed = [dict(p, name=(names[i] or "").strip(), label=labels[i] or "", category=(cats[i] or "").strip(),
                     pattern=p["pattern"] if "keep" in (pats[i] or []) else "",
                     spellings=[s for s in p["spellings"] if s in ticked.get(i, [])])
                for i, p in enumerate(props)]
    pending, text = _convert_preview(reviewed)
    if pending is None:
        return None, _HIDDEN, "", text
    return pending, {"display": "flex"}, text, ""


def _merchant_preview(act: str, mkey: str, value=None, spelling=None, cat=None):
    """(pending change, preview text): what CONFIRM would do and which labels
    it would move, or (None, why it can't)."""
    m = _merchants()
    pending = {"act": act, "mkey": mkey, "value": value, "spelling": spelling, "cat": cat, "version": m.version}
    if act == "relabel":
        try:
            return pending, _relabel_preview(m, pending)
        except ValueError as e:
            return None, str(e)
    try:
        (table, aliases), what, _ = _merchant_change(m, pending)
    except ValueError as e:
        return None, str(e)
    after = merchants_from(table, aliases)
    moves = label_changes(_hand_labels(), m, after, RULES_PATH, RULES_PATH)
    effect = "; ".join(f"{r['rows']} row{'s' if r['rows'] != 1 else ''} ({_dollar0(r['dollars'])}) "
                       f"{r['from']} → {r['to']}" for r in moves) or "no labels change"
    if act == "patterns":                       # what the new patterns would put in front of you
        spellings = _without_pending_dups(df)["description"].map(merchant_key)
        n = sum(1 for t in pattern_suggestions(spellings, after).values() if t == mkey)
        effect += f" · suggests {n} spelling{'s' if n != 1 else ''}"
    return pending, f"{what}: {effect}"


def _do_merchant_change(pending: dict, version):
    """Apply a previewed change, if the merchant files are still the ones it
    was previewed on. Only the merchant files change; UNDO puts them back.
    Returns (status, undo, undo-button style, version)."""
    global df
    if not pending:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if pending["act"] == "relabel":
        return _do_relabel(pending, version)
    if pending["act"] == "convert":
        return _do_convert(pending, version)
    with MASTER_LOCK:
        m = _merchants()
        if m.version != pending["version"]:
            return ("The merchants changed since the preview — nothing was changed.",
                    dash.no_update, dash.no_update, (version or 0) + 1)
        try:
            (table, aliases), _, done = _merchant_change(m, pending)
        except ValueError as e:
            return str(e), dash.no_update, dash.no_update, dash.no_update
        folder = MASTER_PATH.parent
        locked = _first_locked([folder / MERCHANTS_NAME, folder / ALIASES_NAME])
        if locked:
            return (f"⚠ Nothing changed: {locked} is open in another program (Excel?) — close it and try again.",
                    dash.no_update, dash.no_update, dash.no_update)
        saved = snapshot_files(folder)
        try:
            save_change(folder, m, table, aliases)
        except PermissionError as e:
            return f"⚠ {e} (Excel?) — close it and try again.", dash.no_update, dash.no_update, dash.no_update
        undo = {"merchant_files": saved, "stamps": _stamps()}
    df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    return f"{done}.", undo, _SHOWN_INLINE, (version or 0) + 1


@app.callback(
    Output("merchant-pending",      "data"),
    Output("merchant-preview",      "style"),
    Output("merchant-preview-text", "children"),
    Output("label-status",          "children", allow_duplicate=True),
    Input({"type": "mer-act", "merchant": ALL, "act": ALL, "spelling": ALL}, "n_clicks"),
    Input({"type": "mer-act", "merchant": ALL, "act": ALL}, "n_clicks"),
    Input({"type": "mer-act", "merchant": ALL, "act": ALL, "cat": ALL}, "n_clicks"),
    State({"type": "mer-name", "merchant": ALL}, "value"),
    State({"type": "mer-name", "merchant": ALL}, "id"),
    State({"type": "mer-into", "merchant": ALL}, "value"),
    State({"type": "mer-into", "merchant": ALL}, "id"),
    State({"type": "mer-cat", "merchant": ALL}, "value"),
    State({"type": "mer-cat", "merchant": ALL}, "id"),
    State({"type": "mer-move", "merchant": ALL, "spelling": ALL}, "value"),
    State({"type": "mer-move", "merchant": ALL, "spelling": ALL}, "id"),
    State({"type": "mer-pat", "merchant": ALL}, "value"),
    State({"type": "mer-pat", "merchant": ALL}, "id"),
    prevent_initial_call=True,
)
def merchant_action(_s, _a, _c, names, name_ids, intos, into_ids, cats, cat_ids, moves, move_ids, pats, pat_ids):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    trig = ctx.triggered_id
    key = trig["merchant"]
    value = {"rename": dict(zip([i["merchant"] for i in name_ids], names)),
             "merge": dict(zip([i["merchant"] for i in into_ids], intos)),
             "relabel": dict(zip([i["merchant"] for i in cat_ids], cats)),
             "patterns": dict(zip([i["merchant"] for i in pat_ids], pats))}.get(trig["act"], {}).get(key)
    if trig["act"] == "move":
        value = dict(zip([(i["merchant"], i["spelling"]) for i in move_ids], moves)).get((key, trig["spelling"]))
    pending, text = _merchant_preview(trig["act"], key, value, trig.get("spelling"), trig.get("cat"))
    if pending is None:                           # can't be done: say why, offer nothing to confirm
        return None, _HIDDEN, "", text
    return pending, {"display": "flex"}, text, ""


@app.callback(
    Output("label-status",     "children", allow_duplicate=True),
    Output("label-undo",       "data",     allow_duplicate=True),
    Output("label-undo-btn",   "style",    allow_duplicate=True),
    Output("label-version",    "data",     allow_duplicate=True),
    Output("merchant-preview", "style",    allow_duplicate=True),
    Output("merchant-pending", "data",     allow_duplicate=True),
    Input("merchant-confirm", "n_clicks"),
    Input("merchant-cancel",  "n_clicks"),
    State("merchant-pending", "data"),
    State("label-version",    "data"),
    prevent_initial_call=True,
)
def merchant_confirm(_ok, _cancel, pending, version):
    if ctx.triggered_id == "merchant-cancel" or not pending:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, _HIDDEN, None
    return (*_do_merchant_change(pending, version), _HIDDEN, None)


def _do_undo(undo: dict, version):
    """Revert the last label action — only if none of the tracked files has
    changed since (otherwise restoring would throw that newer change away)."""
    global df
    if not undo:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if undo.get("stamps") != _stamps():
        return "Can't undo — the data changed since.", None, _HIDDEN, dash.no_update
    try:
        with MASTER_LOCK:
            if _first_locked(_undo_files()):        # refuse before touching anything
                raise PermissionError
            folder, rules_path = MASTER_PATH.parent, Path(RULES_PATH)
            labeled = snapshot_files(folder)
            if undo.get("merchant_files"):
                restore_files(folder, undo["merchant_files"])
            if undo.get("rules_file") is not None:      # a conversion retired it
                tmp = rules_path.with_suffix(".csv.tmp")
                tmp.write_bytes(undo["rules_file"].encode("latin-1"))
                os.replace(tmp, rules_path)
            try:
                if undo.get("backup"):              # a merchant change wrote no master
                    restore_backup(Path(undo["backup"]), MASTER_PATH)
            except PermissionError:
                restore_files(folder, labeled)      # not half undone: put the rule back too
                if undo.get("rules_file") is not None:
                    rules_path.unlink(missing_ok=True)      # and retire rules.csv again
                raise
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except PermissionError:
        return ("⚠ The data or a merchant file is open in another program (Excel?) — close it and try again.",
                dash.no_update, dash.no_update, dash.no_update)
    return "Undone.", None, _HIDDEN, (version or 0) + 1


def _do_label_pairs(trig: dict, version, filt=None):
    """Label one transfer pair (or every pair shown, for "__all__") as Transfer.
    The pair key / list signature must still match what was drawn. Returns
    (status, undo, undo-button style, version), like _do_label."""
    global df
    bumped = (version or 0) + 1
    stale = ("The list changed — it has been refreshed.", dash.no_update, dash.no_update, bumped)
    pairs, _ = _shown_pairs(filt)
    if trig.get("pair") == "__all__":
        chosen = pairs if pairs and _pairs_sig(pairs) == trig.get("sig") else None
    else:
        chosen = [p for p in pairs if p["key"] == trig.get("pair")] or None
    if not chosen:
        return stale
    rows = [r for p in chosen for r in p["to_label"]]
    with MASTER_LOCK:
        try:
            written = _write_labels(rows, "Transfer")
        except PermissionError:
            return _LOCKED_MSG, dash.no_update, dash.no_update, dash.no_update
        if written is None:
            return stale
        n, backup = written
        undo = {"backup": str(backup), "stamps": _stamps()}
    note = ""
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception:
        note = " · couldn't reload the data — use RELOAD DATA"
    what = f"{len(chosen)} pair{'s' if len(chosen) != 1 else ''}"
    return (f"Labeled {n} row{'s' if n != 1 else ''} ({what}) as Transfer" + note,
            undo, _SHOWN_INLINE, bumped)


@app.callback(
    Output("label-status",   "children"),
    Output("label-undo",     "data"),
    Output("label-undo-btn", "style"),
    Output("label-version",  "data"),
    Input({"type": "lbl-group", "group": ALL, "sig": ALL, "cat": ALL}, "n_clicks"),
    Input({"type": "lbl-row", "group": ALL, "row": ALL, "cat": ALL}, "n_clicks"),
    State({"type": "lbl-sub", "group": ALL}, "value"),
    State({"type": "lbl-sub", "group": ALL}, "id"),
    State({"type": "lbl-remember", "group": ALL}, "value"),
    State({"type": "lbl-remember", "group": ALL}, "id"),
    State("label-version", "data"),
    State("label-filter",  "data"),
    prevent_initial_call=True,
)
def label_click(_g, _r, subs, sub_ids, rems, rem_ids, version, filt):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return (dash.no_update,) * 4
    trig = dict(ctx.triggered_id)
    key = trig["group"]
    sub = ({i["group"]: v for i, v in zip(sub_ids, subs)}.get(key) or "").strip()
    keep_rule = bool({i["group"]: v for i, v in zip(rem_ids, rems)}.get(key))
    return _do_label(trig, sub, keep_rule, version, filt)


@app.callback(
    Output("label-status",   "children", allow_duplicate=True),
    Output("label-undo",     "data",     allow_duplicate=True),
    Output("label-undo-btn", "style",    allow_duplicate=True),
    Output("label-version",  "data",     allow_duplicate=True),
    Input({"type": "lbl-pair", "pair": ALL, "sig": ALL}, "n_clicks"),
    State("label-version", "data"),
    State("label-filter",  "data"),
    prevent_initial_call=True,
)
def pair_click(_clicks, version, filt):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return (dash.no_update,) * 4
    return _do_label_pairs(dict(ctx.triggered_id), version, filt)


def _do_fix_suspect(trig: dict, version, filt=None):
    """RELABEL AS TRANSFER: overwrite the Expense/Income side(s) of one likely
    transfer — an explicit fix, so labeled rows are touched (relabel). NOT A
    TRANSFER: remember the pair and stop flagging it; labels untouched.
    Returns (status, undo, undo-button style, version), like _do_label."""
    global df
    bumped = (version or 0) + 1
    stale = ("The list changed — it has been refreshed.", dash.no_update, dash.no_update, bumped)
    pair = next((p for p in _suspects(filt) if p["key"] == trig.get("pair")), None)
    if pair is None:
        return stale
    if trig.get("act") == "dismiss":
        try:
            with MASTER_LOCK:
                add_not_transfer(MASTER_PATH, pair["key"])
        except PermissionError:
            return ("⚠ SORTED/not_transfers.csv is open in another program (Excel?) — close it and try again.",
                    dash.no_update, dash.no_update, dash.no_update)
        except (OSError, KeyError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
            # Never replace a file we can't read: that would undo every earlier dismissal
            return ("⚠ SORTED/not_transfers.csv couldn't be read (edited by hand?) — fix or delete it "
                    "and try again.", dash.no_update, dash.no_update, dash.no_update)
        return "Kept as is — this pair won't be flagged again.", dash.no_update, dash.no_update, bumped
    with MASTER_LOCK:
        try:
            written = _write_labels(pair["to_fix"], "Transfer", relabel=True)
        except PermissionError:
            return _LOCKED_MSG, dash.no_update, dash.no_update, dash.no_update
        if written is None:
            return stale
        n, backup = written
        undo = {"backup": str(backup), "stamps": _stamps()}
    note = ""
    try:
        df = load_transactions(MASTER_PATH, rules_path=RULES_PATH)
    except Exception:
        note = " · couldn't reload the data — use RELOAD DATA"
    return (f"Relabeled {n} row{'s' if n != 1 else ''} as Transfer "
            f"({_dollar0(pair['counted'])} no longer counted)" + note, undo, _SHOWN_INLINE, bumped)


@app.callback(
    Output("label-status",   "children", allow_duplicate=True),
    Output("label-undo",     "data",     allow_duplicate=True),
    Output("label-undo-btn", "style",    allow_duplicate=True),
    Output("label-version",  "data",     allow_duplicate=True),
    Input({"type": "lbl-fix", "pair": ALL, "act": ALL}, "n_clicks"),
    State("label-version", "data"),
    State("label-filter",  "data"),
    prevent_initial_call=True,
)
def fix_click(_clicks, version, filt):
    if not _is_real_click(ctx.triggered) or not isinstance(ctx.triggered_id, dict):
        return (dash.no_update,) * 4
    return _do_fix_suspect(dict(ctx.triggered_id), version, filt)


@app.callback(
    Output("label-status",   "children", allow_duplicate=True),
    Output("label-undo",     "data",     allow_duplicate=True),
    Output("label-undo-btn", "style",    allow_duplicate=True),
    Output("label-version",  "data",     allow_duplicate=True),
    Input("label-undo-btn", "n_clicks"),
    State("label-undo",     "data"),
    State("label-version",  "data"),
    prevent_initial_call=True,
)
def undo_label(n_clicks, undo, version):
    if not n_clicks:
        return (dash.no_update,) * 4
    return _do_undo(undo, version)


@app.callback(
    Output("label-status", "children", allow_duplicate=True),
    Input("label-tab", "value"),
    prevent_initial_call=True,
)
def clear_label_status(_tab):
    # A status belongs to the tab it was made on ("Undone." under RULES reads
    # as if a rule was undone); Undo itself stays available
    return ""


if __name__ == "__main__":
    # Local-only and debug-off by default: the dashboard has no login, so
    # binding to every interface would expose your finances (export, import,
    # change-folder) to anyone on the same network. Docker sets
    # FINANCE_HOST=0.0.0.0 inside the container — see the Dockerfile.
    host  = os.environ.get("FINANCE_HOST", "127.0.0.1")
    debug = os.environ.get("FINANCE_DEBUG", "0") == "1"
    port  = int(os.environ.get("FINANCE_PORT", "8050"))   # the browser tests use their own
    app.run(debug=debug, host=host, port=port)
