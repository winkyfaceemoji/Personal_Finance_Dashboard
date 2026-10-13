# 0016. Local-only and debug-off by default

Status: Accepted

## Context
The app has no login, yet its settings menu can export every transaction, overwrite labels and repoint the data folder. Debug mode also exposes tracebacks and the Werkzeug debugger.

## Decision
- `app.py` binds to `127.0.0.1` with debug off unless `FINANCE_HOST` / `FINANCE_DEBUG` say otherwise.
- The Docker image sets `FINANCE_HOST=0.0.0.0`, which port forwarding requires, and `FINANCE_DEBUG=1` for hot reload.
- Because of that, the documented `docker run` publishes only to `-p 127.0.0.1:8050:8050`.

Rejected: binding to all interfaces by default, and a bare `-p 8050:8050`.

## Consequences
- Exposing the app to the network is an explicit opt-in.
- Any new run instructions must keep the loopback-only publish.
