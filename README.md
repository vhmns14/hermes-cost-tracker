# Hermes Cost Tracker

[![CI](https://github.com/vhmns14/hermes-cost-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/vhmns14/hermes-cost-tracker/actions/workflows/ci.yml)

A tiny, **dependency-free** CLI to track and visualize your [Hermes](https://nousresearch.com) (Nous Research) API spend — ideal for Hermes Agent / OpenRouter / any OpenAI-compatible endpoint.

Agents can quietly rack up cost (the famous *runaway cost* problem). This tool logs every call's token usage, computes the USD cost from a pricing table, and renders a dashboard so you always know where the money goes.

## Features

- 🌐 **Multi-provider** — OpenRouter, OpenAI, Anthropic, Nous Portal, DeepInfra, Groq, Together, Ollama, plus Qwen, Xiaomi MiMo, Tencent Hunyuan, DeepSeek, Moonshot Kimi, MiniMax, Zhipu GLM, StepFun, Doubao, Google Gemini, Azure — all editable in `providers.json`
- 📊 Per-call logging: provider, model, input/output tokens, computed cost
- 💵 Editable pricing table (`providers.json`) — per-provider, per-model rates
- 🔑 **Secure keys** — API keys read from env vars or a git-ignored `config.json` (never committed)
- 🔄 `sync` — pull real usage from providers that expose a usage API (OpenRouter supported)
- 📈 `report` — totals by period and by model
- 📉 `dashboard` — self-contained HTML with an SVG spend chart
- 🧪 `selftest` — generates demo data to try it instantly
- 🚫 **Zero dependencies** — Python 3 standard library only

## Security

API keys are **never** stored in this repo.
- Keys come from environment variables (named per provider in `providers.json`, e.g. `OPENROUTER_API_KEY`) or a local `config.json` (copy from `config.json.example`).
- `config.json`, `.env`, and your real `usage.jsonl` are git-ignored.
- `providers` shows only whether a key is **set**, never the key value.

## Install

```bash
git clone https://github.com/vhmns14/hermes-cost-tracker
cd hermes-cost-tracker
```

## Usage

```bash
# Log a real call (provider resolves the price automatically)
python tracker.py log --provider openrouter --model nousresearch/hermes-4-70b --in 12000 --out 3000 --note "daily digest"

# Or let it find the model across all providers
python tracker.py log --model gpt-4o --in 15000 --out 4200

# List providers and which API keys are configured
python tracker.py providers

# Pull real usage from a provider (OpenRouter supported)
export OPENROUTER_API_KEY=sk-or-...
python tracker.py sync --provider openrouter --days 7

# Summarize
python tracker.py report --period week
python tracker.py report --period all --json

# Generate an HTML dashboard with a spend chart
python tracker.py dashboard --out dashboard.html

# Try it without real data
python tracker.py selftest
python tracker.py dashboard --file examples/demo-usage.jsonl --out examples/dashboard.html
```

Data is stored in `usage.jsonl` (one JSON object per line, append-only).

## Pricing & providers

`providers.json` groups models by provider with USD-per-million-token rates
(`hermes-4-70b` / `hermes-4-405b` match OpenRouter's published prices; others are
placeholders — edit to match your account). Each provider declares the
`env_key` the tracker reads its API key from. Unknown models log cost as `null`.

## License

MIT
