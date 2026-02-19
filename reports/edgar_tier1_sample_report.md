# EDGAR Tier-1 Sample Evaluation (Improved)

Tier-1 only: direct `us-gaap:*` concept mapping to fiscal-style raw metrics (no heuristics, no extension tags).

## Executive Summary

| Ticker | Class | IS coverage | BS coverage | CF coverage | Anchor pass | Go/No-Go |
|---|---|---:|---:|---:|---:|---|
| AAPL | normal | 10/12 (83.3%) | 16/18 (88.9%) | 9/9 (100.0%) | yes | GO |
| BAC | bank | 9/15 (60.0%) | 9/18 (50.0%) | 8/9 (88.9%) | yes | GO |
| AIG | insurer | 9/14 (64.3%) | 10/18 (55.6%) | 6/9 (66.7%) | yes | GO |

## AAPL (normal)

- CIK: `0000320193`
- Anchor pass: **yes**
- Decision: **GO**
- Statement coverage: IS 83.3% | BS 88.9% | CF 100.0%

### Missing `us-gaap` concepts (Tier-1 gaps)

- IS (2): `us-gaap:CostOfGoodsSold`, `us-gaap:IncomeBeforeTax`
- BS (2): `us-gaap:ShortTermInvestments`, `us-gaap:AdditionalPaidInCapital`
- CF (0): none

### Mapped concept examples

- IS (10): `us-gaap:Revenues`→Total Revenues, `us-gaap:SalesRevenueNet`→Total Revenues, `us-gaap:GrossProfit`→Gross Profit, `us-gaap:OperatingIncomeLoss`→Operating Profit, `us-gaap:IncomeTaxExpenseBenefit`→Provision for Income Taxes, `us-gaap:NetIncomeLoss`→Consolidated Net Income, `us-gaap:EarningsPerShareBasic`→Basic EPS, `us-gaap:EarningsPerShareDiluted`→Diluted EPS, `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`→Basic Weighted Average Shares Outstanding, `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`→Diluted Weighted Average Shares Outstanding
- BS (16): `us-gaap:CashAndCashEquivalentsAtCarryingValue`→Cash and Cash Equivalents, `us-gaap:AccountsReceivableNetCurrent`→Accounts Receivable, `us-gaap:InventoryNet`→Inventories, `us-gaap:AssetsCurrent`→Total Current Assets, `us-gaap:PropertyPlantAndEquipmentNet`→Net Property, Plant & Equipment, `us-gaap:Goodwill`→Goodwill, `us-gaap:IntangibleAssetsNetExcludingGoodwill`→Net Intangible Assets, `us-gaap:Assets`→Total Assets, `us-gaap:AccountsPayableCurrent`→Accounts Payable, `us-gaap:LiabilitiesCurrent`→Total Current Liabilities, `us-gaap:LongTermDebtNoncurrent`→Long-Term Debt, `us-gaap:Liabilities`→Total Liabilities, … +4 more
- CF (9): `us-gaap:NetIncomeLoss`→Net Income, `us-gaap:DepreciationDepletionAndAmortization`→Depreciation & Amortization, `us-gaap:ShareBasedCompensation`→Share-Based Compensation Expense, `us-gaap:NetCashProvidedByUsedInOperatingActivities`→Cash from Operating Activities, `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`→Capital Expenditure, `us-gaap:NetCashProvidedByUsedInInvestingActivities`→Cash from Investing Activities, `us-gaap:NetCashProvidedByUsedInFinancingActivities`→Cash from Financing Activities, `us-gaap:PaymentsForRepurchaseOfCommonStock`→Repurchases of Common Shares, `us-gaap:ProceedsFromIssuanceOfCommonStock`→Issuance of Common Shares

### Expected fiscal raw metrics still missing in output

- IS (2): Cost of Sales, Income Before Provision for Income Taxes
- BS (2): Additional Paid-in Capital, Short-Term Investments
- CF (0): none

## BAC (bank)

- CIK: `0000070858`
- Anchor pass: **yes**
- Decision: **GO**
- Statement coverage: IS 60.0% | BS 50.0% | CF 88.9%

### Missing `us-gaap` concepts (Tier-1 gaps)

- IS (6): `us-gaap:SalesRevenueNet`, `us-gaap:CostOfGoodsSold`, `us-gaap:GrossProfit`, `us-gaap:OperatingIncomeLoss`, `us-gaap:IncomeBeforeTax`, `us-gaap:InterestIncomeOperating`
- BS (9): `us-gaap:ShortTermInvestments`, `us-gaap:AccountsReceivableNetCurrent`, `us-gaap:InventoryNet`, `us-gaap:AssetsCurrent`, `us-gaap:AccountsPayableCurrent`, `us-gaap:LiabilitiesCurrent`, `us-gaap:LongTermDebtNoncurrent`, `us-gaap:CommonStockValue`, `us-gaap:AdditionalPaidInCapital`
- CF (1): `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`

### Mapped concept examples

