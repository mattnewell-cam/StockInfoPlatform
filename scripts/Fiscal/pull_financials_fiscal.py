import argparse
import csv
import imaplib
import quopri
from email import message_from_bytes
from email.utils import parsedate_to_datetime
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = (BASE_DIR / ".." / "..").resolve()
load_dotenv(PROJECT_ROOT / ".env")

# --- Paths ---
OUT_JSON = str(PROJECT_ROOT / "data" / "all_us_financials.json")
FAILED_CSV = str(PROJECT_ROOT / "data" / "financials_failed_us.csv")
NOT_FOUND_CSV = str(PROJECT_ROOT / "data" / "financials_not_found_us.csv")
INCOMPLETE_DATA_CSV = str(PROJECT_ROOT / "data" / "financials_incomplete_data_us.csv")
# TICKERS_CSV = str(PROJECT_ROOT / "data" / "sp500_tickers.csv")
TICKERS_CSV = str(PROJECT_ROOT / "data" / "all_us_tickers.csv")
# TICKERS_CSV = str(PROJECT_ROOT / "data" / "lse_all_tickers.csv")
LOG_JSONL = str(PROJECT_ROOT / "tmp" / "fiscal_pull_log_us.jsonl")
LOGS_DIR = BASE_DIR / "logs"

# --- Config ---
URL = "https://fiscal.ai"
LOGIN_EMAIL = os.getenv("FISCAL_LOGIN_EMAIL", "")
MAGIC_LINK_SOURCE = os.getenv("FISCAL_MAGIC_LINK_SOURCE", "manual").strip().lower()
if MAGIC_LINK_SOURCE not in {"manual", "imap"}:
    MAGIC_LINK_SOURCE = "manual"
MAGIC_LINK_TIMEOUT = int(os.getenv("FISCAL_MAGIC_LINK_TIMEOUT_SECONDS", "240"))
MAGIC_LINK_POLL = int(os.getenv("FISCAL_MAGIC_LINK_POLL_SECONDS", "5"))
IMAP_HOST = os.getenv("FISCAL_MAGIC_IMAP_HOST", "")
IMAP_PORT = int(os.getenv("FISCAL_MAGIC_IMAP_PORT", "993"))
IMAP_USER = os.getenv("FISCAL_MAGIC_IMAP_USER", "")
IMAP_PASSWORD = os.getenv("FISCAL_MAGIC_IMAP_PASSWORD", "")
IMAP_MAILBOX = os.getenv("FISCAL_MAGIC_IMAP_MAILBOX", "INBOX")
IMAP_MAX_SCAN = int(os.getenv("FISCAL_MAGIC_IMAP_MAX_SCAN", "30"))
CHROME_BINARY = os.getenv("CHROME_BINARY", "")
CHROME_VERSION_MAIN = int(os.getenv("CHROME_VERSION_MAIN", "144"))

WORKERS = 1
RETRY_ATTEMPTS = 1
HEARTBEAT_SECONDS = 300
FAST_MODE = True
STATEMENT_SLUGS = {
    "IS": ["income-statement"],
    "BS": ["balance-sheet"],
    "CF": ["cash-flow-statement"],
}
SUPPLEMENTAL_TABLES = {
    "BS": {"slug": "balance-sheet", "names": ["Liabilities", "Equity"]},
    "CF": {"slug": "cash-flow-statement", "names": ["Investing Activities", "Financing Activities"]},
}


class PageNotFoundError(RuntimeError):
    pass


class IncompleteDataError(RuntimeError):
    pass


# --- Utilities ---

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def load_json(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"Warning: failed to parse JSON at {path}; using default")
        return default


def _compact_dumps(obj, indent=2, _level=0):
    """JSON where leaf arrays (all-primitive lists) are written on one line."""
    pad = ' ' * (indent * _level)
    ipad = ' ' * (indent * (_level + 1))
    if isinstance(obj, dict):
        if not obj:
            return '{}'
        parts = [f'{ipad}{json.dumps(k)}: {_compact_dumps(v, indent, _level + 1)}' for k, v in obj.items()]
        return '{\n' + ',\n'.join(parts) + '\n' + pad + '}'
    if isinstance(obj, list):
        if not obj:
            return '[]'
        if all(not isinstance(x, (list, dict)) for x in obj):
            return '[' + ', '.join(json.dumps(x, ensure_ascii=False) for x in obj) + ']'
        parts = [f'{ipad}{_compact_dumps(x, indent, _level + 1)}' for x in obj]
        return '[\n' + ',\n'.join(parts) + '\n' + pad + ']'
    return json.dumps(obj, ensure_ascii=False)


