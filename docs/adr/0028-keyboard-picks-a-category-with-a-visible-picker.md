# 0028. The keyboard picks a category with a visible picker beside the chart

Status: Accepted

## Context
Clicking a category bar selects it and opens its drilldown (ADR 0011). Plotly bars can't take keyboard focus, so keyboard and screen-reader users had no way to reach the drilldown (WCAG 2.1.1), and the charts' numbers lived only in hover text (1.1.1).

## Decision
- A "Pick a category" dropdown (`category-pick`) sits in the category card's head. It writes the same `selected-category` Store as a bar click.
- `select_category` owns the picker's value. It listens to the Store too, so the picker follows a selection made by a click or by the chat. Every write stays in that one callback, because Dash rejects a cycle that runs across two callbacks.
- Each chart also renders its numbers as visually hidden text (`period-chart-text`, `category-chart-text`) for screen readers.
- The spending chart's bar click needs no picker: the ‹ › stepper already reaches every period from the keyboard.

Rejected:
- Hidden category buttons reachable only by keyboard or screen reader: no visual change, but harder to find, and sighted keyboard users can't see where focus is.
- Text summaries alone: the smallest change, but picking a category would stay mouse-only.

## Consequences
- The picker adds a control to the card's head, styled like the EXPENSES title dropdown.
- Dash 4's dropdown doesn't always move focus into its list when it opens. Tab reaches the options then, which is Dash's own behaviour and the same for every dropdown.