- IS (9): `us-gaap:Revenues`→Total Revenues, `us-gaap:IncomeTaxExpenseBenefit`→Provision for Income Taxes, `us-gaap:NetIncomeLoss`→Consolidated Net Income, `us-gaap:EarningsPerShareBasic`→Basic EPS, `us-gaap:EarningsPerShareDiluted`→Diluted EPS, `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`→Basic Weighted Average Shares Outstanding, `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`→Diluted Weighted Average Shares Outstanding, `us-gaap:InterestExpense`→Interest Expense, `us-gaap:InterestIncomeExpenseNet`→Net Interest Income
- BS (9): `us-gaap:CashAndCashEquivalentsAtCarryingValue`→Cash and Cash Equivalents, `us-gaap:PropertyPlantAndEquipmentNet`→Net Property, Plant & Equipment, `us-gaap:Goodwill`→Goodwill, `us-gaap:IntangibleAssetsNetExcludingGoodwill`→Net Intangible Assets, `us-gaap:Assets`→Total Assets, `us-gaap:Liabilities`→Total Liabilities, `us-gaap:RetainedEarningsAccumulatedDeficit`→Retained Earnings, `us-gaap:StockholdersEquity`→Total Shareholders' Equity, `us-gaap:LiabilitiesAndStockholdersEquity`→Total Liabilities and Shareholders' Equity
- CF (8): `us-gaap:NetIncomeLoss`→Net Income, `us-gaap:DepreciationDepletionAndAmortization`→Depreciation & Amortization, `us-gaap:ShareBasedCompensation`→Share-Based Compensation Expense, `us-gaap:NetCashProvidedByUsedInOperatingActivities`→Cash from Operating Activities, `us-gaap:NetCashProvidedByUsedInInvestingActivities`→Cash from Investing Activities, `us-gaap:NetCashProvidedByUsedInFinancingActivities`→Cash from Financing Activities, `us-gaap:PaymentsForRepurchaseOfCommonStock`→Repurchases of Common Shares, `us-gaap:ProceedsFromIssuanceOfCommonStock`→Issuance of Common Shares

### Expected fiscal raw metrics still missing in output

- IS (5): Cost of Sales, Gross Profit, Income Before Provision for Income Taxes, Interest Income, Operating Profit
- BS (9): Accounts Payable, Accounts Receivable, Additional Paid-in Capital, Common Stock, Inventories, Long-Term Debt, Short-Term Investments, Total Current Assets, Total Current Liabilities
- CF (1): Capital Expenditure

## AIG (insurer)

- CIK: `0000005272`
- Anchor pass: **yes**
- Decision: **GO**
- Statement coverage: IS 64.3% | BS 55.6% | CF 66.7%

### Missing `us-gaap` concepts (Tier-1 gaps)

- IS (5): `us-gaap:SalesRevenueNet`, `us-gaap:CostOfGoodsSold`, `us-gaap:GrossProfit`, `us-gaap:OperatingIncomeLoss`, `us-gaap:IncomeBeforeTax`
- BS (8): `us-gaap:CashAndCashEquivalentsAtCarryingValue`, `us-gaap:AccountsReceivableNetCurrent`, `us-gaap:InventoryNet`, `us-gaap:AssetsCurrent`, `us-gaap:AccountsPayableCurrent`, `us-gaap:LiabilitiesCurrent`, `us-gaap:LongTermDebtNoncurrent`, `us-gaap:AdditionalPaidInCapital`
- CF (3): `us-gaap:DepreciationDepletionAndAmortization`, `us-gaap:ShareBasedCompensation`, `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`

### Mapped concept examples

- IS (9): `us-gaap:Revenues`→Total Revenues, `us-gaap:IncomeTaxExpenseBenefit`→Provision for Income Taxes, `us-gaap:NetIncomeLoss`→Consolidated Net Income, `us-gaap:EarningsPerShareBasic`→Basic EPS, `us-gaap:EarningsPerShareDiluted`→Diluted EPS, `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`→Basic Weighted Average Shares Outstanding, `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`→Diluted Weighted Average Shares Outstanding, `us-gaap:PremiumsEarnedNet`→Net Premiums Earned, `us-gaap:PolicyholderBenefitsAndClaimsIncurredNet`→Insurance Benefits & Claims
- BS (10): `us-gaap:ShortTermInvestments`→Short-Term Investments, `us-gaap:PropertyPlantAndEquipmentNet`→Net Property, Plant & Equipment, `us-gaap:Goodwill`→Goodwill, `us-gaap:IntangibleAssetsNetExcludingGoodwill`→Net Intangible Assets, `us-gaap:Assets`→Total Assets, `us-gaap:Liabilities`→Total Liabilities, `us-gaap:RetainedEarningsAccumulatedDeficit`→Retained Earnings, `us-gaap:CommonStockValue`→Common Stock, `us-gaap:StockholdersEquity`→Total Shareholders' Equity, `us-gaap:LiabilitiesAndStockholdersEquity`→Total Liabilities and Shareholders' Equity
- CF (6): `us-gaap:NetIncomeLoss`→Net Income, `us-gaap:NetCashProvidedByUsedInOperatingActivities`→Cash from Operating Activities, `us-gaap:NetCashProvidedByUsedInInvestingActivities`→Cash from Investing Activities, `us-gaap:NetCashProvidedByUsedInFinancingActivities`→Cash from Financing Activities, `us-gaap:PaymentsForRepurchaseOfCommonStock`→Repurchases of Common Shares, `us-gaap:ProceedsFromIssuanceOfCommonStock`→Issuance of Common Shares

### Expected fiscal raw metrics still missing in output

- IS (4): Cost of Sales, Gross Profit, Income Before Provision for Income Taxes, Operating Profit
- BS (8): Accounts Payable, Accounts Receivable, Additional Paid-in Capital, Cash and Cash Equivalents, Inventories, Long-Term Debt, Total Current Assets, Total Current Liabilities
- CF (3): Capital Expenditure, Depreciation & Amortization, Share-Based Compensation Expense