def save_json(path: str, data):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_compact_dumps(data))


def log_event(payload: dict, lock=None):
    ensure_parent(LOG_JSONL)
    line = json.dumps({**payload, "ts": utc_now_iso()}, ensure_ascii=False)
    if lock:
        with lock:
            with open(LOG_JSONL, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    else:
        with open(LOG_JSONL, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# --- WebDriver helpers ---

def wait_for(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def wait_for_table(driver, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'))
    )


def safe_click(driver, element):
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


# --- Ticker helpers ---

def normalize_exchange(exchange: str) -> str:
    if not exchange:
        return exchange
    u = exchange.strip().upper()
    if u in {"NASDAQ", "NMS", "NAS", "NGS"}:
        return "NasdaqGS"
    if u in {"NYSE", "NYQ", "NYS"}:
        return "NYSE"
    return exchange.strip()


def build_fiscal_ticker(ticker, exchange):
    return ticker if "-" in ticker else f"{normalize_exchange(exchange)}-{ticker}"


# --- IMAP magic link ---

FISCAL_SENDER = "notifications@notifications.fiscal.ai"
MAGIC_LINK_PREFIX = "https://fiscal.ai/email-login/redirect?"


def _check_imap_for_link():
    """Single IMAP pass — returns a recent magic link string or None."""
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASSWORD]):
        return None
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as client:
            client.login(IMAP_USER, IMAP_PASSWORD)
            client.select(IMAP_MAILBOX or "INBOX", readonly=True)
            _, data = client.search(None, f'FROM "{FISCAL_SENDER}"')
            if not data or not data[0]:
                return None
            for msg_id in reversed(data[0].split()[-IMAP_MAX_SCAN:]):
                _, fetched = client.fetch(msg_id, "(RFC822)")
                raw = next(
                    (bytes(item[1]) for item in fetched if isinstance(item, tuple) and isinstance(item[1], (bytes, bytearray))),
                    b"",
                )
                if not raw:
                    continue
                try:
                    sent_at = parsedate_to_datetime(message_from_bytes(raw).get("Date", ""))
                    if (datetime.now(timezone.utc) - sent_at.astimezone(timezone.utc)).total_seconds() > 600:
                        continue
                except Exception:
                    pass
                text = quopri.decodestring(raw).decode("utf-8", errors="replace")
                idx = text.find(MAGIC_LINK_PREFIX)
                if idx != -1:
                    return text[idx:].split()[0].rstrip(".,;\"'")
    except Exception:
        pass
    return None


def wait_for_magic_link_via_imap():
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASSWORD]):
        raise RuntimeError("IMAP requires FISCAL_MAGIC_IMAP_HOST/USER/PASSWORD env vars.")
    deadline = time.time() + max(10, MAGIC_LINK_TIMEOUT)
    poll = max(2, MAGIC_LINK_POLL)
    while time.time() < deadline:
        link = _check_imap_for_link()
        if link:
            return link
        time.sleep(poll)
    raise TimeoutError(f"No fiscal.ai magic link found within {MAGIC_LINK_TIMEOUT}s")


# --- Auth ---

PAGES_DIR = BASE_DIR / "pages"


def _save_page(driver, name: str):
    PAGES_DIR.mkdir(exist_ok=True)
    (PAGES_DIR / f"{name}.html").write_text(driver.page_source, encoding="utf-8")


