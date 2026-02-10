import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://fiscal.ai"
FAST_MODE_DEFAULT = True
WORKERS_DEFAULT = 4

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_JSON = str((BASE_DIR / ".." / "cached_financials_2.json").resolve())
FAILED_CSV_DEFAULT = str((BASE_DIR / ".." / "financials_failed.csv").resolve())
DEFAULT_TICKERS_CSV = str((BASE_DIR / ".." / "lse_all_tickers.csv").resolve())
USE_TEST_TICKER = False
TEST_TICKER_DEFAULT = "LSE-SHEL"
SKIP_IF_CACHED = True
SKIP_IF_FAILED = False  # Retry failed tickers


def ensure_django():
    project_root = BASE_DIR.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django
        from django.apps import apps
        if not apps.ready:
            django.setup()
    except Exception:
        import django
        django.setup()


def wait_for(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def wait_clickable(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


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
    time.sleep(0.12)


def _take_slider_debug(driver, label):
    try:
        out_dir = (BASE_DIR / ".." / "tmp" / "slider_debug").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        path = out_dir / f"{label}_{ts}.png"
        driver.save_screenshot(str(path))
        print(f"[slider] debug screenshot: {path}")
    except Exception as exc:
        print(f"[slider] screenshot failed: {exc}")


def _wait_slider_unobstructed(driver, thumb, timeout=4):
    def _ok(_):
        return driver.execute_script(
            """
            const thumb = arguments[0];
            if (!thumb) return false;
            const r = thumb.getBoundingClientRect();
            const x = r.left + r.width / 2;
            const y = r.top + r.height / 2;
            const top = document.elementFromPoint(x, y);
            return !!top && (top === thumb || thumb.contains(top));
            """,
            thumb,
        )

    try:
        WebDriverWait(driver, timeout).until(_ok)
        return True
    except Exception:
        return False


def _set_thumb_to_value(driver, thumb, target_val, is_left_thumb, key_delay=0.02):
    _scroll_into_safe_viewport(driver, thumb)

    if not _wait_slider_unobstructed(driver, thumb, timeout=2):
        print("[slider] thumb appears obstructed before interaction; attempting anyway")

    current_val = int(thumb.get_attribute("aria-valuenow"))
    if current_val == target_val:
        return True

    # Attempt 1: focus + keyboard steps (most reliable when focus lands correctly)
    try:
        driver.execute_script("arguments[0].focus();", thumb)
        safe_click(driver, thumb)
        key = Keys.ARROW_LEFT if target_val < current_val else Keys.ARROW_RIGHT
        for _ in range(abs(target_val - current_val)):
            thumb.send_keys(key)
            time.sleep(key_delay)
        if int(thumb.get_attribute("aria-valuenow")) == target_val:
            return True
    except Exception as exc:
        print(f"[slider] keyboard adjustment failed: {exc}")

    # Attempt 2: drag the thumb by x-offset
    try:
        min_v = int(thumb.get_attribute("aria-valuemin") or "0")
        max_v = int(thumb.get_attribute("aria-valuemax") or "100")
        slider = driver.execute_script(
            "return arguments[0].closest('[class*=\"Slider-root\"], [class*=\"Slider-trackContainer\"], [class*=\"Slider-track\"]')",
            thumb,
        )
        width = driver.execute_script("return arguments[0].getBoundingClientRect().width", slider) if slider else 0
        value_span = max(max_v - min_v, 1)
        px_per_unit = (width / value_span) if width else 6
        delta = target_val - int(thumb.get_attribute("aria-valuenow"))
        x_offset = int(delta * px_per_unit)
        ActionChains(driver).move_to_element(thumb).click_and_hold(thumb).move_by_offset(x_offset, 0).release().perform()
        time.sleep(0.12)
        if int(thumb.get_attribute("aria-valuenow")) == target_val:
            return True
    except Exception as exc:
        print(f"[slider] drag adjustment failed: {exc}")

    # Attempt 3: direct JS aria + events fallback
    try:
        driver.execute_script(
            """
            const thumb = arguments[0], target = String(arguments[1]);
            thumb.setAttribute('aria-valuenow', target);
            const ev1 = new Event('input', { bubbles: true });
            const ev2 = new Event('change', { bubbles: true });
            thumb.dispatchEvent(ev1);
            thumb.dispatchEvent(ev2);
            """,
            thumb,
            int(target_val),
        )
        time.sleep(0.12)
        # Nudge via key so React/Mantine state reconciles from focused element
        driver.execute_script("arguments[0].focus();", thumb)
        if is_left_thumb:
            thumb.send_keys(Keys.ARROW_RIGHT)
            thumb.send_keys(Keys.ARROW_LEFT)
        else:
            thumb.send_keys(Keys.ARROW_LEFT)
            thumb.send_keys(Keys.ARROW_RIGHT)
        time.sleep(0.05)
        if int(thumb.get_attribute("aria-valuenow")) == target_val:
            return True
    except Exception as exc:
        print(f"[slider] JS fallback failed: {exc}")

    return int(thumb.get_attribute("aria-valuenow")) == target_val


def set_slider_range(driver, min_val=5, max_val=22, key_delay=0.02):
    """Adjust Mantine range slider thumbs with robust headless-safe fallbacks."""
    thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
    if len(thumbs) < 2:
        print(f"[slider] Expected 2 slider thumbs, found {len(thumbs)}")
        _take_slider_debug(driver, "thumbs_missing")
        return False

    left_thumb, right_thumb = thumbs[0], thumbs[1]

    left_before = int(left_thumb.get_attribute("aria-valuenow"))
    right_before = int(right_thumb.get_attribute("aria-valuenow"))

    for attempt in range(1, 4):
        ok_left = _set_thumb_to_value(driver, left_thumb, min_val, is_left_thumb=True, key_delay=key_delay)
        ok_right = _set_thumb_to_value(driver, right_thumb, max_val, is_left_thumb=False, key_delay=key_delay)

        left_after = int(left_thumb.get_attribute("aria-valuenow"))
        right_after = int(right_thumb.get_attribute("aria-valuenow"))
        print(
            f"[slider] attempt={attempt} left {left_before}->{left_after} target={min_val} "
            f"right {right_before}->{right_after} target={max_val}"
        )

        if ok_left and ok_right and left_after == min_val and right_after == max_val:
            time.sleep(0.2)
            return True

        _take_slider_debug(driver, f"slider_attempt_{attempt}")
        time.sleep(0.2)

    print("[slider] Failed to set desired range after retries")
    return False


def build_fiscal_ticker(ticker, exchange):
    if "-" in ticker:
        return ticker
    return f"{exchange}-{ticker}"


def start_login_flow(driver):
    """Navigate to fiscal.ai, enter email, and return magic link."""
    driver.get(URL)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    print(f"Loaded {URL}")
    time.sleep(1)  # Let page fully render

    def click_login():
        login_btn = driver.find_element(By.ID, "ph-marketing-header__sign-up-button")
        print(f"Found login button: {login_btn.text}")
        driver.execute_script("arguments[0].scrollIntoView(true);", login_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", login_btn)
        print("Clicked login button via JS")

    # Click the login button
    try:
        click_login()
    except Exception as e:
        print(f"Could not click login button: {e}")
        print("Page source snippet:")
        print(driver.page_source[:2000])
        raise

    # Enter email (retry once if the modal doesn't appear)
    email_selectors = [
        "input[placeholder='your@email.com']",
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='@']",
    ]
    email_input = None
    for _ in range(2):
        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ",".join(email_selectors)))
            )
            break
        except Exception:
            driver.refresh()
            wait_for(driver, By.TAG_NAME, "body", timeout=15)
            time.sleep(1)
            click_login()

    if email_input is None:
        raise RuntimeError("Email input not found after clicking login.")

    email_input.clear()
    email_input.send_keys("matthew_newell@outlook.com")
    print("Entered email")

    # Submit the email (look for submit button)
    try:
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)
        print("Clicked submit")
    except Exception:
        # Try pressing Enter instead
        from selenium.webdriver.common.keys import Keys
        email_input.send_keys(Keys.RETURN)
        print("Pressed Enter to submit")

    time.sleep(0.5)
    print("\nCheck your email for the sign-in link.")
    magic_link = input("Paste the sign-in link here: ").strip()
    return magic_link


