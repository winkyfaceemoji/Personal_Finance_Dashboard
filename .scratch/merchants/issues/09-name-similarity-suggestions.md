# 09: Name-similarity suggestions from the embedding server

**What to build:** Beyond patterns, a spelling without an alias is suggested as the merchant whose name looks most alike, when the similarity clears a cutoff. `AMZN MKTP` is offered as Amazon. It comes from the app's embedding server (EmbeddingGemma 2, set up by the embedding session). When the server is down, these suggestions just don't appear.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] A small client asks the app's embedding server for vectors with the `task: search result | query: ` prefix and reuses its text-hash cache
- [ ] Closest merchant by cosine; suggested only at or above a named cutoff constant (0.84). Dismissed pairings and aliased spellings are skipped; a pattern suggestion takes precedence when both exist
- [ ] Server down or unreachable: no similarity suggestions and no error, with pattern suggestions unaffected
- [ ] Tests (seam 3): against a fake server with known vectors: the cutoff, closest pick, server down, cache hit. No test needs a model
- [ ] A hand-run script (not in CI) measures right and wrong suggestions at the cutoff against the local answer key in the research folder, and never writes real names anywhere tracked
- [ ] Real use depends on the embedding server existing; until it does, the feature stays dormant
