import argparse
import json
import sqlite3
from pathlib import Path

import requests

SEC_UA = 'Matt Newell matthew_newell@outlook.com'
TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
FACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'

MAP_COMMON = {
    'IS': {
        'Total Revenues': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet'],
        'Cost of Sales': ['CostOfGoodsAndServicesSold', 'CostOfGoodsSold', 'CostOfRevenue'],
        'Gross Profit': ['GrossProfit'],
        'Operating Profit': ['OperatingIncomeLoss'],
        'Income Before Provision for Income Taxes': ['IncomeBeforeTax', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'],
        'Provision for Income Taxes': ['IncomeTaxExpenseBenefit'],
        'Consolidated Net Income': ['NetIncomeLoss'],
        'Basic EPS': ['EarningsPerShareBasic'],
        'Diluted EPS': ['EarningsPerShareDiluted'],
    },
    'BS': {
        'Cash and Cash Equivalents': ['CashAndCashEquivalentsAtCarryingValue'],
        'Accounts Receivable': ['AccountsReceivableNetCurrent'],
        'Inventories': ['InventoryNet'],
        'Total Current Assets': ['AssetsCurrent'],
        'Net Property, Plant & Equipment': ['PropertyPlantAndEquipmentNet'],
        'Goodwill': ['Goodwill'],
        'Total Assets': ['Assets'],
        'Accounts Payable': ['AccountsPayableCurrent'],
        'Total Current Liabilities': ['LiabilitiesCurrent'],
        'Long-Term Debt': ['LongTermDebtNoncurrent', 'LongTermDebt'],
        'Total Liabilities': ['Liabilities'],
        'Retained Earnings': ['RetainedEarningsAccumulatedDeficit'],
        "Total Shareholders' Equity": ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
        "Total Liabilities and Shareholders' Equity": ['LiabilitiesAndStockholdersEquity'],
    },
    'CF': {
        'Net Income': ['NetIncomeLoss'],
        'Depreciation & Amortization': ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet'],
        'Share-Based Compensation Expense': ['ShareBasedCompensation'],
        'Cash from Operating Activities': ['NetCashProvidedByUsedInOperatingActivities'],
        'Capital Expenditure': ['PaymentsToAcquirePropertyPlantAndEquipment'],
        'Cash from Investing Activities': ['NetCashProvidedByUsedInInvestingActivities'],
        'Cash from Financing Activities': ['NetCashProvidedByUsedInFinancingActivities'],
        'Repurchases of Common Shares': ['PaymentsForRepurchaseOfCommonStock'],
        'Issuance of Common Shares': ['ProceedsFromIssuanceOfCommonStock'],
    },
}

CLASS_EXTRA = {
    'bank': {
        'IS': {
            'Net Interest Income': ['InterestIncomeExpenseNet', 'NetInterestIncome'],
            'Interest Expense': ['InterestExpense'],
        }
    },
    'insurer': {
        'IS': {
            'Net Premiums Earned': ['PremiumsEarnedNet'],
            'Insurance Benefits & Claims': ['PolicyholderBenefitsAndClaimsIncurredNet'],
        }
    },
}


def sec_get(url):
    r = requests.get(url, headers={'User-Agent': SEC_UA, 'Accept': 'application/json'}, timeout=30)
    r.raise_for_status()
    return r.json()


def ticker_to_cik():
    data = sec_get(TICKERS_URL)
    return {v['ticker'].upper(): str(v['cik_str']).zfill(10) for v in data.values()}


def company_classes(db_path, tickers):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    q = 'select ticker,coalesce(sector,\'\'),coalesce(industry,\'\') from companies_company where ticker in (%s)' % (','.join('?' * len(tickers)))
    cur.execute(q, tickers)
    out = {}
    for t, s, i in cur.fetchall():
        x = (s + ' ' + i).lower()
        if 'insurance' in x:
            out[t] = 'insurer'
        elif 'bank' in x:
            out[t] = 'bank'
        else:
            out[t] = 'normal'
    conn.close()
    return out


def pick_series(us, concept):
    obj = us.get(concept)
    if not obj:
        return {}
    vals = {}
    for _, arr in obj.get('units', {}).items():
        for it in arr:
            if not (it.get('form') or '').startswith('10-K'):
                continue
            fp = (it.get('fp') or '')
            if fp and fp != 'FY':
                continue
            end = it.get('end')
            val = it.get('val')
            if end is None or val is None:
                continue
            vals[str(end)] = val
    return vals


def build_stmt(us, map_stmt):
    metric_data = {}
    concept_used = {}
    concept_missing = []
    all_dates = set()

    for metric, candidates in map_stmt.items():
        chosen_series = {}
        used = None
        for concept in candidates:
            s = pick_series(us, concept)
            if s:
                chosen_series = s
                used = concept
                break
        if used:
            metric_data[metric] = chosen_series
            concept_used[metric] = used
            all_dates.update(chosen_series.keys())
        else:
            concept_missing.append((metric, candidates))

    dates = sorted(all_dates, reverse=True)[:5]
    rows = [['Metric'] + dates]
    for metric in sorted(metric_data):
        rows.append([metric] + [metric_data[metric].get(d) for d in dates])

    return rows, concept_used, concept_missing


def append_mapping_details(md_lines, statement_name, ordered_map, used_map, missing_pairs):
    miss_by_metric = {m: cands for m, cands in missing_pairs}
    md_lines.append(f'### {statement_name} mapping detail')
    md_lines.append('')
    for metric, candidates in ordered_map.items():
        if metric in used_map:
            md_lines.append(f"- ✅ **{metric}** ← `us-gaap:{used_map[metric]}`")
        else:
            tried = ', '.join(f'`us-gaap:{c}`' for c in miss_by_metric.get(metric, candidates))
            md_lines.append(f"- ❌ **{metric}** ← EMPTY (tried: {tried})")
    md_lines.append('')


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument('--tickers', default='JPM,BRK-B,CRM')
    ap.add_argument('--db', default=str(root / 'db.sqlite3'))
    ap.add_argument('--cache', default=str(root / 'cached_financials_2.json'))
    ap.add_argument('--out-json', default=str(root / 'reports/data/edgar_mapped_examples.json'))
    ap.add_argument('--out-md', default=str(root / 'reports/edgar_mapped_examples.md'))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    cache = json.load(open(args.cache))
    not_in_cache = [t for t in tickers if t not in cache]
    ciks = ticker_to_cik()
    classes = company_classes(Path(args.db), tickers)

    out = {'tickers': {}, 'requested': tickers, 'not_in_cached_financials_2': not_in_cache}

    md = [
        '# EDGAR -> Fiscal-style mapping examples',
        '',
        'Requested tickers: ' + ', '.join(tickers),
        'Tickers confirmed not in cached_financials_2: ' + (', '.join(not_in_cache) if not_in_cache else 'none'),
        '',
        'Legend: ✅ mapped to SEC us-gaap concept | ❌ left empty (no candidate concept had usable 10-K FY data)',
        '',
    ]

    for t in tickers:
        cik = ciks.get(t)
        if not cik:
            out['tickers'][t] = {'error': 'no_cik'}
            md += [f'## {t}', '', '- ERROR: no CIK found', '']
            continue

        facts = sec_get(FACTS_URL.format(cik=cik))
        us = facts.get('facts', {}).get('us-gaap', {})
        company_class = classes.get(t, 'normal')

        mapping = {k: dict(v) for k, v in MAP_COMMON.items()}
        for st, extra in CLASS_EXTRA.get(company_class, {}).items():
            mapping[st].update(extra)

        is_rows, is_used, is_missing = build_stmt(us, mapping['IS'])
        bs_rows, bs_used, bs_missing = build_stmt(us, mapping['BS'])
        cf_rows, cf_used, cf_missing = build_stmt(us, mapping['CF'])

        out['tickers'][t] = {
            'class': company_class,
            'cik': cik,
            'statements': {'IS': is_rows, 'BS': bs_rows, 'CF': cf_rows},
            'used_concepts': {'IS': is_used, 'BS': bs_used, 'CF': cf_used},
            'missing_metrics': {'IS': is_missing, 'BS': bs_missing, 'CF': cf_missing},
            'counts': {
                'IS': {'mapped': len(is_used), 'total': len(mapping['IS'])},
                'BS': {'mapped': len(bs_used), 'total': len(mapping['BS'])},
                'CF': {'mapped': len(cf_used), 'total': len(mapping['CF'])},
            },
        }

        md += [
            f'## {t} ({company_class})',
            '',
            f"- IS: {len(is_used)}/{len(mapping['IS'])}",
            f"- BS: {len(bs_used)}/{len(mapping['BS'])}",
            f"- CF: {len(cf_used)}/{len(mapping['CF'])}",
            '',
        ]

        append_mapping_details(md, 'IS', mapping['IS'], is_used, is_missing)
        append_mapping_details(md, 'BS', mapping['BS'], bs_used, bs_missing)
        append_mapping_details(md, 'CF', mapping['CF'], cf_used, cf_missing)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2), encoding='utf-8')
    Path(args.out_md).write_text('\n'.join(md), encoding='utf-8')
    print('wrote', args.out_json)
    print('wrote', args.out_md)


if __name__ == '__main__':
    main()
