# 05: Merge, split, rename, with preview and UNDO

**What to build:** On an All merchants card the user can merge a spelling or a whole merchant into another merchant, split a spelling out into its own merchant, and rename a merchant. Each action shows which rows change label and by how many dollars before saving, and UNDO reverses it.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Merge: a spelling or merchant moves into the target. A merchant newly made by a merge is named after its highest-spend spelling
- [ ] Split: a spelling becomes its own merchant (no rule unless the user sets one)
- [ ] Rename: a unique name is required, and a clash is refused with a message
- [ ] Preview: rows and dollars by label, before and after, computed with the same rule application the loader uses
- [ ] Saves go through the two-file save, and a refused save changes nothing and says which file is open
- [ ] UNDO reverses each action while nothing else has written since
- [ ] Tests (seam 2): each action's effect on labels and files, preview equals result, a locked file, UNDO; browser tests for the actions and the preview
