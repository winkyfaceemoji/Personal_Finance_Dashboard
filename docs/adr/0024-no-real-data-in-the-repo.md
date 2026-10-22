# 0024. No real financial data in the repo: rules live in the data folder, demo data is made up

Status: Accepted

## Context
The GitHub repo is public. `rules.csv` sat in the repo root and was committed; its keywords named real merchants, which showed where the user lives, banks, shops, gambles and donates. Every rule the labeling panel remembers adds another real name. The demo exports in `Test Data/RAW/` were the user's real transactions with dates and amounts shuffled, so they named the same merchants and people.

## Decision
- The app reads and writes rules at `SORTED/rules.csv` in the data folder (`config.get_rules_path`). `FINANCE_RULES_PATH` still overrides it. A root `rules.csv` is git-ignored.
- The demo exports are generated from scratch by `make_demo_data.py`: invented merchants, people, amounts and dates, seeded so a rerun writes the same bytes. The demo's made-up `Test Data/SORTED/rules.csv` is tracked; tests copy it before writing.
- Both the old `rules.csv` and the old demo exports were erased from git history and the branches force-pushed.

Rejected:
- Scrubbing sensitive lines from `rules.csv` and keeping it in the repo: every new remembered rule would need the same review.
- Anonymising real exports again: shuffling dates and amounts left the merchant names, which were the leak.
- Only untracking the files: the old commits would still show them.

## Consequences
- Rules move with the data folder and its backups, like the merchant alias file.
- Pointing the app at a new data folder starts with no rules until you copy them over.
- The demo no longer looks like one real person's spending, so it tests shapes (overlaps, transfers, refunds, nameless payments), not realism.
- GitHub keeps old pull-request pages; removing them needs GitHub Support.
