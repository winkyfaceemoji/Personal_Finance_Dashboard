---
type: Design System
title: UI design system
description: Theme tokens, typography, component patterns, and the CSS gotchas behind the dashboard's look.
resource: app.py, assets/app.css, assets/theme_sync.js
updated: 2026-10-11
---

# UI design system

The dashboard is a two-theme (dark default) Dash app with no CSS framework, styled neutral and monochrome: white or near-black surfaces, grey text, black or white primary actions, one sans-serif typeface. Colour is reserved for meaning. Styling lives in `assets/app.css` (served automatically by Dash), and every colour in it is a theme token generated from one Python dict. This doc captures the conventions and, more importantly, the non-obvious pitfalls.

## Themes

Two themes — `dark` (default) and `light`. The choice is held in the `theme-store` Store with `storage_type="local"`, so it **persists across reloads**, and `apply_theme` writes it as a `dark-theme` / `light-theme` class on `#app-root` (and highlights the active LIGHT / DARK button). `assets/theme_sync.js` mirrors that class onto `<body>` — see gotcha #3.

### Tokens — `_CHART[theme]`, the single source of colour

`_CHART` in `app.py` holds every colour, per theme. It is used two ways:

- **Plotly figures and Python code** read the hex values directly (`c = _CHART[theme]; c["accent2"]`).
- **CSS** reads the same values as custom properties: `theme_css()` turns each token into `--token-name` (underscores → hyphens) on `.dark-theme` / `.light-theme`, injected into the page head. `app.css` only ever uses `var(--…)` — never a hex.

| Token | Dark | Light | Use |
|-------|------|-------|-----|
| `bg` | `#111111` | `#ffffff` | page background |
| `surface` | `#1a1a1a` | `#ffffff` | cards, dropdowns, hover labels (light cards are white, set off by their border) |
| `chip` | `#111111` | `#ffffff` | unselected pill background |
| `border` | `#2e2e2e` | `#e5e5e5` | card outlines, hairlines, gridlines, outline buttons |
| `text` | `#ececec` | `#0d0d0d` | primary text, big numbers |
| `subtext` | `#a3a3a3` | `#5d5d5d` | labels, hints, muted text, drilldown bars |
| `label` | `#a3a3a3` | `#5d5d5d` | card titles (`.app-label`) |
| `accent` | `#ececec` | `#0d0d0d` | primary action: filled buttons (ink, not a hue) |
| `accent2` | `#f87171` | `#c62828` | **bad** only: over typical (and the over-typical part of the track), the warning ⚠, worse than last year, negative net |
| `accent3` | `#4fbf7f` | `#1a7f37` | **good** only: under / in line with typical, positive net, saved status |
| `accent_weak` | `#2a2a2a` | `#f2f2f2` | selected pill, hover fill, empty part of tracks |
| `on_accent` | `#111111` | `#ffffff` | text on an accent fill (primary button) |
| `bar` | `#ececec` | `#0d0d0d` | chart marks: grey (45% opacity) for context, full ink for the selected bar |
| `control` | `#737373` | `#858585` | outlines of buttons, the stepper, the dropdown and inputs — ≥ 3:1 against `bg` and `surface` (WCAG 1.4.11), unlike card borders |
| `overlay` | 90% bg | 90% bg | loading-spinner backdrop |

Plus the `--Dash-*` variables Dash 4 components theme themselves with, mapped onto these tokens by `_DASH_VARS`.

**Contrast:** every text colour passes WCAG AA (4.5:1) on both `bg` and `surface`: `subtext` 6.9 (dark) / 6.6 (light), `accent2` 6.3 / 5.6, `accent3` 7.5 / 5.1. Grey bars (45% ink) are 4.0:1 (dark) / 3.1:1 (light) against the card, above the 3:1 needed for marks. Red and green are hard to tell apart with red–green colour blindness, so they never carry meaning alone: every use comes with words or arrows ("over" / "under", ▲ / ▼) or a position (net bars above or below zero).

**Charts are ink, colour means good or bad.** Expense and income bars, category bars and drilldown bars are grey; the selected period or clicked category is full ink (black in light, near-white in dark); "Other" is lighter still. Spending isn't "bad" and income isn't "good", so neither is coloured — only net cash flow is green or red, by its sign. There is no categorical palette.

## Typography

- **Inter** (Google Fonts, falling back to the system sans-serif) for everything, with tabular figures so amounts line up.
- Wordmark: 22px semibold, "Finance" in `text` and "Dashboard" in `subtext`. Big numbers: 28px semibold, -0.02em tracking. Headline sentence: 20–26px semibold.
- Card titles: 12px, uppercase, 0.04em tracking, `label` colour (`.app-label`). Hints: 12px `subtext` (`.hint`).

## Component patterns

