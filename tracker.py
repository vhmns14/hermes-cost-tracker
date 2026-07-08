#!/usr/bin/env python3
"""hermes-cost-tracker — track & visualize Hermes API spend.

Usage:
    python tracker.py log --model hermes-4-70b --in 12000 --out 3000 [--note "task x"]
    python tracker.py report [--period day|week|all] [--json]
    python tracker.py dashboard [--out dashboard.html]
    python tracker.py selftest [--file examples/demo-usage.jsonl]

Cost = in_tokens/1e6 * price_in + out_tokens/1e6 * price_out  (USD).
Storage is an append-only JSONL file (one JSON object per line).
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(HERE, "usage.jsonl")
PRICING_FILE = os.path.join(HERE, "pricing.json")
UTC = dt.timezone.utc


def load_pricing():
    with open(PRICING_FILE) as f:
        return json.load(f)["models"]


def now_iso():
    return dt.datetime.now(UTC).isoformat()


def cost_for(model, tin, tout, pricing):
    p = pricing.get(model)
    if not p:
        return None
    return round(tin / 1e6 * p["in"] + tout / 1e6 * p["out"], 6)


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


def cmd_log(args, pricing):
    cost = cost_for(args.model, args.in_tokens, args.out_tokens, pricing)
    entry = {
        "ts": now_iso(),
        "model": args.model,
        "in": args.in_tokens,
        "out": args.out_tokens,
        "cost": cost,
        "note": args.note or "",
    }
    with open(args.file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    price_note = f"${cost:.4f}" if cost is not None else "unknown model (cost not computed)"
    print(f"logged: {args.model} in={args.in_tokens} out={args.out_tokens} -> {price_note}")


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


def cmd_report(args, pricing):
    entries = [e for e in read_entries(args.file) if in_period(e, args.period)]
    if not entries:
        print(f"No entries for period '{args.period}'.")
        return
    total_cost = sum(e["cost"] for e in entries if e.get("cost") is not None)
    total_in = sum(e.get("in", 0) for e in entries)
    total_out = sum(e.get("out", 0) for e in entries)
    by_model = {}
    for e in entries:
        m = e["model"]
        by_model.setdefault(m, {"cost": 0.0, "calls": 0})
        if e.get("cost") is not None:
            by_model[m]["cost"] += e["cost"]
        by_model[m]["calls"] += 1
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
            print(f"  {m:35} ${v['cost']:.4f}  ({v['calls']} calls)")


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
            f'<title>{day}: ${val:.4f}</title></rect>'
        )
        bars.append(f'<text x="{x+bw*0.35:.1f}" y="{h-pad+14:.1f}" font-size="9" fill="#888" '
                    f'text-anchor="middle">{day[5:]}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(bars) + "</svg>")


def cmd_dashboard(args, pricing):
    entries = read_entries(args.file)
    days = daily_costs(entries)
    total = sum(e["cost"] for e in entries if e.get("cost") is not None)
    chart = svg_chart(days)
    rows = "".join(
        f"<tr><td>{e.get('ts','')}</td><td>{e.get('model','')}</td>"
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
<table><thead><tr><th>time</th><th>model</th><th>in</th><th>out</th><th>cost</th><th>note</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(html)
    print(f"dashboard written to {args.out} ({len(entries)} entries)")


def cmd_selftest(args, pricing):
    samples = [
        ("hermes-4-70b", 12000, 3000, "daily digest"),
        ("hermes-4-70b", 8000, 5200, "code review"),
        ("hermes-4-405b", 40000, 9000, "hard reasoning"),
        ("hermes-4-70b", 15000, 4200, "chat"),
        ("deepharmes-3-mistral-24b-preview", 9000, 2600, "summarize"),
    ]
    base = dt.datetime.now(UTC) - dt.timedelta(days=4)
    lines = []
    for i, (m, ti, to, note) in enumerate(samples):
        ts = (base + dt.timedelta(days=i, hours=3)).isoformat()
        cost = cost_for(m, ti, to, pricing)
        lines.append(json.dumps({"ts": ts, "model": m, "in": ti, "out": to, "cost": cost, "note": note}))
    os.makedirs(os.path.dirname(os.path.abspath(args.file)), exist_ok=True)
    with open(args.file, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"selftest data written to {args.file} ({len(lines)} entries)")


def main():
    ap = argparse.ArgumentParser(description="Track Hermes API spend")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("log", help="log a usage entry")
    pl.add_argument("--model", required=True)
    pl.add_argument("--in", dest="in_tokens", type=int, required=True)
    pl.add_argument("--out", dest="out_tokens", type=int, required=True)
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

    ps = sub.add_parser("selftest")
    ps.add_argument("--file", default=os.path.join(HERE, "examples", "demo-usage.jsonl"))
    ps.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    pricing = load_pricing()
    args.func(args, pricing)


if __name__ == "__main__":
    main()
