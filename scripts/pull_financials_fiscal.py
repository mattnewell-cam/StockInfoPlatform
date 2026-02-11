import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://fiscal.ai"
FAST_MODE_DEFAULT = True
WORKERS_DEFAULT = 4

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_JSON = str((BASE_DIR / ".." / "cached_financials_2.json").resolve())
FAILED_CSV_DEFAULT = str((BASE_DIR / ".." / "financials_failed.csv").resolve())
DEFAULT_TICKERS_CSV = str((BASE_DIR / ".." / "lse_all_tickers.csv").resolve())
DEFAULT_CHECKPOINT_JSON = str((BASE_DIR / ".." / "tmp" / "fiscal_pull_checkpoint.json").resolve())
DEFAULT_TIMINGS_JSONL = str((BASE_DIR / ".." / "tmp" / "fiscal_pull_timings.jsonl").resolve())
DEFAULT_EVENTS_JSONL = str((BASE_DIR / ".." / "tmp" / "fiscal_pull_events.jsonl").resolve())

USE_TEST_TICKER = False
TEST_TICKER_DEFAULT = "LSE-SHEL"
SKIP_IF_FAILED = False

STATEMENT_SLUGS = {
    "IS": ["income-statement"],
    "BS": ["balance-sheet"],
    "CF": ["cash-flow-statement"],
}

SUPPLEMENTAL_TABLES = {
    "BS": {"slug": "balance-sheet", "names": ["Liabilities", "Equity"]},
    "CF": {"slug": "cash-flow-statement", "names": ["Investing Activities", "Financing Activities"]},
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def load_json(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def jsonl_append(path: str, payload: dict, lock=None):
    if not path:
        return
    ensure_parent(path)
    row = dict(payload)
    row.setdefault("ts", utc_now_iso())
    line = json.dumps(row, ensure_ascii=False)
    if lock:
        with lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


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


def _scroll_into_safe_viewport(driver, element):
    driver.execute_script(
        """
        const el = arguments[0];
        const rect = el.getBoundingClientRect();
        const targetY = window.scrollY + rect.top - Math.max(160, window.innerHeight * 0.25);
        window.scrollTo({top: Math.max(0, targetY), behavior: 'instant'});
        """,
        element,
    )
    time.sleep(0.02)


def _set_thumb_to_value(driver, thumb, target_val, is_left_thumb, key_delay=0.0, deadline=None):
    _scroll_into_safe_viewport(driver, thumb)
    try:
        current_val = int(thumb.get_attribute("aria-valuenow"))
    except Exception:
        return False

    if current_val == target_val:
        return True

    try:
        driver.execute_script("arguments[0].focus();", thumb)
        safe_click(driver, thumb)
        try:
            thumb.send_keys(Keys.HOME if is_left_thumb else Keys.END)
            time.sleep(0.01)
            current_val = int(thumb.get_attribute("aria-valuenow"))
        except Exception:
            pass

        key = Keys.ARROW_LEFT if target_val < current_val else Keys.ARROW_RIGHT
        for _ in range(abs(target_val - current_val)):
            if deadline and time.perf_counter() > deadline:
                return False
            thumb.send_keys(key)
            if key_delay:
                time.sleep(key_delay)

        return int(thumb.get_attribute("aria-valuenow")) == target_val
    except Exception:
        return False


def set_slider_range(driver, min_val=5, max_val=22, key_delay=0.0, max_seconds=3.0):
    try:
        max_seconds = float(os.getenv("SLIDER_MAX_SECONDS", str(max_seconds)))
    except Exception:
        pass

    try:
        thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
    except Exception:
        return False

    if len(thumbs) < 2:
        return False

    left_thumb, right_thumb = thumbs[0], thumbs[1]
    deadline = time.perf_counter() + max_seconds
    ok_left = _set_thumb_to_value(driver, left_thumb, min_val, True, key_delay=key_delay, deadline=deadline)
    if time.perf_counter() > deadline:
        return False
    ok_right = _set_thumb_to_value(driver, right_thumb, max_val, False, key_delay=key_delay, deadline=deadline)

    try:
        left_after = int(left_thumb.get_attribute("aria-valuenow"))
        right_after = int(right_thumb.get_attribute("aria-valuenow"))
    except Exception:
        return False

    return ok_left and ok_right and left_after == min_val and right_after == max_val


def slider_range_already_adequate(driver, min_val=5, max_val=22):
    try:
        thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
        if len(thumbs) < 2:
            return False
        left, right = thumbs[0], thumbs[1]
        left_val = int(left.get_attribute("aria-valuenow"))
        right_val = int(right.get_attribute("aria-valuenow"))
        return left_val <= min_val and right_val >= max_val
    except Exception:
        return False


def normalize_exchange(exchange: str) -> str:
    if not exchange:
        return exchange
    ex = exchange.strip()
    u = ex.upper()
    if u in {"NASDAQ", "NMS", "NAS", "NGS"}:
        return "NasdaqGS"
    if u in {"NYSE", "NYQ", "NYS"}:
        return "NYSE"
    return ex


def build_fiscal_ticker(ticker, exchange):
    if "-" in ticker:
        return ticker
    return f"{normalize_exchange(exchange)}-{ticker}"


def start_login_flow(driver):
    driver.get(URL)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    time.sleep(1)

    login_btn = driver.find_element(By.ID, "ph-marketing-header__sign-up-button")
    driver.execute_script("arguments[0].click();", login_btn)

    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'],input[name='email']"))
    )
    email_input.clear()
    email_input.send_keys("matthew_newell@outlook.com")

    try:
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)
    except Exception:
        email_input.send_keys(Keys.RETURN)

    print("Check your email and paste fiscal.ai magic link:")
    return input().strip()


