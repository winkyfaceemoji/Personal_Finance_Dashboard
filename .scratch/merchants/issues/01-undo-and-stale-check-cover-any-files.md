# 01: Prefactor: UNDO and the stale check cover any set of files

**What to build:** Today the labeling panel's UNDO record and its "something else wrote since" check are hard-wired to two files: the master and the rules file. Make them track a list of files, so later tickets only add the merchant files to that list. Nothing the user sees changes.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The UNDO record stores each tracked file with its modification time as a string (nanosecond times exceed 2^53), for any number of files
- [ ] UNDO restores only while none of the tracked files has changed since the click, and reports that it can't otherwise, as today
- [ ] Labeling, transfer pairs, RELABEL AS TRANSFER and rule deletion all use the list form
- [ ] Every existing test passes unchanged, including the browser tests
