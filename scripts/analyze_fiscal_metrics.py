import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def pctl(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    idx = int((len(vals) - 1) * q)
    return vals[idx]


def main():
    ap = argparse.ArgumentParser(description="Analyze fiscal pull JSONL metrics")
    ap.add_argument("--metrics-jsonl", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = []
    with open(args.metrics_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    ticker_rows = [r for r in rows if r.get("type") == "ticker"]
    ok = [r for r in ticker_rows if r.get("outcome") == "ok"]
    fail = [r for r in ticker_rows if r.get("outcome") == "failed"]
    secs = [float(r.get("seconds", 0)) for r in ticker_rows if isinstance(r.get("seconds"), (int, float))]

    section_vals = defaultdict(list)
    for r in ok:
        t = r.get("timings") or {}
        for stmt, obj in t.items():
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (int, float)):
                        section_vals[f"{stmt}.{k}"].append(float(v))

    by_ticker = defaultdict(list)
    for r in ticker_rows:
        by_ticker[r.get("ticker", "?")].append(float(r.get("seconds", 0)))

    slowest = sorted(
        [{"ticker": t, "seconds": sum(v)} for t, v in by_ticker.items()],
        key=lambda x: x["seconds"],
        reverse=True,
    )[:20]

    failure_tax = Counter((r.get("reason") or "unknown").split(":")[0][:120] for r in fail)

    heartbeat = [r for r in rows if r.get("type") == "heartbeat"]
    util = []
    for h in heartbeat:
        inflight = h.get("in_flight") or {}
        util.append(len(inflight))

    total_hours = (sum(secs) / 3600.0) if secs else 0
    tph = (len(ticker_rows) / total_hours) if total_hours > 0 else None

    out = {
        "total_tickers": len(ticker_rows),
        "ok": len(ok),
        "failed": len(fail),
        "seconds_avg": statistics.mean(secs) if secs else None,
        "seconds_p50": pctl(secs, 0.5),
        "seconds_p95": pctl(secs, 0.95),
        "tickers_per_hour": tph,
        "worker_utilization_avg_inflight": statistics.mean(util) if util else None,
        "section_stats": {
            k: {
                "avg": statistics.mean(v),
                "p50": pctl(v, 0.5),
                "p95": pctl(v, 0.95),
                "n": len(v),
            }
            for k, v in sorted(section_vals.items())
        },
        "per_ticker_distribution": {k: {"runs": len(v), "avg_seconds": statistics.mean(v)} for k, v in by_ticker.items()},
        "top20_slowest": slowest,
        "failure_taxonomy": dict(failure_tax),
    }

    text = json.dumps(out, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
