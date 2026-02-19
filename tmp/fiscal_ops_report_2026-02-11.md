# Fiscal Pull Optimization/Ops Report (2026-02-11)

## Scope completed
- Updated path target: `/mnt/c/Users/matth/PycharmProjects/StockInfoPlatform`.
- Implemented performance/reliability/operations hardening in `scripts/pull_financials_fiscal.py`.
- Added structured JSONL analysis and watchdog tooling.
- Added benchmark input set (20 mixed S&P tickers) and validation checks.
- Created dedicated branch and committed only scope files.

## Files changed
- `scripts/pull_financials_fiscal.py`
- `scripts/analyze_fiscal_timings.py` (new)
- `scripts/fiscal_watchdog.py` (new)
- `scripts/compare_fiscal_benchmarks.py` (new)
- `tmp/benchmark_20_mixed.csv` (new, 20 mixed NYSE/NASDAQ tickers)

## Key improvements in `pull_financials_fiscal.py`
1. **Structured telemetry JSONL**
   - `--timings-jsonl` logs per-ticker timing + status + reason.
   - `--events-jsonl` logs failures, heartbeats, run completion.
2. **Resume-safe checkpoints**
   - `--checkpoint-json` tracks:
     - `completed` (with timing/rows/exchange)
     - `failed` (reason + attempts)
     - `in_flight` (per worker ticker + start time)
   - Resume skips completed automatically; `--retry-failed` re-attempts failed list.
3. **Heartbeat progress logging**
   - `--heartbeat-seconds` emits processed/total/rate/ETA to stdout + JSONL.
4. **Required table validation (hard fail if missing)**
   - Must include IS + BS + CF
   - BS must include: Liabilities + Equity
   - CF must include: Investing Activities + Financing Activities
5. **Operational driver options**
   - `--chrome-binary` (or `CHROME_BINARY`) explicit browser path.
   - `--version-main` configurable UC major version.

## New helper scripts
1. `scripts/analyze_fiscal_timings.py`
   - Summarizes JSONL: ok/failed counts, mean/p50/p90/p95/max, by-kind stats, top failure reasons.
2. `scripts/fiscal_watchdog.py`
   - Restarts failed pull command with exponential backoff.
   - Enforces restart cap within rolling time window.
   - Logs restart reasons/events to JSONL.
3. `scripts/compare_fiscal_benchmarks.py`
   - Compares before/after benchmark JSONL means and delta %. 

## Commands run
```bash
# Syntax validation
python3 -m py_compile scripts/pull_financials_fiscal.py scripts/analyze_fiscal_timings.py scripts/fiscal_watchdog.py scripts/compare_fiscal_benchmarks.py

# Required-table validation audit on existing cache
python3 - <<'PY'
import json
from pathlib import Path
p=Path('cached_financials_2.json')
obj=json.load(p.open())
req_missing=0
for t,d in obj.items():
    miss=[]
    for k in ['IS','BS','CF']:
        if k not in d or not d[k]: miss.append(k)
    if 'BS' in d:
        labels={r[0].strip().lower() for r in d['BS'] if r}
        if 'liabilities' not in labels: miss.append('BS:Liabilities')
        if 'equity' not in labels: miss.append('BS:Equity')
    if 'CF' in d:
        labels={r[0].strip().lower() for r in d['CF'] if r}
        if 'investing activities' not in labels: miss.append('CF:Investing Activities')
        if 'financing activities' not in labels: miss.append('CF:Financing Activities')
    if miss:
        req_missing+=1
print('total_tickers',len(obj))
print('tickers_missing_required',req_missing)
PY

# Benchmark attempt (blocked by browser binary issue)
python3 scripts/pull_financials_fiscal.py --headless --magic-link 'https://fiscal.ai/invalid' \
  --use-csv --tickers-csv tmp/benchmark_20_mixed.csv --workers 1 \
  --heartbeat-seconds 15 --timings-jsonl tmp/after_benchmark.jsonl \
  --events-jsonl tmp/after_events.jsonl --checkpoint-json tmp/after_checkpoint.json
```

## Before/After benchmark table (>=20 mixed tickers)
| Metric | Before | After | Notes |
|---|---:|---:|---|
| Sample size | N/A | N/A | Blocked before authenticated run could start |
| Mean sec/ticker | N/A | N/A | No successful live run on this host |
| p90 sec/ticker | N/A | N/A | No successful live run on this host |
| Failure rate | N/A | N/A | No successful live run on this host |

## Reliability tests
- ✅ Python compile checks passed for all modified/new scripts.
- ✅ Checkpoint schema and JSONL emit paths validated in code path.
- ✅ Required table validator executed against existing cache:
  - `total_tickers=1230`
  - `tickers_missing_required=134`
- ❌ Live fiscal pull benchmark not executable on current host due blocker below.

## Exact blocker
`undetected_chromedriver` fails at startup in this WSL host:

- Error: `TypeError: Binary Location Must be a String`
- Meaning: Chrome/Chromium binary path is unavailable/unresolved in current environment.

## Minimal next action to unblock
Set a valid browser binary and rerun benchmark/overnight command, e.g.:

```bash
export CHROME_BINARY="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
```

(Or pass `--chrome-binary "..."` directly.)

## Current completion count
- New checkpoint completion count (this run): **0** (run blocked before processing tickers).
- Existing cache coverage snapshot: **1230 tickers present** in `cached_financials_2.json`.

## Exact overnight command (post-unblock)
```bash
python3 scripts/fiscal_watchdog.py \
  --max-restarts 8 \
  --window-seconds 3600 \
  --backoff-start 20 \
  --backoff-max 900 \
  --log-jsonl tmp/fiscal_watchdog_overnight.jsonl \
  -- python3 scripts/pull_financials_fiscal.py \
    --headless \
    --chrome-binary "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
    --use-csv --tickers-csv sp500_remaining_fiscal.csv \
    --workers 4 --fast \
    --heartbeat-seconds 60 \
    --checkpoint-json tmp/fiscal_checkpoint_sp503.json \
    --timings-jsonl tmp/fiscal_timings_sp503.jsonl \
    --events-jsonl tmp/fiscal_events_sp503.jsonl \
    --failed-csv financials_failed.csv \
    --magic-link '<PASTE_VALID_MAGIC_LINK>'
```
