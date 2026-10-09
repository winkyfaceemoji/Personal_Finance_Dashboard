---
type: Design System
title: UI design system
description: Theme tokens, typography, component patterns, and the CSS gotchas behind the dashboard's look.
resource: app.py, assets/app.css, assets/theme_sync.js
updated: 2026-10-09
---

# UI design system

The dashboard is a dark-first, two-theme Dash app with no CSS framework. Styling lives in `assets/app.css` (served automatically by Dash), and every colour in it is a theme token generated from one Python dict. This doc captures the conventions and, more importantly, the non-obvious pitfalls.

## Themes

Two themes — `dark` (default) and `light`. The choice is held in the `theme-store` Store with `storage_type="local"`, so it **persists across reloads**, and `apply_theme` writes it as a `dark-theme` / `light-theme` class on `#app-root` (and highlights the active LIGHT / DARK button). `assets/theme_sync.js` mirrors that class onto `<body>` — see gotcha #3.

### Tokens — `_CHART[theme]`, the single source of colour

`_CHART` in `app.py` holds every colour, per theme. It is used two ways:

- **Plotly figures and Python code** read the hex values directly (`c = _CHART[theme]; c["accent2"]`).
- **CSS** reads the same values as custom properties: `theme_css()` turns each token into `--token-name` (underscores → hyphens) on `.dark-theme` / `.light-theme`, injected into the page head. `app.css` only ever uses `var(--…)` — never a hex.

| Token | Dark | Light | Use |
|-------|------|-------|-----|
| `bg` | `#0a0a0f` | `#ffffff` | page background |
| `surface` | `#111318` | `#f0f1f5` | cards, buttons, dropdowns, hover labels |
| `chip` | `#0a0a0f` | `#ffffff` | unselected pill background |
| `border` | `#252830` | `#dcdee8` | hairlines, gridlines, bar tracks |
| `text` | `#ffffff` | `#0a0a0f` | primary text, big numbers |
| `subtext` | `#8a8fa8` | `#5c5f72` | labels, hints, muted text |
| `label` | `#e0e2f0` | `#5c5f72` | card titles (`.app-label`) |
| `accent` | `#6c8aff` | `#3d5bd9` | primary accent (blue): selection, category bars, highlighted year |
| `accent2` | `#ff6c8a` | `#c42a4f` | spending / "bad" (red) |
| `accent3` | `#6cffd4` | `#067a58` | income / "good" (green) |
| `accent_weak` | 18% accent | 12% accent | selected-pill tint |
| `on_accent` | `#0a0a0f` | `#ffffff` | text on an accent fill (primary button) |
| `muted_line` | `#4a4f63` | `#c3c7d6` | non-highlighted seasonality years |
| `overlay` | 90% bg | 90% bg | loading-spinner backdrop |

Plus the `--Dash-*` variables Dash 4 components theme themselves with, mapped onto these tokens by `_DASH_VARS`.

**Contrast:** light-theme accents are darkened so small text passes WCAG AA (4.5:1) on `surface`: `accent` 5.0, `accent2` 4.9, `accent3` 4.7. `subtext` is 5.8 (dark) / 5.6 (light).

**Charts use colour for meaning, not identity.** Red is spending, green is income, blue is "selected / this one", muted grey is context. There is no categorical palette: category bars are all the accent, and the seasonality chart highlights one year against muted others. That avoids near-identical hues and the light-mode contrast failures a 12-colour palette had.

## Typography

- **Syne** — display: the wordmark, big stat numbers, the period label.
- **IBM Plex Mono** — everything else: labels, pills, hints, figures in charts.
- Card titles: 11px, uppercase, 2px tracking (`.app-label`). Hints: 11px `subtext` (`.hint`). The wordmark scales with `clamp(24px, 5vw, 32px)`.

## Component patterns

- **Cards (`.app-card`)** — `surface` background, 1px `border`, 12px radius, 24px padding. Text inside inherits `--text`; coloured text (deltas, warnings) just sets its own class. `card(children)` builds one.
- **Pills** — `dcc.RadioItems` with `className="pills"` and the radio input hidden; each option is a chip. The selected one gets an accent border and `accent_weak` tint. Used for WEEK / MONTH / YEAR and the seasonality Expenses/Income toggle. See gotcha #2.
- **Period bar (`.period-bar`)** — sticky row: pills on the left, `‹ label ›` stepper (`.step-btn`, 36px square) plus a LATEST button on the right. Wraps under 640px.
- **Stat cards (`.stat-card`)** — muted title → Syne number → two `.stat-delta` lines. Delta colour comes from `.delta-good` / `.delta-bad` and means good/bad *for that metric*.
- **Pace strip (`.pace-card`)** — a 10px track (`border`), a fill (red ahead of pace / green under), and a 2px `text`-coloured marker for "typical by now".
- **Buttons** — `.btn-primary` (accent fill, `on_accent` text) for the one main action (SAVE & LAUNCH); `.btn-secondary` (transparent, accent outline) for everything else; `.btn-small` for the settings menu; `.active` marks the current theme.
- **Settings menu** — a `.app-card` panel under the gear. A transparent full-screen `#settings-backdrop` sits behind it while open, so a click anywhere outside closes it; theme / export / change-folder actions close it too. Reload and import leave it open so their status line stays visible.
- **Labeling panel (`#label-panel`)** — fixed full-screen, `bg` background, scrolls on its own, 32px / 40px padding (20px / 16px under 640px). Content is capped at 1100px (`.label-panel-inner`). Built only from theme tokens and the existing `.app-card`, `.btn-secondary`, `.btn-small`, `.setup-input` and `.pills`. See [features/labeling-panel.md](features/labeling-panel.md).
  - **`.label-group`** — one merchant card (an `.app-card`, 16px / 18px padding, 12px apart). `.lg-main` holds the name block (`.lg-info`) and the `.lg-buttons` row; `.lg-options` holds the subcategory input, the remember checkbox and its note; `.lg-rows` is the expandable row list (`.lg-row`: date, truncated description, right-aligned amount, its own `.lg-buttons`).
  - **`.suggested`** — `.btn-secondary.suggested` gives the TRANSFER button an `accent_weak` fill and `text` colour: a hint that the group looks like a card payment or own-account transfer, never a state. It is subtle by design; it must not read as selected.
  - **`.lg-badge`** — the `MIXED` tag beside a merchant name: 10px, 1px letter-spacing, 1px `accent2` outline and text. It marks a group with money both in and out, which gets row-by-row buttons only.
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
