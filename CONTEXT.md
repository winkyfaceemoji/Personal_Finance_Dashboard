# Personal Finance

A local dashboard that turns bank and card exports into labeled spending, income and transfers.

## Language

### Transactions and labels

**Bank text**:
The description of a transaction exactly as the bank exported it, store numbers and reference codes included.
_Avoid_: description (in conversation), raw text, memo

**Label**:
A transaction's `master_category`: Expense, Income or Transfer. Anything else, or blank, is unlabeled.
_Avoid_: tag, type

**Rule**:
A merchant's saved label: it labels every transaction of that merchant that has no hand label, past and future. Every rule belongs to exactly one merchant.
_Avoid_: merchant rule, text rule, keyword rule, auto-tag, filter

**Hand label**:
A label stored on the transaction in the master file, set by you (labeling panel, Merchants view or Excel import). It always wins over a rule.
_Avoid_: manual label, saved label

**Rule label**:
A label a rule gives a transaction each time the app loads; it is never stored, so changing or deleting the rule changes it everywhere.
_Avoid_: auto label, derived label

**Unreviewed**:
The money in a period's unlabeled transactions, which totals leave out and show beside them (`+ $X unreviewed`). It skips the sides of likely transfer pairs and copies waiting on a replacement-card question, so it can be less than the header's unlabeled count.
_Avoid_: uncounted, pending

### Merchants

**Merchant**:
Who a transaction was with, at the level you would label it: two bank texts belong to one merchant only if you would always give them the same label (Uber rides and Uber Eats can be two merchants).
_Avoid_: umbrella merchant, brand, company, payee, vendor

**Spelling**:
Bank text with store numbers, reference codes and card-processor prefixes removed; it is what an alias points at. Bank text with no recognisable name (e.g. a real-time payment) has no spelling and belongs to no merchant.
_Avoid_: merchant key (in conversation), cleaned description, keyword

**Merchant alias**:
A confirmed statement that one spelling belongs to a named merchant. It matches that spelling exactly, never a part of it.
_Avoid_: mapping, synonym, alternate name

**Merchant pattern**:
A piece of text a merchant owns (e.g. `zelle payment to`); a new spelling containing it is suggested as that merchant, never joined on its own.
_Avoid_: text rule, keyword

**Alias suggestion**:
The app's guess that a spelling belongs to an existing merchant, from a merchant pattern or from similar-looking names, shown for you to confirm or reject; it is never applied on its own.
_Avoid_: auto-merge, match

### AI chat

**Tool**:
A pre-written lookup the chat's model may call (by category, by merchant); the only source of numbers in an answer.
_Avoid_: function, query, plugin

**Turn**:
One question to one answer: the model's calls, the tools' results, and the reply.
_Avoid_: request, exchange

**Unverified amount**:
A dollar amount in a reply that no tool returned in that turn; shown with a warning, never trusted.
_Avoid_: hallucination (in the UI)
