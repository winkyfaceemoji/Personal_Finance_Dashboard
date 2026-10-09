---
type: Feature Doc
title: Period view & charts
description: The week / month / year period bar, stat cards, pace strip, spending-over-time chart, seasonality chart, and the page header.
resource: app.py, Modules/transforms.py
updated: 2026-10-09
---

# Period view & charts

The dashboard answers two questions — **"am I on track?"** and **"where did the money go?"** — for a week, a month, or a year. One control, the **period bar**, picks the period, and everything beneath it follows. Top to bottom:

1. **Header** — wordmark, data freshness, stale-data notice, unlabeled-rows note (with `LABEL THEM →`), last-import line (with `REVIEW →`), settings gear
2. **Period bar** — `WEEK | MONTH | YEAR` pills and a `‹ period ›` stepper (sticky while scrolling)
3. **Stat cards** — spent, income, net, savings rate for the selected period
4. **Pace strip** — spending so far vs a typical period at the same point (in-progress periods only)
5. **Spending over time** — one bar per week / month / year; click a bar to open that period
6. **Spend by category** — for the selected period, with a click drilldown (see [category-breakdown.md](category-breakdown.md))
7. **Seasonality** — same-calendar-month lines, one per year

Each card has its own callback, so changing one control only recomputes what depends on it.

---

## Periods

