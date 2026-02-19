import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def classify(sector: str, industry: str) -> str:
    x = f"{sector or ''} {industry or ''}".lower()
    if "insurance" in x:
        return "insurer"
    if "bank" in x:
        return "bank"
    return "normal"


def load_sp500_tickers(csv_path: Path):
    out = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = (row.get("ticker") or "").strip()
            if t:
                out.append(t)
    return out


def load_company_class_map(db_path: Path, tickers: list[str]):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    q = "select ticker, coalesce(sector,''), coalesce(industry,'') from companies_company where ticker in (%s)" % (
        ",".join("?" * len(tickers))
    )
    cur.execute(q, tickers)
    out = {}
    for ticker, sector, industry in cur.fetchall():
        if ticker not in out:
            out[ticker] = classify(sector, industry)
    conn.close()
    return out


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


def metric_set(statement_rows):
    out = set()
    for row in (statement_rows or [])[1:]:
        if isinstance(row, list) and row and isinstance(row[0], str):
            m = row[0].strip()
            if m:
                out.add(m)
    return out


def top_core(counter: Counter, denom: int, threshold: float):
    items = []
    for k, v in counter.items():
        if denom and (v / denom) >= threshold:
            items.append((k, v, v / denom))
    items.sort(key=lambda x: (-x[1], x[0]))
    return items


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--cache-json", default=str(root / "data" / "cached_financials_2.json"))
    ap.add_argument("--sp500-csv", default=str(root / "data" / "sp500_tickers_fiscal_exchange.csv"))
    ap.add_argument("--db", default=str(root / "db.sqlite3"))
    ap.add_argument("--core-threshold", type=float, default=0.8)
    ap.add_argument("--out-json", default=str(root / "configs" / "fiscal_raw_catalog.json"))
    ap.add_argument("--out-md", default=str(root / "reports" / "fiscal_raw_catalog_summary.md"))
    args = ap.parse_args()

    cache = json.load(open(args.cache_json, "r", encoding="utf-8"))
    tickers = load_sp500_tickers(Path(args.sp500_csv))
    cls_map = load_company_class_map(Path(args.db), tickers)

    by_class = {"normal": [], "bank": [], "insurer": []}
    for t in tickers:
        e = cache.get(t)
        if not is_strict_done(e):
            continue
        c = cls_map.get(t, "normal")
        by_class[c].append(t)

    catalog = {"meta": {"core_threshold": args.core_threshold}, "classes": {}}

    for c in ("normal", "bank", "insurer"):
        lst = by_class[c]
        stmt_cnt = {"IS": Counter(), "BS": Counter(), "CF": Counter()}
        for t in lst:
            d = cache[t]
            for st in ("IS", "BS", "CF"):
                for m in metric_set(d.get(st, [])):
                    stmt_cnt[st][m] += 1

        class_obj = {"n_companies": len(lst), "statements": {}}
        for st in ("IS", "BS", "CF"):
            all_metrics = sorted(stmt_cnt[st].items(), key=lambda x: (-x[1], x[0]))
            core = top_core(stmt_cnt[st], len(lst), args.core_threshold)
            class_obj["statements"][st] = {
                "all_possible_metrics": [
                    {"metric": m, "count": v, "pct": round(v / len(lst), 4) if lst else 0.0}
                    for m, v in all_metrics
                ],
                "core_metrics": [
                    {"metric": m, "count": v, "pct": round(p, 4)} for m, v, p in core
                ],
            }
        catalog["classes"][c] = class_obj

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    json.dump(catalog, open(out_json, "w", encoding="utf-8"), indent=2)

    md_lines = ["# Fiscal Raw Metric Catalog (pre-normalization)", ""]
    md_lines.append(f"Core threshold: {args.core_threshold:.0%}")
    md_lines.append("")
    for c in ("normal", "bank", "insurer"):
        cc = catalog["classes"][c]
        md_lines.append(f"## {c.title()} (n={cc['n_companies']})")
        for st in ("IS", "BS", "CF"):
            core = cc["statements"][st]["core_metrics"]
            md_lines.append(f"- {st}: core={len(core)} | all_possible={len(cc['statements'][st]['all_possible_metrics'])}")
            if core:
                md_lines.append("  - core metrics: " + ", ".join(x["metric"] for x in core[:25]))
        md_lines.append("")

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
