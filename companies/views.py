from django.shortcuts import render, redirect
from django.views.generic import DetailView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login, logout as auth_logout
from django.contrib import messages
from collections import defaultdict
import json
import yfinance as yf
import requests

import os
from companies.models import Company, Financial, StockPrice, Note, EmailVerificationToken, SavedScreen
from companies.utils import send_verification_email, execute_screener_query, generate_screener_sql
from django.db.models import Q
from django.utils import timezone
from django.db.models import Count, Q as DQ

from companies.models import DiscussionThread, DiscussionMessage, ChatSession, ChatMessage, NoteCompany


def home(request):
    return render(request, 'companies/home.html')


def search_api(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)
    results = Company.objects.filter(Q(name__icontains=q) | Q(ticker__icontains=q))[:10]
    return JsonResponse([{'ticker': c.ticker, 'name': c.name} for c in results], safe=False)


def newsfeed_api(request):
    """Fetch latest FCA NSM filings, optionally filtered by type."""
    type_codes_param = request.GET.get("type_codes", "").strip()
    size = min(max(int(request.GET.get("size", 50)), 1), 200)

    selected_codes = [t.strip() for t in type_codes_param.split(",") if t.strip()]

    criteria = [{"name": "latest_flag", "value": "Y"}]
    if selected_codes:
        criteria.append({"name": "type_code", "value": selected_codes})

    payload = {
        "from": 0,
        "size": size,
        "sort": "submitted_date",
        "sortorder": "desc",
        "criteriaObj": {"criteria": criteria},
    }

    try:
        resp = requests.post(
            "https://api.data.fca.org.uk/search",
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "Origin": "https://data.fca.org.uk", "Referer": "https://data.fca.org.uk/"},
            params={"index": "fca-nsm-searchdata"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)

    hits = resp.json().get("hits", {}).get("hits", [])

    items = []
    type_map = {}
    for hit in hits:
        info = hit.get("_source", {})
        rns_type = info.get("type", "")
        rns_code = info.get("type_code", "")
        if rns_code and rns_type:
            type_map[rns_code] = rns_type
        dl = info.get("download_link", "")
        items.append({
            "type": rns_type,
            "type_code": rns_code,
            "headline": info.get("headline") or info.get("title") or "",
            "company": info.get("company") or info.get("company_name") or "",
            "date": info.get("submitted_date") or "",
            "url": f"https://data.fca.org.uk/artefacts/{dl}" if dl else "",
        })

    return JsonResponse({"items": items, "type_map": type_map})


