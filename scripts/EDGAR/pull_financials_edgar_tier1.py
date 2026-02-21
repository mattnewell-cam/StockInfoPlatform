import argparse
import json
from datetime import datetime, UTC
from pathlib import Path

import requests

SEC_UA = "Matt Newell matthew_newell@outlook.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Tier-1 only (direct concept mapping)
MAPPING = {
    "common": {
        "IS": {
            "Revenues": "Total Revenues",
            "SalesRevenueNet": "Total Revenues",
            "CostOfGoodsSold": "Cost of Sales",
            "GrossProfit": "Gross Profit",
            "OperatingIncomeLoss": "Operating Profit",
            "IncomeBeforeTax": "Income Before Provision for Income Taxes",
            "IncomeTaxExpenseBenefit": "Provision for Income Taxes",
            "NetIncomeLoss": "Consolidated Net Income",
            "EarningsPerShareBasic": "Basic EPS",
            "EarningsPerShareDiluted": "Diluted EPS",
            "WeightedAverageNumberOfSharesOutstandingBasic": "Basic Weighted Average Shares Outstanding",
            "WeightedAverageNumberOfDilutedSharesOutstanding": "Diluted Weighted Average Shares Outstanding",
        },
        "BS": {
            "CashAndCashEquivalentsAtCarryingValue": "Cash and Cash Equivalents",
            "ShortTermInvestments": "Short-Term Investments",
            "AccountsReceivableNetCurrent": "Accounts Receivable",
            "InventoryNet": "Inventories",
            "AssetsCurrent": "Total Current Assets",
            "PropertyPlantAndEquipmentNet": "Net Property, Plant & Equipment",
            "Goodwill": "Goodwill",
            "IntangibleAssetsNetExcludingGoodwill": "Net Intangible Assets",
            "Assets": "Total Assets",
            "AccountsPayableCurrent": "Accounts Payable",
            "LiabilitiesCurrent": "Total Current Liabilities",
            "LongTermDebtNoncurrent": "Long-Term Debt",
            "Liabilities": "Total Liabilities",
            "RetainedEarningsAccumulatedDeficit": "Retained Earnings",
            "CommonStockValue": "Common Stock",
            "AdditionalPaidInCapital": "Additional Paid-in Capital",
            "StockholdersEquity": "Total Shareholders' Equity",
            "LiabilitiesAndStockholdersEquity": "Total Liabilities and Shareholders' Equity",
        },
        "CF": {
            "NetIncomeLoss": "Net Income",
            "DepreciationDepletionAndAmortization": "Depreciation & Amortization",
            "ShareBasedCompensation": "Share-Based Compensation Expense",
            "NetCashProvidedByUsedInOperatingActivities": "Cash from Operating Activities",
            "PaymentsToAcquirePropertyPlantAndEquipment": "Capital Expenditure",
            "NetCashProvidedByUsedInInvestingActivities": "Cash from Investing Activities",
            "NetCashProvidedByUsedInFinancingActivities": "Cash from Financing Activities",
            "PaymentsForRepurchaseOfCommonStock": "Repurchases of Common Shares",
            "ProceedsFromIssuanceOfCommonStock": "Issuance of Common Shares",
        },
    },
    "bank": {
        "IS": {
            "InterestIncomeOperating": "Interest Income",
            "InterestExpense": "Interest Expense",
            "InterestIncomeExpenseNet": "Net Interest Income",
        }
    },
    "insurer": {
        "IS": {
            "PremiumsEarnedNet": "Net Premiums Earned",
            "PolicyholderBenefitsAndClaimsIncurredNet": "Insurance Benefits & Claims",
        }
    },
}


def sec_get(url: str):
    r = requests.get(url, headers={"User-Agent": SEC_UA, "Accept": "application/json"}, timeout=40)
    r.raise_for_status()
    return r.json()


