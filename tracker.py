#!/usr/bin/env python3
"""hermes-cost-tracker — track & visualize AI API spend across providers.

Usage:
    python tracker.py log --model hermes-4-70b --in 12000 --out 3000 [--provider openrouter] [--note x]
    python tracker.py report [--period day|week|all] [--json]
    python tracker.py dashboard [--out dashboard.html]
    python tracker.py providers                 # list providers + key status
    python tracker.py sync --provider openrouter [--days 7]
    python tracker.py selftest

Cost = in_tokens/1e6 * price_in + out_tokens/1e6 * price_out  (USD).

API keys are NEVER stored in this repo. They are read from environment
variables (see providers.json `env_key`) or a git-ignored config.json.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(HERE, "usage.jsonl")
PROVIDERS_FILE = os.path.join(HERE, "providers.json")
CONFIG_FILE = os.path.join(HERE, "config.json")
UTC = dt.timezone.utc


def load_providers():
    with open(PROVIDERS_FILE) as f:
        return json.load(f)["providers"]


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def get_key(provider, providers, config):
    spec = providers.get(provider, {})
    env_name = spec.get("env_key")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return (config.get("providers") or {}).get(provider)


def resolve_price(model, provider, providers):
    """Return (in_price, out_price, provider_name) or None."""
    if provider:
        models = (providers.get(provider) or {}).get("models", {})
        if model in models:
            p = models[model]
            return p["in"], p["out"], provider
        return None
    for pname, spec in providers.items():
        if model in spec.get("models", {}):
            p = spec["models"][model]
            return p["in"], p["out"], pname
    return None


def now_iso():
    return dt.datetime.now(UTC).isoformat()


def cost_for(price, tin, tout):
    if not price:
        return None
    pin, pout, _ = price
    return round(tin / 1e6 * pin + tout / 1e6 * pout, 6)


def read_entries(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def write_entry(path, entry):
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def cmd_log(args, providers):
    price = resolve_price(args.model, args.provider, providers)
    cost = cost_for(price, args.in_tokens, args.out_tokens)
    provider_name = price[2] if price else (args.provider or "unknown")
    entry = {
        "ts": now_iso(),
        "provider": provider_name,
        "model": args.model,
        "in": args.in_tokens,
        "out": args.out_tokens,
        "cost": cost,
        "note": args.note or "",
    }
    write_entry(args.file, entry)
    shown = f"${cost:.4f}" if cost is not None else "unknown model/provider (cost not computed)"
    print(f"logged: [{provider_name}] {args.model} in={args.in_tokens} out={args.out_tokens} -> {shown}")


def in_period(entry, period):
    try:
        ts = dt.datetime.fromisoformat(entry["ts"])
    except Exception:
        return False
    today = dt.datetime.now(UTC).date()
    if period == "day":
        return ts.date() == today
    if period == "week":
        return (today - ts.date()).days < 7
    return True


def cmd_report(args, providers):
    entries = [e for e in read_entries(args.file) if in_period(e, args.period)]
    if not entries:
        print(f"No entries for period '{args.period}'.")
        return
    total_cost = sum(e["cost"] for e in entries if e.get("cost") is not None)
    total_in = sum(e.get("in", 0) for e in entries)
    total_out = sum(e.get("out", 0) for e in entries)
    by_model = {}
    for e in entries:
        key = f"{e.get('provider','?')}/{e.get('model','?')}"
        by_model.setdefault(key, {"cost": 0.0, "calls": 0})
        if e.get("cost") is not None:
            by_model[key]["cost"] += e["cost"]
        by_model[key]["calls"] += 1
    summary = {
        "period": args.period,
        "entries": len(entries),
        "total_cost_usd": round(total_cost, 4),
        "total_in_tokens": total_in,
        "total_out_tokens": total_out,
        "by_model": {m: {"cost_usd": round(v["cost"], 4), "calls": v["calls"]} for m, v in by_model.items()},
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Period: {args.period} | entries: {summary['entries']}")
        print(f"Total cost: ${summary['total_cost_usd']:.4f}")
        print(f"Tokens: in={total_in:,} out={total_out:,}")
        print("By model:")
        for m, v in sorted(by_model.items(), key=lambda x: -x[1]["cost"]):
            print(f"  {m:45} ${v['cost']:.4f}  ({v['calls']} calls)")


def daily_costs(entries):
    days = {}
    for e in entries:
        if e.get("cost") is None:
            continue
        day = e["ts"][:10]
        days[day] = days.get(day, 0.0) + e["cost"]
    return dict(sorted(days.items()))


def svg_chart(days):
    if not days:
        return "<p>No cost data to chart.</p>"
    w, h = 720, 220
    pad = 30
    maxv = max(days.values()) or 1
    n = len(days)
    bw = (w - 2 * pad) / max(n, 1)
    bars = []
    for i, (day, val) in enumerate(days.items()):
        bh = (h - 2 * pad) * (val / maxv)
        x = pad + i * bw
        y = h - pad - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.7:.1f}" height="{bh:.1f}" fill="#2f81f7">'
            f'<title>{day}: ${val:.4f}</title></rect>')
        bars.append(f'<text x="{x+bw*0.35:.1f}" y="{h-pad+14:.1f}" font-size="9" fill="#888" '
                    f'text-anchor="middle">{day[5:]}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(bars) + "</svg>")


def cmd_dashboard(args, providers):
    entries = read_entries(args.file)
    days = daily_costs(entries)
    total = sum(e["cost"] for e in entries if e.get("cost") is not None)
    chart = svg_chart(days)
    rows = "".join(
        f"<tr><td>{e.get('ts','')}</td><td>{e.get('provider','')}</td><td>{e.get('model','')}</td>"
        f"<td>{e.get('in',0):,}</td><td>{e.get('out',0):,}</td>"
        f"<td>${e['cost']:.4f}</td><td>{e.get('note','')}</td></tr>"
        for e in entries[::-1]
    )
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Hermes Cost Tracker</title><style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}
h1{{font-size:1.4rem}}table{{border-collapse:collapse;width:100%;font-size:.85rem}}
th,td{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}}
th{{background:#f6f8fa}}svg{{max-width:100%}}
.total{{font-size:1.1rem;margin:1rem 0}}
</style></head><body>
<h1>🦞 Hermes Cost Tracker</h1>
<div class="total">Total spend: <b>${total:.4f}</b> &middot; {len(entries)} entries</div>
{chart}
<table><thead><tr><th>time</th><th>provider</th><th>model</th><th>in</th><th>out</th><th>cost</th><th>note</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(html)
    print(f"dashboard written to {args.out} ({len(entries)} entries)")


def cmd_providers(args, providers, config):
    print(f"{'PROVIDER':14} {'LABEL':22} {'MODELS':8} KEY")
    for name, spec in providers.items():
        n = len(spec.get("models", {}))
        has_key = "set" if get_key(name, providers, config) else "-"
        print(f"{name:14} {spec.get('label',''):22} {n:<8} {has_key}")


def cmd_sync(args, providers, config):
    spec = providers.get(args.provider)
    if not spec:
        print(f"Unknown provider '{args.provider}'. See `providers`.")
        return
    if not spec.get("usage_api"):
        print(f"sync not implemented for '{args.provider}' yet. Add `usage_api` to providers.json.")
        return
    key = get_key(args.provider, providers, config)
    if not key:
        print(f"No API key for '{args.provider}'. Set ${spec.get('env_key')} or config.json (git-ignored).")
        return
    end = dt.datetime.now(UTC).date()
    start = end - dt.timedelta(days=args.days)
    url = f"{spec['usage_api']}?start_date={start.isoformat()}&end_date={end.isoformat()}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"sync failed: HTTP {e.code} {e.reason}")
        return
    except Exception as e:  # noqa
        print(f"sync failed: {e}")
        return
    rows = data.get("data", []) if isinstance(data, dict) else []
    if not rows:
        print("No usage returned for the period.")
        return
    count = 0
    for row in rows:
        model = row.get("model", "unknown")
        cost = row.get("total_cost") or 0.0
        tin = row.get("total_prompt_tokens") or 0
        tout = row.get("total_completion_tokens") or 0
        entry = {
            "ts": now_iso(),
            "provider": args.provider,
            "model": model,
            "in": tin,
            "out": tout,
            "cost": round(float(cost), 6),
            "note": f"sync {args.provider}",
        }
        write_entry(args.file, entry)
        count += 1
    print(f"synced {count} usage row(s) from {args.provider} into {args.file}")


def cmd_selftest(args, providers):
    samples = [
        ("openrouter", "nousresearch/hermes-4-70b", 12000, 3000, "daily digest"),
        ("openrouter", "nousresearch/hermes-4-70b", 8000, 5200, "code review"),
        ("openrouter", "nousresearch/hermes-4-405b", 40000, 9000, "hard reasoning"),
        ("openai", "gpt-4o", 15000, 4200, "chat"),
        ("groq", "llama-3.3-70b-versatile", 9000, 2600, "summarize"),
    ]
    base = dt.datetime.now(UTC) - dt.timedelta(days=4)
    lines = []
    for i, (prov, m, ti, to, note) in enumerate(samples):
        ts = (base + dt.timedelta(days=i, hours=3)).isoformat()
        price = resolve_price(m, prov, providers)
        cost = cost_for(price, ti, to)
        lines.append(json.dumps({"ts": ts, "provider": prov, "model": m,
                                 "in": ti, "out": to, "cost": cost, "note": note}))
    out_dir = os.path.dirname(os.path.abspath(args.file))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.file, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"selftest data written to {args.file} ({len(lines)} entries)")


def main():
    ap = argparse.ArgumentParser(description="Track AI API spend across providers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("log")
    pl.add_argument("--model", required=True)
    pl.add_argument("--in", dest="in_tokens", type=int, required=True)
    pl.add_argument("--out", dest="out_tokens", type=int, required=True)
    pl.add_argument("--provider", default=None)
    pl.add_argument("--note", default="")
    pl.add_argument("--file", default=DEFAULT_FILE)
    pl.set_defaults(func=cmd_log)

    pr = sub.add_parser("report")
    pr.add_argument("--period", choices=["day", "week", "all"], default="all")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--file", default=DEFAULT_FILE)
    pr.set_defaults(func=cmd_report)

    pd = sub.add_parser("dashboard")
    pd.add_argument("--out", default=os.path.join(HERE, "dashboard.html"))
    pd.add_argument("--file", default=DEFAULT_FILE)
    pd.set_defaults(func=cmd_dashboard)

    pp = sub.add_parser("providers")
    pp.set_defaults(func=cmd_providers)

    ps = sub.add_parser("sync")
    ps.add_argument("--provider", required=True)
    ps.add_argument("--days", type=int, default=7)
    ps.add_argument("--file", default=DEFAULT_FILE)
    ps.set_defaults(func=cmd_sync)

    pst = sub.add_parser("selftest")
    pst.add_argument("--file", default=os.path.join(HERE, "examples", "demo-usage.jsonl"))
    pst.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    providers = load_providers()
    config = load_config()
    if args.cmd == "providers":
        args.func(args, providers, config)
    elif args.cmd == "sync":
        args.func(args, providers, config)
    else:
        args.func(args, providers)


if __name__ == "__main__":
    main()