def regulatory_newsfeed(request, ticker):
    """Fetch FCA NSM filings for a company (paged)."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    def clamp_int(raw, default, min_value, max_value):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(min_value, min(value, max_value))

    type_codes_param = request.GET.get("type_codes", "").strip()
    size = clamp_int(request.GET.get("size"), 20, 1, 200)
    offset = clamp_int(request.GET.get("from"), 0, 0, 10000)

    criteria = [{"name": "latest_flag", "value": "Y"}]
    company_name = getattr(company, "name", "") or ""
    if company_name:
        criteria.append({
            "name": "company_lei",
            "value": [company_name, "", "disclose_org", "related_org"],
        })

    selected_codes = [t.strip() for t in type_codes_param.split(",") if t.strip()]
    if selected_codes:
        criteria.append({"name": "type_code", "value": selected_codes})

    # On the initial unfiltered load, fetch a larger batch so we can
    # discover all available filing types for the filter dropdown.
    discover_types = not selected_codes and offset == 0
    fetch_size = 200 if discover_types else size

    payload = {
        "from": offset,
        "size": fetch_size,
        "sort": "submitted_date",
        "sortorder": "desc",
        "criteriaObj": {
            "criteria": criteria,
        },
    }

    url = "https://api.data.fca.org.uk/search"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://data.fca.org.uk",
        "Referer": "https://data.fca.org.uk/",
    }
    params = {"index": "fca-nsm-searchdata"}

    try:
        resp = requests.post(url=url, headers=headers, params=params, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return JsonResponse({"error": "Failed to fetch FCA newsfeed", "detail": str(exc)}, status=502)

    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])

    type_map = {}
    items = []
    for i, hit in enumerate(hits):
        info = hit.get("_source", {})
        rns_type = info.get("type", "") or ""
        rns_code = info.get("type_code", "") or ""
        if rns_code and rns_type:
            type_map[rns_code] = rns_type

        if i < size:
            download_link = info.get("download_link", "") or ""
            items.append({
                "type": rns_type,
                "type_code": rns_code,
                "headline": info.get("title")
                or info.get("headline")
                or info.get("document_title")
                or "",
                "company_name": info.get("company_name") or info.get("name") or "",
                "submitted_date": info.get("submitted_date") or info.get("published_date") or "",
                "download_url": f"https://data.fca.org.uk/artefacts/{download_link}" if download_link else "",
            })

    total_hits = data.get("hits", {}).get("total", {})
    total_count = None
    if isinstance(total_hits, dict):
        total_count = total_hits.get("value")
    elif isinstance(total_hits, int):
        total_count = total_hits

    return JsonResponse({
        "items": items,
        "type_map": type_map,
        "company_filter_applied": bool(company_name),
        "offset": offset,
        "size": size,
        "total": total_count,
    })


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
    "Cash & Short-Term Investments",
    "Accounts Receivable",
    "Inventories",
    "Other Current Assets",
    "Total Current Assets",
    "Property, Plant & Equipment",
    "Goodwill",
    "Other Intangible Assets",
    "Other Assets",
    "Total Assets",
    None,  # spacer
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
    None,  # spacer
    "Liabilities & Equity",
]
# QFS BS metrics that combine multiple DB metrics for display
QFS_BS_COMBINE = {
    "Cash & Short-Term Investments": ["Cash & Equivalents", "Short-Term Investments"],
}
# QFS BS metrics with display name different from DB name
QFS_BS_RENAME = {
    "Property, Plant & Equipment": "Property, Plant, & Equipment (Net)",
}
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
    "Shareholders' Equity",
    "Total Shareholders' Equity",
    "Total Common Equity",
    "Total Common Shareholders' Equity",
    "Liabilities & Equity",
    "Total Liabilities And Equity",
    "Total Liabilities and Shareholders' Equity",
    "Cash From Operations",
    "Cash From Investing",
    "Cash From Financing",
]

# Fiscal data display transformations (display only, not stored)
FISCAL_METRIC_RENAMES = {
    "Total Revenues": "Revenue",
    "Cost of Goods Sold, Total": "Cost of Goods Sold",
    "Amort. of Goodwill & Intang. Assets": "Amortization",
    "Amortization of Goodwill and Intangible Assets": "Amortization",
    "Selling, General & Administrative Expenses": "SG&A",
    "Selling General & Admin Expenses, Total": "SG&A",
    "Other Operating Expenses, Total": "Other Operating Expenses",
    "Net Interest Expenses": "Net Interest Expense",
    "EBT, Incl. Unusual Items": "Profit Before Tax",
    "Weighted Avg. Shares Outstanding": "Basic Avg. Shares Outstanding",
    "Weighted Avg. Shares Outstanding Dil": "Diluted Avg. Shares Outstanding",
    "Net Property Plant And Equipment": "Property, Plant & Equipment",
    "Net Property, Plant & Equipment": "Property, Plant & Equipment",
}

FISCAL_METRICS_DROP = [
    "Total Revenues % Chg.",
    "Total Revenues %Chg",
    "Operating Margin",
    "Interest Expense",
    "Interest Expense, Total",
    "Interest And Invest. Income",
    "Interest And Investment Income",
    "Interest and Investment Income",
    "Gross Profit Margin",
    "Earnings From Continuing Operations",
    "Net Income to Common Excl. Extra Items",
    "Net Income to Common Incl Extra Items",
    "Total Shares Outstanding",
    "EBT, Excl. Unusual Items",
    "Basic EPS",
    "Diluted EPS",
    "EPS",
    "EPS Diluted",
    "Basic Weighted Average Shares Outstanding",
    "Diluted Weighted Average Shares Outstanding",
    "EBITDA",
    "Effective Tax Rate",
    "Gross Property Plant And Equipment",
    "Accumulated Depreciation",
]

# Metrics to combine into other metrics (source -> target)
FISCAL_METRICS_COMBINE = {
    "Provision for Bad Debts": "Other Operating Expenses",
    # Equity investment income into Other Non Operating
    "(Income) Loss on Equity Invest.": "Other Non Operating Income (Expenses)",
    "Income (Loss) On Equity Invest.": "Other Non Operating Income (Expenses)",
    "Income (Loss) on Equity Invest.": "Other Non Operating Income (Expenses)",
}

# Metrics that roll up into "Exceptional Items" (expandable)
EXCEPTIONAL_ITEMS_METRICS = [
    "Restructuring Charges",
    "Merger & Related Restructuring Charges",
    "Total Merger & Related Restructuring Charges",
    "Impairment of Goodwill",
    "Impairment of Oil, Gas & Mineral Properties",
    "Gain (Loss) On Sale Of Assets",
    "Gain (Loss) on Sale of Assets",
    "Gain (Loss) on Sale of Assets, Total",
    "Asset Writedown",
    "Other Unusual Items",
    "Legal Settlements",
    "In Process R&D Expenses",
    "Gain (Loss) On Sale Of Investments",
    "Gain (Loss) on Sale of Investments",
    "Gain (Loss) on Sale of Investments, Total",
    "Gain (Loss) on Sale of Invest. & Securities",
    "Gain (Loss) on Sale of Investment, Total",
]


def preprocess_fiscal_bs(items):
    """
    Pre-process Fiscal BS items: combine cash metrics into
    'Cash & Short-Term Investments'. Uses the Total if available,
    otherwise sums individual components.
    """
    CASH_COMPONENTS = {
        "Cash And Equivalents", "Cash and Cash Equivalents",
        "Short Term Investments", "Short-Term Investments",
    }
    CASH_TOTALS = {
        "Total Cash And Short Term Investments",
        "Total Cash and Cash Equivalents",
    }
    TARGET = "Cash & Short-Term Investments"

    has_total = any(m in CASH_TOTALS for m, _, _ in items)

    if has_total:
        result = []
        for m, d, v in items:
            if m in CASH_TOTALS:
                result.append((TARGET, d, v))
            elif m in CASH_COMPONENTS:
                continue
            else:
                result.append((m, d, v))
        return result

    # No total: sum individual components
    cash_values = defaultdict(float)
    insert_pos = None
    result = []
    for m, d, v in items:
        if m in CASH_COMPONENTS:
            cash_values[d] += float(v) if v else 0
            if insert_pos is None:
                insert_pos = len(result)
        else:
            result.append((m, d, v))
    if cash_values:
        cash_items = [(TARGET, d, v) for d, v in cash_values.items()]
        result = result[:insert_pos] + cash_items + result[insert_pos:]
    return result


def transform_fiscal_items(items):
    """
    Transform Fiscal data metrics for display:
    - Rename metrics
    - Drop unwanted metrics
    - Combine certain metrics
    - Group exceptional items
    - Insert PBT before Exceptional Items, then Exceptional Items, then Profit Before Tax
    Returns (transformed_items, exceptional_breakdown) where:
    - transformed_items: list of (metric, date, value) tuples
    - exceptional_breakdown: dict of {date: [(metric, value), ...]} for exceptional items
    """
    from collections import defaultdict
    from decimal import Decimal

    def to_float(v):
        if v is None:
            return 0.0
        if isinstance(v, Decimal):
            return float(v)
        return float(v) if v else 0.0

    # First pass: collect values to combine, exceptional items, and PBT values
    combine_values = defaultdict(float)  # (target_metric, date) -> sum
    exceptional_by_date = defaultdict(list)  # date -> [(metric, value), ...]
    exceptional_totals = defaultdict(float)  # date -> total
    pbt_values = {}  # date -> Profit Before Tax value

    for metric, date, value in items:
        if metric in FISCAL_METRICS_COMBINE:
            target = FISCAL_METRICS_COMBINE[metric]
            combine_values[(target, date)] += to_float(value)
        elif metric in EXCEPTIONAL_ITEMS_METRICS:
            if value:
                exceptional_by_date[date].append((metric, float(value) if value else 0))
                exceptional_totals[date] += to_float(value)
        elif metric == "EBT, Incl. Unusual Items":
            pbt_values[date] = to_float(value)

    # Second pass: transform items (skip Profit Before Tax, we'll add it later)
    result = []
    seen = set()
    has_exceptional = bool(exceptional_totals)

    for metric, date, value in items:
        # Skip dropped metrics
        if metric in FISCAL_METRICS_DROP:
            continue

        # Skip metrics being combined into others
        if metric in FISCAL_METRICS_COMBINE:
            continue

        # Skip exceptional items (handled separately)
        if metric in EXCEPTIONAL_ITEMS_METRICS:
            continue

        # Skip Profit Before Tax - we'll insert it after Exceptional Items
        if metric == "EBT, Incl. Unusual Items":
            continue

        # Rename metric if needed
        display_metric = FISCAL_METRIC_RENAMES.get(metric, metric)

        # Add combined values if this is a target metric
        key = (display_metric, date)
        if key in combine_values:
            value = to_float(value) + combine_values[key]
            del combine_values[key]

        # Avoid duplicates
        if (display_metric, date) in seen:
            continue
        seen.add((display_metric, date))

        result.append((display_metric, date, value))

    # Build PBT items to insert before Income Tax Expense
    pbt_items = []
    if has_exceptional:
        # PBT before Exceptional Items = Profit Before Tax - Exceptional Items
        for date in pbt_values:
            pbt = pbt_values[date]
            exc = exceptional_totals.get(date, 0)
            pbt_items.append(("PBT before Exceptional Items", date, pbt - exc))

        # Exceptional Items
        for date, total in exceptional_totals.items():
            pbt_items.append(("Exceptional Items", date, total))

        # Profit Before Tax
        for date, pbt in pbt_values.items():
            pbt_items.append(("Profit Before Tax", date, pbt))
    else:
        # No exceptional items - just add Profit Before Tax
        for date, pbt in pbt_values.items():
            pbt_items.append(("Profit Before Tax", date, pbt))

    # Find position to insert (before Income Tax Expense)
    insert_pos = len(result)
    for i, (metric, _, _) in enumerate(result):
        if metric == "Income Tax Expense":
            insert_pos = i
            break

    # Insert PBT items at the right position
    result = result[:insert_pos] + pbt_items + result[insert_pos:]

    return result, dict(exceptional_by_date)

# Fiscal BS metrics that become blank spacer rows
FISCAL_BS_SPACER_METRICS = {"Liabilities", "Equity"}
# Fiscal BS metrics after which to insert a spacer row
FISCAL_BS_SPACER_AFTER = {
    "Total Equity", "Total Shareholders' Equity",
    "Total Common Shareholders' Equity", "Shareholders' Equity",
}


def pivot_fiscal_items(items, exceptional_breakdown=None):
    """
    Pivot Fiscal data items with support for expandable exceptional items.
    """
    if not items:
        return {"dates": [], "rows": []}

    dates = sorted({d for _, d, _ in items}, reverse=True)
    lookup = {(m, d): v for m, d, v in items}

    # Get metrics in order they appear
    metrics = []
    seen = set()
    for m, _, _ in items:
        if m not in seen:
            metrics.append(m)
            seen.add(m)

    rows = []
    equity_spacer_added = False
    for m in metrics:
        # Convert section headers to spacer rows
        if m in FISCAL_BS_SPACER_METRICS:
            rows.append({"spacer": True})
            continue

        values = [lookup.get((m, d)) for d in dates]
        if any(v is not None for v in values):
            row = {
                "metric": m,
                "values": values,
                "sum_metric": m in SUM_METRICS,
                "expandable": False,
                "breakdown": [],
            }
            # Add breakdown for Exceptional Items
            if m == "Exceptional Items" and exceptional_breakdown:
                row["expandable"] = True
                # Get all unique breakdown metrics across all dates
                breakdown_metrics = {}
                for d in dates:
                    if d in exceptional_breakdown:
                        for bm, bv in exceptional_breakdown[d]:
                            if bm not in breakdown_metrics:
                                breakdown_metrics[bm] = {}
                            breakdown_metrics[bm][d] = bv
                # Build breakdown rows
                for bm in breakdown_metrics:
                    brow = {
                        "metric": bm,
                        "values": [breakdown_metrics[bm].get(d) for d in dates],
                    }
                    row["breakdown"].append(brow)
            rows.append(row)

            # Add spacer after total equity (only once)
            if m in FISCAL_BS_SPACER_AFTER and not equity_spacer_added:
                rows.append({"spacer": True})
                equity_spacer_added = True

    dates = [d.strftime("%b %Y") for d in dates]
    return {"dates": dates, "rows": rows}


def pivot_items(items, metrics=None, combine=None, rename=None):
    """
    Pivot financial items into a table format.
    items: [(metric, date, value), ...]
    metrics: list of metrics to show in order, or None to show all available.
             Use None entries for spacer rows.
    combine: dict mapping display_name -> [db_metric, ...] to sum multiple DB metrics
    rename: dict mapping display_name -> db_metric for renamed metrics
    """
    if not items:
        return {"dates": [], "rows": []}

    combine = combine or {}
    rename = rename or {}

    dates = sorted({d for _, d, _ in items}, reverse=True)
    lookup = {(m, d): v for m, d, v in items}

    # If no metrics specified, use all unique metrics from the data
    if metrics is None:
        metrics = []
        seen = set()
        for m, _, _ in items:
            if m not in seen:
                metrics.append(m)
                seen.add(m)

    rows = []
    for m in metrics:
        if m is None:
            rows.append({"spacer": True})
            continue

        if m in combine:
            # Combined metric: sum values from multiple source metrics
            values = []
            for d in dates:
                total = None
                for source in combine[m]:
                    v = lookup.get((source, d))
                    if v is not None:
                        total = (total or 0) + float(v)
                values.append(total)
        elif m in rename:
            # Renamed metric: look up the DB metric name
            values = [lookup.get((rename[m], d)) for d in dates]
        else:
            values = [lookup.get((m, d)) for d in dates]

        if any(v is not None for v in values):
            rows.append({
                "metric": m,
                "values": values,
                "sum_metric": m in SUM_METRICS
            })

    dates = [d.strftime("%b %Y") for d in dates]
    return {"dates": dates, "rows": rows}


def is_qfs_data(items):
    """Check if the financial data is from QuickFS (has 'Revenue' metric)."""
    metrics = {m for m, _, _ in items}
    return "Revenue" in metrics


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

        # Check if this is QFS data (has "Revenue") or Fiscal data
        all_items = buckets["IS"] + buckets["BS"] + buckets["CF"]
        if is_qfs_data(all_items):
            # Use predefined QFS metric order
            ctx["IS_table"] = pivot_items(buckets["IS"], METRICS_IS)
            ctx["BS_table"] = pivot_items(
                buckets["BS"], METRICS_BS,
                combine=QFS_BS_COMBINE, rename=QFS_BS_RENAME,
            )
            ctx["CF_table"] = pivot_items(buckets["CF"], METRICS_CF)
        else:
            # Transform Fiscal data for display (renames, drops, combines, exceptional items)
            is_items, is_exceptional = transform_fiscal_items(buckets["IS"])
            bs_raw = preprocess_fiscal_bs(buckets["BS"])
            bs_items, _ = transform_fiscal_items(bs_raw)
            cf_items, _ = transform_fiscal_items(buckets["CF"])
            ctx["IS_table"] = pivot_fiscal_items(is_items, is_exceptional)
            ctx["BS_table"] = pivot_fiscal_items(bs_items)
            ctx["CF_table"] = pivot_fiscal_items(cf_items)

        # Price data for chart
        prices = StockPrice.objects.filter(company=self.object).order_by('date')
        price_data = [
            {
                "time": p.date.isoformat(),
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
            }
            for p in prices
        ]
        volume_data = [
            {
                "time": p.date.isoformat(),
                "value": p.volume,
                "color": "#26a69a" if p.close >= p.open else "#ef5350"
            }
            for p in prices
        ]
        ctx["price_data_json"] = json.dumps(price_data)
        ctx["volume_data_json"] = json.dumps(volume_data)

        # Notes for logged-in users
        if self.request.user.is_authenticated:
            notes = Note.objects.filter(user=self.request.user, company=self.object)
            ctx["notes"] = notes
            ctx["note_folders"] = sorted({n.folder for n in notes if n.folder})
        else:
            ctx["notes"] = []
            ctx["note_folders"] = []

        return ctx


def _window_start(window):
    now = timezone.now()
    if window == "week":
        return now - timezone.timedelta(days=7)
    if window == "month":
        return now - timezone.timedelta(days=30)
    if window == "year":
        return now - timezone.timedelta(days=365)
    return None


def discussion_threads(request, ticker):
    """List discussion threads for a company."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    sort = request.GET.get("sort", "chrono")
    window = request.GET.get("window", "all")

    qs = DiscussionThread.objects.filter(company=company)
    if sort == "top":
        since = _window_start(window)
        if since:
            qs = qs.annotate(
                message_count=Count("messages", filter=DQ(messages__created_at__gte=since))
            )
        else:
            qs = qs.annotate(message_count=Count("messages"))
        qs = qs.order_by("-message_count", "-created_at")
    else:
        qs = qs.order_by("-created_at")

    threads = []
    for thread in qs:
        threads.append({
            "id": thread.id,
            "title": thread.title,
            "created_at": thread.created_at.strftime("%d/%m/%Y, %I:%M %p"),
            "message_count": getattr(thread, "message_count", thread.messages.count()),
            "latest_message": thread.messages.order_by("-created_at").first().content if thread.messages.exists() else "",
        })

    return JsonResponse({"threads": threads})


