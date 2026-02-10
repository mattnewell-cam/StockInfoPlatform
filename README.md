# StockInfoPlatform

A Django web app for building and browsing a lightweight “tearsheet” on public companies: profiles, prices, financial statements, notes, screening, alerts/notifications, and lightweight discussion + chat tied to a company.

This repo includes both the **web application** and a set of **data/AI scripts** that help populate/enrich the database.

---

## What’s in here (high level)

### Web app (Django)

Core features implemented in the `companies` app:

- **Company pages**: search + detail pages for each company
- **Financial statements storage**: normalized `Financial` rows (IS/BS/CF metrics by period end date)
- **Price history**: daily OHLCV stored in `StockPrice` (data source: `yfinance`)
- **Notes**: per-user notes on a company + a “notes home”
- **Screener**:
  - UI at `/screener/`
  - Can run saved screens
  - Generates SQL from natural language using **OpenAI** (guard-railed + validated)
- **Follow + alerts + notifications**:
  - Follow/unfollow a company
  - Alert preferences per company
  - In-app notifications API
- **Company discussion threads**: threads + messages per company
- **Company chat**: chat sessions + messages per company (stored in DB)

Anti-crawler controls:
- `robots.txt` is served by the app
- Middleware blocks known AI crawler user agents with a 403 unless a `bot_key` is provided

### Data + AI scripts

Scripts in `/scripts` support populating/enriching the DB and caches:

- `scripts/pull_financials_fiscal.py` — scrape statements from fiscal.ai into a JSON cache (and optionally later save to DB)
- `scripts/generate_AI_summaries.py` — uses OpenAI + web search to generate:
  - plain-English company description
  - “special situations” summary (material items only)
  - links to third-party writeups
- `scripts/compare_gpt5_costs.py` — model cost comparison utility

---

## Project layout

- `config/` — Django project config (settings/urls/wsgi/asgi)
- `companies/` — main Django app (models, views, templates)
- `scripts/` — standalone scripts (scraping / AI enrichment)
- `db.sqlite3` — local SQLite database (default)
- `cached_financials_2.json` — large JSON cache used by fiscal pull workflows

Templates:
- `companies/templates/companies/` — company detail, screener, notes, statement table
- `companies/templates/registration/` — login/signup/email verification

---

## Data model (key tables)

Main entities in `companies/models.py`:

- `Company`
  - identity + metadata (exchange, ticker, sector/industry, market cap, etc.)
  - stores freeform research fields (description/special_sits/writeups/history)
- `Financial`
  - normalized metric values per period end date
  - `statement` in {`IS`,`BS`,`CF`}
  - unique per (company, period_end_date, statement, metric)
- `StockPrice`
  - daily OHLCV per company
- `Note` + `NoteCompany`
  - per-user research notes
- `Follow`, `AlertPreference`, `Notification`
  - following companies + alert preferences + in-app notifications
- `DiscussionThread` + `DiscussionMessage`
  - per-company discussion threads
- `ChatSession` + `ChatMessage`
  - per-company chat history
- `Filing`
  - stores filing metadata + raw text (if used)
- `SavedScreen`
  - stores saved screen definitions + generated SQL

---

## Running locally

### 1) Virtualenv

This repo already contains a Windows venv at `.venv/`.

- PowerShell
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- cmd.exe
  ```bat
  .\.venv\Scripts\activate.bat
  ```

### 2) Install deps

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Environment variables are loaded from `.env` via `python-dotenv`.

Common env vars:

- `DEBUG` — `True`/`False`
- `SECRET_KEY` — Django secret
- `DATABASE_URL` — if set, `dj-database-url` is used (e.g. Postgres on Render)
- `OPENAI_API_KEY` — required for screener NL→SQL + AI summary generation
- `CSRF_TRUSTED_ORIGINS` — comma-separated list of trusted origins (for hosted deployments)

### 4) Migrate + run

```bash
python manage.py migrate
python manage.py runserver
```

---

## Deployment notes

- Uses `gunicorn` and `whitenoise` for static files.
- `ALLOWED_HOSTS` includes `tearsheet.one` and the Render hostname.
- DB defaults to SQLite, but if `DATABASE_URL` is present it will use that connection.

See also: `DB_CUTOVER.md`.

---

## Screener (NL → SQL)

The screener can generate SQL from natural language queries using OpenAI.

Safety measures:
- SQL must start with `SELECT` or `WITH`
- blocks destructive keywords and multi-statement patterns
- restricts table access to a small allowlist (`companies_company`, `companies_financial`, `companies_stockprice`) plus CTE names
- forces a reasonable `LIMIT`

Code:
- `companies/utils.py`: `generate_screener_sql()`, `SQLValidator`, `execute_screener_query()`
- `companies/views.py`: screener endpoints + UI

---

## Prices via yfinance

- `yfinance` is used to fetch market data.
- `companies/utils.py` contains a `yfinance_symbol()` helper with exchange suffix mapping (e.g. LSE/AIM → `.L`).

---

## Fiscal.ai scraping (optional / one component)

The fiscal.ai pull is **one ingestion path** for statements.

- Script: `scripts/pull_financials_fiscal.py`
- Output cache: `cached_financials_2.json`
- Failure log: `financials_failed.csv`

Exchange prefix mapping matters for fiscal.ai:
- we map `NASDAQ` → `NasdaqGS`

Typical command:

```bash
./.venv/Scripts/python.exe -u scripts/pull_financials_fiscal.py \
  --headless \
  --use-csv --tickers-csv sp500_remaining_fiscal.csv \
  --workers 4 \
  --magic-link "<PASTE_LINK>" \
  --out-json cached_financials_2.json \
  --failed-csv financials_failed.csv
```

---

## AI enrichment (summaries)

`scripts/generate_AI_summaries.py` can generate and/or update research fields (description, special situations, writeups) using OpenAI + web search.

Requires:
- `OPENAI_API_KEY`

---

## API endpoints (selected)

Not exhaustive, but useful entry points:

- `/api/search/?q=...` — company search
- `/api/newsfeed/` — newsfeed API
- `/screener/` — screener UI
- `/api/screener/run/` — run screener query
- `/notes/` — notes UI
- `/companies/<ticker>/...` — company endpoints (alerts, follow/unfollow, prices, discussion, chat)

See routing:
- `config/urls.py`
- `companies/urls.py`

---

## Operational notes

### Blocking AI crawlers

`companies/middleware.py` blocks known AI/LLM crawler user agents with 403.

Bypass (if you really need it) requires sending a `bot_key` query param or `X-Bot-Key` header matching the expected value.

---

## Related docs

- `DB_CUTOVER.md` — DB cutover notes
- `ToDo.txt` — scratch TODO list
- `AGENTS.md` / `claude.md` — internal dev/agent notes