def open_magic_link(driver, magic_link):
    if not magic_link:
        raise RuntimeError("Magic link missing.")
    driver.get(magic_link)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    print(f"Navigated to magic link. Current URL: {driver.current_url}")
    time.sleep(1)


def assert_authenticated_with_full_financials(driver):
    """Auth gate without parking all windows on a probe ticker."""
    driver.get(f"{URL}/dashboard")
    wait_for(driver, By.TAG_NAME, "body", timeout=12)
    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    cur = (driver.current_url or "").lower()

    if any(x in cur for x in ["login", "sign-in", "auth"]) or any(
        x in body_text for x in ["check your email", "magic link", "log in", "login with email"]
    ):
        raise RuntimeError("Auth check failed: worker appears logged out")


def wait_for_table(driver, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'))
    )


def extract_rows_from_table(table_root):
    rows = table_root.find_elements(By.CSS_SELECTOR, "tr")
    if not rows:
        rows = table_root.find_elements(By.CSS_SELECTOR, "[role='row']")
    if not rows:
        rows = table_root.find_elements(By.CSS_SELECTOR, ":scope > *")

    parsed = []
    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "th, td")
        if not cells:
            cells = row.find_elements(By.CSS_SELECTOR, "[role='columnheader'], [role='cell']")
        if not cells:
            cells = row.find_elements(By.CSS_SELECTOR, ":scope > *")
        values = [c.text.strip() for c in cells]
        if len(values) >= 2 and any(values[1:]):
            parsed.append(values)

    return parsed


