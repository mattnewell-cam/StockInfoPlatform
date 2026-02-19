# EDGAR statement-tree mapping report

Source: filing XBRL statements (IS/BS/CF membership explicit).

## JPM (bank)
- Filing: `0000019617-25-000270`
- Balance check: **pass** (diff=0.0)
- Cashflow bridge check: **missing_inputs** (diff=None)

### IS fiscal mapping

- ✅ **Net Interest Income** ← `us-gaap:InterestIncomeExpenseNet` (Net interest income)
- ❌ **Interest Expense** ← EMPTY (tried `us-gaap:InterestExpense`)
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` (Income/(loss) before income tax expense/(benefit))
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit` (Income tax expense)
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss` (Net income/(loss))
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic` (Basic earnings per share (in dollars per share))
- ✅ **Diluted EPS** ← `us-gaap:EarningsPerShareDiluted` (Diluted earnings per share (in dollars per share))

#### IS us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:AssetManagementFees`
- `us-gaap:CommunicationsAndInformationTechnology`
- `us-gaap:DebtSecuritiesAvailableForSaleRealizedGainLoss`
- `us-gaap:EarningsPerShareBasic`
- `us-gaap:EarningsPerShareDiluted`
- `us-gaap:FeesAndCommissions1`
- `us-gaap:FeesAndCommissionsCreditAndDebitCards1`
- `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- `us-gaap:IncomeTaxExpenseBenefit`
- `us-gaap:InterestExpenseOperating`
- `us-gaap:InterestIncomeExpenseNet`
- `us-gaap:InterestIncomeOperating`
- `us-gaap:InvestmentBankingRevenue`
- `us-gaap:LaborAndRelatedExpense`
- `us-gaap:LendingAndDepositRelatedFees`
- `us-gaap:MarketingAndAdvertisingExpense`
- `us-gaap:MortgageFeesAndRelatedIncome`
- `us-gaap:NetIncomeLoss`
- `us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic`
- `us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted`
- `us-gaap:NoninterestExpense`
- `us-gaap:NoninterestIncome`
- `us-gaap:NoninterestIncomeOther`
- `us-gaap:OccupancyNet`
- `us-gaap:OtherNoninterestExpense`
- `us-gaap:PrincipalTransactionsRevenue`
- `us-gaap:ProfessionalAndContractServicesExpense`
- `us-gaap:ProvisionForLoanLeaseAndOtherLosses`
- `us-gaap:RevenuesNetOfInterestExpense`
- `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`
- `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`

### BS fiscal mapping

- ✅ **Cash and Cash Equivalents** ← `us-gaap:CashAndDueFromBanks` (Cash and due from banks)
- ✅ **Trading Assets** ← `us-gaap:TradingAssets` (Trading assets (included assets pledged of $136,070 and $128,994))
- ✅ **Trading Liabilities** ← `us-gaap:TradingLiabilities` (Trading liabilities)
- ❌ **Goodwill** ← EMPTY (tried `us-gaap:Goodwill`)
- ❌ **Net Intangible Assets** ← EMPTY (tried `us-gaap:IntangibleAssetsNetExcludingGoodwill`)
- ✅ **Total Assets** ← `us-gaap:Assets` (Total assets)
- ❌ **Long-Term Debt** ← EMPTY (tried `us-gaap:LongTermDebtNoncurrent`, `us-gaap:LongTermDebt`)
- ✅ **Total Liabilities** ← `us-gaap:Liabilities` (Total liabilities)
- ✅ **Retained Earnings** ← `us-gaap:RetainedEarningsAccumulatedDeficit` (Retained earnings)
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity` (Total stockholders’ equity)
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity` (Total liabilities and stockholders’ equity)

#### BS us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent`
- `us-gaap:AccruedInterestAndAccountsReceivable`
- `us-gaap:AccumulatedOtherComprehensiveIncomeLossNetOfTax`
- `us-gaap:AdditionalPaidInCapitalCommonStock`
- `us-gaap:Assets`
- `us-gaap:BeneficialInterest`
- `us-gaap:CashAndDueFromBanks`
- `us-gaap:CommitmentsAndContingencies`
- `us-gaap:CommonStockValue`
- `us-gaap:DebtSecuritiesAvailableForSaleExcludingAccruedInterest`
- `us-gaap:DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss`
- `us-gaap:DebtSecuritiesNetCarryingAmount`
- `us-gaap:Deposits`
- `us-gaap:FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase`
- `us-gaap:FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell`
- `us-gaap:FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest`
- `us-gaap:FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss`
- `us-gaap:FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossesNetOfDeferredIncome`
- `us-gaap:GoodwillServicingAssetsatFairValueandOtherIntangibleAssets`
- `us-gaap:InterestBearingDepositsInBanks`
- `us-gaap:Liabilities`
- `us-gaap:LiabilitiesAndStockholdersEquity`
- `us-gaap:LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`
- `us-gaap:OtherAssets`
- `us-gaap:OtherLiabilities`
- `us-gaap:PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount`
- `us-gaap:PropertyPlantAndEquipmentAndOperatingLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization`
- `us-gaap:RetainedEarningsAccumulatedDeficit`
- `us-gaap:SecuritiesBorrowed`
- `us-gaap:ShortTermBorrowings`
- `us-gaap:StockholdersEquity`
- `us-gaap:TradingAssets`
- `us-gaap:TradingLiabilities`
- `us-gaap:TreasuryStockCommonValue`

