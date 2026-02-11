import argparse
import json
from pathlib import Path


def load_ok(path):
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
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == "ticker_done" and r.get("status") == "ok":
                rows.append(r)
    return rows


def summarize(rows):
    vals = [float(r.get("elapsed_sec", 0.0)) for r in rows if r.get("elapsed_sec") is not None]
    if not vals:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "min": min(vals),
        "max": max(vals),
    }


def main():
    ap = argparse.ArgumentParser(description="Compare before/after fiscal benchmark JSONL")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    args = ap.parse_args()

    b = load_ok(args.before)
    a = load_ok(args.after)
    sb = summarize(b)
    sa = summarize(a)

    print("== Benchmark Compare ==")
    print(f"before: n={sb['n']} mean={sb['mean']:.2f}s min={sb['min']:.2f}s max={sb['max']:.2f}s" if sb['n'] else "before: n=0")
    print(f"after:  n={sa['n']} mean={sa['mean']:.2f}s min={sa['min']:.2f}s max={sa['max']:.2f}s" if sa['n'] else "after: n=0")

    if sb["n"] and sa["n"]:
        diff = sa["mean"] - sb["mean"]
        pct = (diff / sb["mean"]) * 100 if sb["mean"] else 0.0
        print(f"delta_mean={diff:.2f}s ({pct:+.2f}%)")


if __name__ == "__main__":
    main()