def discussion_messages(request, ticker):
    """List all discussion messages for a company."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    messages = DiscussionMessage.objects.filter(thread__company=company).select_related("thread")
    messages = messages.order_by("-created_at")

    items = []
    for msg in messages:
        title = msg.thread.title if msg.is_opening else f"Re: {msg.thread.title}"
        items.append({
            "id": msg.id,
            "title": title,
            "content": msg.content,
            "created_at": msg.created_at.strftime("%d/%m/%Y, %I:%M %p"),
            "thread_id": msg.thread_id,
        })

    return JsonResponse({"messages": items})


def discussion_thread_messages(request, ticker, thread_id):
    """List messages for a single thread."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        thread = DiscussionThread.objects.get(id=thread_id, company=company)
    except DiscussionThread.DoesNotExist:
        return JsonResponse({"error": "Thread not found"}, status=404)

    messages = DiscussionMessage.objects.filter(thread=thread).order_by("-created_at")
    items = []
    for msg in messages:
        title = thread.title if msg.is_opening else f"Re: {thread.title}"
        items.append({
            "id": msg.id,
            "title": title,
            "content": msg.content,
            "created_at": msg.created_at.strftime("%d/%m/%Y, %I:%M %p"),
            "thread_id": thread.id,
        })

    return JsonResponse({
        "thread": {"id": thread.id, "title": thread.title},
        "messages": items,
    })


