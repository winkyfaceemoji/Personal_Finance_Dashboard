# 0010. No Dash background callbacks

Status: Accepted

## Context
Reload and Import can take a moment, and Dash offers `background=True` callbacks for long-running work.

## Decision
Reload and Import run synchronously, and a `dcc.Loading` overlay shows that they are working.

Rejected: background callbacks. They can run in a separate process, which would break the module-global `df` that Reload mutates and every callback reads.

## Consequences
- Loading feedback needs no extra infrastructure.
- The module-global `df` stays the single in-memory source of truth.
- `dcc.Loading`'s hardcoded white backdrop must be overridden in CSS.
