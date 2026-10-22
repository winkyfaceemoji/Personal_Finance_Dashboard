# 0024. Rules are private data: they live in the data folder, not the repo

Status: Accepted

## Context
`rules.csv` sat in the repo root and was committed. Its keywords name real merchants, which showed where the user lives, banks, shops, gambles and donates, and the GitHub repo is public. Every rule the labeling panel remembers adds another real name.

## Decision
- The app reads and writes rules at `SORTED/rules.csv` in the data folder (`config.get_rules_path`). `FINANCE_RULES_PATH` still overrides it.
- A root `rules.csv` is git-ignored, so a stray copy can't be committed again.
- The demo gets its own made-up `Test Data/SORTED/rules.csv`, tracked. Tests copy it before writing.

Rejected:
- Keeping `rules.csv` in the repo and scrubbing sensitive lines: every new remembered rule would need the same review.
- Only untracking it: the old commits would still show it.

## Consequences
- Rules move with the data folder and its backups, like the merchant alias file.
- Pointing the app at a new data folder starts with no rules until you copy them over.
- A clone of the repo has no personal rules.
