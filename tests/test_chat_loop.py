"""The chat's model client and turn loop (ADR 0021), against a fake
llama-server on a real local socket. No model is needed."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from Modules.chat import health, run_turn

TOOLS = [{"type": "function", "function": {"name": "spending_by_category", "parameters": {}}}]


class FakeServer:
    """Answers /v1/chat/completions from a script of assistant messages (the
    last one repeats) and /health with a fixed status; records every request."""

    def __init__(self, script, health_status=200, hook=None):
        self.script, self.requests, self.health_status = list(script), [], health_status
        self.hook = hook or (lambda n: None)          # runs before answering request n (0-based)
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(fake.health_status, {"status": "ok" if fake.health_status == 200 else "loading model"})

            def do_POST(self):
                fake.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                fake.hook(len(fake.requests) - 1)
                msg = fake.script.pop(0) if len(fake.script) > 1 else fake.script[0]
                self._send(200, {"choices": [{"message": msg}]})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def fake():
    servers = []

    def make(script, **kw):
        servers.append(FakeServer(script, **kw))
        return servers[-1]
    yield make
    for s in servers:
        s.close()


def _tool_call(name, args, call_id="c1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}]}


def _answer(text):
    return {"role": "assistant", "content": text}


def _tool(name, args):
    return {"total": "$80.00", "asked": [name, args]}


def test_a_tool_call_then_an_answer(fake):
    server = fake([_tool_call("spending_by_category", '{"direction": "out"}'), _answer("You spent $80.00.")])
    seen = []
    turn = run_turn(server.url, [{"role": "user", "content": "How much did I spend?"}], TOOLS, _tool,
                    progress=seen.append)
    assert turn["reply"] == "You spent $80.00." and turn["error"] is None
    assert turn["calls"] == [("spending_by_category", {"direction": "out"})]
    assert turn["results"] == [{"total": "$80.00", "asked": ["spending_by_category", {"direction": "out"}]}]
    assert seen == ["Looking up money out by category…"]
    second = server.requests[1]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert json.loads(second[-1]["content"])["total"] == "$80.00"


def test_every_request_sends_the_tools_with_thinking_off_and_temperature_zero(fake):
    server = fake([_answer("Hi.")])
    run_turn(server.url, [{"role": "user", "content": "hi"}], TOOLS, _tool)
    body = server.requests[0]
    assert body["tools"] == TOOLS and body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_the_loop_stops_after_four_model_calls(fake):
    server = fake([_tool_call("spending_by_category", '{"direction": "out"}')])
    turn = run_turn(server.url, [{"role": "user", "content": "loop"}], TOOLS, _tool)
    assert len(server.requests) == 4
    assert turn["error"] is None and "couldn't finish" in turn["reply"]


def test_arguments_that_are_not_json_go_back_to_the_model_as_an_error(fake):
    server = fake([_tool_call("spending_by_category", "{direction: out"), _answer("Sorry.")])
    turn = run_turn(server.url, [{"role": "user", "content": "x"}], TOOLS, _tool)
    assert turn["reply"] == "Sorry." and turn["calls"] == []
    assert "not valid JSON" in json.loads(server.requests[1]["messages"][-1]["content"])["error"]


def test_a_server_that_is_down_gives_an_error_not_a_crash():
    turn = run_turn("http://127.0.0.1:9", [{"role": "user", "content": "x"}], TOOLS, _tool)
    assert turn["reply"] is None and "isn't responding" in turn["error"]


def test_health_reports_ok_loading_or_down(fake):
    assert health(fake([_answer("")]).url) == "ok"
    assert health(fake([_answer("")], health_status=503).url) == "loading"
    assert health("http://127.0.0.1:9") == "down"