def extract_all_tables_from_page(driver):
    """Find all TableContent elements on the page and extract rows from each."""
    elements = driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]')
    tables = []
    for el in elements:
        rows = extract_rows_from_table(el)
        if rows:
            tables.append(rows)
    return tables


def find_table_by_name(tables, name):
    """Find a table whose first row's first cell matches the given name."""
    name_lower = name.strip().lower()
    for table in tables:
        if table and table[0]:
            label = table[0][0].strip().lower()
            if label == name_lower:
                return table
    return None


def load_statement_table(driver, ticker, slug, expand_slider=True, fast_mode=False):
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    print(f"Loaded {url}")
    if not fast_mode:
        time.sleep(1)

    if slug == "income-statement":
        ensure_k_units(driver)

    quick_missing_check(driver, ticker, timeout=3 if fast_mode else 5)

    if expand_slider:
        key_delay = 0.005 if fast_mode else 0.02
        set_slider_range(driver, min_val=5, max_val=22, key_delay=key_delay)

    WebDriverWait(driver, 20).until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                '[data-sentry-component="TableContent"] tr, [data-sentry-component="TableContent"] [role="row"]',
            )
        )
        > 1
    )
    table_root = wait_for_table(driver, timeout=15 if fast_mode else 20)
    rows = extract_rows_from_table(table_root)
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{ticker} {slug} returned empty rows.")
    return rows


def ensure_k_units(driver, timeout=10):
    if getattr(driver, "_k_units_attempted", False):
        return
    driver._k_units_attempted = True
    try:
        label = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//label[.//span[contains(@class,'mantine-SegmentedControl-innerLabel')"
                    " and normalize-space()='K']]",
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", label)
        time.sleep(0.1)
        if label.get_attribute("data-active") != "true":
            safe_click(driver, label)
        time.sleep(0.2)
        driver._k_units_set = True
        print("Set financial units to K")
    except Exception as exc:
        print(f"Failed to set financial units to K: {exc}")


