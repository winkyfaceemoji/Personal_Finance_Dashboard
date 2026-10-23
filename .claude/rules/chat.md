---
paths:
  - Modules/chat.py
  - Modules/chat_tools.py
  - app.py
  - ai_eval.py
  - start_llm.ps1
  - tests/test_chat_*.py
---

# AI chat

Background: ADR 0021 and `docs/specs/ai-chat.md`. Terms are in `CONTEXT.md`.

## The rule
- The model only chooses a tool and its inputs. Every number comes from `Modules/chat_tools.py`, already totalled and formatted as dollars. Never give the model raw rows, or a tool that runs code or queries.
- `call_tool` re-checks the schema's enums (direction, category) itself, whatever llama-server does with them. A bad request returns `{"error": …}` for the model to read; it never guesses.
- A fact the page states, like the date range or the unreviewed money, goes under the answer from code (`_chat_period`, `_unreviewed_note`). Don't rely on the prompt to make the model say it.
- Totals are label-based (ADR 0007), and the unreviewed amount is counted with `_counted_rows`, exactly as the stat cards count it.
- `spending_by_category` uses `category_split` with the chart's `CATEGORY_TOP_N`, so its lines are the chart's bars. Change the number there, never per caller.

## Turn and status line
- Dash rejects callback cycles, so a Store can't drive a loop. One ordinary callback (`chat_send` → `_chat_turn` → `run_turn`) runs the whole turn and writes its status to `_CHAT_PROGRESS`.
- `chat-poll` (an Interval, switched on by `running=` only while the turn runs) reads that status. The poll never calls the model. This isn't a background callback (ADR 0010).
- `chat_send` clears `chat-status` itself: the Interval stops before its last tick, so the final status would otherwise stay on screen.
- While the model server is down, `toggle_chat` disables SEND *and* the box. Disabling SEND alone isn't enough: Enter in the box still fires `chat_send`, and its `running=` turns SEND back on when the turn ends. A model still loading keeps both on.
- `run_turn` stops after 4 model calls and never raises. A server problem comes back as `error`, telling the user how to start it.

## Model settings
- Thinking is off (`chat_template_kwargs.enable_thinking: false`) and temperature is 0. `--jinja` is needed for tool calls.
- After changing the prompt, the tools or the model, run `ai_eval.py` against the real server. A 9B model varies a little, so a single failure is a hint, not a verdict. Fix a wrong expectation in `CASES` only when the answer was right.