**Weeks run Monday → Sunday** (ISO); months and years are calendar months and years. The period maths lives in `Modules/transforms.py` (see [transforms.md](transforms.md#periods)) and is covered by `tests/test_periods.py`.

**Periods are anchored to your data, not to today.** "Latest" means the period containing your newest transaction. If your exports end on Dec 26, the dashboard opens on December (or the week of Dec 22), not on an empty current month full of `$0.00`. See the decision record in [decisions.md](../decisions.md#periods-are-anchored-to-the-latest-transaction-not-today).

A period is **in progress** when it contains the newest transaction date and runs past it (Dec 1–31 with data through Dec 26: day 26 of 31). In-progress periods are compared like-for-like — see below.

---

## Header

- **Wordmark** — `FINANCE` in text colour, `DASHBOARD` in the accent.
- **Data line** (`data-updated`) — the sources, the newest transaction date (`data through Dec 26, 2025`), and any source lagging the newest by more than 7 days (`behind: Discover Credit through Nov 26`) — its recent transactions are missing, so recent totals undercount.
- **Stale notice** (`stale-note`) — when the newest transaction is more than 7 days before today: *"No transactions in the last N days. Download newer statements…"*. Weekly tracking only works with fresh exports; this says so instead of showing an empty week.
- **Unlabeled note** (`unlabeled-note`, red) — count **and dollar size** of rows with no valid label, which every total ignores (`⚠ 562 of 1,343 transactions ($152,346) are unlabeled and not counted.`). Beside it, the **`LABEL THEM →`** button (`open-label-panel`) opens the [labeling panel](labeling-panel.md); it hides when nothing is unlabeled. Labeling in bulk with Export → Excel → Import still works. See [import-export.md](import-export.md).
- **Last-import line** (`last-import-note`) — what the most recent import added and how much of it still needs you: `Last import: 31 new · 27 labeled · 4 need you`, from `SORTED/last_import.csv`. The **`REVIEW →`** button (`open-label-review`) opens the panel filtered to those rows and shows only while some are unlabeled. Empty when no import has recorded new rows. See [labeling-panel.md](labeling-panel.md#the-last-import-last_importcsv).
- **Skipped-files note** (`skipped-note`, red) — RAW files the last import couldn't use (unrecognised format, unreadable, malformed), with the reason; their transactions are missing from every total. Read from `SORTED/skipped_files.csv`. See [ingest-pipeline.md](ingest-pipeline.md).
- **Orphan note** (`orphan-note`, red) — shown while some of your labels match no transaction; they're kept in `SORTED/orphaned_labels.csv` and re-attach automatically if the transactions return. See [ingest-pipeline.md](ingest-pipeline.md).

---

## Period bar

| Control | ID | Behaviour |
|---------|----|-----------|
| Granularity pills | `period-freq` | WEEK / MONTH / YEAR. Remembered across reloads (`persistence`, local storage). Default MONTH. |
| Previous / next | `period-prev`, `period-next` | Step one period; disabled at the first / latest period with data. |
| Period label | `period-label`, `period-sub` | `Dec 22 – 28, 2025` / `Dec 2025` / `2025`; the sub-line shows `in progress · data through Dec 26 · day 5 of 7`, or `latest complete month`. |
| LATEST | `period-latest` | Jump back to the period containing the newest transaction. |

The selection lives in the `period-store` Store as `{"freq": …, "start": "YYYY-MM-DD"}`, written only by `navigate_period`. **Switching granularity keeps your place**: from the week of Nov 10 you land on Nov 2025, and from a month on its year. Clicking a bar in the spending chart also navigates. The bar is `position: sticky` so it stays visible while you scroll the cards it drives.

---

## Stat cards (`period-stats`)

Four cards for the selected period. Each shows the value and two comparisons:

| Card | Value | Compared as | Higher is… |
|------|-------|-------------|-----------|
| Spent | Expense-labeled total | % change | bad |
| Income | Income-labeled total | % change | good |
| Net | Income − spent | **dollar** change (net hovers around zero and flips sign, where a % explodes) | good |
| Savings rate | Net ÷ income (— with no income) | **percentage points** | good |

- **vs previous** — the period before (`vs Nov 2025`, `vs last week`, `vs 2024`).
- **vs typical** — the **median** of up to the previous 12 weeks or months, or of every earlier year (`TYPICAL_LOOKBACK`). A median, so one huge month doesn't define "normal". Hover the line for exactly what it was measured over.

**Unreviewed line.** The Spent and Income cards add a muted italic line, `+ $292 unreviewed` (`unreviewed_amounts`): the unlabeled money out (Spent) or in (Income) in the selected period. It is **not** included in the value above it, since counting unlabeled rows by sign would double-count card payments; it only makes an incomplete total look incomplete. It is hidden under $0.50 and absent from the Net and Savings-rate cards. Hover for the explanation.

**In-progress periods compare like-for-like.** On day 26 of December the cards read `SPENT SO FAR`, and both comparisons use the *first 26 days* of each earlier period (`vs same point in Nov 2025`, `vs typical by now`) — a part-finished month is never compared to whole ones.

**Delta colour means good or bad for that metric**, not merely up or down — more income is green, more spending is red. The % divides by `|prior|` so the arrow stays correct when the prior value was negative. A comparison shows `—` when either side is $0 (a ▲/▼100% against nothing describes missing data, not your money). Changes over +1000% are written as a multiple (`▲21×`).

---

## Pace strip (`pace-strip`)

Shown only while the selected period is in progress. One bar:

- the **fill** is spending so far — red if ahead of typical pace, green if under;
- the **marker** is what you typically spend by this point;
- the track's scale covers a typical *full* period.

The headline states the gap in dollars (`$782 over your typical pace`). With no earlier periods in the data it says so instead. The pace strip is the forward-looking "am I on track?" read; it's a separate card because the cumulative version of the seasonality chart was tried and reverted (see below).

---

## Spending over time (`period-chart`)

One bar per period at the selected granularity: the latest **26 weeks**, **24 months**, or **every year** (`CHART_PERIODS`). If you've stepped back further than that, the window shifts to keep the selected period on screen.

- **Metric dropdown** (`cashflow-metric`, doubles as the card title): Expenses (default, red), Income (green), or Net Cash Flow (green/red by sign, with a zero line).
- **Selected period** — full opacity with an outline; the rest are dimmed.
- **In-progress period** — hatched, so a short bar reads as "not over yet".
- **Typical line** — dashed, at the median of the complete periods on screen (needs at least 3).
- **Click a bar** to open that period. Hover shows the full period label and amount.

Gap periods (no labeled transactions) appear as zero bars rather than disappearing, and count toward "typical".

---

## Seasonality (`seasonality-chart`)

`{EXPENSES|INCOME} BY CALENDAR MONTH`: one line per year over a fixed Jan–Dec axis, so every February shares a column and Feb '24 vs Feb '25 is a straight vertical read. The pill toggle (`seasonality-metric`) switches between expenses and income.

- The **year of the selected period** is drawn bold in the accent; every other year is a thin muted line — readable as "this year vs the range of other years" rather than eleven competing colours.
- Click a year in the legend to hide or show it (legend stays chronological via `legendrank`).
- Hover shows the value plus the change vs the same month a year earlier (`+$312 (+18%) vs Mar 2024`).
- Partial years are shorter lines; missing months are gaps, not zeros.

A cumulative "pace" variant of this chart was tried and reverted — the monthly shape (spike months, seasonality) is information only this chart carries. Pace lives in its own strip instead.

---

## Label-based totals

All numbers everywhere are **label-based**: expenses are rows with `master_category == "Expense"` (refunds labeled Expense net against them), income is `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total; the header's unlabeled note and the stat cards' `unreviewed` line show what's being left out.

## Theme

Figures use transparent backgrounds and read hex colours from `_CHART[theme]` via `chart_template(theme)`, which also themes hover labels and formats the y-axis in dollars. Empty states use `empty_figure(message)` — hidden axes and a centred explanation instead of Plotly's bare grid. See [design.md](../design.md).
