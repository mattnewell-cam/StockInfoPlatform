import argparse, csv, json, sqlite3
from collections import defaultdict
from pathlib import Path
import requests

SEC_UA='Matt Newell matthew_newell@outlook.com'
TICKERS_URL='https://www.sec.gov/files/company_tickers.json'
FACTS_URL='https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'

MAP_COMMON={
 'IS':{
  'Total Revenues':['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet'],
  'Cost of Sales':['CostOfGoodsAndServicesSold','CostOfGoodsSold','CostOfRevenue'],
  'Gross Profit':['GrossProfit'],
  'Operating Profit':['OperatingIncomeLoss'],
  'Income Before Provision for Income Taxes':['IncomeBeforeTax','IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'],
  'Provision for Income Taxes':['IncomeTaxExpenseBenefit'],
  'Consolidated Net Income':['NetIncomeLoss'],
  'Basic EPS':['EarningsPerShareBasic'],
  'Diluted EPS':['EarningsPerShareDiluted'],
 },
 'BS':{
  'Cash and Cash Equivalents':['CashAndCashEquivalentsAtCarryingValue'],
  'Accounts Receivable':['AccountsReceivableNetCurrent'],
  'Inventories':['InventoryNet'],
  'Total Current Assets':['AssetsCurrent'],
  'Net Property, Plant & Equipment':['PropertyPlantAndEquipmentNet'],
  'Goodwill':['Goodwill'],
  'Total Assets':['Assets'],
  'Accounts Payable':['AccountsPayableCurrent'],
  'Total Current Liabilities':['LiabilitiesCurrent'],
  'Long-Term Debt':['LongTermDebtNoncurrent','LongTermDebt'],
  'Total Liabilities':['Liabilities'],
  'Retained Earnings':['RetainedEarningsAccumulatedDeficit'],
  "Total Shareholders' Equity":['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
  "Total Liabilities and Shareholders' Equity":['LiabilitiesAndStockholdersEquity'],
 },
 'CF':{
  'Net Income':['NetIncomeLoss'],
  'Depreciation & Amortization':['DepreciationDepletionAndAmortization','DepreciationAmortizationAndAccretionNet'],
  'Share-Based Compensation Expense':['ShareBasedCompensation'],
  'Cash from Operating Activities':['NetCashProvidedByUsedInOperatingActivities'],
  'Capital Expenditure':['PaymentsToAcquirePropertyPlantAndEquipment'],
  'Cash from Investing Activities':['NetCashProvidedByUsedInInvestingActivities'],
  'Cash from Financing Activities':['NetCashProvidedByUsedInFinancingActivities'],
  'Repurchases of Common Shares':['PaymentsForRepurchaseOfCommonStock'],
  'Issuance of Common Shares':['ProceedsFromIssuanceOfCommonStock'],
 }
}
CLASS_EXTRA={
 'bank':{'IS':{'Net Interest Income':['InterestIncomeExpenseNet','NetInterestIncome'],'Interest Expense':['InterestExpense'] }},
 'insurer':{'IS':{'Net Premiums Earned':['PremiumsEarnedNet'],'Insurance Benefits & Claims':['PolicyholderBenefitsAndClaimsIncurredNet']}}
}

def sec_get(url):
 r=requests.get(url,headers={'User-Agent':SEC_UA,'Accept':'application/json'},timeout=30)
 r.raise_for_status(); return r.json()

def ticker_to_cik():
 data=sec_get(TICKERS_URL)
 return {v['ticker'].upper():str(v['cik_str']).zfill(10) for v in data.values()}

def company_classes(db_path,tickers):
 conn=sqlite3.connect(str(db_path)); cur=conn.cursor()
 q='select ticker,coalesce(sector,\'\'),coalesce(industry,\'\') from companies_company where ticker in (%s)'%(','.join('?'*len(tickers)))
 cur.execute(q,tickers)
 out={}
 for t,s,i in cur.fetchall():
  x=(s+' '+i).lower()
  if 'insurance' in x: out[t]='insurer'
  elif 'bank' in x: out[t]='bank'
  else: out[t]='normal'
 conn.close(); return out

def pick_series(us,concept):
 obj=us.get(concept)
 if not obj: return {}
 vals={}
 for unit,arr in obj.get('units',{}).items():
  for it in arr:
   if not (it.get('form') or '').startswith('10-K'): continue
   fp=(it.get('fp') or '')
   if fp and fp!='FY': continue
   end=it.get('end'); val=it.get('val')
   if end is None or val is None: continue
   vals[str(end)]=val
 return vals

def build_stmt(us,map_stmt):
 metric_data={}; concept_used={}; concept_missing=[]
 all_dates=set()
 for metric,cands in map_stmt.items():
  chosen={}; used=None
  for c in cands:
   s=pick_series(us,c)
   if s:
    chosen=s; used=c; break
  if used:
    metric_data[metric]=chosen; concept_used[metric]=used; all_dates.update(chosen.keys())
  else:
    concept_missing.append((metric,cands))
 dates=sorted(all_dates,reverse=True)[:5]
 rows=[['Metric']+dates]
 for m in sorted(metric_data): rows.append([m]+[metric_data[m].get(d) for d in dates])
 return rows,concept_used,concept_missing

def main():
 ap=argparse.ArgumentParser()
 root=Path(__file__).resolve().parents[1]
 ap.add_argument('--tickers',default='JPM,BRK-B,CRM')
 ap.add_argument('--db',default=str(root/'db.sqlite3'))
 ap.add_argument('--cache',default=str(root/'cached_financials_2.json'))
 ap.add_argument('--out-json',default=str(root/'reports/data/edgar_mapped_examples.json'))
 ap.add_argument('--out-md',default=str(root/'reports/edgar_mapped_examples.md'))
 args=ap.parse_args()

 tickers=[t.strip().upper() for t in args.tickers.split(',') if t.strip()]
 cache=json.load(open(args.cache))
 missing=[t for t in tickers if t not in cache]
 ciks=ticker_to_cik()
 cls=company_classes(Path(args.db),tickers)
 out={'tickers':{},'requested':tickers,'not_in_cached_financials_2':missing}
 md=['# EDGAR -> Fiscal-style mapping examples','','Requested tickers: '+', '.join(tickers),'Tickers confirmed not in cached_financials_2: '+', '.join(missing),'']

 for t in tickers:
  cik=ciks.get(t)
  if not cik:
   out['tickers'][t]={'error':'no_cik'}; continue
  facts=sec_get(FACTS_URL.format(cik=cik))
  us=facts.get('facts',{}).get('us-gaap',{})
  cl=cls.get(t,'normal')
  m={k:dict(v) for k,v in MAP_COMMON.items()}
  for st,extra in CLASS_EXTRA.get(cl,{}).items():
   m[st].update(extra)
  is_rows,is_used,is_miss=build_stmt(us,m['IS'])
  bs_rows,bs_used,bs_miss=build_stmt(us,m['BS'])
  cf_rows,cf_used,cf_miss=build_stmt(us,m['CF'])
  out['tickers'][t]={
   'class':cl,'cik':cik,
   'statements':{'IS':is_rows,'BS':bs_rows,'CF':cf_rows},
   'used_concepts':{'IS':is_used,'BS':bs_used,'CF':cf_used},
   'missing_metrics':{'IS':is_miss,'BS':bs_miss,'CF':cf_miss}
  }
  md += [f"## {t} ({cl})",'',
         f"- IS mapped: {len(is_used)}/{len(m['IS'])}",
         f"- BS mapped: {len(bs_used)}/{len(m['BS'])}",
         f"- CF mapped: {len(cf_used)}/{len(m['CF'])}",
         f"- Missing IS metrics: {', '.join(x[0] for x in is_miss) if is_miss else 'none'}",
         f"- Missing BS metrics: {', '.join(x[0] for x in bs_miss) if bs_miss else 'none'}",
         f"- Missing CF metrics: {', '.join(x[0] for x in cf_miss) if cf_miss else 'none'}",
         '']

 Path(args.out_json).parent.mkdir(parents=True,exist_ok=True)
 Path(args.out_md).parent.mkdir(parents=True,exist_ok=True)
 Path(args.out_json).write_text(json.dumps(out,indent=2),encoding='utf-8')
 Path(args.out_md).write_text('\n'.join(md),encoding='utf-8')
 print('wrote',args.out_json)
 print('wrote',args.out_md)

if __name__=='__main__':
 main()
