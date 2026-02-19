import argparse
import json
from pathlib import Path

from edgar import Company, set_identity

set_identity('Matt Newell matthew_newell@outlook.com')

TEMPLATES = {
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
            'Cash and Cash Equivalents': ['CashAndCashEquivalentsAtCarryingValue', 'CashAndDueFromBanks'],
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

CLASS_HINT = {'JPM': 'bank', 'PGR': 'insurer'}


def normalize_concept(raw: str) -> str:
    if not raw:
        return ''
    if '_' in raw:
        return raw.split('_', 1)[1]
    if ':' in raw:
        return raw.split(':', 1)[1]
    return raw


def statement_df(statement_obj):
    df = statement_obj.to_dataframe()
    if df.empty:
        return df
    for col in ('abstract', 'dimension', 'is_breakdown'):
        if col in df.columns:
            df = df[df[col] == False]  # noqa: E712
    return df


def first_period_col(df):
    period_cols = [c for c in df.columns if isinstance(c, str) and len(c) == 10 and c[4] == '-' and c[7] == '-']
    period_cols = sorted(period_cols, reverse=True)
    return period_cols[0] if period_cols else None


def concept_values(df):
    pcol = first_period_col(df)
    vals = {}
    labels = {}
    if pcol is None:
        return vals, labels, None
    for _, row in df.iterrows():
        c = normalize_concept(str(row.get('concept', '')))
        if not c:
            continue
        vals[c] = row.get(pcol)
        labels[c] = row.get('label')
    return vals, labels, pcol


def map_statement(df, template_stmt):
    vals, labels, pcol = concept_values(df)
    mapped = {}
    details = []
    for metric, candidates in template_stmt.items():
        chosen = None
        for c in candidates:
            if c in vals and vals[c] is not None:
                chosen = c
                break
        if chosen:
            mapped[metric] = vals[chosen]
            details.append({'metric': metric, 'mapped': True, 'concept': chosen, 'label': labels.get(chosen), 'value': vals[chosen], 'candidates': candidates})
        else:
            details.append({'metric': metric, 'mapped': False, 'concept': None, 'label': None, 'value': None, 'candidates': candidates})
    return mapped, details, pcol, vals, labels


def balance_check(bs_mapped):
    a = bs_mapped.get('Total Assets')
    l = bs_mapped.get('Total Liabilities')
    e = bs_mapped.get("Total Shareholders' Equity")
    if a is None or l is None or e is None:
        return {'check': 'assets = liabilities + equity', 'status': 'missing_inputs', 'diff': None}
    diff = float(a) - float(l) - float(e)
    status = 'pass' if abs(diff) <= max(1.0, abs(float(a)) * 0.005) else 'fail'
    return {'check': 'assets = liabilities + equity', 'status': status, 'diff': diff, 'assets': a, 'liabilities': l, 'equity': e}


def cashflow_check(cf_vals):
    cfo = cf_vals.get('NetCashProvidedByUsedInOperatingActivities')
    cfi = cf_vals.get('NetCashProvidedByUsedInInvestingActivities')
    cff = cf_vals.get('NetCashProvidedByUsedInFinancingActivities')
    net = cf_vals.get('CashAndCashEquivalentsPeriodIncreaseDecrease')
    if None in (cfo, cfi, cff, net):
        return {'check': 'cfo + cfi + cff = net change cash', 'status': 'missing_inputs', 'diff': None}
    diff = float(cfo) + float(cfi) + float(cff) - float(net)
    status = 'pass' if abs(diff) <= max(1.0, abs(float(net)) * 0.01) else 'fail'
    return {'check': 'cfo + cfi + cff = net change cash', 'status': status, 'diff': diff, 'cfo': cfo, 'cfi': cfi, 'cff': cff, 'net_change_cash': net}


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument('--tickers', default='JPM,PGR')
    ap.add_argument('--out-md', default=str(root / 'reports' / 'edgar_statement_tree_report.md'))
    ap.add_argument('--out-json', default=str(root / 'reports' / 'data' / 'edgar_statement_tree_report.json'))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    out = {'tickers': {}}
    md = ['# EDGAR statement-tree mapping report', '', 'Source: filing XBRL statements (IS/BS/CF membership explicit).', '']

    for t in tickers:
        company = Company(t)
        filing = company.get_filings(form='10-K')[0]
        x = filing.xbrl()
        statements = x.statements

        cls = CLASS_HINT.get(t, 'bank')
        template = TEMPLATES[cls]

        is_df = statement_df(statements.income_statement())
        bs_df = statement_df(statements.balance_sheet())
        cf_df = statement_df(statements.cashflow_statement())

        is_mapped, is_details, is_period, is_vals, is_labels = map_statement(is_df, template['IS'])
        bs_mapped, bs_details, bs_period, bs_vals, bs_labels = map_statement(bs_df, template['BS'])
        cf_mapped, cf_details, cf_period, cf_vals, cf_labels = map_statement(cf_df, template['CF'])

        bcheck = balance_check(bs_mapped)
        cfcheck = cashflow_check(cf_vals)

        out['tickers'][t] = {
            'class': cls,
            'filing_accession': filing.accession_no,
            'periods': {'IS': is_period, 'BS': bs_period, 'CF': cf_period},
            'mapped': {'IS': is_mapped, 'BS': bs_mapped, 'CF': cf_mapped},
            'details': {'IS': is_details, 'BS': bs_details, 'CF': cf_details},
            'checks': {'balance_sheet': bcheck, 'cashflow_bridge': cfcheck},
            'statement_concepts_present': {
                'IS': sorted(is_vals.keys()),
                'BS': sorted(bs_vals.keys()),
                'CF': sorted(cf_vals.keys()),
            },
        }

        md += [
            f'## {t} ({cls})',
            f'- Filing: `{filing.accession_no}`',
            f"- Balance check: **{bcheck['status']}** (diff={bcheck.get('diff')})",
            f"- Cashflow bridge check: **{cfcheck['status']}** (diff={cfcheck.get('diff')})",
            '',
        ]
        for st_name, details in [('IS', is_details), ('BS', bs_details), ('CF', cf_details)]:
            md.append(f'### {st_name} fiscal mapping')
            md.append('')
            for d in details:
                if d['mapped']:
                    md.append(f"- ✅ **{d['metric']}** ← `us-gaap:{d['concept']}` ({d['label']})")
                else:
                    tried = ', '.join(f'`us-gaap:{c}`' for c in d['candidates'])
                    md.append(f"- ❌ **{d['metric']}** ← EMPTY (tried {tried})")
            md.append('')
            md.append(f'#### {st_name} us-gaap concepts present in statement (primary, non-dimensional)')
            md.append('')
            concepts = out['tickers'][t]['statement_concepts_present'][st_name]
            for c in concepts[:120]:
                md.append(f'- `us-gaap:{c}`')
            if len(concepts) > 120:
                md.append(f'- ... +{len(concepts)-120} more')
            md.append('')

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text('\n'.join(md), encoding='utf-8')
    Path(args.out_json).write_text(json.dumps(out, indent=2), encoding='utf-8')
    print('wrote', args.out_md)
    print('wrote', args.out_json)


if __name__ == '__main__':
    main()
