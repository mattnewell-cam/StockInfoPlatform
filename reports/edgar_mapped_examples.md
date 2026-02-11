# EDGAR -> Fiscal-style mapping examples

Requested tickers: JPM, BRK-B, CRM
Tickers confirmed not in cached_financials_2: JPM, BRK-B, CRM

Legend: ✅ mapped to SEC us-gaap concept | ❌ left empty (no candidate concept had usable 10-K FY data)

## JPM (bank)

- IS: 8/11
- BS: 9/14
- CF: 8/9

### IS mapping detail

- ✅ **Total Revenues** ← `us-gaap:Revenues`
- ❌ **Cost of Sales** ← EMPTY (tried: `us-gaap:CostOfGoodsAndServicesSold`, `us-gaap:CostOfGoodsSold`, `us-gaap:CostOfRevenue`)
- ❌ **Gross Profit** ← EMPTY (tried: `us-gaap:GrossProfit`)
- ❌ **Operating Profit** ← EMPTY (tried: `us-gaap:OperatingIncomeLoss`)
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit`
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic`
- ✅ **Diluted EPS** ← `us-gaap:EarningsPerShareDiluted`
- ✅ **Net Interest Income** ← `us-gaap:InterestIncomeExpenseNet`
- ✅ **Interest Expense** ← `us-gaap:InterestExpense`

### BS mapping detail

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndCashEquivalentsAtCarryingValue`
- ❌ **Accounts Receivable** ← EMPTY (tried: `us-gaap:AccountsReceivableNetCurrent`)
- ❌ **Inventories** ← EMPTY (tried: `us-gaap:InventoryNet`)
- ❌ **Total Current Assets** ← EMPTY (tried: `us-gaap:AssetsCurrent`)
- ✅ **Net Property, Plant & Equipment** ← `us-gaap:PropertyPlantAndEquipmentNet`
- ✅ **Goodwill** ← `us-gaap:Goodwill`
- ✅ **Total Assets** ← `us-gaap:Assets`
- ❌ **Accounts Payable** ← EMPTY (tried: `us-gaap:AccountsPayableCurrent`)
- ❌ **Total Current Liabilities** ← EMPTY (tried: `us-gaap:LiabilitiesCurrent`)
- ✅ **Long-Term Debt** ← `us-gaap:LongTermDebt`
- ✅ **Total Liabilities** ← `us-gaap:Liabilities`
- ✅ **Retained Earnings** ← `us-gaap:RetainedEarningsAccumulatedDeficit`
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity`
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity`

### CF mapping detail

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Depreciation & Amortization** ← `us-gaap:DepreciationAmortizationAndAccretionNet`
- ✅ **Share-Based Compensation Expense** ← `us-gaap:ShareBasedCompensation`
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- ❌ **Capital Expenditure** ← EMPTY (tried: `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`)
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock`
- ✅ **Issuance of Common Shares** ← `us-gaap:ProceedsFromIssuanceOfCommonStock`

## BRK-B (insurer)

- IS: 6/11
- BS: 8/14
- CF: 7/9

### IS mapping detail

- ✅ **Total Revenues** ← `us-gaap:Revenues`
- ❌ **Cost of Sales** ← EMPTY (tried: `us-gaap:CostOfGoodsAndServicesSold`, `us-gaap:CostOfGoodsSold`, `us-gaap:CostOfRevenue`)
- ❌ **Gross Profit** ← EMPTY (tried: `us-gaap:GrossProfit`)
- ✅ **Operating Profit** ← `us-gaap:OperatingIncomeLoss`
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit`
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic`
- ❌ **Diluted EPS** ← EMPTY (tried: `us-gaap:EarningsPerShareDiluted`)
- ❌ **Net Premiums Earned** ← EMPTY (tried: `us-gaap:PremiumsEarnedNet`)
- ❌ **Insurance Benefits & Claims** ← EMPTY (tried: `us-gaap:PolicyholderBenefitsAndClaimsIncurredNet`)

