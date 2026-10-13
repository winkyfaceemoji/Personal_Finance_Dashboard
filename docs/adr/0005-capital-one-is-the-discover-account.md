# 0005. Capital One exports are the Discover account; the Discover history owns its dates

Status: Accepted

## Context
Capital One took over the Discover card: the card stayed the same and only its exporter changed. Under folder-authoritative identity (0004), the natural `RAW/CapitalOne/` folder made the card a second account and silently double-counted every overlapping date.

## Decision
- Capital One-format files are filed under the Discover institution, whatever folder they sit in (`CAPITAL_ONE_ACCOUNT`).
- Within that account, Discover-format files outrank any date span (`FORMAT_PRIORITY`).
- A Capital One row on a Discover-owned date with no same-date, same-amount Discover row is listed in `SORTED/overlap_only.csv` and shown on the attention line. It is reported, not added back.

Rejected (council review):
- A doc rule ("keep them in RAW/Discover/"). It is no safeguard in a drop-files-and-Reload workflow.
- Plain span ranking. A Capital One "download everything" export would take over years of labeled Discover dates and orphan their labels, because Capital One words merchants differently.

## Consequences
- The Discover history is treated as a closed archive.
- A charge still pending at the switch exists only in the Capital One export, so it is dropped. It is reported rather than re-added, because a changed amount would count one charge twice.
- A second Capital One card would also be read as Discover. If that happens, `Card No.` is the field to separate them.