def start_login_flow(driver, login_email: str):
    driver.get(URL)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    time.sleep(1)

    _save_page(driver, "01_before_login_click")
    login_btn = driver.find_element(By.ID, "ph-marketing-header__sign-up-button")
    driver.execute_script("arguments[0].click();", login_btn)
    time.sleep(0.5)
    _save_page(driver, "02_after_login_click")

    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-path='email']"))
    )
    email_input.send_keys(login_email)
    try:
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)
    except Exception:
        email_input.send_keys(Keys.RETURN)

    if MAGIC_LINK_SOURCE == "imap":
        print("Waiting for fiscal.ai magic link via IMAP...")
        link = wait_for_magic_link_via_imap()
    else:
        print("Check your email and paste fiscal.ai magic link:")
        link = input().strip()

    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / f"magic_link_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.txt"
    log_path.write_text(link, encoding="utf-8")
    print(f"Magic link logged to {log_path}")
    return link


def open_magic_link(driver, magic_link: str):
    if not magic_link:
        raise RuntimeError("Magic link missing")
    driver.get(magic_link)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "ph-app-header__upgrade-button"))
    )
    print(f"[driver] authenticated: landed on {driver.current_url}")


def assert_authenticated(driver):
    driver.get(f"{URL}/dashboard")
    wait_for(driver, By.TAG_NAME, "body", timeout=12)
    print(f"[driver] after dashboard nav: {driver.current_url}")
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    cur = (driver.current_url or "").lower()
    if any(x in cur for x in ["login", "sign-in", "auth"]) or any(
        x in body for x in ["check your email", "magic link", "log in", "login with email"]
    ):
        raise RuntimeError("Auth check failed")


# --- Table extraction ---

def ensure_k_units(driver, timeout=4):
    if getattr(driver, "_k_units_attempted", False):
        return
    driver._k_units_attempted = True
    try:
        # Find, check, and click all in one JS call — no stale element risk.
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script("""
            for (var l of document.querySelectorAll('label')) {
                for (var s of l.querySelectorAll('span.mantine-SegmentedControl-innerLabel')) {
                    if (s.textContent.trim() === 'K') {
                        if (l.getAttribute('data-active') !== 'true') l.click();
                        return true;
                    }
                }
            }
            return false;
        """))
    except Exception:
        pass


def extract_rows_from_table(table_root):
    driver = getattr(table_root, "_parent", None)
    if driver:
        try:
            rows = driver.execute_script(
                """
                const root = arguments[0];
                const rowEls = root.querySelectorAll('tr, [role="row"]');
                const out = [];
                for (let i = 0; i < rowEls.length; i++) {
                  const r = rowEls[i];
                  const isParent = r.classList.contains('parent-item') || r.querySelector('.parent-item');
                  if (!(i === 0 || isParent)) continue;
                  const cellEls = r.querySelectorAll('th, td, [role="columnheader"], [role="cell"]');
                  out.push(Array.from(cellEls).map(c => (c.innerText || c.textContent || '').trim()));
                }
                return out;
                """,
                table_root,
            )
            fast = [v for v in rows if isinstance(v, list) and len(v) >= 2 and any((x or "").strip() for x in v[1:])]
            if fast:
                return fast
        except Exception:
            pass

    parsed = []
    for idx, row in enumerate(table_root.find_elements(By.CSS_SELECTOR, "tr, [role='row']")):
        row_class = (row.get_attribute("class") or "").lower()
        cell_class = ""
        if "parent-item" not in row_class:
            cells = row.find_elements(By.CSS_SELECTOR, "th, td, [role='columnheader'], [role='cell']")
            if cells:
                cell_class = (cells[0].get_attribute("class") or "").lower()
        is_parent = ("parent-item" in row_class) or ("parent-item" in cell_class)
        if not (idx == 0 or is_parent):
            continue
        cells = row.find_elements(By.CSS_SELECTOR, "th, td, [role='columnheader'], [role='cell']")
        vals = [c.text.strip() for c in cells]
        if len(vals) >= 2 and any(vals[1:]):
            parsed.append(vals)
    return parsed


def extract_all_tables_from_page(driver):
    all_tables = driver.execute_script("""
        const tables = document.querySelectorAll('[data-sentry-component="TableContent"]');
        return Array.from(tables).map(table => {
            const rows = table.querySelectorAll('tr, [role="row"]');
            return Array.from(rows).map((r, i) => {
                const isParent = r.classList.contains('parent-item') || r.querySelector('.parent-item');
                if (!(i === 0 || isParent)) return null;
                const cells = r.querySelectorAll('th, td, [role="columnheader"], [role="cell"]');
                return Array.from(cells).map(c => (c.innerText || c.textContent || '').trim());
            }).filter(row => row && row.length >= 2 && row.slice(1).some(v => v));
        }).filter(t => t.length > 0);
    """)
    return all_tables or []