### BS mapping detail

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndCashEquivalentsAtCarryingValue`
- ❌ **Accounts Receivable** ← EMPTY (tried: `us-gaap:AccountsReceivableNetCurrent`)
- ✅ **Inventories** ← `us-gaap:InventoryNet`
- ❌ **Total Current Assets** ← EMPTY (tried: `us-gaap:AssetsCurrent`)
- ❌ **Net Property, Plant & Equipment** ← EMPTY (tried: `us-gaap:PropertyPlantAndEquipmentNet`)
- ✅ **Goodwill** ← `us-gaap:Goodwill`
- ✅ **Total Assets** ← `us-gaap:Assets`
- ❌ **Accounts Payable** ← EMPTY (tried: `us-gaap:AccountsPayableCurrent`)
- ❌ **Total Current Liabilities** ← EMPTY (tried: `us-gaap:LiabilitiesCurrent`)
- ❌ **Long-Term Debt** ← EMPTY (tried: `us-gaap:LongTermDebtNoncurrent`, `us-gaap:LongTermDebt`)
- ✅ **Total Liabilities** ← `us-gaap:Liabilities`
- ✅ **Retained Earnings** ← `us-gaap:RetainedEarningsAccumulatedDeficit`
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity`
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity`

### CF mapping detail

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Depreciation & Amortization** ← `us-gaap:DepreciationDepletionAndAmortization`
- ❌ **Share-Based Compensation Expense** ← EMPTY (tried: `us-gaap:ShareBasedCompensation`)
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- ✅ **Capital Expenditure** ← `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock`
- ❌ **Issuance of Common Shares** ← EMPTY (tried: `us-gaap:ProceedsFromIssuanceOfCommonStock`)

## CRM (normal)

- IS: 9/9
- BS: 13/14
- CF: 8/9

### IS mapping detail

- ✅ **Total Revenues** ← `us-gaap:Revenues`
- ✅ **Cost of Sales** ← `us-gaap:CostOfGoodsAndServicesSold`
- ✅ **Gross Profit** ← `us-gaap:GrossProfit`
- ✅ **Operating Profit** ← `us-gaap:OperatingIncomeLoss`
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit`
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic`
- ✅ **Diluted EPS** ← `us-gaap:EarningsPerShareDiluted`

### BS mapping detail

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndCashEquivalentsAtCarryingValue`
- ✅ **Accounts Receivable** ← `us-gaap:AccountsReceivableNetCurrent`
- ❌ **Inventories** ← EMPTY (tried: `us-gaap:InventoryNet`)
- ✅ **Total Current Assets** ← `us-gaap:AssetsCurrent`
- ✅ **Net Property, Plant & Equipment** ← `us-gaap:PropertyPlantAndEquipmentNet`
- ✅ **Goodwill** ← `us-gaap:Goodwill`
- ✅ **Total Assets** ← `us-gaap:Assets`
- ✅ **Accounts Payable** ← `us-gaap:AccountsPayableCurrent`
- ✅ **Total Current Liabilities** ← `us-gaap:LiabilitiesCurrent`
- ✅ **Long-Term Debt** ← `us-gaap:LongTermDebtNoncurrent`
- ✅ **Total Liabilities** ← `us-gaap:Liabilities`
- ✅ **Retained Earnings** ← `us-gaap:RetainedEarningsAccumulatedDeficit`
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity`
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity`

### CF mapping detail

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss`
- ✅ **Depreciation & Amortization** ← `us-gaap:DepreciationDepletionAndAmortization`
- ✅ **Share-Based Compensation Expense** ← `us-gaap:ShareBasedCompensation`
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- ✅ **Capital Expenditure** ← `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock`
- ❌ **Issuance of Common Shares** ← EMPTY (tried: `us-gaap:ProceedsFromIssuanceOfCommonStock`)