def quick_missing_check(driver, ticker, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
            return
        if is_ticker_not_found(driver):
            raise RuntimeError(f"{ticker} not found on fiscal.ai")
        time.sleep(0.2)


def is_ticker_not_found(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return False
    markers = (
        "not found",
        "no results",
        "no data",
        "does not exist",
        "can't find",
        "cannot find",
    )
    return any(m in body for m in markers)


STATEMENT_SLUGS = {
    "IS": ["income-statement"],
    "BS": ["balance-sheet"],
    "CF": ["cash-flow-statement"],
}

SUPPLEMENTAL_TABLES = {
    "BS": {
        "slug": "balance-sheet",
        "names": ["Liabilities", "Equity"],
    },
    "CF": {
        "slug": "cash-flow-statement",
        "names": ["Investing Activities", "Financing Activities"],
    },
}


def load_page_all_tables(driver, ticker, slug, expand_slider=True, fast_mode=False):
    """Load a statement page and return all tables found on it."""
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    if not fast_mode:
        time.sleep(1)

    quick_missing_check(driver, ticker, timeout=3 if fast_mode else 5)

    if expand_slider:
        key_delay = 0.005 if fast_mode else 0.02
        set_slider_range(driver, min_val=5, max_val=22, key_delay=key_delay)

    # Wait for at least one table with rows
    WebDriverWait(driver, 20).until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                '[data-sentry-component="TableContent"] tr, '
                '[data-sentry-component="TableContent"] [role="row"]',
            )
        )
        > 1
    )
    # Extra time for all sub-tables to render
    time.sleep(1.5 if not fast_mode else 0.5)

    return extract_all_tables_from_page(driver)


