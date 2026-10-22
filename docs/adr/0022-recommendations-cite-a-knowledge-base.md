# 0022. Recommendations must cite a passage from a public knowledge base (not yet built)

Status: Accepted

## Context
The user wants recommendations from the chat, not just facts. A local model's own financial judgment can't be traced and may be confidently wrong.

## Decision
- Recommendations come only when the user asks. The model gets data through the ADR 0021 tools, and its advice comes from a knowledge base kept in the repo, searched with BM25 plus embeddings.
- Every recommendation cites a passage. With no matching passage there is no recommendation. With the embedding server down there are no recommendations.
- **Knowledge base:** Markdown is the source of truth. A script converts it to JSONL (stable passage IDs, a source link, a content hash), both are committed, and a test fails when they're out of step. It holds public guidance only. Transactions never go in.
- **Incomplete data** (stale, or more than 10% unlabeled) still gets recommendations, with a warning line.

Rejected:
- **Pre-written spending checks** worded by the model: the user wants advice grounded in a curated philosophy, not fixed rules.
- **Uncited "general" advice:** it can't be traced.

## Consequences
- With a small knowledge base, the chat will rarely recommend anything at first.
- This deliberately differs from ADR 0018's *Can't say yet*: the headline still refuses a verdict on incomplete data, while chat recommendations proceed with a warning. ADR 0018's one page and no budget still stand.
- The app starts and owns the embedding server. The details are decided separately.