def find_table_by_name(tables, name):
    n = name.strip().lower()
    return next((t for t in tables if t and t[0] and t[0][0].strip().lower() == n), None)


def quick_missing_check(driver, ticker, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = driver.execute_script("""
            if (document.querySelector('[data-sentry-component="TableContent"]')) return 'table';
            var body = (document.body && document.body.innerText || '').toLowerCase();
            if (/not found|no results|no data|does not exist|cannot find|data not found/.test(body)) return 'not_found';
            if (body.includes('data is not available for')) return 'not_found';
            return null;
        """)
        if result == 'table':
            return
        if result == 'not_found':
            raise PageNotFoundError(f"{ticker}: not found or data unavailable")
        time.sleep(0.2)


def _count_filled_data_cells(driver):
    """Count non-empty, non-dash values across all data rows (skipping header row 0) in all tables."""
    total = 0
    try:
        tables = driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]')
        for table in tables:
            rows = driver.execute_script(
                """
                const rows = arguments[0].querySelectorAll('tr, [role="row"]');
                const out = [];
                for (const r of rows) {
                    const cells = r.querySelectorAll('th, td, [role="columnheader"], [role="cell"]');
                    out.push(Array.from(cells).map(c => (c.innerText || c.textContent || '').trim()));
                }
                return out;
                """,
                table,
            )
            for row in (rows or [])[1:]:  # skip header row
                if not isinstance(row, list):
                    continue
                total += sum(1 for v in row[1:] if (v or "").strip() not in ("", "—", "–", "-"))
    except Exception:
        pass
    return total