@login_required
def chat_sessions(request, ticker):
    """List or create chat sessions for a company."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        title = (data.get("title") or "").strip()
        session = ChatSession.objects.create(
            user=request.user,
            company=company,
            title=title,
        )
        return JsonResponse({
            "id": session.id,
            "title": session.title,
            "updated_at": session.updated_at.strftime("%d/%m/%Y, %I:%M %p"),
        })

    sessions = ChatSession.objects.filter(user=request.user, company=company).order_by("-updated_at")
    return JsonResponse({
        "sessions": [
            {
                "id": s.id,
                "title": s.title or "Untitled chat",
                "updated_at": s.updated_at.strftime("%d/%m/%Y, %I:%M %p"),
            }
            for s in sessions
        ]
    })


@login_required
def chat_session_messages(request, ticker, session_id):
    """List messages for a chat session."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        session = ChatSession.objects.get(id=session_id, user=request.user, company=company)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    messages = ChatMessage.objects.filter(session=session).order_by("created_at")
    return JsonResponse({
        "session": {
            "id": session.id,
            "title": session.title or "Untitled chat",
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.strftime("%d/%m/%Y, %I:%M %p"),
            }
            for m in messages
        ],
    })


@login_required
@require_POST
def chat_send_message(request, ticker, session_id):
    """Send a message to a chat session and get assistant reply."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        session = ChatSession.objects.get(id=session_id, user=request.user, company=company)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    try:
        data = json.loads(request.body)
        content = (data.get("content") or "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not content:
        return JsonResponse({"error": "Message is required"}, status=400)

    user_message = ChatMessage.objects.create(
        session=session,
        role="user",
        content=content,
    )

    session.title = session.title or content[:60]
    session.save(update_fields=["title", "updated_at"])

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "Missing OPENAI_API_KEY"}, status=500)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        history = ChatMessage.objects.filter(session=session).order_by("created_at")
        messages = [{"role": m.role, "content": m.content} for m in history]

        context_parts = []
        if company.description:
            context_parts.append(f"Business description:\n{company.description}")
        if company.special_sits:
            context_parts.append(f"Special situations:\n{company.special_sits}")
        if context_parts:
            context_text = "\n\n".join(context_parts)
            messages.insert(0, {
                "role": "system",
                "content": (
                    "Be concise and answer only what the user asked. Avoid follow-up questions or extra context "
                    "unless essential. Use the following company context when answering user questions.\n\n"
                    + context_text
                )
            })

        response = client.responses.create(
            model=model,
            input=messages,
        )
        assistant_text = response.output_text

        # Calculate cost
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        # Pricing per 1M tokens (as of 2024)
        pricing = {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        }
        rates = pricing.get(model, {"input": 0.15, "output": 0.60})
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

    except Exception as exc:
        return JsonResponse({"error": f"OpenAI request failed: {exc}"}, status=502)

    assistant_message = ChatMessage.objects.create(
        session=session,
        role="assistant",
        content=assistant_text,
    )
    session.save(update_fields=["updated_at"])

    return JsonResponse({
        "user_message": {
            "id": user_message.id,
            "role": user_message.role,
            "content": user_message.content,
            "created_at": user_message.created_at.strftime("%d/%m/%Y, %I:%M %p"),
        },
        "assistant_message": {
            "id": assistant_message.id,
            "role": assistant_message.role,
            "content": assistant_message.content,
            "created_at": assistant_message.created_at.strftime("%d/%m/%Y, %I:%M %p"),
        },
        "cost": {"input_tokens": input_tokens, "output_tokens": output_tokens, "usd": round(cost, 6)},
    })


@login_required
def chat_session_rename(request, ticker, session_id):
    """Rename a chat session."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        session = ChatSession.objects.get(id=session_id, user=request.user, company=company)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        title = (data.get("title") or "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not title:
        return JsonResponse({"error": "Title is required"}, status=400)

    session.title = title
    session.save(update_fields=["title"])
    return JsonResponse({"ok": True, "title": session.title})


