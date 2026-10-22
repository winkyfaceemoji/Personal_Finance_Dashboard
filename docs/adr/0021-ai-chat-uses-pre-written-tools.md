# 0021. The AI chat answers only through pre-written tools, from a local llama-server

Status: Accepted

## Context
We want plain-English questions answered about the ledger by a local model (Qwen3.5-9B on llama.cpp). Small models get arithmetic and dates wrong. The ledger holds irreplaceable labels and private data.

## Decision
- The model only chooses among pre-written, tested tool functions and their inputs, then puts the results into words. Tools return totals already computed and dollar amounts already formatted. The app marks any dollar amount in a reply that no tool returned.
- The chat is read only, and it uses the period chosen on the page.
- The app sends HTTP requests to a `llama-server` the user starts, at `FINANCE_LLM_URL`. The app doesn't start or own the chat model.

Rejected:
- **RAG over transactions:** retrieving the "most similar" rows can't filter and add up a table.
- **Model-written pandas or SQL:** it would run code from a 9B model against the master.
- **`llama-cpp-python` in-process:**
  - it needs a Vulkan build from source on Windows;
  - its bundled llama.cpp lags behind new models;
  - the debug reloader would reload the 9 GB model on every save;
  - a GPU crash would take the dashboard down.
- **Starting the chat model from the app:** for now. Running the model inside the app is on the roadmap.

## Consequences
- The chat can answer only what the tools cover. A new kind of question means writing a new tool and its test.
- The chat needs a second process the user starts.
- A tool may show figures the page doesn't.
