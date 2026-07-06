---
type: Design System
title: UI design system
description: Colors, theme mechanics, component patterns, and the CSS gotchas behind the dashboard's look.
resource: app.py, assets/dropdown_theme.css
updated: 2026-07-06
---

# UI design system

The dashboard is a dark-first, two-theme Dash app with no CSS framework. All styling lives in `app.py`'s `index_string` `<style>` block plus `assets/dropdown_theme.css`. This doc captures the conventions and, more importantly, the non-obvious pitfalls.

## Themes

Two themes — `dark` (default) and `light` — held in the `theme-store` and applied as a `dark-theme` / `light-theme` class on `#app-root`. All theme CSS is scoped under those classes.

### Colours — `_CHART[theme]`

Plotly figures and any inline-styled component read real hex values from the `_CHART` dict (never CSS variables — see gotcha #2). One entry per theme:

| Token | Dark | Light | Use |
|-------|------|-------|-----|
| `text` | `#ffffff` | `#0a0a0f` | primary text / neutral values |
| `subtext` | `#8a8fa8` | `#5c5f72` | labels, muted text |
| `surface` | `#111318` | `#f0f1f5` | card background |
| `border` | `#252830` | `#dcdee8` | hairlines, dividers, chip borders |
| `accent` | `#6c8aff` | `#4a68e8` | primary accent (blue) |
| `accent2` | `#ff6c8a` | `#d63157` | expenses / "bad" (red) |
| `accent3` | `#6cffd4` | `#0a9e72` | income / "good" (green) |

`PIE_COLORS` is a fixed 12-hex categorical palette (theme-independent) for pie slices and trend lines. A category keeps its colour across years via its all-time spend rank, so switching year chips never re-colours it.

Callbacks that build figures/components pull `c = _CHART[theme]` and use `c["accent2"]` etc. That is the reliable path for colour in both themes.

## Typography

- **Syne** (`'Syne', sans-serif`) — display: the big stat numbers and the FINANCE title.
- **IBM Plex Mono** — everything else: labels, chip text, mono figures, the cash-flow dropdown-as-title.

## Component patterns

- **Cards (`.app-card`)** — surface bg, 1px border, 12px radius. Chart cards and the settings panel. ⚠ see gotcha #1.
- **Pill chips** — `dcc.RadioItems` with the radio input hidden and each option styled as a pill (padding, 6px radius, bold, letter-spacing). Used for the cash-flow range (YTD/1Y/3Y), year chips, and the Expenses/Income toggle. The selected pill is accent-tinted — see gotcha #3.
- **Stat cards** (YTD summary) — small muted label → large neutral number → coloured good/bad delta. Hand-styled inline with `_CHART` hex (not `.app-card`) specifically to keep the coloured delta visible (gotcha #1). Delta colour is good/bad *per metric*, not up/down: expenses up = red, income up = green; the % divides by `abs(prior)` so the arrow stays correct when the prior value was negative.
- **Buttons (`.btn-secondary`)** — transparent bg, accent outline, mono. Every settings-menu button shares this one style (no per-button variants).

## CSS gotchas (hard-won)

These cost real debugging time — check here first.

1. **`.app-card *` forces child text colour.** `.dark-theme .app-card * { color: #ffffff !important }` (and the light equivalent) overrides *every* descendant's text colour, beating inline `color`. → Anything needing a custom text colour (coloured figures, red/green deltas) must **not** be nested in `.app-card`; build the container inline with `_CHART` hex instead. This is why the stat cards and the category drilldown are hand-styled divs, not `card()` wrappers.

2. **The `--*` CSS variables in `COLORS` are mostly undefined.** `COLORS["surface"] = "var(--surface)"` and friends reference custom properties that are never declared, so they resolve to nothing (inheriting the parent colour). Only a few have inline fallbacks. → For anything that must render a specific colour, trust `_CHART[theme]` hex, not the `COLORS[...]` `var()` strings.

3. **Dash 4.1 RadioItems selection class.** Dash 4 rewrote dcc components. The selected option renders as `<label class="dash-options-list-option selected …">` — style it via `.dash-options-list-option.selected`, **not** the old `input[type=radio]:checked + label` (which never matches Dash-4 markup). The container carries the RadioItems `id`; the shown dropdown value is `.dash-dropdown-value`.

4. **dcc.Loading fullscreen hardcodes a white backdrop.** `.dash-spinner-container` sets `background-color: white`. Override per theme with `.dark-theme .dash-spinner-container { … !important }` — the `.dark-theme`-scoped selector (specificity 0,2,0) beats the component's inline rule (0,1,0).

5. **Theme classes reach fixed-position overlays.** The fullscreen spinner is `position: fixed` but still a DOM descendant of `#app-root`, so `.dark-theme <selector>` theming cascades to it.

> When you learn a new styling pitfall in this app, add it here — that's the whole point of this doc.