@login_required
def chat_session_delete(request, ticker, session_id):
    """Delete a chat session."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        session = ChatSession.objects.get(id=session_id, user=request.user, company=company)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Chat session not found"}, status=404)

    if request.method != "DELETE":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    session.delete()
    return JsonResponse({"ok": True})


def intraday_prices(request, ticker, period):
    """Fetch intraday prices from yfinance for 1D/5D views."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    # Replace dots with hyphens for yfinance (e.g., BT.A -> BT-A)
    yf_symbol = ticker.replace('.', '-')
    yf_ticker = yf.Ticker(f"{yf_symbol}.L")

    # Map period to yfinance parameters
    period_config = {
        "1d": {"period": "1d", "interval": "5m"},
        "5d": {"period": "5d", "interval": "15m"},
    }

    if period not in period_config:
        return JsonResponse({"error": "Invalid period"}, status=400)

    config = period_config[period]

    try:
        df = yf_ticker.history(period=config["period"], interval=config["interval"])

        if df.empty:
            return JsonResponse({"price_data": [], "volume_data": []})

        price_data = []
        volume_data = []

        for idx, row in df.iterrows():
            # Convert to Unix timestamp for Lightweight Charts
            timestamp = int(idx.timestamp())

            price_data.append({
                "time": timestamp,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            })

            volume_data.append({
                "time": timestamp,
                "value": int(row["Volume"]),
                "color": "#26a69a" if row["Close"] >= row["Open"] else "#ef5350"
            })

        return JsonResponse({"price_data": price_data, "volume_data": volume_data})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def add_note(request, ticker):
    """Add a note for a company."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        data = json.loads(request.body)
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()
        folder = data.get("folder", "").strip()

        if not content:
            return JsonResponse({"error": "Content is required"}, status=400)

        note = Note.objects.create(
            user=request.user,
            company=company,
            title=title,
            content=content,
            folder=folder
        )
        NoteCompany.objects.get_or_create(user=request.user, company=company)

        return JsonResponse({
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "folder": note.folder,
            "created_at": note.created_at.strftime("%d/%m/%Y, %I:%M %p")
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def notes_home(request):
    note_company_ids = set(NoteCompany.objects.filter(user=request.user).values_list("company_id", flat=True))
    note_company_ids.update(
        Note.objects.filter(user=request.user).values_list("company_id", flat=True)
    )
    companies = Company.objects.filter(id__in=note_company_ids).annotate(
        note_count=Count("notes", filter=DQ(notes__user=request.user))
    ).order_by("name")
    return render(request, "companies/notes_home.html", {
        "companies": companies,
    })


@login_required
def notes_company(request, ticker):
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return redirect("notes_home")

    notes = Note.objects.filter(user=request.user, company=company)
    note_folders = sorted({n.folder for n in notes if n.folder})
    return render(request, "companies/notes_company.html", {
        "company": company,
        "notes": notes,
        "note_folders": note_folders,
    })


@login_required
@require_POST
def notes_add_company(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ticker = (data.get("ticker") or "").strip()
    if not ticker:
        return JsonResponse({"error": "Ticker is required"}, status=400)

    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    NoteCompany.objects.get_or_create(user=request.user, company=company)
    return JsonResponse({
        "ticker": company.ticker,
        "name": company.name,
    })


@login_required
@require_POST
def add_thread(request, ticker):
    """Create a new discussion thread with opening message."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        data = json.loads(request.body)
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)
        if not content:
            return JsonResponse({"error": "Message is required"}, status=400)

        thread = DiscussionThread.objects.create(
            company=company,
            user=request.user,
            title=title
        )
        message = DiscussionMessage.objects.create(
            thread=thread,
            user=request.user,
            content=content,
            is_opening=True
        )

        return JsonResponse({
            "thread_id": thread.id,
            "message_id": message.id,
        })
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def add_message(request, ticker, thread_id):
    """Add a reply to a discussion thread."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    try:
        thread = DiscussionThread.objects.get(id=thread_id, company=company)
    except DiscussionThread.DoesNotExist:
        return JsonResponse({"error": "Thread not found"}, status=404)

    try:
        data = json.loads(request.body)
        content = data.get("content", "").strip()
        if not content:
            return JsonResponse({"error": "Message is required"}, status=400)

        message = DiscussionMessage.objects.create(
            thread=thread,
            user=request.user,
            content=content,
            is_opening=False
        )

        return JsonResponse({
            "message_id": message.id,
        })
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def logout_view(request):
    """Log out the user and redirect to home."""
    auth_logout(request)
    return redirect('/')


def signup(request):
    """Handle user registration with email verification."""
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []

        existing = User.objects.filter(email=email).first()
        if existing:
            if existing.is_active:
                errors.append("An account with this email already exists.")
            else:
                existing.delete()

        if not email:
            errors.append("Email is required.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        elif password != password_confirm:
            errors.append("Passwords do not match.")

        if errors:
            return render(request, 'registration/signup.html', {'errors': errors, 'email': email})

        user = User.objects.create_user(username=email, email=email, password=password, is_active=False)
        token = EmailVerificationToken.objects.create(user=user)

        if not send_verification_email(email, token.code):
            user.delete()
            return render(request, 'registration/signup.html', {'errors': ["Failed to send email."], 'email': email})

        request.session['verify_email'] = email
        return redirect('verify_email')

    return render(request, 'registration/signup.html')


def verify_email(request):
    """Verify email with 6-digit code."""
    email = request.session.get('verify_email')
    if not email:
        return redirect('signup')

    error = None
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        try:
            verification = EmailVerificationToken.objects.select_related('user').get(user__email=email)
            if verification.is_expired():
                verification.user.delete()
                error = "Code expired. Please sign up again."
            elif verification.code != code:
                error = "Invalid code."
            else:
                user = verification.user
                user.is_active = True
                user.save()
                verification.delete()
                del request.session['verify_email']
                login(request, user)
                return redirect('/')
        except EmailVerificationToken.DoesNotExist:
            error = "No pending verification. Please sign up again."

    return render(request, 'registration/verify_code.html', {'email': email, 'error': error})


def screener_home(request):
    """Render the screener page with filter options."""
    exchanges = list(Company.objects.exclude(exchange="").values_list("exchange", flat=True).distinct().order_by("exchange"))
    countries = list(Company.objects.exclude(country="").values_list("country", flat=True).distinct().order_by("country"))
    sectors = list(Company.objects.exclude(sector="").values_list("sector", flat=True).distinct().order_by("sector"))

    saved_screens = []
    if request.user.is_authenticated:
        saved_screens = list(SavedScreen.objects.filter(user=request.user).values("id", "name", "updated_at"))

    return render(request, 'companies/screener.html', {
        "exchanges": exchanges,
        "countries": countries,
        "sectors": sectors,
        "saved_screens": saved_screens,
    })


def _apply_basic_filters(results, basic_filters):
    """Apply basic filters to a list of result dicts."""
    if not basic_filters:
        return results

    filtered = results

    countries = basic_filters.get("countries", [])
    if countries:
        filtered = [r for r in filtered if r.get("country") in countries]

    exchanges = basic_filters.get("exchanges", [])
    if exchanges:
        filtered = [r for r in filtered if r.get("exchange") in exchanges]

    sectors = basic_filters.get("sectors", [])
    if sectors:
        filtered = [r for r in filtered if r.get("sector") in sectors]

    market_cap_min = basic_filters.get("market_cap_min")
    if market_cap_min:
        try:
            min_val = int(market_cap_min)
            filtered = [r for r in filtered if r.get("market_cap") and r.get("market_cap") >= min_val]
        except (ValueError, TypeError):
            pass

    market_cap_max = basic_filters.get("market_cap_max")
    if market_cap_max:
        try:
            max_val = int(market_cap_max)
            filtered = [r for r in filtered if r.get("market_cap") and r.get("market_cap") <= max_val]
        except (ValueError, TypeError):
            pass

    return filtered


@require_POST
def screener_run(request):
    """Execute a screener query with basic filters and/or natural language."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    basic_filters = data.get("basic_filters", {})
    nl_query = (data.get("nl_query") or "").strip()

    # If there's a natural language query, use OpenAI to generate SQL
    if nl_query:
        sql, error = generate_screener_sql(nl_query)
        if error:
            return JsonResponse({"error": error}, status=400)

        results, exec_error = execute_screener_query(sql)
        if exec_error:
            return JsonResponse({"error": exec_error, "generated_sql": sql}, status=400)

        # Enrich results with company data for filtering
        company_ids = [r.get("id") for r in results if r.get("id")]
        companies_by_id = {
            c.id: c for c in Company.objects.filter(id__in=company_ids)
        }
        for r in results:
            company = companies_by_id.get(r.get("id"))
            if company:
                r.setdefault("country", company.country)
                r.setdefault("exchange", company.exchange)
                r.setdefault("sector", company.sector)
                r.setdefault("market_cap", company.market_cap)

        # Apply basic filters to NL query results
        results = _apply_basic_filters(results, basic_filters)

        return JsonResponse({
            "results": results,
            "generated_sql": sql,
            "count": len(results),
        })

    # Otherwise, use basic filters with Django ORM
    qs = Company.objects.all()

    countries = basic_filters.get("countries", [])
    if countries:
        qs = qs.filter(country__in=countries)

    exchanges = basic_filters.get("exchanges", [])
    if exchanges:
        qs = qs.filter(exchange__in=exchanges)

    sectors = basic_filters.get("sectors", [])
    if sectors:
        qs = qs.filter(sector__in=sectors)

    market_cap_min = basic_filters.get("market_cap_min")
    if market_cap_min:
        try:
            qs = qs.filter(market_cap__gte=int(market_cap_min))
        except (ValueError, TypeError):
            pass

    market_cap_max = basic_filters.get("market_cap_max")
    if market_cap_max:
        try:
            qs = qs.filter(market_cap__lte=int(market_cap_max))
        except (ValueError, TypeError):
            pass

    qs = qs.order_by("ticker")[:100]

    results = [
        {
            "id": c.id,
            "ticker": c.ticker,
            "name": c.name,
            "exchange": c.exchange,
            "sector": c.sector,
            "country": c.country,
            "market_cap": c.market_cap,
        }
        for c in qs
    ]

    return JsonResponse({
        "results": results,
        "generated_sql": "",
        "count": len(results),
    })


