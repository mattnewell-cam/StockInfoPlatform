import argparse
import json
import math
from collections import Counter, defaultdict
from statistics import mean


def pct(values, p):
    if not values:
        return None
    arr = sorted(values)
    k = max(0, min(len(arr) - 1, math.ceil((p / 100) * len(arr)) - 1))
    return arr[k]


def fmt(x):
    return "-" if x is None else f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser(description="Analyze fiscal pull JSONL logs")
    ap.add_argument("--timings-jsonl", required=True)
    ap.add_argument("--benchmark-tag", default="")
    args = ap.parse_args()

    rows = []
    with open(args.timings_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("event") != "ticker_done":
                continue
            if args.benchmark_tag and r.get("benchmark_tag") != args.benchmark_tag:
                continue
            rows.append(r)

    if not rows:
        print("No rows")
        return

    ok = [r for r in rows if r.get("status") == "ok"]
    failed = [r for r in rows if r.get("status") != "ok"]

    durations = [float(r.get("elapsed_sec", 0.0)) for r in ok if r.get("elapsed_sec") is not None]
    total_elapsed = sum(durations)
    tph = (len(ok) / (total_elapsed / 3600.0)) if total_elapsed > 0 else 0.0

    section_vals = defaultdict(list)
    for r in ok:
        st = r.get("section_timings") or {}
        for slug_metrics in st.values():
            for k in ("nav", "missing", "slider", "extract", "sleep", "units", "total"):
                if k in slug_metrics and slug_metrics[k] is not None:
                    section_vals[k].append(float(slug_metrics[k]))

    print(f"tickers_ok={len(ok)} tickers_failed={len(failed)}")
    print(f"tickers_per_hour={tph:.2f}")
    print("\nSection timings (s):")
    for k in ("nav", "missing", "slider", "extract", "sleep", "units", "total"):
        vals = section_vals.get(k, [])
        print(f"  {k:8} avg={fmt(mean(vals) if vals else None)} p50={fmt(pct(vals,50))} p95={fmt(pct(vals,95))}")

    print("\nTicker duration distribution (s):")
    print(f"  avg={fmt(mean(durations) if durations else None)} p50={fmt(pct(durations,50))} p95={fmt(pct(durations,95))}")

    print("\nTop 20 slowest tickers:")
    for r in sorted(ok, key=lambda x: float(x.get("elapsed_sec", 0.0)), reverse=True)[:20]:
        print(f"  {r.get('ticker'):8} {float(r.get('elapsed_sec',0.0)):.2f}s kind={r.get('kind')} worker={r.get('worker_id')}")

    reasons = Counter((r.get("reason_type") or "unknown") for r in failed)
    print("\nFailure taxonomy:")
    for k, v in reasons.most_common():
        print(f"  {k:24} {v}")


if __name__ == "__main__":
    main()
