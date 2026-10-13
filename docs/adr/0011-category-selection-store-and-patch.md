# 0011. Category selection lives in a Store and is patched, not driven by clickData

Status: Accepted

## Context
Clicking a category highlights it and opens a drilldown. The category view started as a pie chart. It is now sorted horizontal bars, which rank and compare more accurately and need no categorical palette. Rebuilding a figure clears its `clickData`, which fights the very click that triggered the rebuild.

## Decision
- The clicked category is held in the `selected-category` `dcc.Store`.
- `highlight_category` applies the highlight with a `Patch` of the bar opacities instead of rebuilding the chart.
- `clickData` is reset to `None` after each click, so re-clicking the same bar registers as a change. Dash fires only on changed inputs.
- The spending-over-time chart uses the same reset for its bar-click navigation.

Rejected: reading the selection straight from `clickData`, and rebuilding the figure on every click.

## Consequences
- Selection is decoupled from the figure.
- A period change clears the selection, so `update_category_chart` must ignore the stale stored value when the period triggered the update.
