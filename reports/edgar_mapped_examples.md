# EDGAR -> Fiscal-style mapping examples (class-specific templates)

Requested tickers: JPM, BRK-B
Tickers confirmed not in cached_financials_2: JPM, BRK-B

Legend: ✅ mapped to SEC us-gaap concept | ❌ left empty (no candidate concept had usable 10-K FY data)

## JPM (bank)

- IS: 7/7
- BS: 9/11
- CF: 7/8

### IS mapping detail

- ✅ **Net Interest Income** ← `us-gaap:InterestIncomeExpenseNet`
- ✅ **Interest Expense** ← `us-gaap:InterestExpense`
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit`
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic`
- ✅ **Diluted EPS** ← `us-gaap:EarningsPerShareDiluted`

### BS mapping detail

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndCashEquivalentsAtCarryingValue`
- ❌ **Trading Assets** ← EMPTY (tried: `us-gaap:TradingAssets`)
- ✅ **Trading Liabilities** ← `us-gaap:TradingLiabilities`
- ✅ **Goodwill** ← `us-gaap:Goodwill`
- ❌ **Net Intangible Assets** ← EMPTY (tried: `us-gaap:IntangibleAssetsNetExcludingGoodwill`)
- ✅ **Total Assets** ← `us-gaap:Assets`
- ✅ **Long-Term Debt** ← `us-gaap:LongTermDebt`
- ✅ **Total Liabilities** ← `us-gaap:Liabilities`
- ✅ **Retained Earnings** ← `us-gaap:RetainedEarningsAccumulatedDeficit`
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity`
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity`

### CF mapping detail

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Depreciation & Amortization** ← `us-gaap:DepreciationAmortizationAndAccretionNet`
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- ❌ **Capital Expenditure** ← EMPTY (tried: `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`)
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock`
- ✅ **Issuance of Common Shares** ← `us-gaap:ProceedsFromIssuanceOfCommonStock`

## BRK-B (insurer)

- IS: 6/10
- BS: 7/12
- CF: 6/7

### IS mapping detail

- ❌ **Net Premiums Earned** ← EMPTY (tried: `us-gaap:PremiumsEarnedNet`, `us-gaap:Premiums`)
- ❌ **Insurance Benefits & Claims** ← EMPTY (tried: `us-gaap:PolicyholderBenefitsAndClaimsIncurredNet`, `us-gaap:PolicyholderBenefitsAndClaimsIncurred`)
- ❌ **Investment Income** ← EMPTY (tried: `us-gaap:InvestmentIncomeInterestAndDividend`)
- ✅ **Total Revenues** ← `us-gaap:Revenues`
- ✅ **Operating Profit** ← `us-gaap:OperatingIncomeLoss`
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit`
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic`
- ❌ **Diluted EPS** ← EMPTY (tried: `us-gaap:EarningsPerShareDiluted`)

### BS mapping detail

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndCashEquivalentsAtCarryingValue`
- ❌ **Debt Securities** ← EMPTY (tried: `us-gaap:DebtSecuritiesAvailableForSaleAmortizedCostBasis`)
- ❌ **Total Investments** ← EMPTY (tried: `us-gaap:Investments`)
- ❌ **Reinsurance Contract Assets** ← EMPTY (tried: `us-gaap:ReinsuranceRecoverables`)
- ✅ **Deferred Acquisition Costs** ← `us-gaap:DeferredPolicyAcquisitionCosts`
- ✅ **Goodwill** ← `us-gaap:Goodwill`
- ✅ **Total Assets** ← `us-gaap:Assets`
- ❌ **Unearned Premiums** ← EMPTY (tried: `us-gaap:UnearnedPremiums`)
- ❌ **Claims Reserves** ← EMPTY (tried: `us-gaap:PolicyholderBenefitsAndClaimsLiability`)
- ✅ **Total Liabilities** ← `us-gaap:Liabilities`
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity`
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity`

### CF mapping detail

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- ✅ **Capital Expenditure** ← `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock`
- ❌ **Issuance of Common Shares** ← EMPTY (tried: `us-gaap:ProceedsFromIssuanceOfCommonStock`)