def open_magic_link(driver, magic_link):
    if not magic_link:
        raise RuntimeError("Magic link missing")
    driver.get(magic_link)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)


def assert_authenticated_with_full_financials(driver):
    driver.get(f"{URL}/dashboard")
    wait_for(driver, By.TAG_NAME, "body", timeout=12)
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    cur = (driver.current_url or "").lower()
    if any(x in cur for x in ["login", "sign-in", "auth"]) or any(
        x in body for x in ["check your email", "magic link", "log in", "login with email"]
    ):
        raise RuntimeError("Auth check failed")


def ensure_k_units(driver, timeout=10):
    if getattr(driver, "_k_units_attempted", False):
        return
    driver._k_units_attempted = True
    try:
        label = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//label[.//span[contains(@class,'mantine-SegmentedControl-innerLabel') and normalize-space()='K']]",
                )
            )
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
    tables = []
    for el in driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
        rows = extract_rows_from_table(el)
        if rows:
            tables.append(rows)
    return tables


def find_table_by_name(tables, name):
    n = name.strip().lower()
    for table in tables:
        if table and table[0] and table[0][0].strip().lower() == n:
            return table
    return None


def quick_missing_check(driver, ticker, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
            return
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(m in body for m in ["not found", "no results", "no data", "does not exist", "cannot find", "can't find"]):
            raise RuntimeError(f"{ticker} not found on fiscal.ai")
        time.sleep(0.2)


def validate_required_tables(financials):
    missing = []
    for req in ("IS", "BS", "CF"):
        if req not in financials or not financials[req]:
            missing.append(req)

    if "BS" in financials:
        labels = {row[0].strip().lower() for row in financials["BS"] if row}
        if "liabilities" not in labels:
            missing.append("BS:Liabilities")
        if "equity" not in labels:
            missing.append("BS:Equity")

    if "CF" in financials:
        labels = {row[0].strip().lower() for row in financials["CF"] if row}
        if "investing activities" not in labels:
            missing.append("CF:Investing Activities")
        if "financing activities" not in labels:
            missing.append("CF:Financing Activities")

    return missing


def dedupe_rows(rows):
    out, seen = [], set()
    for row in rows or []:
        if not isinstance(row, list):
            continue
        key = tuple((c or "").strip() if isinstance(c, str) else str(c) for c in row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def merge_statement_rows(existing_rows, new_rows):
    return dedupe_rows((existing_rows or []) + (new_rows or []))


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


def load_statement_table(driver, ticker, slug, expand_slider=True, fast_mode=False, skip_slider_if_adequate=True, metrics=None):
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    t_nav = time.perf_counter() - t0

    t0 = time.perf_counter()
    if not fast_mode:
        time.sleep(0.25)
    t_sleep = time.perf_counter() - t0

    t0 = time.perf_counter()
    if slug == "income-statement":
        ensure_k_units(driver)
    t_units = time.perf_counter() - t0

    t0 = time.perf_counter()
    quick_missing_check(driver, ticker, timeout=2 if fast_mode else 4)
    t_missing = time.perf_counter() - t0

    t0 = time.perf_counter()
    slider_skipped = False
    if expand_slider:
        if skip_slider_if_adequate and slider_range_already_adequate(driver):
            slider_skipped = True
        else:
            set_slider_range(driver, min_val=5, max_val=22, key_delay=(0.003 if fast_mode else 0.015))
    t_slider = time.perf_counter() - t0

    t0 = time.perf_counter()
    WebDriverWait(driver, 15 if fast_mode else 20).until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                '[data-sentry-component="TableContent"] tr, [data-sentry-component="TableContent"] [role="row"]',
            )
        )
        > 1
    )
    table_root = wait_for_table(driver, timeout=10 if fast_mode else 15)
    rows = extract_rows_from_table(table_root)
    t_extract = time.perf_counter() - t0

    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{ticker} {slug} returned empty rows")

    if metrics is not None:
        metrics.update(
            {
                "nav": t_nav,
                "sleep": t_sleep,
                "units": t_units,
                "missing": t_missing,
                "slider": t_slider,
                "extract": t_extract,
                "total": time.perf_counter() - t_all,
                "skipped_slider": slider_skipped,
            }
        )
    return rows


