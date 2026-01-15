# CLAUDE.md

## Project Overview

Django web application for small-cap investors to quickly get up to speed on companies. Provides financial data, AI-generated analysis, and document access in one place.

**Status:** Early development. Core data ingestion working, basic frontend exists, AI summaries partially implemented.

## Tech Stack

- Python 3.12
- Django 6.0
- SQLite (db.sqlite3)
- Selenium (for scraping QuickFS)
- OpenAI API (for AI summaries)
- Pandas (data processing)
- BeautifulSoup (parsing)

## Project Structure

```
config/             # Django project settings
companies/          # Main Django app
  management/commands/   # Django management commands
    add_companies.py     # Load companies from tickers.csv
    save_cached_financials.py  # Save cached data to DB
  templates/             # Django templates
    company_detail.html  # Main company page
    statement_table.html # Financial table partial
scripts/            # Standalone scripts (not Django)
  pull_financials.py     # Scrapes QuickFS → cached_financials.js
  generate_AI_summaries.py  # Generates summaries via OpenAI
```

## How to Run

```bash
# Dev server
python manage.py runserver

# Load companies from CSV
python manage.py add_companies

# Save cached financials to DB
python manage.py save_cached_financials
```

## Data Pipeline

1. `tickers.csv` — source list of company tickers
2. `scripts/pull_financials.py` — scrapes QuickFS, outputs to `cached_financials.js`
3. `manage.py save_cached_financials` — loads cached data into SQLite
4. `scripts/generate_AI_summaries.py` — generates summaries (not yet wired to DB)

## Key Conventions

- Management commands for anything that touches the database
- Standalone scripts in `scripts/` for external API calls and scraping
- Templates use Django template language
- No tests yet — use Django's standard testing (pytest-django or unittest)

## Files to Ignore

Do not modify these (personal/dev use only):
- `ToDo.txt`
- `prompt_versions`
- `test.py`
- `tickers.csv` (dev data)
- `cached_financials.js` (dev data)

## Notes

- AI summary generation costs money (OpenAI API) — minimize unnecessary calls
- Financial scraping is slow (minutes for small sets, hours at scale)
- Frontend is minimal — `company_detail.html` will eventually hold all company info