def load_ticker_map():
    data = sec_get(TICKERS_URL)
    out = {}
    for _, row in data.items():
        out[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return out


def extract_series(concept_obj):
    units = concept_obj.get("units", {})
    preferred = ["USD", "shares", "USD/shares", "pure"]
    data = []
    for u in preferred + [k for k in units if k not in preferred]:
        for item in units.get(u, []):
            form = (item.get("form") or "")
            fp = (item.get("fp") or "")
            if not form.startswith("10-K"):
                continue
            if fp and fp != "FY":
                continue
            end = item.get("end")
            val = item.get("val")
            fy = item.get("fy")
            if end is None or val is None:
                continue
            data.append((str(end), int(fy) if isinstance(fy, int) else None, val))
    by_end = {}
    for end, fy, val in data:
        by_end[end] = (fy, val)
    out = sorted(((end, fy, val) for end, (fy, val) in by_end.items()), key=lambda x: x[0], reverse=True)
    return out[:8]


def build_statement_rows(facts, mapping):
    us = facts.get("facts", {}).get("us-gaap", {})

    date_set = set()
    concept_vals = {}
    mapped_concepts = []
    missing_concepts = []

    for concept, label in mapping.items():
        cobj = us.get(concept)
        if not cobj:
            missing_concepts.append(concept)
            continue
        series = extract_series(cobj)
        if not series:
            missing_concepts.append(concept)
            continue
        concept_vals[label] = {end: val for end, _, val in series}
        date_set.update(end for end, _, _ in series)
        mapped_concepts.append({"concept": concept, "metric": label, "points": len(series)})

    dates = sorted(date_set, reverse=True)[:8]
    if not dates:
        return [], mapped_concepts, missing_concepts

    header = ["Metric"] + dates
    rows = [header]
    for label in sorted(concept_vals.keys()):
        vals = [concept_vals[label].get(d) for d in dates]
        rows.append([label] + vals)

    return rows, mapped_concepts, missing_concepts


def insert_fiscal_section_rows(bs_rows, cf_rows):
    if bs_rows:
        bs_rows.insert(1, ["Liabilities"] + [None] * (len(bs_rows[0]) - 1))
        bs_rows.append(["Equity"] + [None] * (len(bs_rows[0]) - 1))
    if cf_rows:
        cf_rows.insert(1, ["Investing Activities"] + [None] * (len(cf_rows[0]) - 1))
        cf_rows.insert(2, ["Financing Activities"] + [None] * (len(cf_rows[0]) - 1))


def strict_anchor_pass(bs_rows, cf_rows):
    bs_labels = {r[0].strip().lower() for r in bs_rows[1:] if r and isinstance(r[0], str)}
    cf_labels = {r[0].strip().lower() for r in cf_rows[1:] if r and isinstance(r[0], str)}
    return (
        "liabilities" in bs_labels
        and "equity" in bs_labels
        and "investing activities" in cf_labels
        and "financing activities" in cf_labels
    )


def pct(mapped: int, total: int) -> float:
    return round((mapped / total) * 100.0, 1) if total else 0.0


def row_metric_names(rows):
    if not rows:
        return []
    return [r[0] for r in rows[1:] if r and isinstance(r[0], str)]


def metric_coverage(rows, expected_map):
    got = set(row_metric_names(rows))
    expected = set(expected_map.values())
    return {
        "got_count": len(got),
        "expected_count": len(expected),
        "expected_hit_count": len(got & expected),
        "expected_miss_count": len(expected - got),
        "expected_miss_metrics": sorted(expected - got),
    }


def format_concept_list(concepts, limit=12):
    if not concepts:
        return "none"
    if isinstance(concepts[0], dict):
        items = [f"`us-gaap:{x['concept']}`→{x['metric']}" for x in concepts[:limit]]
        more = len(concepts) - limit
        if more > 0:
            items.append(f"… +{more} more")
        return ", ".join(items)
    items = [f"`us-gaap:{x}`" for x in concepts[:limit]]
    more = len(concepts) - limit
    if more > 0:
        items.append(f"… +{more} more")
    return ", ".join(items)


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--tickers", default="AAPL,BAC,AIG")
    ap.add_argument("--out-json", default=str(root / "reports" / "data" / "edgar_tier1_sample.json"))
    ap.add_argument("--out-md", default=str(root / "reports" / "edgar_tier1_sample_report.md"))
    args = ap.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    cls_hint = {"AAPL": "normal", "BAC": "bank", "AIG": "insurer"}
    tmap = load_ticker_map()

    out = {"samples": {}, "generated_utc": datetime.now(UTC).isoformat()}

    md = [
        "# EDGAR Tier-1 Sample Evaluation (Improved)",
        "",
        "Tier-1 only: direct `us-gaap:*` concept mapping to fiscal-style raw metrics (no heuristics, no extension tags).",
        "",
        "## Executive Summary",
        "",
        "| Ticker | Class | IS coverage | BS coverage | CF coverage | Anchor pass | Go/No-Go |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    sample_lines = []

    for t in tickers:
        cik = tmap.get(t)
        if not cik:
            out["samples"][t] = {"error": "ticker_not_found_in_sec_index"}
            md.append(f"| {t} | ? | - | - | - | no | NO-GO |")
            continue

        facts = sec_get(FACTS_URL.format(cik=cik))
        cls = cls_hint.get(t, "normal")

        map_is = dict(MAPPING["common"]["IS"])
        map_bs = dict(MAPPING["common"]["BS"])
        map_cf = dict(MAPPING["common"]["CF"])
        map_is.update(MAPPING.get(cls, {}).get("IS", {}))

        is_rows, is_mapped, is_missing = build_statement_rows(facts, map_is)
        bs_rows, bs_mapped, bs_missing = build_statement_rows(facts, map_bs)
        cf_rows, cf_mapped, cf_missing = build_statement_rows(facts, map_cf)

        insert_fiscal_section_rows(bs_rows, cf_rows)
        anchor_ok = strict_anchor_pass(bs_rows, cf_rows) if (bs_rows and cf_rows) else False

        is_cov = metric_coverage(is_rows, map_is)
        bs_cov = metric_coverage(bs_rows, map_bs)
        cf_cov = metric_coverage(cf_rows, map_cf)

        stmt_cov_pct = {
            "IS": pct(len(is_mapped), len(map_is)),
            "BS": pct(len(bs_mapped), len(map_bs)),
            "CF": pct(len(cf_mapped), len(map_cf)),
        }

        decision = "GO" if anchor_ok and min(stmt_cov_pct.values()) >= 50.0 else "NO-GO"

        out["samples"][t] = {
            "class": cls,
            "cik": cik,
            "anchor_pass": anchor_ok,
            "decision": decision,
            "mapping_totals": {"IS": len(map_is), "BS": len(map_bs), "CF": len(map_cf)},
            "mapped_counts": {"IS": len(is_mapped), "BS": len(bs_mapped), "CF": len(cf_mapped)},
            "mapped_pct": stmt_cov_pct,
            "mapped_concepts": {"IS": is_mapped, "BS": bs_mapped, "CF": cf_mapped},
            "missing_concepts": {"IS": is_missing, "BS": bs_missing, "CF": cf_missing},
            "coverage_vs_expected_metrics": {"IS": is_cov, "BS": bs_cov, "CF": cf_cov},
            "preview": {"IS": is_rows[:10], "BS": bs_rows[:10], "CF": cf_rows[:10]},
        }

        md.append(
            f"| {t} | {cls} | {len(is_mapped)}/{len(map_is)} ({stmt_cov_pct['IS']}%) | {len(bs_mapped)}/{len(map_bs)} ({stmt_cov_pct['BS']}%) | {len(cf_mapped)}/{len(map_cf)} ({stmt_cov_pct['CF']}%) | {'yes' if anchor_ok else 'no'} | {decision} |"
        )

        sample_lines.extend([
            "",
            f"## {t} ({cls})",
            "",
            f"- CIK: `{cik}`",
            f"- Anchor pass: **{'yes' if anchor_ok else 'no'}**",
            f"- Decision: **{decision}**",
            f"- Statement coverage: IS {stmt_cov_pct['IS']}% | BS {stmt_cov_pct['BS']}% | CF {stmt_cov_pct['CF']}%",
            "",
            "### Missing `us-gaap` concepts (Tier-1 gaps)",
            "",
            f"- IS ({len(is_missing)}): {format_concept_list(is_missing)}",
            f"- BS ({len(bs_missing)}): {format_concept_list(bs_missing)}",
            f"- CF ({len(cf_missing)}): {format_concept_list(cf_missing)}",
            "",
            "### Mapped concept examples",
            "",
            f"- IS ({len(is_mapped)}): {format_concept_list(is_mapped)}",
            f"- BS ({len(bs_mapped)}): {format_concept_list(bs_mapped)}",
            f"- CF ({len(cf_mapped)}): {format_concept_list(cf_mapped)}",
            "",
            "### Expected fiscal raw metrics still missing in output",
            "",
            f"- IS ({is_cov['expected_miss_count']}): {', '.join(is_cov['expected_miss_metrics'][:15]) if is_cov['expected_miss_metrics'] else 'none'}",
            f"- BS ({bs_cov['expected_miss_count']}): {', '.join(bs_cov['expected_miss_metrics'][:15]) if bs_cov['expected_miss_metrics'] else 'none'}",
            f"- CF ({cf_cov['expected_miss_count']}): {', '.join(cf_cov['expected_miss_metrics'][:15]) if cf_cov['expected_miss_metrics'] else 'none'}",
        ])

    md.extend(sample_lines)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
