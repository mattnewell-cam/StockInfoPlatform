from django.shortcuts import render, redirect
from django.views.generic import DetailView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib import messages
from collections import defaultdict
import json
import yfinance as yf
import requests

from companies.models import Company, Financial, StockPrice, Note, EmailVerificationToken
from companies.utils import send_verification_email
from django.db.models import Q


def home(request):
    return render(request, 'companies/home.html')


def search_api(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)
    results = Company.objects.filter(Q(name__icontains=q) | Q(ticker__icontains=q))[:10]
    return JsonResponse([{'ticker': c.ticker, 'name': c.name} for c in results], safe=False)


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

    types_param = request.GET.get("types", "").strip()
    size = clamp_int(request.GET.get("size"), 20, 1, 200)
    offset = clamp_int(request.GET.get("from"), 0, 0, 10000)

    criteria = [{"name": "latest_flag", "value": "Y"}]
    company_name = getattr(company, "name", "") or ""
    if company_name:
        criteria.append({
            "name": "company_lei",
            "value": [company_name, "", "disclose_org", "related_org"],
        })

    payload = {
        "from": offset,
        "size": size,
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

    selected_types = [t.strip() for t in types_param.split(",") if t.strip()]
    selected_types_lower = {t.lower() for t in selected_types}

    items = []
    available_types = set()
    for hit in hits:
        info = hit.get("_source", {})
        rns_type = info.get("type", "") or ""
        if rns_type:
            available_types.add(rns_type)
        if selected_types_lower:
            if not rns_type or rns_type.lower() not in selected_types_lower:
                continue

        download_link = info.get("download_link", "") or ""
        items.append({
            "type": rns_type,
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
        "types": sorted(available_types),
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
        else:
            ctx["notes"] = []

        return ctx


def intraday_prices(request, ticker, period):
    """Fetch intraday prices from yfinance for 1D/5D views."""
    try:
        company = Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return JsonResponse({"error": "Company not found"}, status=404)

    yf_ticker = yf.Ticker(f"{ticker}.L")

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

        if not content:
            return JsonResponse({"error": "Content is required"}, status=400)

        note = Note.objects.create(
            user=request.user,
            company=company,
            title=title,
            content=content
        )

        return JsonResponse({
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "created_at": note.created_at.strftime("%d/%m/%Y, %I:%M %p")
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


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

