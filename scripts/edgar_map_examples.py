import argparse
import json
import sqlite3
from pathlib import Path

import requests

SEC_UA = 'Matt Newell matthew_newell@outlook.com'
TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
FACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'

# Class-specific fiscal-style templates (not forcing bank/insurer into normal template)
TEMPLATES = {
    'normal': {
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
    },
    'bank': {
        'IS': {
            'Net Interest Income': ['InterestIncomeExpenseNet', 'NetInterestIncome'],
            'Interest Expense': ['InterestExpense'],
            'Income Before Provision for Income Taxes': ['IncomeBeforeTax', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'],
            'Provision for Income Taxes': ['IncomeTaxExpenseBenefit'],
            'Consolidated Net Income': ['NetIncomeLoss'],
            'Basic EPS': ['EarningsPerShareBasic'],
            'Diluted EPS': ['EarningsPerShareDiluted'],
        },
        'BS': {
            'Cash and Cash Equivalents': ['CashAndCashEquivalentsAtCarryingValue'],
            'Trading Assets': ['TradingAssets'],
            'Trading Liabilities': ['TradingLiabilities'],
            'Goodwill': ['Goodwill'],
            'Net Intangible Assets': ['IntangibleAssetsNetExcludingGoodwill'],
            'Total Assets': ['Assets'],
            'Long-Term Debt': ['LongTermDebtNoncurrent', 'LongTermDebt'],
            'Total Liabilities': ['Liabilities'],
            'Retained Earnings': ['RetainedEarningsAccumulatedDeficit'],
            "Total Shareholders' Equity": ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
            "Total Liabilities and Shareholders' Equity": ['LiabilitiesAndStockholdersEquity'],
        },
        'CF': {
            'Net Income': ['NetIncomeLoss'],
            'Depreciation & Amortization': ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet'],
            'Cash from Operating Activities': ['NetCashProvidedByUsedInOperatingActivities'],
            'Cash from Investing Activities': ['NetCashProvidedByUsedInInvestingActivities'],
            'Cash from Financing Activities': ['NetCashProvidedByUsedInFinancingActivities'],
            'Capital Expenditure': ['PaymentsToAcquirePropertyPlantAndEquipment'],
            'Repurchases of Common Shares': ['PaymentsForRepurchaseOfCommonStock'],
            'Issuance of Common Shares': ['ProceedsFromIssuanceOfCommonStock'],
        },
    },
    'insurer': {
        'IS': {
            'Net Premiums Earned': ['PremiumsEarnedNet', 'Premiums'],
            'Insurance Benefits & Claims': ['PolicyholderBenefitsAndClaimsIncurredNet', 'PolicyholderBenefitsAndClaimsIncurred'],
            'Investment Income': ['InvestmentIncomeInterestAndDividend'],
            'Total Revenues': ['Revenues', 'SalesRevenueNet'],
            'Operating Profit': ['OperatingIncomeLoss'],
            'Income Before Provision for Income Taxes': ['IncomeBeforeTax', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'],
            'Provision for Income Taxes': ['IncomeTaxExpenseBenefit'],
            'Consolidated Net Income': ['NetIncomeLoss'],
            'Basic EPS': ['EarningsPerShareBasic'],
            'Diluted EPS': ['EarningsPerShareDiluted'],
        },
        'BS': {
            'Cash and Cash Equivalents': ['CashAndCashEquivalentsAtCarryingValue'],
            'Debt Securities': ['DebtSecuritiesAvailableForSaleAmortizedCostBasis'],
            'Total Investments': ['Investments'],
            'Reinsurance Contract Assets': ['ReinsuranceRecoverables'],
            'Deferred Acquisition Costs': ['DeferredPolicyAcquisitionCosts'],
            'Goodwill': ['Goodwill'],
            'Total Assets': ['Assets'],
            'Unearned Premiums': ['UnearnedPremiums'],
            'Claims Reserves': ['PolicyholderBenefitsAndClaimsLiability'],
            'Total Liabilities': ['Liabilities'],
            "Total Shareholders' Equity": ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
            "Total Liabilities and Shareholders' Equity": ['LiabilitiesAndStockholdersEquity'],
        },
        'CF': {
            'Net Income': ['NetIncomeLoss'],
            'Cash from Operating Activities': ['NetCashProvidedByUsedInOperatingActivities'],
            'Cash from Investing Activities': ['NetCashProvidedByUsedInInvestingActivities'],
            'Cash from Financing Activities': ['NetCashProvidedByUsedInFinancingActivities'],
            'Capital Expenditure': ['PaymentsToAcquirePropertyPlantAndEquipment'],
            'Repurchases of Common Shares': ['PaymentsForRepurchaseOfCommonStock'],
            'Issuance of Common Shares': ['ProceedsFromIssuanceOfCommonStock'],
        },
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
    candidate_presence = {}
    all_dates = set()

    for metric, candidates in map_stmt.items():
        chosen_series = {}
        used = None
        present_candidates = []
        for concept in candidates:
            s = pick_series(us, concept)
            if s:
                present_candidates.append(concept)
                if used is None:
                    chosen_series = s
                    used = concept
        candidate_presence[metric] = present_candidates
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

    return rows, concept_used, concept_missing, candidate_presence


def append_mapping_details(md_lines, statement_name, ordered_map, used_map, missing_pairs, candidate_presence):
    miss_by_metric = {m: cands for m, cands in missing_pairs}
    md_lines.append(f'### {statement_name} mapping detail')
    md_lines.append('')
    for metric, candidates in ordered_map.items():
        present = candidate_presence.get(metric, [])
        present_txt = ', '.join(f'`us-gaap:{c}`' for c in present) if present else 'none'
        if metric in used_map:
            md_lines.append(f"- ✅ **{metric}** ← `us-gaap:{used_map[metric]}` | also present: {present_txt}")
        else:
            tried = ', '.join(f'`us-gaap:{c}`' for c in miss_by_metric.get(metric, candidates))
            md_lines.append(f"- ❌ **{metric}** ← EMPTY (tried: {tried}) | present from candidates: {present_txt}")
    md_lines.append('')


def list_present_statementish_concepts(us, limit=180):
    keys = []
    for concept in us.keys():
        s = concept.lower()
        if any(k in s for k in [
            'revenue', 'income', 'expense', 'tax', 'earningspershare', 'interest', 'premium', 'claim',
            'asset', 'liabil', 'equity', 'inventory', 'receivable', 'payable', 'goodwill', 'intangible', 'debt',
            'cash', 'operatingactivities', 'investingactivities', 'financingactivities', 'depreciation', 'amortization',
            'repurchase', 'issuance'
        ]):
            if pick_series(us, concept):
                keys.append(concept)
    return sorted(set(keys))[:limit]


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument('--tickers', default='JPM,PGR')
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
        '# EDGAR -> Fiscal-style mapping examples (class-specific templates)',
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
        template = TEMPLATES.get(company_class, TEMPLATES['normal'])

        is_rows, is_used, is_missing, is_presence = build_stmt(us, template['IS'])
        bs_rows, bs_used, bs_missing, bs_presence = build_stmt(us, template['BS'])
        cf_rows, cf_used, cf_missing, cf_presence = build_stmt(us, template['CF'])

        out['tickers'][t] = {
            'class': company_class,
            'cik': cik,
            'template': 'class-specific',
            'statements': {'IS': is_rows, 'BS': bs_rows, 'CF': cf_rows},
            'used_concepts': {'IS': is_used, 'BS': bs_used, 'CF': cf_used},
            'missing_metrics': {'IS': is_missing, 'BS': bs_missing, 'CF': cf_missing},
            'candidate_presence': {'IS': is_presence, 'BS': bs_presence, 'CF': cf_presence},
            'present_statementish_us_gaap': list_present_statementish_concepts(us),
            'counts': {
                'IS': {'mapped': len(is_used), 'total': len(template['IS'])},
                'BS': {'mapped': len(bs_used), 'total': len(template['BS'])},
                'CF': {'mapped': len(cf_used), 'total': len(template['CF'])},
            },
        }

        md += [
            f'## {t} ({company_class})',
            '',
            f"- IS: {len(is_used)}/{len(template['IS'])}",
            f"- BS: {len(bs_used)}/{len(template['BS'])}",
            f"- CF: {len(cf_used)}/{len(template['CF'])}",
            '',
        ]

        append_mapping_details(md, 'IS', template['IS'], is_used, is_missing, is_presence)
        append_mapping_details(md, 'BS', template['BS'], bs_used, bs_missing, bs_presence)
        append_mapping_details(md, 'CF', template['CF'], cf_used, cf_missing, cf_presence)

        present_statementish = list_present_statementish_concepts(us)
        md.append('### Additional us-gaap items present (statement-ish, 10-K FY)')
        md.append('')
        if present_statementish:
            for concept in present_statementish:
                md.append(f"- `us-gaap:{concept}`")
        else:
            md.append('- none')
        md.append('')

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2), encoding='utf-8')
    Path(args.out_md).write_text('\n'.join(md), encoding='utf-8')
    print('wrote', args.out_json)
    print('wrote', args.out_md)


if __name__ == '__main__':
    main()