### CF fiscal mapping

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss` (Net income)
- ✅ **Depreciation & Amortization** ← `us-gaap:DepreciationAmortizationAndAccretionNet` (Depreciation and amortization)
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities` (Net cash (used in)/provided by operating activities)
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities` (Net cash (used in)/provided by investing activities)
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities` (Net cash provided by/(used in) financing activities)
- ❌ **Capital Expenditure** ← EMPTY (tried `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`)
- ✅ **Repurchases of Common Shares** ← `us-gaap:PaymentsForRepurchaseOfCommonStock` (Treasury stock repurchased)
- ❌ **Issuance of Common Shares** ← EMPTY (tried `us-gaap:ProceedsFromIssuanceOfCommonStock`)

#### CF us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:BusinessCombinationBargainPurchaseGainRecognizedAmount`
- `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`
- `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect`
- `us-gaap:DeferredIncomeTaxExpenseBenefit`
- `us-gaap:DepreciationAmortizationAndAccretionNet`
- `us-gaap:EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`
- `us-gaap:EquitySecuritiesGainLossOnShareExchange`
- `us-gaap:IncomeTaxesPaidNet`
- `us-gaap:IncreaseDecreaseInAccountsPayableAndOtherLiabilities`
- `us-gaap:IncreaseDecreaseInAccruedInterestsAndAccountsReceivable`
- `us-gaap:IncreaseDecreaseInBeneficialInterestsIssuedByConsolidatedVariableInterestEntities`
- `us-gaap:IncreaseDecreaseInCashCollateralForBorrowedSecurities`
- `us-gaap:IncreaseDecreaseInDeposits`
- `us-gaap:IncreaseDecreaseInFederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchaseNet`
- `us-gaap:IncreaseDecreaseInFinancialInstrumentsUsedInOperatingActivities`
- `us-gaap:IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets`
- `us-gaap:IncreaseDecreaseInTradingLiabilities`
- `us-gaap:InterestPaidNet`
- `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- `us-gaap:NetIncomeLoss`
- `us-gaap:OtherNoncashIncomeExpense`
- `us-gaap:OtherOperatingActivitiesCashFlowStatement`
- `us-gaap:PaymentsForOriginationAndPurchasesOfLoansHeldForSale`
- `us-gaap:PaymentsForProceedsFromOtherInvestingActivities`
- `us-gaap:PaymentsForRepurchaseOfCommonStock`
- `us-gaap:PaymentsForRepurchaseOfRedeemablePreferredStock`
- `us-gaap:PaymentsOfDividends`
- `us-gaap:PaymentsToAcquireAvailableForSaleSecuritiesDebt`
- `us-gaap:PaymentsToAcquireBusinessesNetOfCashAcquired`
- `us-gaap:PaymentsToAcquireHeldToMaturitySecurities`
- `us-gaap:ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet`
- `us-gaap:ProceedsFromIssuanceOfPreferredStockAndPreferenceStock`
- `us-gaap:ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities`
- `us-gaap:ProceedsFromMaturitiesPrepaymentsAndCallsOfHeldToMaturitySecurities`
- `us-gaap:ProceedsFromPaymentsForFederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResellNet`
- `us-gaap:ProceedsFromPaymentsForOtherFinancingActivities`
- `us-gaap:ProceedsFromPaymentsForOtherLoansAndLeases`
- `us-gaap:ProceedsFromSaleOfAvailableForSaleSecuritiesDebt`
- `us-gaap:ProceedsFromSaleOfFinanceReceivables`
- `us-gaap:ProceedsFromSalesSecuritizationsAndPaydownsOfLoansHeldForSale`
- `us-gaap:ProceedsFromShortTermDebt`
- `us-gaap:ProvisionForLoanLeaseAndOtherLosses`
- `us-gaap:RepaymentsOfLongTermDebtAndCapitalSecurities`
- `us-gaap:RepaymentsOfShortTermDebt`

## PGR (insurer)
- Filing: `0000080661-25-000007`
- Balance check: **pass** (diff=0.0)
- Cashflow bridge check: **missing_inputs** (diff=None)

### IS fiscal mapping

- ❌ **Net Premiums Earned** ← EMPTY (tried `us-gaap:PremiumsEarnedNet`, `us-gaap:Premiums`)
- ✅ **Insurance Benefits & Claims** ← `us-gaap:PolicyholderBenefitsAndClaimsIncurredNet` (Losses and loss adjustment expenses)
- ❌ **Investment Income** ← EMPTY (tried `us-gaap:InvestmentIncomeInterestAndDividend`)
- ✅ **Total Revenues** ← `us-gaap:Revenues` (Total revenues)
- ❌ **Operating Profit** ← EMPTY (tried `us-gaap:OperatingIncomeLoss`)
- ✅ **Income Before Provision for Income Taxes** ← `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` (Income before income taxes)
- ✅ **Provision for Income Taxes** ← `us-gaap:IncomeTaxExpenseBenefit` (Provision for income taxes)
- ✅ **Consolidated Net Income** ← `us-gaap:NetIncomeLoss` (Net income)
- ✅ **Basic EPS** ← `us-gaap:EarningsPerShareBasic` (Basic: Earnings per common share (usd per share))
- ✅ **Diluted EPS** ← `us-gaap:EarningsPerShareDiluted` (Diluted: Earnings per common share (usd per share))

#### IS us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:BenefitsLossesAndExpenses`
- `us-gaap:ComprehensiveIncomeNetOfTax`
- `us-gaap:DebtAndEquitySecuritiesGainLoss`
- `us-gaap:DebtAndEquitySecuritiesRealizedGainLoss`
- `us-gaap:DebtAndEquitySecuritiesUnrealizedGainLoss`
- `us-gaap:DeferredPolicyAcquisitionCostAmortizationExpense`
- `us-gaap:EarningsPerShareBasic`
- `us-gaap:EarningsPerShareDiluted`
- `us-gaap:FeesAndOtherRevenues`
- `us-gaap:GoodwillImpairmentLoss`
- `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- `us-gaap:IncomeTaxExpenseBenefit`
- `us-gaap:InterestAndDividendIncomeOperating`
- `us-gaap:InterestExpenseDebt`
- `us-gaap:InvestmentIncomeInvestmentExpense`
- `us-gaap:NetIncomeLoss`
- `us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic`
- `us-gaap:NonInsuranceServiceExpenses`
- `us-gaap:NonInsuranceServiceRevenues`
- `us-gaap:OtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax`
- `us-gaap:OtherUnderwritingExpense`
- `us-gaap:PolicyholderBenefitsAndClaimsIncurredNet`
- `us-gaap:PreferredStockDividendsIncomeStatementImpact`
- `us-gaap:PremiumsEarnedNetPropertyAndCasualty`
- `us-gaap:Revenues`
- `us-gaap:TotalOtherThanTemporaryImpairmentLoss`
- `us-gaap:WeightedAverageNumberDilutedSharesOutstandingAdjustment`
- `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`
- `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`

### BS fiscal mapping

- ❌ **Cash and Cash Equivalents** ← EMPTY (tried `us-gaap:CashAndCashEquivalentsAtCarryingValue`)
- ❌ **Debt Securities** ← EMPTY (tried `us-gaap:DebtSecuritiesAvailableForSaleAmortizedCostBasis`)
- ✅ **Total Investments** ← `us-gaap:Investments` (Total investments)
- ❌ **Reinsurance Contract Assets** ← EMPTY (tried `us-gaap:ReinsuranceRecoverables`)
- ✅ **Deferred Acquisition Costs** ← `us-gaap:DeferredPolicyAcquisitionCosts` (Deferred acquisition costs)
- ❌ **Goodwill** ← EMPTY (tried `us-gaap:Goodwill`)
- ✅ **Total Assets** ← `us-gaap:Assets` (Total assets)
- ✅ **Unearned Premiums** ← `us-gaap:UnearnedPremiums` (Unearned premiums)
- ❌ **Claims Reserves** ← EMPTY (tried `us-gaap:PolicyholderBenefitsAndClaimsLiability`)
- ✅ **Total Liabilities** ← `us-gaap:Liabilities` (Total liabilities)
- ✅ **Total Shareholders' Equity** ← `us-gaap:StockholdersEquity` (Total shareholders’ equity)
- ✅ **Total Liabilities and Shareholders' Equity** ← `us-gaap:LiabilitiesAndStockholdersEquity` (Total liabilities and shareholders’ equity)

#### BS us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent`
- `us-gaap:AccruedInvestmentIncomeReceivable`
- `us-gaap:AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax`
- `us-gaap:AccumulatedOtherComprehensiveIncomeLossForeignCurrencyTranslationAdjustmentNetOfTax`
- `us-gaap:AccumulatedOtherComprehensiveIncomeLossNetOfTax`
- `us-gaap:AdditionalPaidInCapitalCommonStock`
- `us-gaap:AociLossCashFlowHedgeCumulativeGainLossAfterTax`
- `us-gaap:Assets`
- `us-gaap:AvailableForSaleSecuritiesDebtSecurities`
- `us-gaap:Cash`
- `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`
- `us-gaap:CommonStockValueOutstanding`
- `us-gaap:DebtLongtermAndShorttermCombinedAmount`
- `us-gaap:DebtSecuritiesAvailableforsaleFixedMaturities`
- `us-gaap:DeferredPolicyAcquisitionCosts`
- `us-gaap:DeferredTaxAssetsFederalTax`
- `us-gaap:EquitySecuritiesFVNICommonEquities`
- `us-gaap:EquitySecuritiesFVNINonredeemablePreferredStock`
- `us-gaap:EquitySecuritiesFvNi`
- `us-gaap:Investments`
- `us-gaap:Liabilities`
- `us-gaap:LiabilitiesAndStockholdersEquity`
- `us-gaap:LiabilityForClaimsAndClaimsAdjustmentExpense`
- `us-gaap:OtherAssets`
- `us-gaap:PreferredStockValueOutstanding`
- `us-gaap:PremiumsReceivableAtCarryingValue`
- `us-gaap:PrepaidReinsurancePremiums`
- `us-gaap:PropertyPlantAndEquipmentNet`
- `us-gaap:ReinsuranceRecoverablesOnPaidAndUnpaidLosses`
- `us-gaap:RestrictedCashAndCashEquivalents`
- `us-gaap:RetainedEarningsAccumulatedDeficit`
- `us-gaap:ShortTermInvestments`
- `us-gaap:StockholdersEquity`
- `us-gaap:UnearnedPremiums`