@login_required
@require_POST
def screener_save(request):
    """Save a screener configuration."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Name is required"}, status=400)

    basic_filters = data.get("basic_filters", {})
    nl_query = (data.get("nl_query") or "").strip()
    generated_sql = (data.get("generated_sql") or "").strip()

    screen = SavedScreen.objects.create(
        user=request.user,
        name=name,
        basic_filters=basic_filters,
        nl_query=nl_query,
        generated_sql=generated_sql,
    )

    return JsonResponse({
        "id": screen.id,
        "name": screen.name,
        "created_at": screen.created_at.strftime("%d/%m/%Y, %I:%M %p"),
    })


@login_required
def screener_saved_list(request):
    """List saved screens for the current user."""
    screens = SavedScreen.objects.filter(user=request.user)
    return JsonResponse({
        "screens": [
            {
                "id": s.id,
                "name": s.name,
                "basic_filters": s.basic_filters,
                "nl_query": s.nl_query,
                "generated_sql": s.generated_sql,
                "updated_at": s.updated_at.strftime("%d/%m/%Y, %I:%M %p"),
            }
            for s in screens
        ]
    })


@login_required
@require_POST
def screener_saved_delete(request, screen_id):
    """Delete a saved screen."""
    try:
        screen = SavedScreen.objects.get(id=screen_id, user=request.user)
        screen.delete()
        return JsonResponse({"success": True})
    except SavedScreen.DoesNotExist:
        return JsonResponse({"error": "Screen not found"}, status=404)