def _wait_for_complete_is_table(driver, timeout=15, poll=0.1, max_empty_ratio=0.5):
    """Wait until IS has <= max_empty_ratio empty value cells (skips header col)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        is_ready, not_found = driver.execute_script("""
            var table = document.querySelector('[data-sentry-component="TableContent"]');
            var body = (document.body && document.body.innerText || '').toLowerCase();
            var nf = /not found|no results|no data|does not exist|cannot find|data not found|data is not available for/.test(body);
            if (!table) return [false, nf];
            var rows = table.querySelectorAll('tr, [role="row"]');
            if (!rows || rows.length < 2) return [false, nf];
            var headerCells = rows[0].querySelectorAll('th, td, [role="columnheader"], [role="cell"]');
            var colCount = headerCells ? headerCells.length : 0;
            if (colCount >= 2) {
                var lastDataCol = 1;
                for (var h = 1; h < headerCells.length; h++) {
                    var ht = (headerCells[h].innerText || headerCells[h].textContent || '').trim();
                    if (ht && ht !== '-' && ht !== '—' && ht !== '–') lastDataCol = h;
                }
                colCount = lastDataCol + 1;
            }
            if (colCount < 2) return [false, nf];
            function isValue(v) {
                if (!v) return false;
                var t = ('' + v).trim();
                if (!t) return false;
                return !(t === '-' || t === '—' || t === '–');
            }
            var total = 0;
            var empty = 0;
            for (var i = 1; i < rows.length; i++) {
                var r = rows[i];
                var cells = r.querySelectorAll('th, td, [role="columnheader"], [role="cell"]');
                var hasReal = false;
                for (var c = 1; c < Math.min(cells.length, colCount); c++) {
                    if (isValue(cells[c].innerText || cells[c].textContent)) { hasReal = true; break; }
                }
                if (!hasReal) continue;
                for (var c2 = 1; c2 < colCount; c2++) {
                    total++;
                    var cell = (c2 < cells.length) ? cells[c2] : null;
                    if (!cell || !isValue(cell.innerText || cell.textContent)) empty++;
                }
            }
            if (total === 0) return [false, nf];
            var emptyRatio = empty / total;
            return [emptyRatio <= arguments[0], nf];
        """, max_empty_ratio)
        if not_found:
            return False, True
        if is_ready:
            return True, False
        time.sleep(poll)
    return False, False


def _load_page(driver, ticker, slug, multi_table=False):
    """Navigate to a fiscal statement page and extract table(s), waiting for data to be populated."""
    t0 = time.perf_counter()
    debug_cf = (slug == "cash-flow-statement")
    target_path = f"/company/{ticker}/financials/{slug}/annual/"
    if f"/company/{ticker}/" in (driver.current_url or "") and slug not in (driver.current_url or ""):
        nav_links = driver.find_elements(By.CSS_SELECTOR, f'a[href*="/company/{ticker}/financials/{slug}/"]')
        if nav_links:
            driver.execute_script("arguments[0].click();", nav_links[0])
            WebDriverWait(driver, 10).until(lambda d: slug in d.current_url)
        else:
            driver.get(f"{URL}{target_path}")
    else:
        driver.get(f"{URL}{target_path}")
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    if debug_cf:
        print(f"  [cf timing] after nav+body: {time.perf_counter() - t0:.3f}s")

    is_404 = driver.execute_script("""
        var h = document.querySelector('h1[data-sentry-source-file="404.tsx"]');
        return h ? h.textContent.toLowerCase().includes('sorry, page not found') : false;
    """)
    if is_404:
        raise PageNotFoundError(f"{ticker}: page not found (fiscal.ai 404)")

    quick_missing_check(driver, ticker, timeout=2 if FAST_MODE else 4)
    if debug_cf:
        print(f"  [cf timing] after missing_check: {time.perf_counter() - t0:.3f}s")

    if slug == "income-statement" and not multi_table:
        ensure_k_units(driver)

    if multi_table:
        if debug_cf:
            print(f"  [cf timing] enter multi_table: {time.perf_counter() - t0:.3f}s")
        # Poll until count reaches 3 (done) or stabilises below 3 (incomplete company).
        # Also bail immediately if error text appears in the page body.
        deadline = time.time() + (15 if FAST_MODE else 20)
        last_count, stable_since = 0, None
        while time.time() < deadline:
            count, not_found = driver.execute_script("""
                var count = document.querySelectorAll('[data-sentry-component="TableContent"]').length;
                var body = (document.body && document.body.innerText || '').toLowerCase();
                var nf = /not found|no results|no data|does not exist|cannot find|data not found|data is not available for/.test(body);
                return [count, nf];
            """)
            if not_found:
                raise PageNotFoundError(f"{ticker}: not found or data unavailable")
            if count >= 3:
                if debug_cf:
                    print(f"  [cf timing] count>=3: {time.perf_counter() - t0:.3f}s")
                t_extract = time.perf_counter()
                tables = extract_all_tables_from_page(driver)
                if debug_cf:
                    print(f"  [cf timing] extract_all_tables: {time.perf_counter() - t_extract:.3f}s")
                return tables
            if count != last_count:
                last_count = count
                stable_since = time.time() if count > 0 else None
            elif stable_since and time.time() - stable_since >= 0.5:
                raise IncompleteDataError(f"{ticker} {slug}: only {count} table(s), expected 3")
            time.sleep(0.1)
        raise TimeoutError(f"{ticker}: timeout waiting for tables on {slug}")

    # Single-table (IS): wait until every visible year column has at least one real value.
    is_ready, not_found = _wait_for_complete_is_table(driver, timeout=15, poll=0.1)
    if not_found:
        raise PageNotFoundError(f"{ticker}: not found or data unavailable")
    if not is_ready:
        raise TimeoutError(f"{ticker} {slug}: timeout waiting for full IS columns")

    tables = extract_all_tables_from_page(driver)
    if not tables or not tables[0] or len(tables[0][0]) < 2:
        raise RuntimeError(f"{ticker} {slug} returned empty rows")
    return tables[0]


# --- Statement pulling ---

def pull_financials(driver, ticker, exchange="LSE"):
    fiscal_ticker = build_fiscal_ticker(ticker, exchange)
    rows_by_stmt = {}
    for stmt, slugs in STATEMENT_SLUGS.items():
        last_exc = None
        use_multi = stmt in ("BS", "CF")
        for slug in slugs:
            try:
                if use_multi:
                    tables = _load_page(driver, fiscal_ticker, slug, multi_table=True)
                    headers = [t[0][0].strip() if t and t[0] else "?" for t in tables]
                    print(f"  [{stmt}] {len(tables)} table(s) found, headers: {headers}")
                    rows_by_stmt[stmt] = [row for table in tables for row in table]
                else:
                    rows_by_stmt[stmt] = _load_page(driver, fiscal_ticker, slug)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc:
            raise last_exc
    return rows_by_stmt, exchange


# --- Data helpers ---

def dedupe_rows(rows):
    out, seen = [], set()
    for row in rows or []:
        if not isinstance(row, list):
            continue
        key = tuple((c or "").strip() if isinstance(c, str) else str(c) for c in row)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def merge_rows(existing, new):
    return dedupe_rows((existing or []) + (new or []))


def validate_financials(financials):
    return [req for req in ("IS", "BS", "CF") if req not in financials or not financials[req]]


def _is_has_data(ticker_data):
    """Return False if IS is missing or >50% of value cells are empty strings."""
    rows = ticker_data.get("IS", [])
    if not rows:
        return False
    total = empty = 0
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        for v in row[1:]:
            total += 1
            if not isinstance(v, str) or not v.strip():
                empty += 1
    if total == 0:
        return False
    return (empty / total) <= 0.5


def needs_work(ticker_data):
    """Return True if the ticker needs a (re-)scrape: missing entirely or missing key statements."""
    if not ticker_data:
        return True
    if not _is_has_data(ticker_data):
        return True
    return any(not ticker_data.get(stmt) for stmt in ("IS", "BS", "CF"))


def remove_ticker_from_csv(ticker, csv_path):
    p = Path(csv_path)
    if not p.exists():
        return
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = [r for r in reader if r and r[0].strip() != ticker]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(rows)


def append_to_not_found_csv(ticker, exchange):
    ensure_parent(NOT_FOUND_CSV)
    with open(NOT_FOUND_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([ticker, exchange])


def append_to_incomplete_csv(ticker, exchange):
    ensure_parent(INCOMPLETE_DATA_CSV)
    with open(INCOMPLETE_DATA_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([ticker, exchange])


def classify_error(exc):
    if isinstance(exc, PageNotFoundError):
        return "page_not_found"
    if isinstance(exc, IncompleteDataError):
        return "incomplete_data"
    s = str(exc).lower()
    if "not found" in s:
        return "ticker_not_found"
    if "timeout" in s:
        return "timeout"
    if "disconnected" in s or "invalid session" in s or "chrome not reachable" in s:
        return "driver_died"
    if "validation missing" in s:
        return "validation_missing"
    if "empty rows" in s:
        return "empty_rows"
    return "other"


def load_failed_set(path):
    if not Path(path).exists():
        return set()
    with open(path, newline="") as f:
        return {row[0] for row in csv.reader(f) if row}


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Fetch fiscal.ai financials")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--ticker", default="")
    parser.add_argument("--magic-link", default="")
    parser.add_argument("--login-email", default=LOGIN_EMAIL)
    args = parser.parse_args()

    if not args.magic_link and not args.login_email:
        raise RuntimeError("Missing login email. Set --login-email or FISCAL_LOGIN_EMAIL.")

    def build_driver():
        options = uc.ChromeOptions()
        if CHROME_BINARY:
            options.binary_location = CHROME_BINARY
        if args.headless:
            options.add_argument("--headless")
        d = uc.Chrome(options=options, version_main=CHROME_VERSION_MAIN)
        d.implicitly_wait(10)
        return d

    def retry(fn, attempts=RETRY_ATTEMPTS):
        last = None
        for attempt in range(1, attempts + 1):
            try:
                return fn(), attempt
            except Exception as exc:
                last = exc
                if attempt < attempts:
                    time.sleep(min(6, 1.5 * attempt))
        raise last

    lock = Lock()
    cached = load_json(OUT_JSON, {})
    failed_set = load_failed_set(FAILED_CSV)
    state = {"processed": 0, "total": 0, "started_at": time.time(), "ok": 0, "failed": 0}
    if args.ticker:
        tickers, ticker_market = [args.ticker], {}
        raw_ticker = args.ticker.strip()
        if "-" in raw_ticker:
            prefix, tail = raw_ticker.split("-", 1)
            known_prefixes = {
                "NasdaqGS", "NasdaqGM", "NasdaqCM",
                "NYSE", "NYS", "NYQ", "NAS", "NMS", "NGS",
                "LSE", "AIM",
            }
            if prefix in known_prefixes and tail:
                tickers = [tail]
                ticker_market[tail] = prefix
        # If running a single ticker, try to resolve its exchange from the tickers CSV.
        try:
            with open(TICKERS_CSV, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row and row[0].strip().upper() == args.ticker.strip().upper():
                        if len(row) >= 2 and row[1].strip():
                            ticker_market[args.ticker.strip()] = normalize_exchange(row[1].strip())
                        break
        except Exception:
            pass
    else:
        tickers, ticker_market = [], {}
        with open(TICKERS_CSV, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row or not row[0].strip():
                    continue
                t = row[0].strip()
                tickers.append(t)
                if len(row) >= 2 and row[1].strip():
                    ticker_market[t] = normalize_exchange(row[1].strip())

    pending = [t for t in tickers if needs_work(cached.get(t))]
    if not pending:
        print("No tickers to process")
        return

    workers = min(WORKERS, len(pending))
    chunks = [pending[i::workers] for i in range(workers)]
    state["total"] = len(pending)

    drivers = []
    try:
        primary = build_driver()
        drivers.append(primary)
        magic_link = args.magic_link.strip()
        if not magic_link and MAGIC_LINK_SOURCE == "imap":
            magic_link = _check_imap_for_link() or ""
            if magic_link:
                print("Found recent magic link in inbox, skipping sign-in flow.")
        if not magic_link:
            magic_link = start_login_flow(primary, args.login_email)
        for _ in range(workers - 1):
            drivers.append(build_driver())
        for d in drivers:
            open_magic_link(d, magic_link)
            assert_authenticated(d)

        def worker_run(worker_id, driver, worker_tickers):
            for t in worker_tickers:
                exchange = ticker_market.get(t, "LSE")
                kind = "full"

                started = time.perf_counter()
                try:
                    (financials, used_exchange), attempts = retry(lambda: pull_financials(driver, t, exchange))
                    with lock:
                        cached[t] = {"exchange": used_exchange, **financials}
                        save_json(OUT_JSON, cached)
                    row_counts = {k: len(financials.get(k, [])) for k in ("IS", "BS", "CF")}

                    missing = validate_financials(cached[t])
                    if missing:
                        raise RuntimeError("validation missing: " + ", ".join(missing))

                    elapsed = round(time.perf_counter() - started, 3)
                    with lock:
                        state["processed"] += 1
                        state["ok"] += 1

                    log_event({"event": "ticker_done", "ticker": t, "status": "ok", "kind": kind,
                               "exchange": used_exchange, "elapsed_sec": elapsed, "rows": row_counts}, lock=lock)
                    print(f"[ok] {t} ({kind}, {used_exchange}) {elapsed:.1f}s rows={row_counts}")

                except Exception as exc:
                    elapsed = round(time.perf_counter() - started, 3)
                    reason_type = classify_error(exc)
                    reason = str(exc)
                    with lock:
                        state["processed"] += 1
                        state["failed"] += 1
                        if t not in failed_set:
                            failed_set.add(t)
                            ensure_parent(FAILED_CSV)
                            with open(FAILED_CSV, "a", newline="") as f:
                                csv.writer(f).writerow([t, exchange, reason_type, reason])
                        if reason_type == "page_not_found":
                            remove_ticker_from_csv(t, TICKERS_CSV)
                            append_to_not_found_csv(t, exchange)
                        elif reason_type == "incomplete_data":
                            remove_ticker_from_csv(t, TICKERS_CSV)
                            append_to_incomplete_csv(t, exchange)

                    log_event({"event": "ticker_failed", "ticker": t, "kind": kind,
                               "reason": reason, "reason_type": reason_type}, lock=lock)
                    print(f"[fail] {t} {exc.__class__.__name__}: {reason[:120]}")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker_run, i, d, chunk) for i, (d, chunk) in enumerate(zip(drivers, chunks), 1)]
            for fut in as_completed(futures):
                fut.result()

        log_event({"event": "run_complete", "processed": state["processed"], "ok": state["ok"], "failed": state["failed"]})
        print("Done")

    finally:
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