### CF fiscal mapping

- ✅ **Net Income** ← `us-gaap:NetIncomeLoss` (Net income)
- ✅ **Cash from Operating Activities** ← `us-gaap:NetCashProvidedByUsedInOperatingActivities` (Net cash provided by operating activities)
- ✅ **Cash from Investing Activities** ← `us-gaap:NetCashProvidedByUsedInInvestingActivities` (Net cash used in investing activities)
- ✅ **Cash from Financing Activities** ← `us-gaap:NetCashProvidedByUsedInFinancingActivities` (Net cash provided by (used in) financing activities)
- ✅ **Capital Expenditure** ← `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` (Purchases of property and equipment)
- ❌ **Repurchases of Common Shares** ← EMPTY (tried `us-gaap:PaymentsForRepurchaseOfCommonStock`)
- ❌ **Issuance of Common Shares** ← EMPTY (tried `us-gaap:ProceedsFromIssuanceOfCommonStock`)

#### CF us-gaap concepts present in statement (primary, non-dimensional)

- `us-gaap:AccretionAmortizationOfDiscountsAndPremiumsInvestments`
- `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`
- `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect`
- `us-gaap:Depreciation`
- `us-gaap:GainLossOnSaleOfPropertyPlantEquipment`
- `us-gaap:GoodwillImpairmentLoss`
- `us-gaap:IncreaseDecreaseInAccountsPayableAndAccruedLiabilities`
- `us-gaap:IncreaseDecreaseInDeferredPolicyAcquisitionCosts`
- `us-gaap:IncreaseDecreaseInIncomeTaxes`
- `us-gaap:IncreaseDecreaseInLiabilityForClaimsAndClaimsAdjustmentExpenseReserve`
- `us-gaap:IncreaseDecreaseInOtherOperatingCapitalNet`
- `us-gaap:IncreaseDecreaseInPremiumsReceivable`
- `us-gaap:IncreaseDecreaseInPrepaidReinsurancePremiums`
- `us-gaap:IncreaseDecreaseInReinsuranceRecoverable`
- `us-gaap:IncreaseDecreaseInUnearnedPremiums`
- `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- `us-gaap:NetIncomeLoss`
- `us-gaap:PaymentsForProceedsFromShortTermInvestments`
- `us-gaap:PaymentsForRepurchaseOfPreferredStockAndPreferenceStock`
- `us-gaap:PaymentsOfDividendsCommonStock`
- `us-gaap:PaymentsOfDividendsPreferredStockAndPreferenceStock`
- `us-gaap:PaymentsToAcquireAvailableForSaleSecuritiesDebt`
- `us-gaap:PaymentsToAcquireEquitySecuritiesFvNi`
- `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
- `us-gaap:PaymentsforRepurchaseofCommonStockforRestrictedStockTaxLiabilities`
- `us-gaap:PaymentsforRepurchaseofCommonStockintheOpenMarket`
- `us-gaap:ProceedsFromIssuanceOfDebt`
- `us-gaap:ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities`
- `us-gaap:ProceedsFromMaturitiesPrepaymentsAndCallsOfEquitySecuritiesFVNI`
- `us-gaap:ProceedsFromPayablesToBrokerDealersInvestingActivities`
- `us-gaap:ProceedsFromSaleOfAvailableForSaleSecuritiesDebt`
- `us-gaap:ProceedsFromSaleOfEquitySecuritiesFvNi`
- `us-gaap:ProceedsFromSaleOfPropertyPlantAndEquipment`
- `us-gaap:RealizedInvestmentGainsLosses`
- `us-gaap:RestrictedStockExpense`
