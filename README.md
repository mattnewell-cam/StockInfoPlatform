# StockInfoPlatform

Django-based platform for collecting company metadata + financial statements and (optionally) storing them in a database.

This repo currently focuses on **pulling annual fiscal statements from fiscal.ai** for a target universe (e.g. S\&P 500) and caching results to JSON, then later importing/saving to the DB.

---

## Quick start

### 1) Create / activate venv

This repo already contains a Windows venv at `.venv/`.

- **PowerShell**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **cmd.exe**
  ```bat
  .\.venv\Scripts\activate.bat
  ```

### 2) Install deps

```bash
pip install -r requirements.txt
```

### 3) Run Django (optional)

```bash
python manage.py migrate
python manage.py runserver
```

---

## Data pipeline (fiscal.ai → cache → DB)

### Overview

1. Build a ticker universe (CSV)
2. Run the fiscal.ai scraper to pull statements
3. Results are written incrementally to `cached_financials_2.json`
4. Failures are appended to `financials_failed.csv`
5. After the cache is correct, run the DB save/import step (TBD / project-specific)

### Cached output

- `cached_financials_2.json`
  - Keyed by ticker symbol (e.g. `ABNB`)
  - Each ticker holds statement tables:
    - `IS` = Income Statement
    - `BS` = Balance Sheet
    - `CF` = Cash Flow

A ticker is considered “DONE” when **IS + BS + CF** are present and non-empty.

### Failure log

- `financials_failed.csv`
  - **Newer rows**: `ticker, attempted_exchange`
  - Note: older runs may have single-column rows (`ticker`) only.

---

## Fiscal pull script

Primary script:
- `scripts/pull_financials_fiscal.py`

Key features:
- **Magic-link login flow** (supports injecting a magic link via CLI)
- **Parallel workers** (`--workers N`)
- Per-worker lightweight auth gate (`/dashboard`) before processing
- Robust (best-effort) headless interaction around the Mantine slider
- Real-time progress logging:
  - per-statement: `[{TICKER}] statement IS/BS/CF captured rows=...`
  - per-ticker completion: `[worker] FULL_OK ticker=... IS=.. BS=.. CF=.. TRIO=Y/N STREAK=n`

### Exchange mapping (important)

fiscal.ai expects certain exchange prefixes. In particular:
- `NASDAQ` → `NasdaqGS`

This mapping is applied automatically when building fiscal.ai tickers.

### Typical command (S\&P 500 remaining)

```bash
./.venv/Scripts/python.exe -u scripts/pull_financials_fiscal.py \
  --headless \
  --use-csv --tickers-csv sp500_remaining_fiscal.csv \
  --workers 4 \
  --magic-link "<PASTE_LINK>" \
  --out-json cached_financials_2.json \
  --failed-csv financials_failed.csv
```

Notes:
- `--magic-link` is time-sensitive; generate a fresh one if workers can’t authenticate.
- Use `--no-slider` if you want to skip year-range expansion entirely.

---

## Ticker universe files

Common CSVs in this repo:
- `sp500_tickers.csv` / `sp500_tickers_with_header.csv`
- `sp500_tickers_fiscal_exchange.csv` (ticker + exchange column)
- `sp500_remaining_fiscal.csv` (subset still needing work)

The scraper will use the **2nd column as exchange** (if present) and falls back to `LSE` when absent.

---

## DB import / save

There are multiple DB-related scripts/files present (e.g. `import_to_postgres.py`, `DB_CUTOVER.md`).

The intended workflow after pulls complete is:
- verify `cached_financials_2.json`
- then run the project’s DB save/import step (for example `save_cached_financials`, if/when enabled) to persist into the database.

---

## Troubleshooting

### Many US tickers “not found”

Most commonly an exchange-prefix mismatch.
Example fix applied in this repo:
- `NASDAQ` must be `NasdaqGS` for fiscal.ai

### Headless slider issues

You may see slider logs like:
- `element click intercepted` (header overlay)
- `move target out of bounds`

The scraper attempts multiple fallbacks and continues; slider max-year expansion is *nice-to-have* and not required for all tickers.

---

## Notes / docs

- `DB_CUTOVER.md` – DB migration/cutover notes
- `AGENTS.md` / `claude.md` – agent/dev notes
