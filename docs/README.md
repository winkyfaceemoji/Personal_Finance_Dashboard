# Documentation

| Area | What's in it |
|------|--------------|
| [features/](features/README.md) | Per-feature architecture — ingest, transforms, charts, drilldown, import/export, setup |
| [design.md](design.md) | UI design system: colours, themes, component patterns, and the CSS gotchas |
| [decisions.md](decisions.md) | Architecture decisions and their rationale (ADR-lite) |

Docs carry lightweight YAML frontmatter (`type`, `title`, `description`, `resource`, `updated`); feature docs name the source file(s) they cover in `resource:`, so a code change points straight to the docs that describe it.