- **Cards (`.app-card`)** — `surface` background, 1px `border`, 16px radius, 24px padding, no shadow. Text inside inherits `--text`; coloured text (deltas, warnings) just sets its own class. `card(children)` builds one.
- **Pills** — `dcc.RadioItems` with `className="pills"` and the radio input hidden; each option is a chip. Pills are fully rounded with no outline; hover gets an `accent_weak` fill, and the selected one is an ink fill (`accent`, `on_accent` text) — a grey tint alone is ~1.1:1 against the page. The radios are visually hidden (not `display: none`), so pills are keyboard-focusable and show a focus ring. Used for WEEK / MONTH / YEAR and the labeling panel's tabs. See gotcha #2.
- **Period bar (`.period-bar`)** — sticky row: pills on the left, `‹ label ›` stepper (`.step-btn`, 36px round, outlined) plus a LATEST button on the right. Wraps under 640px.
- **Attention line (`.attention`)** — header line in `text`, a flex row that wraps; each `.attention-item` gets a red (`accent2`) ⚠ and hides when empty, and the whole line is hidden when nothing fires. A warning is a chore, not overspending, so only the icon is red.
- **Headline (`.pace-card`)** — muted label → `.headline-status` sentence (red over typical, green under or in line, ink *Can't say yet* — missing data isn't overspending) → the pace track.
- **Stat cards (`.stat-card`)** — muted title → big number → one `.stat-delta` line against last year (`$450 more than Oct 2024 ($2,420)`) plus the unreviewed line. Only the amount-and-word span is coloured, by `.delta-good` / `.delta-bad`, meaning good/bad *for that metric*.
- **Pace track** — an 8px track (`accent_weak`); spending up to typical is a grey (`subtext`) fill, and only the part past typical is red, when the headline says over; a 2px `text`-coloured marker for typical.
- **Focus and affordance** — `button`, `input`, `summary` and the dropdown get a 2px `text` outline on `:focus-visible`; the clickable charts (spending over time, categories) show a pointer cursor.
- **Buttons** — fully rounded. `.btn-primary` (ink fill, `on_accent` text) for the one main action (SAVE & LAUNCH); `.btn-secondary` (transparent, `border` outline, `text` label, `accent_weak` on hover) for everything else; `.btn-small` for compact ones; `.active` marks the current theme.
- **Settings menu** — a `.app-card` panel under the gear. A transparent full-screen `#settings-backdrop` sits behind it while open, so a click anywhere outside closes it; theme / export / change-folder actions close it too. Reload and import leave it open so their status line stays visible.
- **Labeling panel (`#label-panel`)** — fixed full-screen, `bg` background, scrolls on its own, 32px / 40px padding (20px / 16px under 640px). Content is capped at 1100px (`.label-panel-inner`). Built only from theme tokens and the existing `.app-card`, `.btn-secondary`, `.btn-small`, `.setup-input` and `.pills`. See [features/labeling-panel.md](features/labeling-panel.md).
  - **`.label-group`** — one merchant card (an `.app-card`, 16px / 18px padding, 12px apart). `.lg-main` holds the name block (`.lg-info`) and the `.lg-buttons` row; `.lg-options` holds the subcategory input, the remember checkbox and its note; `.lg-rows` is the expandable row list (`.lg-row`: date, truncated description, right-aligned amount, its own `.lg-buttons`).
  - **`.suggested`** — `.btn-secondary.suggested` gives the TRANSFER button an `accent_weak` fill and `text` colour: a hint that the group looks like a card payment or own-account transfer, never a state. It is subtle by design; it must not read as selected.
  - **`.lg-badge`** — the `MIXED` tag beside a merchant name: 11px, rounded, 1px `accent2` outline and text. It marks a group with money both in and out, which gets row-by-row buttons only.
- **Empty states** — `empty_figure(message)` hides the axes and centres a sentence. Never ship Plotly's bare `-1…6` grid.

## Layering

| z-index | Element |
|---------|---------|
| 100 | `#setup-overlay` — above everything, including the settings menu |
| 90 | `#label-panel` — the full-screen labeling panel; above the settings menu, below the setup overlay |
| 50 | `#settings-menu-wrapper` (gear + panel) |
| 40 | `#settings-backdrop` |
| 30 | `.period-bar` (sticky) |

## CSS gotchas (hard-won)

These cost real debugging time — check here first.

1. **Never use a CSS variable that isn't generated from `_CHART`.** An earlier version styled components with `var(--accent)` etc. *without ever defining them*, so they silently resolved to nothing: the wordmark's accent and the primary button's fill simply didn't render. Every `var(--x)` in `app.css` must have a matching `_CHART` key (or be a `--Dash-*` from `_DASH_VARS`). Adding a colour = add a token to both themes in `_CHART`.

2. **Dash 4.1 RadioItems selection class.** Dash 4 rewrote dcc components. The selected option renders as `<label class="dash-options-list-option selected …">` — style it via `.pills .dash-options-list-option.selected`, **not** the old `input[type=radio]:checked + label` (which never matches Dash-4 markup). The shown dropdown value is `.dash-dropdown-value`.

3. **Dropdown popups render outside `#app-root`.** Dash 4 puts dropdown menus in a portal directly under `<body>`, so tokens defined only on `#app-root` don't reach them. `assets/theme_sync.js` copies `#app-root`'s theme class onto `<body>` (and sets `dark-theme` before Dash renders, so there's no white flash).

4. **dcc.Loading fullscreen hardcodes a white backdrop.** `.dash-spinner-container` sets `background-color: white`; `body .dash-spinner-container { background-color: var(--overlay) !important; }` overrides it in both themes.

5. **Plotly can't read CSS variables.** Figures need real hex values — read them from `_CHART[theme]`, never `var(--…)`. `chart_template(theme)` sets fonts, gridlines, `$` y-axis ticks and themed hover labels (Plotly's default hover label is the trace colour with auto-contrast text, which was unreadable on mid-blue).

6. **Category axes and `$` ticks.** `chart_template` puts a `$` tick prefix on the y-axis. Horizontal bar charts have *categories* on the y-axis, so they must reset `tickprefix=""` or every category name gets a dollar sign.