def pull_supplemental(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False):
    """Pull missing sub-tables (Liabilities, Equity, Investing, Financing) for a cached ticker."""

    def run_for_exchange(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        result = {}
        for statement, config in SUPPLEMENTAL_TABLES.items():
            all_tables = load_page_all_tables(
                driver,
                fiscal_ticker,
                config["slug"],
                expand_slider=expand_slider,
                fast_mode=fast_mode,
            )
            print(f"  Found {len(all_tables)} table(s) on {config['slug']} page for {ticker}")
            found_rows = []
            for name in config["names"]:
                table = find_table_by_name(all_tables, name)
                if table:
                    found_rows.extend(table)
                    print(f"  Found '{name}' table ({len(table)} rows)")
                else:
                    print(f"  Warning: Could not find '{name}' table for {ticker}")
            if found_rows:
                result[statement] = found_rows
        return result

    try:
        return run_for_exchange(exchange), exchange
    except Exception as exc:
        if "not found" in str(exc).lower():
            fallback = "AIM" if exchange != "AIM" else "LSE"
            print(f"{ticker} not found on {exchange}. Retrying with {fallback}.")
            return run_for_exchange(fallback), fallback
        raise


def pull_financials(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False):
    def run_for_exchange(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        rows_by_statement = {}
        for statement, slugs in STATEMENT_SLUGS.items():
            last_exc = None
            for slug in slugs:
                try:
                    rows = load_statement_table(
                        driver,
                        fiscal_ticker,
                        slug,
                        expand_slider=expand_slider,
                        fast_mode=fast_mode,
                    )
                    rows_by_statement[statement] = rows
                    print(f"[{ticker}] statement {statement} captured rows={len(rows)}")
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
            if last_exc:
                raise last_exc
        return rows_by_statement

    try:
        return run_for_exchange(exchange), exchange
    except Exception as exc:
        if "not found" in str(exc).lower():
            fallback = "AIM" if exchange != "AIM" else "LSE"
            print(f"{ticker} not found on {exchange}. Retrying with {fallback}.")
            return run_for_exchange(fallback), fallback
        raise


def load_cached_json(path):
    if not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cached_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_failed_set(path):
    if not Path(path).exists():
        return set()
    failed = set()
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                failed.add(row[0])
    return failed



def main():
    parser = argparse.ArgumentParser(description="Fetch fiscal.ai financials and store in cached_financials.json.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=TEST_TICKER_DEFAULT,
        help="Only update a specific ticker",
    )
    parser.add_argument(
        "--magic-link",
        default="",
        help="Optional prefilled fiscal.ai magic link to skip interactive paste",
    )
    parser.add_argument(
        "--tickers-csv",
        default=DEFAULT_TICKERS_CSV,
        help="Path to CSV with tickers (default: lse_all_tickers.csv in repo root)",
    )
    parser.add_argument(
        "--use-csv",
        action="store_true",
        help="Load tickers from --tickers-csv instead of --ticker",
    )
    parser.add_argument(
        "--out-json",
        default=DEFAULT_OUT_JSON,
        help="Output JSON path (default: cached_financials_2.json in repo root)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing cached rows for each ticker",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip tickers already present in cached_financials.json",
    )
    parser.add_argument(
        "--failed-csv",
        default=FAILED_CSV_DEFAULT,
        help="Path for CSV list of tickers that failed",
    )
    parser.add_argument(
        "--no-slider",
        action="store_true",
        help="Skip adjusting the year range slider",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=FAST_MODE_DEFAULT,
        help="Reduce fixed sleeps and tighten waits (may be less stable)",
    )
    parser.add_argument(
        "--no-fast",
        action="store_true",
        help="Disable fast mode for extra stability",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS_DEFAULT,
        help=f"Number of parallel browser workers (default: {WORKERS_DEFAULT})",
    )
    args = parser.parse_args()

    def build_driver():
        options = uc.ChromeOptions()
        if args.headless:
            options.add_argument("--headless")
        d = uc.Chrome(options=options, version_main=144)
        d.implicitly_wait(10)
        return d

    def split_chunks(items, workers):
        if workers <= 1:
            return [items]
        chunks = [[] for _ in range(workers)]
        for idx, item in enumerate(items):
            chunks[idx % workers].append(item)
        return [c for c in chunks if c]

    def needs_supplemental(ticker_data):
        """Check if a cached ticker is missing any supplemental tables."""
        for stmt, config in SUPPLEMENTAL_TABLES.items():
            if stmt not in ticker_data:
                return True
            existing_labels = {row[0].strip().lower() for row in ticker_data[stmt] if row}
            for name in config["names"]:
                if name.strip().lower() not in existing_labels:
                    return True
        return False

    def worker_run(worker_id, driver, tickers, cached, failed_existing, ticker_market, lock):
        failed = []
        fast_mode = args.fast and not args.no_fast
        consecutive_full_ok = 0
        for t in tickers:
            if not t:
                continue
            with lock:
                if SKIP_IF_FAILED and t in failed_existing:
                    print(f"[{worker_id}] {t} is in failed list. Skipping.")
                    continue

                is_cached = t in cached

                # If cached, check if supplemental data is needed
                if is_cached and not needs_supplemental(cached[t]):
                    print(f"[{worker_id}] {t} already has full data. Skipping.")
                    continue

                if not is_cached and args.no_overwrite and t in cached:
                    print(f"[{worker_id}] {t} already cached. Skipping.")
                    continue

                ticker_exchange = ticker_market.get(t, "LSE")

            if is_cached:
                # Pull only the missing supplemental tables
                try:
                    print(f"[{worker_id}] {t} cached but missing sub-tables. Pulling supplemental (trying {ticker_exchange})...")
                    supplemental, used_exchange = pull_supplemental(
                        driver,
                        t,
                        exchange=ticker_exchange,
                        expand_slider=not args.no_slider,
                        fast_mode=fast_mode,
                    )
                    with lock:
                        for stmt, rows in supplemental.items():
                            if stmt in cached[t]:
                                cached[t][stmt].extend(rows)
                            else:
                                cached[t][stmt] = rows
                        save_cached_json(args.out_json, cached)
                    print(f"[{worker_id}] Saved supplemental data for {t} (exchange: {used_exchange})")
                except Exception as e:
                    consecutive_full_ok = 0
                    print(f"[{worker_id}] Failed supplemental for {t}: {e}")
                    failed.append(t)
                    with lock:
                        if t not in failed_existing:
                            failed_existing.add(t)
                            try:
                                with open(args.failed_csv, "a", newline="") as f:
                                    writer = csv.writer(f)
                                    writer.writerow([t])
                            except Exception as write_exc:
                                print(f"[{worker_id}] Failed to write {t} to {args.failed_csv}: {write_exc}")
            else:
                # Full pull for new tickers
                try:
                    financials, used_exchange = pull_financials(
                        driver,
                        t,
                        exchange=ticker_exchange,
                        expand_slider=not args.no_slider,
                        fast_mode=fast_mode,
                    )
                    with lock:
                        cached[t] = financials
                        save_cached_json(args.out_json, cached)
                    trio_ok = all(k in financials and financials[k] for k in ("IS", "BS", "CF"))
                    row_counts = {k: len(financials.get(k, [])) for k in ("IS", "BS", "CF")}
                    consecutive_full_ok = consecutive_full_ok + 1 if trio_ok else 0
                    print(
                        f"[{worker_id}] FULL_OK ticker={t} exchange={used_exchange} "
                        f"IS={row_counts['IS']} BS={row_counts['BS']} CF={row_counts['CF']} "
                        f"TRIO={'Y' if trio_ok else 'N'} STREAK={consecutive_full_ok}"
                    )
                except Exception as e:
                    consecutive_full_ok = 0
                    print(f"[{worker_id}] Failed {t}: {e}")
                    failed.append(t)
                    with lock:
                        if t not in failed_existing:
                            failed_existing.add(t)
                            try:
                                with open(args.failed_csv, "a", newline="") as f:
                                    writer = csv.writer(f)
                                    writer.writerow([t])
                            except Exception as write_exc:
                                print(f"[{worker_id}] Failed to write {t} to {args.failed_csv}: {write_exc}")
        return failed

    drivers = []
    try:
        use_csv = args.use_csv or not USE_TEST_TICKER
        ticker_market = {}
        if use_csv:
            with open(args.tickers_csv, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                tickers = []
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    ticker = row[0].strip()
                    tickers.append(ticker)
                    if len(row) >= 2 and row[1].strip():
                        ticker_market[ticker] = row[1].strip()
        elif args.ticker:
            tickers = [args.ticker]
        else:
            tickers = []

        cached = load_cached_json(args.out_json)
        failed_existing = load_failed_set(args.failed_csv)

        workers = max(1, int(args.workers or WORKERS_DEFAULT))
        chunks = split_chunks(tickers, workers)
        if not chunks:
            print("No tickers to process.")
            return
        primary_driver = build_driver()
        drivers.append(primary_driver)
        if args.magic_link:
            magic_link = args.magic_link.strip()
            print("Using provided magic link (skipping interactive paste)")
        else:
            magic_link = start_login_flow(primary_driver)

        for _ in range(len(chunks) - 1):
            d = build_driver()
            drivers.append(d)

        for idx, d in enumerate(drivers, start=1):
            open_magic_link(d, magic_link)
            assert_authenticated_with_full_financials(d)
            print(f"Successfully logged in (window {idx}/{len(drivers)}).")
            print(f"Current URL: {d.current_url}")

        lock = Lock()
        failed = []
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = []
            for idx, (d, chunk) in enumerate(zip(drivers, chunks), start=1):
                futures.append(executor.submit(worker_run, idx, d, chunk, cached, failed_existing, ticker_market, lock))
            for fut in as_completed(futures):
                try:
                    failed.extend(fut.result())
                except Exception as e:
                    print(f"Worker error: {e}")

        if failed:
            print(f"Appended {len(failed)} failures to {args.failed_csv}")

        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