def load_page_all_tables(driver, ticker, slug, expand_slider=True, fast_mode=False, skip_slider_if_adequate=True, metrics=None):
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    t_nav = time.perf_counter() - t0

    t0 = time.perf_counter()
    if not fast_mode:
        time.sleep(0.25)
    t_sleep = time.perf_counter() - t0

    t0 = time.perf_counter()
    quick_missing_check(driver, ticker, timeout=2 if fast_mode else 4)
    t_missing = time.perf_counter() - t0

    t0 = time.perf_counter()
    slider_skipped = False
    if expand_slider:
        if skip_slider_if_adequate and slider_range_already_adequate(driver):
            slider_skipped = True
        else:
            set_slider_range(driver, min_val=5, max_val=22, key_delay=(0.003 if fast_mode else 0.015))
    t_slider = time.perf_counter() - t0

    t0 = time.perf_counter()
    WebDriverWait(driver, 15 if fast_mode else 20).until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                '[data-sentry-component="TableContent"] tr, [data-sentry-component="TableContent"] [role="row"]',
            )
        )
        > 1
    )
    time.sleep(0.15 if fast_mode else 0.5)
    tables = extract_all_tables_from_page(driver)
    t_extract = time.perf_counter() - t0

    if metrics is not None:
        metrics.update(
            {
                "nav": t_nav,
                "sleep": t_sleep,
                "missing": t_missing,
                "slider": t_slider,
                "extract": t_extract,
                "total": time.perf_counter() - t_all,
                "skipped_slider": slider_skipped,
            }
        )
    return tables


