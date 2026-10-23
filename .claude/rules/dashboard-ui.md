---
paths:
  - app.py
  - assets/*
---

# Dashboard UI, callbacks & styling

## Colour tokens
- `_CHART[theme]` in `app.py` is the only source of colour. `theme_css()` turns each key into `--key-name` (underscores become hyphens) on `.dark-theme` / `.light-theme`. `app.css` uses only `var(--…)`, never a hex.
- **Never use a CSS variable that isn't generated from `_CHART`** or `_DASH_VARS` (`--Dash-*`). An earlier version used `var(--accent)` without defining it. It silently resolved to nothing, and the wordmark accent and primary button fill vanished. To add a colour, add the token to *both* themes.
- **Plotly can't read CSS variables.** Figures take hex from `_CHART[theme]` through `chart_template(theme)`. Its themed hover labels exist because Plotly's default (trace colour plus auto-contrast text) was unreadable.
- Colour means good or bad only:
  - `accent2` is red/bad, `accent3` is green/good.
  - Spending and income bars are grey ink. Selected bars are full ink. There is no categorical palette.
  - Red and green never carry meaning alone. Always pair them with words, ▲/▼, or position.
- Every text colour must pass 4.5:1 on `bg` *and* `surface`. `control` outlines must pass 3:1 (WCAG 1.4.11).

## CSS gotchas (hard-won)
1. **No blanket descendant colour rules.** A past `.dark-theme .app-card * { color: … !important }` overrode every child's text colour, inline styles included, and forced coloured content out of cards. It has been removed. Text in `.app-card` inherits `--text`, and coloured text sets its own class (`.delta-good` / `.delta-bad`). Don't reintroduce a `*` colour override.
2. **Dash 4.1 RadioItems.** The selected option renders as `.dash-options-list-option.selected`. Style it as `.pills .dash-options-list-option.selected`. The old `input[type=radio]:checked + label` never matches Dash 4 markup. The shown dropdown value is `.dash-dropdown-value`.
3. **Dropdown popups render in a portal under `<body>`**, outside `#app-root`, so tokens on `#app-root` don't reach them. `assets/theme_sync.js` mirrors the theme class onto `<body>`. It sets `dark-theme` before Dash renders, so there's no white flash.
4. **`dcc.Loading` hardcodes a white backdrop** (`.dash-spinner-container`). It is overridden by `body .dash-spinner-container { background-color: var(--overlay) !important; }`.
5. **Category axes and `$` ticks.** `chart_template` adds a `$` y-tick prefix. Horizontal bar charts have categories on y, so they must reset `tickprefix=""`.
6. **Dash 4 styles interactive states with our colours.** Hover and focus use `--Dash-Fill-Interactive-Strong`, which maps to our ink, at specificity 0,3,1. A selected pill that kept focus turned ink-on-ink, which showed as blank. Don't remap the variable, because checkbox and input focus rely on it. Instead, any Dash component we restyle owns *every* state, scoped under `#app-root` so it outranks Dash.
7. Pills use visually hidden radios, not `display: none`, so they stay keyboard-focusable. Hover fills apply only under `@media (hover: hover)`, because a phone keeps `:hover` on the last tapped pill.
8. "Selected" looks the same everywhere: an ink fill, in every state, with a border in forced-colors mode. The light grey fill means hover, or the panel's *suggested* button. Never use it for selection.

## Verifying styles
`tests/test_ui_states.py` (Playwright + Chromium; it skips without a browser) clicks, hovers, taps and tabs every control in both themes. It checks contrast, focus rings, the dropdown's current-choice mark, and the keyboard and screen-reader paths below. A style change isn't done until it passes. A resting screenshot proves nothing about hover or focus.

## Layering (z-index)
`#setup-overlay` 100 > `#label-panel` 90 > `#settings-menu-wrapper` 50 > `#chat-panel` 45 > `#settings-backdrop` 40 > `.period-bar` (sticky) 30.

## Callbacks
- `df` is a module global that reload, import, labeling and setup reassign (`global df`). Never use `background=True` callbacks: they can run in another process (ADR 0010).
- `_run_ingest_pipeline()` is the single entry to `main.main()`. `reload_data` passes `MASTER_PATH.parent.parent` explicitly, and `save_setup` passes the picked folder (see the ingest rule).
- Category selection (ADR 0011):
  - It lives in the `selected-category` Store, and `highlight_category` Patches the opacities.
  - Reset `clickData` to `None` after a click, or re-clicking the same bar won't fire.
  - `update_category_chart` must ignore the stored selection when the *period* triggered it. Otherwise a never-clicked bar lights up in the new period.
  - `select_category` alone writes `category-pick.value` (ADR 0027). It takes the Store as an Input so the picker follows a selection set elsewhere (the chat). A second callback writing the picker from the Store would make a cycle across callbacks, which Dash rejects.
- The chart, the drilldown and the AI chat all use `category_split` (through `_category_split` in the app), so a drilldown total or a chat answer always equals its bar, including Other.
- Outputs written by several callbacks (`setup-overlay.style`, `setup-status`, `setup-path-input.value`, `refresh-trigger`, …) need `allow_duplicate=True`.
- Reload and import leave the settings menu open so their status line stays visible.
- The stat cards never show a comparison while the headline says *Can't say yet* (`cant_say_reasons`).
- The spending chart's dashed line is labelled "median", never "typical". It is the median of the complete periods on screen, a different measure from the headline's typical. Its label lives in the note under the chart (`period-chart-note`, with the striped bar's meaning). A label drawn on the line sat on whichever bars were near it, at the right *and* at the left.

## Keyboard & screen readers (WCAG 2.1 AA; tests in `test_ui_states.py`)
- **`dcc` components take no `aria-*` props** (Input, Dropdown, RadioItems, Graph, Upload all raise). Name a text box with `_labeled(text, input)`, a `<label>` with `.input-label { display: contents }` so it adds no box. Name pills or a dropdown with `_named_group`. Never leave a placeholder as the only name. `html.*` components do take `aria-*` via `**{...}`, and a callback can output one (`Output(id, "aria-pressed")`).
- `#label-panel` is a dialog. `assets/dialog.js` moves focus in on open, keeps Tab inside, closes on Escape (through DONE, so the close callback runs) and returns focus to the opener. It watches the panel's `style`, so keep opening and closing it through `display`. Its key handler runs in the capture phase and leaves Escape alone while a dropdown is open (Dash renders those in a portal outside the panel), so Escape closes the dropdown first.
- Pill groups stay Dash's `listbox`/`option` markup, named by `_named_group`. A script rewriting them to tabs or radios was turned down: it would break on a Dash update, and the listbox already announces the selected option.
- Buttons repeated per row (EXPENSE / INCOME / TRANSFER, YES / NO) carry an `aria-label` naming their row or merchant. A screen reader lists dozens of identical words otherwise.
- The bars can't take focus. `category-pick` is the keyboard's way to a bar click (ADR 0027), and each chart has a `.sr-only` text version. Keep those in step when the chart changes.
- Chat output regions are live (`role="log"`, `role="status"`). The chat rule covers SEND while the model is down.
- A word a reader needs explained gets visible text (the All merchants view's `Spellings:` line). A `title` reaches only mouse users.
- No text under 12px, chart text included.
- `dcc.Upload`'s own file `<input>` is a second, nameless tab stop. app.css hides it (`display: none`); its button still opens the picker.
- Empty states use `empty_figure(message)`. Never ship Plotly's bare `-1…6` grid.
