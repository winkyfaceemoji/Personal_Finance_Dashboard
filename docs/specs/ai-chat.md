# Spec: local AI chat

Status: agreed in a grilling session on 2026-10-22. Phase 2 is built (tickets: `docs/specs/ai-chat-tickets.md`).

## Goal
Ask plain-English questions about your spending ("where did the Dining money go?") in a chat beside the dashboard. A local model answers from pre-written, tested tools, so every number comes from code, never from the model.

## Phases
1. **Merchant rework** (ADR 0025). What phase 2 needs is on main: `merchant_of` and `merchant_list` in `Modules/merchants.py`. The rest of the rework doesn't change them.
2. **Chat with data tools.** This spec's main subject.
3. **Recommendations from a cited knowledge base.** Built after phase 2, with the embedding server set up in its own session.
4. **Roadmap, not now:** the app runs the model itself, with an option to connect your own model (see `readme.md`).

## Phase 2: chat with data tools

### Rule
The model only picks a tool and its inputs, then puts the result into words. It never writes code or queries (ADR 0021). A tool may return figures the page doesn't show. The chat is **read only**: it never writes the master, `rules.csv` or any side file.

### Model and connection
- Qwen3.5-9B (`Qwen3.5-9B-Q8_0.gguf`), served by `llama-server`, which the user starts.
- `start_llm.ps1` in the repo starts it with the model path and flags: `--jinja -ngl 99 -c 16384`, on `127.0.0.1:8080`.
- The app sends plain HTTP requests with `requests` (already installed) to `FINANCE_LLM_URL`, default `http://127.0.0.1:8080`, using the `/v1/chat/completions` endpoint with tools. `GET /health` decides whether the panel shows the "not running" line.
- Thinking mode is off. Temperature is 0.

### UI
- A **CHAT** button shows and hides a panel on the right. While it's open, the page sits on the left. The panel is closed by default.
- If `llama-server` can't be reached, the panel shows one line saying so and how to start it.
- **Replies:** each one appears in full when ready. While it's working, a status line shows each tool call ("Looking up Dining by merchant…").
  - ADR 0010 rules out background callbacks, and Dash can't loop callbacks through a Store. So one ordinary callback runs the whole turn (model call → tools → model call) and records each step's status in an in-memory dict, keyed by the chat's id. While the turn runs, a `dcc.Interval` reads that dict for the status line. It never calls the model.
- **Period:** the chat uses the period picked on the page and can't change it. Under every answer, code adds the period's date range and the stat cards' unreviewed money (`+ $X money out unreviewed, not counted`).
- **History:** kept for the open tab only, so a reload clears it. Nothing is written to disk.
- **Driving the page:** when an answer is about one category, the chat sets the `selected-category` Store (ADR 0011). That highlights the bar and opens its drilldown. Merchant lists and name searches stay in the chat.
- Styling follows the dashboard-ui rule: only `_CHART` tokens, both themes, and `tests/test_ui_states.py` covers the new controls.

### Tools
Each tool runs on the selected period. Every result includes:
- the date range;
- the amounts already formatted as dollars;
- the totals, counts and averages, already worked out;
- the `+ $X unreviewed` amount.

Totals follow ADR 0007: label-based only, with Transfer and unlabeled rows excluded.

| Tool | Inputs | Returns |
|------|--------|---------|
| `spending_by_category` | `direction`: `out` \| `in` | One line per category (amount, share, count), an `Other · N` line matching `_category_split`, and the total. |
| `spending_by_merchant` | `direction`; optional `category`; optional `name` | Top 10 merchants (amount, charges, average), an `Other · N merchants` line, and the total. With `name`: every merchant whose bank description contains the text, *plus the list of merchant names it matched*. |

- `category` is a fixed list in the tool schema: every category in the whole history, not just the period. A category with no spending this period returns $0.
- Merchants come from `merchant_of` (ADR 0025): the merged merchant's name, otherwise the row's spelling. Rows with no spelling are grouped as `(no recognisable name)`. The name search matches text in the merchant's name or in the bank text, using `normalize_description` on both sides, so "amazon" also finds an `amzn mktp us` spelling aliased to Amazon. It reports each merchant it matched with that merchant's spellings, from `merchant_list`.
- **Number check:** the model is told to quote tool numbers and never do arithmetic. The app finds every dollar amount in a reply and marks any amount that doesn't appear in that turn's tool results as *unverified*.
- A question the tools can't answer (comparisons, recurring charges, "when did I last…") gets a reply saying it can't answer that yet.

### Tests
- **pytest (in CI):**
  - each tool against Test Data, checked against what the page shows (the category totals equal the chart);
  - the number check;
  - the tool-call loop, run against a fake server.
  - No test needs a model.
- **Question set (by hand):** `ai_eval.py` runs about 20 questions through the real `llama-server` on Test Data. For each one it checks the tool called, the inputs, and that the reply has no unverified amounts, then reports how many passed. Not in CI.

## Phase 3: recommendations (outline)
- **When:** only when you ask. The model fetches data through the tools, searches the knowledge base, and must cite a passage for every recommendation. With no matching passage, there is no recommendation (ADR 0022).
- **Incomplete data** (over 14 days old, or more than 10% unlabeled): it still gives recommendations, with a warning line. This deliberately differs from the headline's *Can't say yet* rule.
- **Knowledge base:**
  - public guidance kept in the repo, starting with summaries of public sources, each with its source link;
  - Markdown is the source; you write it with a model's help, and checking it against your philosophy happens while writing it;
  - a script converts the Markdown to JSONL, giving each passage a stable ID, its source link and a content hash;
  - both files are committed, and a test fails when the JSONL is out of date.
- **Search:** BM25 plus embeddings. The app starts a small embedding `llama-server`; how is being decided in its own session. While it's down there are no recommendations, and the chat says why.

## Out of scope
- Writing labels or rules from the chat.
- RAG over transactions (ADR 0021).
- Spending checks invented by the model.
- Persisting chat history.
- Budgets (ADR 0018).
