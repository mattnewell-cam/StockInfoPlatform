from django.shortcuts import render
from django.views.generic import DetailView
from collections import defaultdict

from companies.models import Company, Financial


METRICS_IS = [
    "Revenue",
    "Cost of Goods Sold",
    "Gross Profit",
    "Sales, General, & Administrative",
    "Other Operating Expense",
    "Total Operating Expenses",
    "Operating Profit",
    "Net Interest Income",
    "Other Non-Operating Income",
    "Pre-Tax Income",
    "Income Tax",
    "Other Non-recurring",
    "Net Income",
    # "EPS (Basic)",
    # "EPS (Diluted)",
    "Shares (Basic)",
    "Shares (Diluted)",
]
METRICS_BS = [
    "Cash & Equivalents",
    "Accounts Receivable",
    "Inventories",
    "Other Current Assets",
    "Total Current Assets",
    "Property, Plant, & Equipment (Net)",
    "Goodwill",
    "Other Intangible Assets",
    "Other Assets",
    "Total Assets",
    "Accounts Payable",
    "Tax Payable",
    "Short-Term Debt",
    "Current Portion of Capital Leases",
    "Other Current Liabilities",
    "Total Current Liabilities",
    "Long-Term Debt",
    "Capital Leases",
    "Pension Liabilities",
    "Other Liabilities",
    "Total Liabilities",
    "Retained Earnings",
    "Paid-in Capital",
    "Common Stock",
    "Other",
    "Shareholders' Equity",
    "Liabilities & Equity",
]
METRICS_CF = [
    "Net Income",
    "Depreciation & Amortization",
    "Change in Working Capital",
    "Change in Deferred Tax",
    "Stock-Based Compensation",
    "Other",  # (operating)
    "Cash From Operations",
    "Property, Plant, & Equipment",
    "Acquisitions",
    "Intangibles",
    "Other",  # (investing)
    "Cash From Investing",
    "Net Issuance of Common Stock",
    "Net Issuance of Debt",
    "Other",  # (financing)
    "Cash From Financing",
    "Free Cash Flow",
]

SUM_METRICS = [
    "Gross Profit",
    "Operating Profit",
    "Pre-Tax Income",
    "Net Income",
    "Total Current Assets",
    "Total Assets",
    "Total Current Liabilities",
    "Total Liabilities",
    "Liabilities & Equity",
    "Cash From Operations",
    "Cash From Investing",
    "Cash From Financing",
]

def pivot_items(items, metrics):
    # items: [(metric, date, value), ...]
    dates = sorted({d for _, d, _ in items}, reverse=True)
    lookup = {(m, d): v for m, d, v in items}
    rows = []
    for m in metrics:
        rows.append({
            "metric": m,
            "values": [lookup.get((m, d)) for d in dates],
            "sum_metric": m in SUM_METRICS
        })
    dates = [d.strftime("%b %Y") for d in dates]

    print(dates)
    return {"dates": dates, "rows": rows}


class CompanyDetailView(DetailView):
    model = Company
    template_name = "companies/company_detail.html"
    context_object_name = "company"
    slug_field = "ticker"        # model field to query
    slug_url_kwarg = "ticker"    # URL kwarg name

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        items = list(
            Financial.objects.filter(company=self.object).values_list("statement", "metric", "period_end_date", "value")
        )

        buckets = defaultdict(list)
        for st, m, d, v in items:
            buckets[st].append((m, d, v))

        ctx["IS_table"] = pivot_items(buckets["IS"], METRICS_IS)
        ctx["BS_table"] = pivot_items(buckets["BS"], METRICS_BS)
        ctx["CF_table"] = pivot_items(buckets["CF"], METRICS_CF)
        return ctx

