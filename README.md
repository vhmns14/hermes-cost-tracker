# Hermes Cost Tracker

[![CI](https://github.com/vhmns14/hermes-cost-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/vhmns14/hermes-cost-tracker/actions/workflows/ci.yml)

A tiny, **dependency-free** CLI to track and visualize your [Hermes](https://nousresearch.com) (Nous Research) API spend — ideal for Hermes Agent / OpenRouter / any OpenAI-compatible endpoint.

Agents can quietly rack up cost (the famous *runaway cost* problem). This tool logs every call's token usage, computes the USD cost from a pricing table, and renders a dashboard so you always know where the money goes.

## Features

- 📊 Per-call logging: model, input/output tokens, computed cost
- 💵 Pricing table (`pricing.json`) — edit to match your provider/model
- 📈 `report` — totals by period and by model
- 📉 `dashboard` — self-contained HTML with an SVG spend chart
- 🧪 `selftest` — generates demo data to try it instantly
- 🚫 **Zero dependencies** — Python 3 standard library only

## Install

```bash
git clone https://github.com/vhmns14/hermes-cost-tracker
cd hermes-cost-tracker
```

## Usage

```bash
# Log a real call (prices from pricing.json)
python tracker.py log --model hermes-4-70b --in 12000 --out 3000 --note "daily digest"

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

## Pricing

`pricing.json` holds USD-per-million-token rates. `hermes-4-70b` and `hermes-4-405b`
match OpenRouter's published prices; others are placeholders — update them for your provider.
Unknown models log cost as `null` (not computed).

## License

MIT
