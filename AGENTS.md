# AGENTS.md

## Project Overview

TrackStack is a Django web app for small-cap investors to search companies and view financials, pricing charts, AI summaries, discussion threads, AI chat, and personal notes.

**Status:** MVP in progress. Data ingestion, auth, company detail views, discussion, notes hub, and AI chat are working; AI summaries are cached and loadable.

## Tech Stack

- Python 3.12
- Django 6.0
- SQLite (db.sqlite3)
- yfinance (company metadata + pricing)
- Selenium (Fiscal scraping)
- OpenAI API (summaries script + in-app chat)
- python-dotenv (loads .env)
- Requests (Brevo email API)
- Tailwind CDN, marked, lightweight-charts (frontend)

## Project Structure

```
config/                 # Django project settings
companies/              # Main Django app
  management/commands/
    add_companies_by_csv.py
    save_cached_financials.py
    save_cached_summaries.py
    update_prices.py
  templates/
    companies/home.html
    companies/company_detail.html
    companies/statement_table.html
    companies/notes_home.html
    companies/notes_company.html
    registration/*.html
scripts/                # Standalone scripts (not Django)
  pull_financials_fiscal.py     # Fiscal scrape -> cached_financials_uk.json
  generate_AI_summaries.py # OpenAI -> cached_summaries.json
```

## How to Run

```bash
python manage.py migrate
python manage.py runserver

python manage.py add_companies_by_csv
python manage.py save_cached_financials
python manage.py save_cached_summaries --ticker TICKER --overwrite
python manage.py update_prices --ticker TICKER --full --years 10
```

## Data Pipeline

1. `tickers.csv` -> `add_companies_by_csv` (yfinance metadata)
2. `scripts/pull_financials_fiscal.py` -> `cached_financials_uk.json`
3. `save_cached_financials` -> Financial rows in SQLite
4. `scripts/generate_AI_summaries.py` -> `cached_summaries.json`
5. `save_cached_summaries` -> Company `description`, `special_sits`, `writeups`
6. `update_prices` -> StockPrice history; intraday 1D/5D uses yfinance in views

## Key Features

- Home search with typeahead (`/api/search`)
- Company detail with price charts, collapsible financial statements, AI chat, and notes
- Discussion threads and messages (threads + all-messages views)
- Regulatory newsfeed (FCA NSM) with filtering + pagination
- Notes hub at `/notes/` with company grid and foldered notes per company
- Markdown rendering for descriptions and special situations
- Email verification signup (Brevo)

## Environment

- `.env` loaded via python-dotenv
- `EMAIL_API_KEY` required for verification emails
- `OPENAI_API_KEY` required for in-app chat (optionally `OPENAI_MODEL`)
- OpenAI key required for `scripts/generate_AI_summaries.py` (currently hardcoded)

## Files to Ignore

Do not modify these (personal/dev use only):
- `ToDo.txt`
- `prompt_versions.txt`
- `test.py`
- `tickers.csv` (dev data)
- `cached_financials.json` (dev data)
- `cached_summaries.json` (dev data)
- `db.sqlite3` (local dev DB)

## Notes

- Fiscal scraping is Selenium-based and can be slow; use cached imports for most workflows.
- AI summary generation costs money (OpenAI API) — minimize unnecessary calls.
