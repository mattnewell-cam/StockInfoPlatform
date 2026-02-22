import csv
import re
import urllib.request
from pathlib import Path

BASE = Path('/mnt/c/Users/matth/PycharmProjects/StockInfoPlatform')
DATA = BASE / 'data'
OUT_PATH = DATA / 'all_us_tickers.csv'
REMOVED_PATH = DATA / 'all_us_tickers_removed.csv'

NASDAQ_URL = 'https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt'
OTHER_URL = 'https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt'


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode('utf-8', errors='ignore')


def load_nasdaq(text: str):
    rows = []
    info = {}
    for line in text.splitlines():
        if line.startswith('Symbol|') or line.startswith('File Creation Time') or not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 8:
            continue
        symbol = parts[0].strip()
        name = parts[1].strip()
        market = parts[2].strip()  # Q,G,S
        test_issue = parts[3].strip()
        etf = parts[6].strip()

        if market == 'Q':
            exchange = 'NasdaqGS'
        elif market == 'G':
            exchange = 'NasdaqGM'
        elif market == 'S':
            exchange = 'NasdaqCM'
        else:
            continue

        rows.append({'ticker': symbol, 'exchange': exchange})
        info[symbol] = {'name': name, 'test': test_issue, 'etf': etf}
    return rows, info


def load_other(text: str):
    # include NYSE from otherlisted; also use for names/flags
    rows = []
    info = {}
    for line in text.splitlines():
        if line.startswith('ACT Symbol|') or line.startswith('File Creation Time') or not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 8:
            continue
        symbol = parts[0].strip()
        name = parts[1].strip()
        exch = parts[2].strip()  # N, A, P, Z, V
        etf = parts[4].strip()
        test_issue = parts[6].strip()
        if exch == 'N':
            rows.append({'ticker': symbol, 'exchange': 'NYSE'})
        info[symbol] = {'name': name, 'test': test_issue, 'etf': etf}
    return rows, info

KEYWORDS_EXCLUDE = re.compile(
    r"\b(ETF|ETN|FUND|TRUST|UNIT|WARRANT|RIGHT|PREFERRED|NOTES|BOND|SERIES|SPAC|HOLDINGS|INCOME|MUNICIPAL|INTERNATIONAL|INDEX|PORTFOLIO|INCOME|S&P|DOW JONES)\b",
    re.IGNORECASE,
)
BAD_SYMBOL_PAT = re.compile(r"\.(W|WS|WT|U|R|P|PR|RT)$|^[A-Z]{4,5}[WUR]$", re.IGNORECASE)

nasdaq_text = fetch_text(NASDAQ_URL)
other_text = fetch_text(OTHER_URL)

nasdaq_rows, nasdaq_info = load_nasdaq(nasdaq_text)
other_rows, other_info = load_other(other_text)

# combine
rows = []
seen = set()
for r in nasdaq_rows + other_rows:
    if r['ticker'] in seen:
        continue
    seen.add(r['ticker'])
    rows.append(r)

# filter
removed = []
kept = []

for r in rows:
    t = r['ticker']
    info = nasdaq_info.get(t) or other_info.get(t) or {}
    name = info.get('name', '')
    test_issue = info.get('test', '')
    etf_flag = info.get('etf', '')

    if test_issue == 'Y':
        removed.append(r); continue
    if etf_flag == 'Y':
        removed.append(r); continue
    if BAD_SYMBOL_PAT.search(t):
        removed.append(r); continue
    if name and KEYWORDS_EXCLUDE.search(name):
        removed.append(r); continue

    kept.append(r)

# write outputs
with OUT_PATH.open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['ticker','exchange'])
    writer.writeheader()
    writer.writerows(kept)

with REMOVED_PATH.open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['ticker','exchange'])
    writer.writeheader()
    writer.writerows(removed)

print(f"Base tickers: {len(rows)}")
print(f"Removed: {len(removed)}")
print(f"Remaining: {len(kept)}")
