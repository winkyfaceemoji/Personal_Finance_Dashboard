---
type: Feature Doc
title: Period view & charts
description: The page header and its attention line, the week / month / year period bar, the spending headline, stat cards, spending-over-time chart, and recurring charges.
resource: app.py, Modules/transforms.py, Modules/recurring.py
updated: 2026-10-10
---

# Period view & charts

The dashboard answers two questions — **"am I on track?"** and **"where did the money go?"** — for a week, a month, or a year. One control, the **period bar**, picks the period, and everything beneath it follows. Top to bottom:

1. **Header** — wordmark, data date, one red **attention line** (only when something needs you), settings gear
2. **Period bar** — `WEEK | MONTH | YEAR` pills and a `‹ period ›` stepper (sticky while scrolling)
3. **Headline** — this period's spending against a typical one, in one sentence — or *Can't say yet* when the data can't support an answer
4. **Stat cards** — spent, income, net for the selected period
5. **Spending over time** — one bar per week / month / year; click a bar to open that period
6. **Spend by category** — for the selected period, with a click drilldown (see [category-breakdown.md](category-breakdown.md))
7. **More** (folded) — recurring charges: subscriptions, rent, utilities, and what they cost a year

The layout is deliberately high-level: one answer at the top, three numbers, two charts, and warnings only when they fire. Budget tracking and the seasonality chart were removed — see [decisions.md](../decisions.md#one-high-level-page-spending-vs-typical-no-budget).

Each card has its own callback, so changing one control only recomputes what depends on it.

---

## Periods

**Weeks run Monday → Sunday** (ISO); months and years are calendar months and years. The period maths lives in `Modules/transforms.py` (see [transforms.md](transforms.md#periods)) and is covered by `tests/test_periods.py`.

**Periods are anchored to your data, not to today.** "Latest" means the period containing your newest transaction. If your exports end on Dec 26, the dashboard opens on December (or the week of Dec 22), not on an empty current month full of `$0.00`. See the decision record in [decisions.md](../decisions.md#periods-are-anchored-to-the-latest-transaction-not-today).

A period is **in progress** when it contains the newest transaction date and runs past it (Dec 1–31 with data through Dec 26: day 26 of 31). In-progress periods are compared like-for-like — see below.

---

## Header

- **Wordmark** — `FINANCE` in text colour, `DASHBOARD` in the accent.
- **Data line** (`data-updated`) — the newest transaction date: `Data through Dec 26, 2025`.
- **Attention line** (`attention`, red) — everything that needs you, on one line that wraps, hidden entirely when nothing fires. Built by `attention_parts`; each item shows only when it applies:

  | Item | Says | Button |
  |------|------|--------|
  | Unlabeled (`att-unlabeled`) | `584 unlabeled ($152,995) not counted` — count and absolute dollar size of rows with no valid label, which every total ignores | **LABEL →** (`open-label-panel`) opens the [labeling panel](labeling-panel.md) |
  | Last import (`att-review`) | `4 new from the last import need a label`, from `SORTED/last_import.csv` | **REVIEW →** (`open-label-review`) opens the panel filtered to those rows. See [labeling-panel.md](labeling-panel.md#the-last-import-last_importcsv) |
  | Likely transfers (`att-transfers`) | likely transfers between your own accounts labeled Expense or Income, and the dollars they wrongly add to totals | **CHECK →** (`open-transfer-check`) opens the TRANSFER PAIRS tab. See [labeling-panel.md](labeling-panel.md#transfer-pairs) |
  | Everything else (`att-other`) | no transactions in over `STALE_DAYS` (14) days; a source lagging the newest by over a week (`Discover Credit only through Nov 26` — its recent spending is missing); labels that match no transaction (kept in `SORTED/orphaned_labels.csv`, see [ingest-pipeline.md](ingest-pipeline.md)); RAW files the last import couldn't use, with the reason (`SORTED/skipped_files.csv`) | — |

  The buttons stay in the layout (callbacks listen to them) and hide with their item. Labeling in bulk with Export → Excel → Import still works. See [import-export.md](import-export.md).

---

## Period bar

| Control | ID | Behaviour |
|---------|----|-----------|
| Granularity pills | `period-freq` | WEEK / MONTH / YEAR. Remembered across reloads (`persistence`, local storage). Default MONTH. |
| Previous / next | `period-prev`, `period-next` | Step one period; disabled at the first / latest period with data. |
| Period label | `period-label`, `period-sub` | `Dec 22 – 28, 2025` / `Dec 2025` / `2025`; the sub-line shows `in progress` or `latest complete month` (the headline shows how far in). |
| LATEST | `period-latest` | Jump back to the period containing the newest transaction. |

The selection lives in the `period-store` Store as `{"freq": …, "start": "YYYY-MM-DD"}`, written only by `navigate_period`. **Switching granularity keeps your place**: from the week of Nov 10 you land on Nov 2025, and from a month on its year. Clicking a bar in the spending chart also navigates. The bar is `position: sticky` so it stays visible while you scroll the cards it drives.

---

## Headline (`headline`)

One sentence answering "how is my spending?" for the selected period, against **typical** — the **median** of up to the previous 12 weeks or months, or of every earlier year (`TYPICAL_LOOKBACK`). A median, so one huge month doesn't define "normal". `headline_view` builds it:

| Situation | Headline | Legend |
|-----------|----------|--------|
| In progress | `$782 over your typical pace` (red) / `$120 under your typical pace` (green) | spent · typical by now · typical full period |
| Finished | `$400 over a typical month` / `under` | spent · typical month |
| Within 5% (`IN_LINE_SHARE`) of typical | `In line with a typical month` (green) | as above |
| Before 15% of an in-progress period has passed (`EARLY_SHARE`: day 1 of a week, days 1–4 of a month) | `Too early to call — $80 so far` — a day or two of spending says nothing yet | typical full period |
| No earlier period in the data | `$X spent` | `No earlier months to compare against yet` |

A bar under the sentence shows spending (fill) against typical (marker). While in progress, "typical" is measured over the same number of days of each earlier period, so a part-finished month is never compared with whole ones.

**Can't say yet.** The headline refuses to answer — red *Can't say yet*, with the reasons — when:

- the period holds your newest data and that data is over `STALE_DAYS` (14) days old (`your data ends Dec 26, 2025 — 288 days ago`), or
- over `UNLABELED_BLOCK` (10%) of the period's money out is unlabeled (`$319 of this month's money out (7 transactions) isn't labeled`). Unlabeled sides of certain transfer pairs don't count — an unlabeled card payment isn't missing spending. A **LABEL THEM →** button (`headline-label`) opens the labeling panel.

A confident verdict over missing data is worse than none; past periods are judged on their own labels only, so they still get an answer once labeled.

## Stat cards (`period-stats`)

Three cards for the selected period:

| Card | Value | Compared with typical as | Higher is… |
|------|-------|--------------------------|-----------|
| Spent | Expense-labeled total | — (the headline is its comparison) | — |
| Income | Income-labeled total | % change | good |
| Net | Income − spent | **dollar** change (net hovers around zero and flips sign, where a % explodes) | good |

Hover a comparison for exactly what "typical" was measured over. While a period is in progress the cards read `SO FAR` and compare `vs typical by now`.

**Unreviewed line.** The Spent and Income cards add a muted italic line, `+ $292 unreviewed` (`unreviewed_amounts`): the unlabeled money out (Spent) or in (Income) in the selected period, leaving out unlabeled sides of certain transfer pairs. It is **not** included in the value above it; it only makes an incomplete total look incomplete. It is hidden under $0.50.

**Delta colour means good or bad for that metric**, not merely up or down. The % divides by `|prior|` so the arrow stays correct when the prior value was negative. A comparison shows `—` when either side is $0 (a ▲/▼100% against nothing describes missing data, not your money). Changes over +1000% are written as a multiple (`▲21×`).

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

## Recurring charges (`recurring-list`, under **More**)

Folded under **MORE** at the bottom of the page — detail, not part of the high-level answer. Subscriptions, memberships, rent and utilities — `recurring_charges` in `Modules/recurring.py`. A merchant (grouped by `merchant_key`, as in the labeling panel) counts as recurring when money goes out to it:

- on **3 or more days**, on a **monthly** (gaps of 20–40 days), **every 2 months** (50–70), **quarterly** (75–105), **every 6 months** (160–200) or **yearly** (330–400) schedule — at least 75% of the gaps must fit;
- at a **steady amount** — at least 75% of charges within 25% of the median, so one price change or odd month doesn't hide it.

Labeled **Expense** and **unlabeled** money out both count — except transfers: rows labeled Transfer or Income, unlabeled rows with transfer wording ("online transfer", "autopay", …), and either side of a likely transfer pair (a fixed monthly move to savings is not a subscription).

Each row shows the merchant, cadence, the **latest charge near the typical amount** (prices change, but a one-off fee or prorated charge from the same payee isn't the subscription), the yearly cost (that × charges per year) and the last charge date. A charge is **active** when it was seen within 1.5 cadences of your newest transaction; ones that stopped fold into **Stopped (N)** — worth a glance when something you cancelled may still be billing. The subtitle totals the active ones per year.

The card isn't tied to the period bar: a subscription is a standing commitment, judged over all your history. Yearly charges need three charges (about two years apart end to end) — two similar charges a year apart (the same trip twice) are too often a coincidence.

**Known limits:** several subscriptions billed under one merchant name (Apple, Google, PayPal at different amounts and days) don't look steady or regular together, so they aren't found; neither is a subscription whose price jumped by more than 25% for half its history (an intro price ending).

---

## Label-based totals

All numbers everywhere are **label-based**: expenses are rows with `master_category == "Expense"` (refunds labeled Expense net against them), income is `master_category == "Income"`. `Transfer` rows and unlabeled rows never appear in any total; the attention line and the stat cards' `unreviewed` line show what's being left out, and the headline won't call a period when too much is.

## Theme

Figures use transparent backgrounds and read hex colours from `_CHART[theme]` via `chart_template(theme)`, which also themes hover labels and formats the y-axis in dollars. Empty states use `empty_figure(message)` — hidden axes and a centred explanation instead of Plotly's bare grid. See [design.md](../design.md).
