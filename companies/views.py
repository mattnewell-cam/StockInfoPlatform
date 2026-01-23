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
from companies.models import Company, Financial, StockPrice, Note, EmailVerificationToken
from companies.utils import send_verification_email
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
    types_param = request.GET.get("types", "").strip()
    size = min(max(int(request.GET.get("size", 50)), 1), 200)

    payload = {
        "from": 0,
        "size": size,
        "sort": "submitted_date",
        "sortorder": "desc",
        "criteriaObj": {"criteria": [{"name": "latest_flag", "value": "Y"}]},
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
    selected = {t.strip().lower() for t in types_param.split(",") if t.strip()}

    items, types = [], set()
    for hit in hits:
        info = hit.get("_source", {})
        rns_type = info.get("type", "")
        if rns_type:
            types.add(rns_type)
        if selected and rns_type.lower() not in selected:
            continue
        dl = info.get("download_link", "")
        items.append({
            "type": rns_type,
            "headline": info.get("headline") or info.get("title") or "",
            "company": info.get("company") or info.get("company_name") or "",
            "date": info.get("submitted_date") or "",
            "url": f"https://data.fca.org.uk/artefacts/{dl}" if dl else "",
        })

    return JsonResponse({"items": items, "types": sorted(types)})


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

