"""
Name-similarity suggestions (merchant ticket 09; terms in CONTEXT.md).

A spelling with no alias is offered the merchant whose spelling looks most
alike, by cosine between EmbeddingGemma 2 vectors from the app's embedding
server. It is only a suggestion: nothing here applies an alias.

- `http_embedder(base_url, timeout=5.0)` returns `embed(texts)`: an (n, d)
  array of unit vectors, or None when the server can't be reached or answers
  badly. It never raises.
- `similar_merchants(open_spellings, merchant_spellings, embed, dismissed,
  cutoff)` returns {spelling: (merchant, score)} for the spellings whose
  closest merchant scores at least `cutoff`.
"""
import http.client
import json
import urllib.request

import numpy as np

# The prefix the cutoff was measured with; change one, re-measure the other
PREFIX = "task: search result | query: "
# Scores bunch high (most pairs 0.75-0.95), so only the closest match counts and
# only from here up. Measured: 87 of 109 right, 65 wrong on 428 other spellings.
CUTOFF = 0.84
BATCH = 64


def http_embedder(base_url: str, timeout: float = 5.0):
    """An `embed(texts)` for the llama-server at base_url (OpenAI-style
    /v1/embeddings). Vectors are kept in memory, so each text is sent once."""
    cache = {}

    def embed(texts: list[str]):
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        try:
            for i in range(0, len(todo), BATCH):
                batch = todo[i:i + BATCH]
                req = urllib.request.Request(
                    base_url.rstrip("/") + "/v1/embeddings",
                    json.dumps({"input": [PREFIX + t for t in batch]}).encode(),
                    {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read())["data"]
                if len(data) != len(batch):
                    return None
                for t, d in zip(batch, data):
                    v = np.asarray(d["embedding"], dtype=float)
                    cache[t] = v / np.linalg.norm(v)   # the server may not normalize
            return np.array([cache[t] for t in texts])
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, IndexError):
            return None   # down, timed out or a bad answer: no suggestions

    return embed


def similar_merchants(open_spellings: list[str], merchant_spellings: dict[str, list[str]], embed,
                      dismissed=frozenset(), cutoff: float = CUTOFF) -> dict[str, tuple[str, float]]:
    """For each open spelling, the merchant owning its closest other spelling,
    when that score is at least cutoff. A dismissed (spelling, merchant)
    pairing and the spelling's own merchant are skipped. {} if embed fails."""
    names = [m for m, spellings in merchant_spellings.items() if spellings]
    owned = [s for m in names for s in merchant_spellings[m]]
    if not open_spellings or not owned:
        return {}
    vectors = embed(list(open_spellings) + owned)
    if vectors is None:
        return {}
    n = len(open_spellings)
    sim = vectors[:n] @ vectors[n:].T
    # each merchant's score is its closest spelling's
    ends = np.cumsum([len(merchant_spellings[m]) for m in names])
    by_merchant = np.column_stack([sim[:, a:b].max(axis=1) for a, b in zip(np.r_[0, ends[:-1]], ends)])
    own = {s: m for m in names for s in merchant_spellings[m]}
    out = {}
    for i, spelling in enumerate(open_spellings):
        for j in np.argsort(-by_merchant[i], kind="stable"):
            m = names[j]
            if m == own.get(spelling) or (spelling, m) in dismissed:
                continue
            if by_merchant[i, j] >= cutoff:
                out[spelling] = (m, float(by_merchant[i, j]))
            break   # sorted: no later merchant scores higher
    return out
