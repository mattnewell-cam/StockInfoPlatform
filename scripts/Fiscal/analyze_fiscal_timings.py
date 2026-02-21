import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_jsonl(path):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    idx = int((len(vals) - 1) * p)
    return vals[idx]


def main():
    ap = argparse.ArgumentParser(description="Analyze fiscal timing/event JSONL")
    ap.add_argument("--timings", required=True)
    ap.add_argument("--events", default="")
    args = ap.parse_args()

    timings = [r for r in read_jsonl(args.timings) if r.get("event") == "ticker_done"]
    events = read_jsonl(args.events) if args.events else []

    ok = [r for r in timings if r.get("status") == "ok"]
    failed = [r for r in timings if r.get("status") != "ok"]

    elapsed_all = [float(r.get("elapsed_sec", 0.0)) for r in ok if r.get("elapsed_sec") is not None]

    by_kind = defaultdict(list)
    for r in ok:
        by_kind[r.get("kind", "unknown")].append(float(r.get("elapsed_sec", 0.0)))

    print("== Fiscal Timing Summary ==")
    print(f"total_rows={len(timings)} ok={len(ok)} failed={len(failed)}")
    if elapsed_all:
        print(
            f"elapsed_sec: mean={sum(elapsed_all)/len(elapsed_all):.2f} "
            f"p50={pct(elapsed_all,0.5):.2f} p90={pct(elapsed_all,0.9):.2f} p95={pct(elapsed_all,0.95):.2f} "
            f"max={max(elapsed_all):.2f}"
        )

    for kind, vals in by_kind.items():
        if not vals:
            continue
        print(f"kind={kind}: n={len(vals)} mean={sum(vals)/len(vals):.2f} p90={pct(vals,0.9):.2f}")

    fail_reasons = defaultdict(int)
    for r in failed:
        fail_reasons[r.get("reason", "<unknown>")] += 1
    if fail_reasons:
        print("\nTop failure reasons:")
        for reason, c in sorted(fail_reasons.items(), key=lambda kv: kv[1], reverse=True)[:10]:
            print(f"- {c}x {reason}")

    run_complete = [e for e in events if e.get("event") == "run_complete"]
    if run_complete:
        last = run_complete[-1]
        print("\nLast run_complete event:")
        print(json.dumps(last, indent=2))


if __name__ == "__main__":
    main()
