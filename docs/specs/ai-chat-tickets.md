# Tickets: AI chat, phase 2

Status: all seven done. `ai_eval.py` passed 20/20 on Qwen3.5-9B-Q8_0, twice.

Spec: `docs/specs/ai-chat.md`. Each ticket is built test-first and is done when its tests pass and the full suite is green.

1. **Category split in `Modules/transforms.py`.** Move the top-N plus Other logic out of `_category_split`, add a `direction` (`out`/`in`), and have the chart and drilldown call it. *Done:* the chart's numbers are unchanged, and money in splits the same way.
2. **Tools (`Modules/chat_tools.py`).**
   - `spending_by_category`, `spending_by_merchant` (category and name filters, matched names), and `tool_schemas` with the fixed category list.
   - These are pure functions. The app passes in the period's rows, the unreviewed amounts and the date range.
   - *Done:* the totals equal the page's on Test Data, and Test Data's merged merchant ("Zelle received") comes out as one line.
3. **Number check (`Modules/chat_tools.py`).** `unverified_amounts(reply, results)`. *Done:* amounts quoted from a tool pass, made-up ones are listed, and negatives and amounts without cents are handled.
4. **Model client and turn loop (`Modules/chat.py`).**
   - `health`, `complete` (HTTP through `requests`), and `run_turn`, which loops model → tools until there's an answer.
   - It takes a progress callback, stops after 4 model calls, and handles unknown tools, bad tool arguments and the server going down.
   - *Done:* tested against a fake HTTP server, with no model needed.
5. **Chat panel (`app.py`, `assets/app.css`).**
   - A CHAT button, and a right-hand panel that's hidden by default.
   - A Store for the history, the "not running" line, and a status line polled by an Interval.
   - The reply shows its date range and any unverified amounts.
   - It sets `selected-category` when the turn used exactly one category.
   - *Done:* the panel runs against a fake server, and `test_ui_states.py` covers the button in both themes.
6. **`start_llm.ps1` and `ai_eval.py`.**
   - The start script for llama-server.
   - About 20 questions on Test Data, each with the tool and inputs expected and a check for unverified amounts.
   - *Done:* the script runs against the real model and reports how many pass, run by hand.
7. **Docs.** `readme.md` (how to start the model, the chat section), `CLAUDE.md` (the command and the `FINANCE_LLM_URL` variable), and a path rule for the chat files.
