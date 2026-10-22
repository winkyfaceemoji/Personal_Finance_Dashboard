# Starts the local chat model for the dashboard's AI chat (ADR 0021).
# Run it in its own terminal and leave it open while you use the chat:
#   powershell -ExecutionPolicy Bypass -File start_llm.ps1
# Needs llama.cpp's llama-server on PATH (winget install ggml.llamacpp).
param(
    [string]$Model = $(if ($env:FINANCE_LLM_MODEL) { $env:FINANCE_LLM_MODEL }
                       else { Join-Path $HOME "Documents\GGUF Models\Qwen3.5-9B-Q8_0.gguf" }),
    [int]$Port = 8080
)

if (-not (Test-Path $Model)) {
    Write-Error "Model not found: $Model. Pass -Model <path to a .gguf> or set FINANCE_LLM_MODEL."
    exit 1
}
if (-not (Get-Command llama-server -ErrorAction SilentlyContinue)) {
    Write-Error "llama-server isn't on PATH. Install llama.cpp: winget install ggml.llamacpp"
    exit 1
}

# --jinja: the model's own chat template, needed for tool calls
# -ngl 99: the whole model on the GPU;  -c 16384: room for tool results
# 127.0.0.1 only: nothing outside this machine can reach it (ADR 0016)
llama-server -m $Model --jinja -ngl 99 -c 16384 --host 127.0.0.1 --port $Port
