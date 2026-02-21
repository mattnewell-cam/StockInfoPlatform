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
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread

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
OUT_JSON = str(PROJECT_ROOT / "cached_financials_2.json")
FAILED_CSV = str(PROJECT_ROOT / "data" / "financials_failed_uk.csv")
# TICKERS_CSV = str(PROJECT_ROOT / "data" / "sp500_tickers.csv")
TICKERS_CSV = str(PROJECT_ROOT / "data" / "lse_all_tickers.csv")
LOG_JSONL = str(PROJECT_ROOT / "tmp" / "fiscal_pull_log_uk.jsonl")
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


# --- Utilities ---

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def load_json(path: str, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save_json(path: str, data):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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

def ensure_k_units(driver, timeout=10):
    if getattr(driver, "_k_units_attempted", False):
        return
    driver._k_units_attempted = True
    try:
        label = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//label[.//span[contains(@class,'mantine-SegmentedControl-innerLabel') and normalize-space()='K']]",
            ))
        )
        if label.get_attribute("data-active") != "true":
            safe_click(driver, label)
            time.sleep(0.2)
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
                for (const r of rowEls) {
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
    for row in table_root.find_elements(By.CSS_SELECTOR, "tr, [role='row']"):
        cells = row.find_elements(By.CSS_SELECTOR, "th, td, [role='columnheader'], [role='cell']")
        vals = [c.text.strip() for c in cells]
        if len(vals) >= 2 and any(vals[1:]):
            parsed.append(vals)
    return parsed


def extract_all_tables_from_page(driver):
    return [
        rows
        for el in driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]')
        if (rows := extract_rows_from_table(el))
    ]


def find_table_by_name(tables, name):
    n = name.strip().lower()
    return next((t for t in tables if t and t[0] and t[0][0].strip().lower() == n), None)


def quick_missing_check(driver, ticker, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
            return
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(m in body for m in ["not found", "no results", "no data", "does not exist", "cannot find", "can't find"]):
            raise RuntimeError(f"{ticker} not found on fiscal.ai")
        time.sleep(0.2)


def _has_populated_data(driver):
    """Return True once the last 3 value columns in at least one data row are non-empty."""
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
            for row in rows:
                if not isinstance(row, list) or len(row) < 4:
                    continue
                last_three = row[-3:]
                if all((v or "").strip() for v in last_three):
                    return True
    except Exception:
        pass
    return False


def _load_page(driver, ticker, slug, multi_table=False):
    """Navigate to a fiscal statement page and extract table(s), waiting for data to be populated."""
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

    if slug == "income-statement" and not multi_table:
        ensure_k_units(driver)

    quick_missing_check(driver, ticker, timeout=2 if FAST_MODE else 4)

    # Wait until the table data is actually populated (session fully authenticated),
    # then give React a moment to finish re-rendering before grabbing elements.
    WebDriverWait(driver, 30).until(_has_populated_data)
    time.sleep(0.5)

    if multi_table:
        WebDriverWait(driver, 15 if FAST_MODE else 20).until(
            lambda d: len([
                el for el in d.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]')
                if el.find_elements(By.CSS_SELECTOR, 'tr, [role="row"]')
            ]) >= 3
        )
        return extract_all_tables_from_page(driver)

    WebDriverWait(driver, 15 if FAST_MODE else 20).until(
        lambda d: len(d.find_elements(
            By.CSS_SELECTOR,
            '[data-sentry-component="TableContent"] tr, [data-sentry-component="TableContent"] [role="row"]',
        )) > 1
    )

    # Re-fetch table_root fresh — the earlier reference may be stale after React re-renders on auth.
    table_root = wait_for_table(driver, timeout=10 if FAST_MODE else 15)
    rows = extract_rows_from_table(table_root)
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{ticker} {slug} returned empty rows")
    return rows


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


def pull_supplemental(driver, ticker, exchange="LSE"):
    fiscal_ticker = build_fiscal_ticker(ticker, exchange)
    result = {}
    for stmt, config in SUPPLEMENTAL_TABLES.items():
        tables = _load_page(driver, fiscal_ticker, config["slug"], multi_table=True)
        found = []
        for name in config["names"]:
            t = find_table_by_name(tables, name)
            if t:
                found.extend(t)
        if found:
            result[stmt] = dedupe_rows(found)
    return result, exchange


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


def needs_work(ticker_data):
    """Return True if the ticker needs a (re-)scrape: missing entirely or incomplete supplemental sections."""
    if not ticker_data:
        return True
    def labels(stmt):
        return [(r[0] or "").strip().lower() for r in ticker_data.get(stmt, []) if r]
    bs = labels("BS")
    cf = labels("CF")
    has_liabilities = any("liabilit" in l for l in bs)
    has_equity = any("equity" in l for l in bs)
    has_investing = any("investing" in l for l in cf)
    has_financing = any("financing" in l for l in cf)
    return not (has_liabilities and has_equity and has_investing and has_financing)


def classify_error(exc):
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
                is_cached = t in cached
                kind = "supplemental" if is_cached else "full"

                started = time.perf_counter()
                try:
                    if is_cached:
                        (supp, used_exchange), attempts = retry(lambda: pull_supplemental(driver, t, exchange))
                        with lock:
                            cached[t]["exchange"] = used_exchange
                            for stmt, rows in supp.items():
                                cached[t][stmt] = merge_rows(cached[t].get(stmt, []), rows)
                            save_json(OUT_JSON, cached)
                        row_counts = {k: len(cached[t].get(k, [])) for k in ("IS", "BS", "CF")}
                    else:
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

                    log_event({"event": "ticker_failed", "ticker": t, "kind": kind,
                               "reason": reason, "reason_type": reason_type}, lock=lock)
                    print(f"[fail] {t} {reason_type}: {reason[:80]}")
                    print(traceback.format_exc())

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
