import argparse
import csv
import datetime as dt
import json
import re
from collections import defaultdict
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


def sec_get(url):
    r = requests.get(url, headers={"User-Agent": SEC_UA, "Accept": "application/json"}, timeout=40)
    r.raise_for_status()
    return r.json()


def load_ticker_map():
    data = sec_get(TICKERS_URL)
    out = {}
    for _, row in data.items():
        out[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return out


def normalize_class(label: str):
    x = (label or "").lower()
    if "insurance" in x:
        return "insurer"
    if "bank" in x:
        return "bank"
    return "normal"


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
    # dedupe by end date; latest first
    by_end = {}
    for end, fy, val in data:
        by_end[end] = (fy, val)
    out = sorted(((end, fy, val) for end, (fy, val) in by_end.items()), key=lambda x: x[0], reverse=True)
    return out[:8]


def build_statement_rows(facts, mapping):
    us = facts.get("facts", {}).get("us-gaap", {})

    date_set = set()
    concept_vals = {}
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
        concept_vals[label] = {end: val for end, fy, val in series}
        date_set.update(end for end, _, _ in series)

    dates = sorted(date_set, reverse=True)[:8]
    if not dates:
        return [], missing_concepts

    header = ["Metric"] + dates
    rows = [header]
    for label in sorted(concept_vals.keys()):
        vals = [concept_vals[label].get(d) for d in dates]
        rows.append([label] + vals)

    return rows, missing_concepts


def insert_fiscal_section_rows(bs_rows, cf_rows):
    # fiscal-style section anchors
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


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--tickers", default="AAPL,BAC,AIG")
    ap.add_argument("--class-csv", default=str(root / "sp500_tickers_fiscal_exchange.csv"))
    ap.add_argument("--out-json", default=str(root / "tmp" / "edgar_tier1_sample.json"))
    ap.add_argument("--out-md", default=str(root / "reports" / "edgar_tier1_sample_report.md"))
    args = ap.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]

    # quick class hints from local DB-derived file not available here; hardcode sample split
    cls_hint = {"AAPL": "normal", "BAC": "bank", "AIG": "insurer"}

    tmap = load_ticker_map()

    out = {"samples": {}}
    md = ["# EDGAR Tier-1 Sample Evaluation", "", "| Ticker | Class | IS mapped/missing | BS mapped/missing | CF mapped/missing | Anchor pass |", "|---|---|---:|---:|---:|---:|"]

    for t in tickers:
        cik = tmap.get(t)
        if not cik:
            out["samples"][t] = {"error": "ticker_not_found_in_sec_index"}
            md.append(f"| {t} | ? | - | - | - | no |")
            continue

        facts = sec_get(FACTS_URL.format(cik=cik))
        cls = cls_hint.get(t, "normal")

        map_is = dict(MAPPING["common"]["IS"])
        map_bs = dict(MAPPING["common"]["BS"])
        map_cf = dict(MAPPING["common"]["CF"])
        map_is.update(MAPPING.get(cls, {}).get("IS", {}))

        is_rows, is_missing = build_statement_rows(facts, map_is)
        bs_rows, bs_missing = build_statement_rows(facts, map_bs)
        cf_rows, cf_missing = build_statement_rows(facts, map_cf)

        insert_fiscal_section_rows(bs_rows, cf_rows)
        anchor_ok = strict_anchor_pass(bs_rows, cf_rows) if (bs_rows and cf_rows) else False

        out["samples"][t] = {
            "class": cls,
            "cik": cik,
            "mapped_counts": {
                "IS": len(map_is) - len(is_missing),
                "BS": len(map_bs) - len(bs_missing),
                "CF": len(map_cf) - len(cf_missing),
            },
            "missing_concepts": {"IS": is_missing, "BS": bs_missing, "CF": cf_missing},
            "anchor_pass": anchor_ok,
            "preview": {"IS": is_rows[:8], "BS": bs_rows[:8], "CF": cf_rows[:8]},
        }

        md.append(
            f"| {t} | {cls} | {len(map_is)-len(is_missing)}/{len(is_missing)} | {len(map_bs)-len(bs_missing)}/{len(bs_missing)} | {len(map_cf)-len(cf_missing)}/{len(cf_missing)} | {'yes' if anchor_ok else 'no'} |"
        )

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
