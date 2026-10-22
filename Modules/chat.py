"""
The AI chat's link to a local llama-server (ADR 0021): a health check, one
chat completion over HTTP, and the turn loop (model → tools → model) that
ends in an answer. The tools themselves live in Modules/chat_tools.py.
No Dash here; the app supplies the tool runner and a progress callback.
"""
import json
import os

import requests

DEFAULT_URL = "http://127.0.0.1:8080"
MAX_MODEL_CALLS = 4
TIMEOUT = 180          # seconds per model call; a long answer on a 9B model


def llm_url() -> str:
    return os.environ.get("FINANCE_LLM_URL", DEFAULT_URL).rstrip("/")


def health(url: str) -> str:
    """"ok", "loading" (the server is up but still loading the model) or "down"."""
    try:
        r = requests.get(f"{url}/health", timeout=2)
    except requests.RequestException:
        return "down"
    return "ok" if r.status_code == 200 else "loading" if r.status_code == 503 else "down"


def complete(url: str, messages: list[dict], tools: list[dict]) -> dict:
    """One chat completion; returns the assistant message. Thinking is off and
    temperature 0, so the same question picks the same tools."""
    r = requests.post(f"{url}/v1/chat/completions", timeout=TIMEOUT, json={
        "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False}})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def describe_call(name: str, args: dict) -> str:
    """The status line while a tool runs."""
    way = "money in" if args.get("direction") == "in" else "money out"
    if name == "spending_by_category":
        return f"Looking up {way} by category…"
    if args.get("name"):
        return f"Searching merchants for “{args['name']}”…"
    if args.get("category"):
        return f"Looking up {args['category']} by merchant…"
    return f"Looking up {way} by merchant…"


def run_turn(url: str, messages: list[dict], tools: list[dict], call_tool, progress=lambda text: None) -> dict:
    """Run one question to an answer. Returns {"reply", "error", "calls",
    "results"}: `calls` are the tool calls that ran, `results` what they
    returned (the number check reads them). A server problem gives `error`
    and no reply; it never raises."""
    messages = list(messages)
    calls, results = [], []
    for _ in range(MAX_MODEL_CALLS):
        try:
            msg = complete(url, messages, tools)
        except (requests.RequestException, KeyError, IndexError, ValueError):
            return {"reply": None, "calls": calls, "results": results,
                    "error": f"The model server isn't responding at {url}. Start it with start_llm.ps1."}
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"reply": (msg.get("content") or "").strip(), "error": None, "calls": calls, "results": results}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                result = {"error": "The tool arguments were not valid JSON."}
            else:
                progress(describe_call(name, args if isinstance(args, dict) else {}))
                result = call_tool(name, args)
                calls.append((name, args))
                results.append(result)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": json.dumps(result, ensure_ascii=False)})
    return {"reply": f"I couldn't finish that in {MAX_MODEL_CALLS} steps. Try asking something narrower.",
            "error": None, "calls": calls, "results": results}
