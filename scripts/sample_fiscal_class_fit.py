import argparse
import json
from pathlib import Path


def is_strict_done(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for st in ("IS", "BS", "CF"):
        if st not in entry or not entry[st]:
            return False
    bs = {r[0].strip().lower() for r in entry.get("BS", [])[1:] if isinstance(r, list) and r and isinstance(r[0], str)}
    cf = {r[0].strip().lower() for r in entry.get("CF", [])[1:] if isinstance(r, list) and r and isinstance(r[0], str)}
    return (
        "liabilities" in bs
        and "equity" in bs
        and "investing activities" in cf
        and "financing activities" in cf
    )


def metric_set(rows):
    return {r[0].strip() for r in (rows or [])[1:] if isinstance(r, list) and r and isinstance(r[0], str) and r[0].strip()}


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--cache-json", default=str(root / "data" / "cached_financials_2.json"))
    ap.add_argument("--catalog-json", default=str(root / "configs" / "fiscal_raw_catalog.json"))
    ap.add_argument("--samples", default="AAPL,BAC,AIG")
    ap.add_argument("--out-md", default=str(root / "reports" / "fiscal_sample_fit.md"))
    args = ap.parse_args()

    cache = json.load(open(args.cache_json, "r", encoding="utf-8"))
    catalog = json.load(open(args.catalog_json, "r", encoding="utf-8"))

    # choose class manually for now
    class_hint = {"AAPL": "normal", "BAC": "bank", "AIG": "insurer"}
    samples = [s.strip() for s in args.samples.split(",") if s.strip()]

    lines = ["# Sample Fit Against Fiscal Raw Core Metrics", ""]
    lines.append("| Ticker | Class | Strict done | IS core hit | BS core hit | CF core hit |")
    lines.append("|---|---|---:|---:|---:|---:|")

    for t in samples:
        d = cache.get(t)
        cls = class_hint.get(t, "normal")
        done = is_strict_done(d)
        if not isinstance(d, dict):
            lines.append(f"| {t} | {cls} | no | - | - | - |")
            continue
        hits = {}
        for st in ("IS", "BS", "CF"):
            core = {x["metric"] for x in catalog["classes"][cls]["statements"][st]["core_metrics"]}
            present = metric_set(d.get(st, []))
            hits[st] = (len(core & present), len(core))
        lines.append(
            f"| {t} | {cls} | {'yes' if done else 'no'} | {hits['IS'][0]}/{hits['IS'][1]} | {hits['BS'][0]}/{hits['BS'][1]} | {hits['CF'][0]}/{hits['CF'][1]} |"
        )

    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
