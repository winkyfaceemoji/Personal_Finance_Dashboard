"""Name-similarity suggestions (merchant ticket 09): a spelling with no alias is
offered the merchant whose spelling looks most alike. Model-free: a fake
embedding server answers with known vectors."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from Modules.similar import CUTOFF, PREFIX, http_embedder, similar_merchants

# Made-up spellings. Each vector's cosine with "amazon" ([1, 0, 0, 0]) is its
# first number over its length; [21, 12, 6, 2] has length 25, so exactly 0.84.
VECTORS = {
    "amazon": [7, 0, 0, 0],
    "amzn mktp": [21, 12, 6, 2],           # 0.84: at the cutoff
    "amzn digital": [0.839, 0.5442, 0, 0],  # just below
    "amazon prime": [0.95, 0.3122, 0, 0],   # closer to Amazon than "amzn mktp" is
    "steam games": [0, 1, 0, 0],
    "steampowered": [0, 0.9, 0.4359, 0],    # 0.9 to "steam games"
    "corner deli": [0, 0, 0, 1],
}


class _Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body["input"])
        if self.server.bad:
            out = b"not json"
        else:
            out = json.dumps({"data": [{"embedding": VECTORS[t.removeprefix(PREFIX)]} for t in body["input"]]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    srv.requests, srv.bad = [], False
    threading.Thread(target=srv.serve_forever, args=(0.05,), daemon=True).start()
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield srv
    srv.shutdown()
    srv.server_close()


def test_every_text_is_sent_with_the_prefix(server):
    similar_merchants(["amzn mktp"], {"Amazon": ["amazon"]}, http_embedder(server.url))
    sent = [t for batch in server.requests for t in batch]
    assert sorted(sent) == [PREFIX + "amazon", PREFIX + "amzn mktp"]
    assert PREFIX == "task: search result | query: "


def test_suggested_at_the_cutoff_not_just_below(server):
    assert CUTOFF == 0.84
    got = similar_merchants(["amzn mktp", "amzn digital"], {"Amazon": ["amazon"]}, http_embedder(server.url))
    assert list(got) == ["amzn mktp"]
    assert got["amzn mktp"][0] == "Amazon"
    assert got["amzn mktp"][1] == pytest.approx(0.84)


def test_closest_merchant_wins(server):
    merchants = {"Amazon": ["amazon"], "Steam": ["steam games"], "Deli": ["corner deli"]}
    got = similar_merchants(["steampowered", "amzn mktp"], merchants, http_embedder(server.url))
    assert {s: m for s, (m, _) in got.items()} == {"steampowered": "Steam", "amzn mktp": "Amazon"}
    assert got["steampowered"][1] == pytest.approx(0.9, abs=1e-3)


def test_own_merchant_is_never_suggested(server):
    # "amzn mktp" already belongs to Amazon: Amazon's other spellings don't count
    merchants = {"Amazon": ["amazon", "amzn mktp"], "Steam": ["steam games"]}
    assert similar_merchants(["amzn mktp"], merchants, http_embedder(server.url)) == {}


def test_dismissed_pairing_falls_to_the_next_merchant(server):
    # "amzn mktp" is 0.84 to Amazon and about 0.95 to Prime; dismiss Prime
    merchants = {"Prime": ["amazon prime"], "Amazon": ["amazon"]}
    embed = http_embedder(server.url)
    assert similar_merchants(["amzn mktp"], merchants, embed)["amzn mktp"][0] == "Prime"
    got = similar_merchants(["amzn mktp"], merchants, embed, dismissed={("amzn mktp", "Prime")})
    assert got["amzn mktp"][0] == "Amazon"


def test_dismissed_pairing_with_no_next_merchant_gives_nothing(server):
    merchants = {"Amazon": ["amazon"], "Deli": ["corner deli"]}
    got = similar_merchants(["amzn mktp"], merchants, http_embedder(server.url), dismissed={("amzn mktp", "Amazon")})
    assert got == {}


def test_server_down_gives_nothing_and_no_error():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]   # closed when the block ends: nothing listens there
    embed = http_embedder(f"http://127.0.0.1:{port}", timeout=1)
    assert embed(["amazon"]) is None
    assert similar_merchants(["amzn mktp"], {"Amazon": ["amazon"]}, embed) == {}


def test_bad_answer_gives_nothing(server):
    server.bad = True
    assert similar_merchants(["amzn mktp"], {"Amazon": ["amazon"]}, http_embedder(server.url)) == {}


def test_vectors_are_cached_per_text(server):
    embed = http_embedder(server.url)
    first = similar_merchants(["amzn mktp"], {"Amazon": ["amazon"]}, embed)
    asked = len(server.requests)
    assert similar_merchants(["amzn mktp"], {"Amazon": ["amazon"]}, embed) == first
    assert len(server.requests) == asked
    embed(["amazon", "corner deli"])   # only the new text goes out
    assert server.requests[-1] == [PREFIX + "corner deli"]


def test_large_lists_go_in_batches(server):
    names = [f"spelling {i}" for i in range(150)]
    VECTORS.update({n: [1, 0, 0, 0] for n in names})
    try:
        assert http_embedder(server.url)(names).shape == (150, 4)
        assert [len(b) for b in server.requests] == [64, 64, 22]
    finally:
        for n in names:
            del VECTORS[n]


def test_similar_merchants_with_a_plain_embed():
    vectors = {"a": [1.0, 0.0], "a2": [0.9, 0.43589], "b": [0.0, 1.0]}
    embed = lambda texts: np.array([vectors[t] for t in texts])
    assert similar_merchants(["a2"], {"A": ["a"], "B": ["b"]}, embed) == {"a2": ("A", pytest.approx(0.9))}
    assert similar_merchants(["a2"], {"A": ["a"]}, embed, cutoff=0.95) == {}
    assert similar_merchants([], {"A": ["a"]}, embed) == {}
    assert similar_merchants(["a2"], {}, embed) == {}