def pull_supplemental(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    def run_for_exchange(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        result = {}
        metrics_by_slug = {}
        for stmt, config in SUPPLEMENTAL_TABLES.items():
            m = {}
            tables = load_page_all_tables(
                driver,
                fiscal_ticker,
                config["slug"],
                expand_slider=expand_slider,
                fast_mode=fast_mode,
                skip_slider_if_adequate=skip_slider_if_adequate,
                metrics=m,
            )
            metrics_by_slug[config["slug"]] = m
            found = []
            for name in config["names"]:
                t = find_table_by_name(tables, name)
                if t:
                    found.extend(t)
            if found:
                result[stmt] = dedupe_rows(found)
        return result, metrics_by_slug

    try:
        data, metrics = run_for_exchange(exchange)
        return data, exchange, metrics
    except Exception as exc:
        if "not found" in str(exc).lower():
            fallback = "AIM" if exchange != "AIM" else "LSE"
            data, metrics = run_for_exchange(fallback)
            return data, fallback, metrics
        raise


def pull_financials(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    def run_for_exchange(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        rows_by_statement = {}
        metrics_by_slug = {}
        for statement, slugs in STATEMENT_SLUGS.items():
            last_exc = None
            for slug in slugs:
                try:
                    m = {}
                    rows = load_statement_table(
                        driver,
                        fiscal_ticker,
                        slug,
                        expand_slider=expand_slider,
                        fast_mode=fast_mode,
                        skip_slider_if_adequate=skip_slider_if_adequate,
                        metrics=m,
                    )
                    rows_by_statement[statement] = rows
                    metrics_by_slug[slug] = m
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
            if last_exc:
                raise last_exc
        return rows_by_statement, metrics_by_slug

    try:
        data, metrics = run_for_exchange(exchange)
        return data, exchange, metrics
    except Exception as exc:
        if "not found" in str(exc).lower():
            fallback = "AIM" if exchange != "AIM" else "LSE"
            data, metrics = run_for_exchange(fallback)
            return data, fallback, metrics
        raise


def load_failed_set(path):
    if not Path(path).exists():
        return set()
    failed = set()
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if row:
                failed.add(row[0])
    return failed


def build_checkpoint(path):
    cp = load_json(path, default=None)
    if not cp:
        cp = {
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "completed": {},
            "failed": {},
            "in_flight": {},
            "workers": {},
            "meta": {},
        }
    cp.setdefault("completed", {})
    cp.setdefault("failed", {})
    cp.setdefault("in_flight", {})
    cp.setdefault("workers", {})
    cp.setdefault("meta", {})
    return cp


def save_checkpoint(path, checkpoint):
    checkpoint["updated_at"] = utc_now_iso()
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    ensure_parent(path)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def needs_supplemental(ticker_data):
    for stmt, config in SUPPLEMENTAL_TABLES.items():
        if stmt not in ticker_data:
            return True
        existing_labels = {row[0].strip().lower() for row in ticker_data[stmt] if row}
        for name in config["names"]:
            if name.strip().lower() not in existing_labels:
                return True
    return False


def heartbeat_loop(stop_event, state, interval_sec, events_jsonl):
    while not stop_event.wait(interval_sec):
        with state["lock"]:
            processed = state["processed"]
            total = state["total"]
            started_at = state["started_at"]
            ok_count = state["ok_count"]
            failed_count = state["failed_count"]
        elapsed = max(time.time() - started_at, 0.001)
        rate = processed / elapsed
        remaining = max(total - processed, 0)
        eta_sec = remaining / rate if rate > 0 else None
        jsonl_append(
            events_jsonl,
            {
                "event": "heartbeat",
                "processed": processed,
                "total": total,
                "remaining": remaining,
                "ok_count": ok_count,
                "failed_count": failed_count,
                "elapsed_sec": round(elapsed, 2),
                "rate_ticker_per_sec": round(rate, 4),
                "eta_sec": round(eta_sec, 2) if eta_sec is not None else None,
            },
        )
        print(f"[heartbeat] processed={processed}/{total} ok={ok_count} failed={failed_count} rate={rate:.3f}/s")


def main():
    parser = argparse.ArgumentParser(description="Fetch fiscal.ai financials and store in cached_financials.json")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--ticker", type=str, default=TEST_TICKER_DEFAULT, help="Only update a specific ticker")
    parser.add_argument("--magic-link", default="", help="Optional prefilled fiscal.ai magic link")
    parser.add_argument("--tickers-csv", default=DEFAULT_TICKERS_CSV, help="Path to CSV with tickers")
    parser.add_argument("--use-csv", action="store_true", help="Load tickers from --tickers-csv")
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON, help="Output JSON path")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing cached rows")
    parser.add_argument("--no-overwrite", action="store_true", help="Skip tickers already present in cache")
    parser.add_argument("--failed-csv", default=FAILED_CSV_DEFAULT, help="Path for failed ticker CSV")
    parser.add_argument("--no-slider", action="store_true", help="Skip adjusting year range slider")
    parser.add_argument("--fast", action="store_true", default=FAST_MODE_DEFAULT, help="Enable fast mode")
    parser.add_argument("--no-fast", action="store_true", help="Disable fast mode")
    parser.add_argument("--workers", type=int, default=WORKERS_DEFAULT, help="Parallel browser workers")
    parser.add_argument("--checkpoint-json", default=DEFAULT_CHECKPOINT_JSON, help="Resume-safe checkpoint JSON")
    parser.add_argument("--timings-jsonl", default=DEFAULT_TIMINGS_JSONL, help="Structured timing JSONL")
    parser.add_argument("--events-jsonl", default=DEFAULT_EVENTS_JSONL, help="Structured events JSONL")
    parser.add_argument("--heartbeat-seconds", type=int, default=300, help="Heartbeat interval")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed tickers from checkpoint")
    parser.add_argument("--retry-attempts", type=int, default=2, help="Per-ticker retry attempts before mark failed")
    parser.add_argument("--skip-slider-if-adequate", action="store_true", default=True, help="Skip slider when range already broad")
    parser.add_argument("--no-skip-slider-if-adequate", action="store_true", help="Always interact with slider")
    parser.add_argument("--chrome-binary", default=os.getenv("CHROME_BINARY", ""), help="Chrome binary path")
    parser.add_argument("--version-main", type=int, default=144, help="Chrome major version for undetected_chromedriver")
    parser.add_argument("--benchmark-tag", default="", help="Optional benchmark run tag for logs")
    args = parser.parse_args()

    def build_driver():
        options = uc.ChromeOptions()
        if args.chrome_binary:
            options.binary_location = args.chrome_binary
        if args.headless:
            options.add_argument("--headless")
        d = uc.Chrome(options=options, version_main=args.version_main)
        d.implicitly_wait(10)
        return d

    def split_chunks(items, workers):
        if workers <= 1:
            return [items]
        chunks = [[] for _ in range(workers)]
        for idx, item in enumerate(items):
            chunks[idx % workers].append(item)
        return [c for c in chunks if c]

    def retry_call(fn, attempts):
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
    checkpoint = build_checkpoint(args.checkpoint_json)
    state = {"lock": lock, "processed": 0, "total": 0, "started_at": time.time(), "ok_count": 0, "failed_count": 0}

    try:
        use_csv = args.use_csv or not USE_TEST_TICKER
        ticker_market = {}
        if use_csv:
            with open(args.tickers_csv, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)
                tickers = []
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    ticker = row[0].strip()
                    tickers.append(ticker)
                    if len(row) >= 2 and row[1].strip():
                        ticker_market[ticker] = normalize_exchange(row[1].strip())
        elif args.ticker:
            tickers = [args.ticker]
        else:
            tickers = []

        cached = load_json(args.out_json, default={})
        failed_existing = load_failed_set(args.failed_csv)

        pending = []
        for t in tickers:
            if t in checkpoint["completed"]:
                continue
            if not args.retry_failed and t in checkpoint["failed"]:
                continue
            pending.append(t)

        if not pending:
            print("No tickers to process")
            return

        workers = max(1, int(args.workers or WORKERS_DEFAULT))
        chunks = split_chunks(pending, workers)

        with lock:
            state["total"] = len(pending)
            checkpoint["meta"].update(
                {
                    "workers": len(chunks),
                    "fast_mode": args.fast and not args.no_fast,
                    "retry_attempts": args.retry_attempts,
                    "benchmark_tag": args.benchmark_tag,
                    "run_started_at": utc_now_iso(),
                }
            )
            save_checkpoint(args.checkpoint_json, checkpoint)

        drivers = []
        primary_driver = build_driver()
        drivers.append(primary_driver)

        magic_link = args.magic_link.strip() if args.magic_link else start_login_flow(primary_driver)
        for _ in range(len(chunks) - 1):
            drivers.append(build_driver())
        for d in drivers:
            open_magic_link(d, magic_link)
            assert_authenticated_with_full_financials(d)

        stop_event = Event()
        hb = Thread(
            target=heartbeat_loop,
            args=(stop_event, state, max(30, int(args.heartbeat_seconds)), args.events_jsonl),
            daemon=True,
        )
        hb.start()

        fast_mode = args.fast and not args.no_fast
        skip_slider_if_adequate = args.skip_slider_if_adequate and not args.no_skip_slider_if_adequate

        def worker_run(worker_id, driver, worker_tickers):
            for t in worker_tickers:
                if not t:
                    continue
                with lock:
                    if SKIP_IF_FAILED and t in failed_existing:
                        continue
                    ticker_exchange = ticker_market.get(t, "LSE")
                    is_cached = t in cached
                    checkpoint["in_flight"][str(worker_id)] = {
                        "ticker": t,
                        "exchange": ticker_exchange,
                        "kind": "supplemental" if is_cached else "full",
                        "started_at": utc_now_iso(),
                    }
                    checkpoint["workers"][str(worker_id)] = {"state": "running", "ticker": t, "ts": utc_now_iso()}
                    save_checkpoint(args.checkpoint_json, checkpoint)

                if is_cached and not needs_supplemental(cached[t]):
                    with lock:
                        checkpoint["completed"][t] = {"at": utc_now_iso(), "kind": "already_complete"}
                        checkpoint["in_flight"].pop(str(worker_id), None)
                        state["processed"] += 1
                        state["ok_count"] += 1
                        save_checkpoint(args.checkpoint_json, checkpoint)
                    continue

                started = time.perf_counter()
                kind = "supplemental" if is_cached else "full"
                try:
                    if is_cached:
                        def run():
                            return pull_supplemental(
                                driver,
                                t,
                                exchange=ticker_exchange,
                                expand_slider=not args.no_slider,
                                fast_mode=fast_mode,
                                skip_slider_if_adequate=skip_slider_if_adequate,
                            )

                        (supp, used_exchange, metrics_by_slug), attempts = retry_call(run, args.retry_attempts)
                        with lock:
                            for stmt, rows in supp.items():
                                cached[t][stmt] = merge_statement_rows(cached[t].get(stmt, []), rows)
                            save_json(args.out_json, cached)
                        row_counts = {k: len(cached[t].get(k, [])) for k in ("IS", "BS", "CF")}
                        payload_metrics = metrics_by_slug
                    else:
                        def run():
                            return pull_financials(
                                driver,
                                t,
                                exchange=ticker_exchange,
                                expand_slider=not args.no_slider,
                                fast_mode=fast_mode,
                                skip_slider_if_adequate=skip_slider_if_adequate,
                            )

                        (financials, used_exchange, metrics_by_slug), attempts = retry_call(run, args.retry_attempts)
                        with lock:
                            cached[t] = financials
                            save_json(args.out_json, cached)
                        row_counts = {k: len(financials.get(k, [])) for k in ("IS", "BS", "CF")}
                        payload_metrics = metrics_by_slug

                    missing = validate_required_tables(cached[t] if is_cached else financials)
                    if missing:
                        raise RuntimeError("validation missing: " + ", ".join(missing))

                    elapsed = time.perf_counter() - started
                    with lock:
                        checkpoint["completed"][t] = {
                            "at": utc_now_iso(),
                            "kind": kind,
                            "exchange": used_exchange,
                            "elapsed_sec": round(elapsed, 3),
                            "attempts": attempts,
                            "rows": row_counts,
                        }
                        checkpoint["failed"].pop(t, None)
                        checkpoint["in_flight"].pop(str(worker_id), None)
                        state["processed"] += 1
                        state["ok_count"] += 1
                        save_checkpoint(args.checkpoint_json, checkpoint)

                    jsonl_append(
                        args.timings_jsonl,
                        {
                            "event": "ticker_done",
                            "ticker": t,
                            "worker_id": worker_id,
                            "kind": kind,
                            "status": "ok",
                            "exchange": used_exchange,
                            "attempts": attempts,
                            "elapsed_sec": round(elapsed, 3),
                            "section_timings": payload_metrics,
                            "rows": row_counts,
                            "benchmark_tag": args.benchmark_tag or None,
                        },
                        lock=lock,
                    )
                except Exception as exc:
                    elapsed = time.perf_counter() - started
                    reason = str(exc)
                    reason_type = classify_error(exc)
                    with lock:
                        prev = checkpoint["failed"].get(t, {})
                        checkpoint["failed"][t] = {
                            "at": utc_now_iso(),
                            "kind": kind,
                            "exchange": ticker_exchange,
                            "elapsed_sec": round(elapsed, 3),
                            "attempts": int(prev.get("attempts", 0)) + 1,
                            "reason": reason,
                            "reason_type": reason_type,
                        }
                        checkpoint["in_flight"].pop(str(worker_id), None)
                        state["processed"] += 1
                        state["failed_count"] += 1
                        save_checkpoint(args.checkpoint_json, checkpoint)
                        if t not in failed_existing:
                            failed_existing.add(t)
                            ensure_parent(args.failed_csv)
                            with open(args.failed_csv, "a", newline="") as f:
                                csv.writer(f).writerow([t, ticker_exchange, reason_type, reason])

                    jsonl_append(
                        args.timings_jsonl,
                        {
                            "event": "ticker_done",
                            "ticker": t,
                            "worker_id": worker_id,
                            "kind": kind,
                            "status": "failed",
                            "elapsed_sec": round(elapsed, 3),
                            "reason": reason,
                            "reason_type": reason_type,
                            "benchmark_tag": args.benchmark_tag or None,
                        },
                        lock=lock,
                    )
                    jsonl_append(
                        args.events_jsonl,
                        {
                            "event": "ticker_failed",
                            "ticker": t,
                            "worker_id": worker_id,
                            "kind": kind,
                            "reason": reason,
                            "reason_type": reason_type,
                        },
                        lock=lock,
                    )

        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [executor.submit(worker_run, idx, d, chunk) for idx, (d, chunk) in enumerate(zip(drivers, chunks), start=1)]
            for fut in as_completed(futures):
                fut.result()

        stop_event.set()
        hb.join(timeout=2)

        with lock:
            jsonl_append(
                args.events_jsonl,
                {
                    "event": "run_complete",
                    "processed": state["processed"],
                    "total": state["total"],
                    "ok_count": state["ok_count"],
                    "failed_count": state["failed_count"],
                    "completed_count": len(checkpoint["completed"]),
                    "failed_checkpoint_count": len(checkpoint["failed"]),
                },
                lock=lock,
            )
        print("Done")
    finally:
        for d in locals().get("drivers", []):
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
