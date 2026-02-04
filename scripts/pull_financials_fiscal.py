import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://fiscal.ai"

BASE_DIR = Path(__file__).resolve().parent


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


def set_slider_range(driver, min_val=5, max_val=22, key_delay=0.02):
    """Adjust the Mantine range slider thumbs to expand year range."""
    thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
    if len(thumbs) < 2:
        print(f"Expected 2 slider thumbs, found {len(thumbs)}")
        return False

    from selenium.webdriver.common.keys import Keys

    # First thumb (left) - set to min_val
    left_thumb = thumbs[0]
    current_left = int(left_thumb.get_attribute("aria-valuenow"))
    left_thumb.click()
    time.sleep(0.1)
    # Move left (decrease value)
    for _ in range(current_left - min_val):
        left_thumb.send_keys(Keys.ARROW_LEFT)
        time.sleep(key_delay)
    print(f"Set left thumb from {current_left} to {min_val}")

    # Second thumb (right) - set to max_val
    right_thumb = thumbs[1]
    current_right = int(right_thumb.get_attribute("aria-valuenow"))
    right_thumb.click()
    time.sleep(0.1)
    # Move right (increase value)
    for _ in range(max_val - current_right):
        right_thumb.send_keys(Keys.ARROW_RIGHT)
        time.sleep(key_delay)
    print(f"Set right thumb from {current_right} to {max_val}")

    time.sleep(0.2)
    return True


def build_fiscal_ticker(ticker, exchange):
    if "-" in ticker:
        return ticker
    return f"{exchange}-{ticker}"


def navigate_to_login(driver):
    """Navigate to the fiscal.ai login page and enter email."""
    driver.get(URL)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    print(f"Loaded {URL}")
    time.sleep(1)  # Let page fully render

    # Click the login button
    try:
        login_btn = driver.find_element(By.ID, "ph-marketing-header__sign-up-button")
        print(f"Found login button: {login_btn.text}")
        driver.execute_script("arguments[0].scrollIntoView(true);", login_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", login_btn)
        print("Clicked login button via JS")
    except Exception as e:
        print(f"Could not click login button: {e}")
        print("Page source snippet:")
        print(driver.page_source[:2000])
        raise

    # Enter email
    email_input = wait_for(driver, By.CSS_SELECTOR, "input[placeholder='your@email.com']", timeout=10)
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

    if magic_link:
        driver.get(magic_link)
        wait_for(driver, By.TAG_NAME, "body", timeout=15)
        print(f"Navigated to magic link. Current URL: {driver.current_url}")
        time.sleep(1)


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


def load_statement_table(driver, ticker, slug, expand_slider=True, fast_mode=False):
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    print(f"Loaded {url}")
    if not fast_mode:
        time.sleep(1)

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


STATEMENT_SLUGS = {
    "IS": ["income-statement", "income"],
    "BS": ["balance-sheet", "balance"],
    "CF": ["cash-flow-statement", "cash-flow-statement", "cashflow-statement"],
}


def pull_financials(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False):
    fiscal_ticker = build_fiscal_ticker(ticker, exchange)
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
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc:
            raise last_exc

    return rows_by_statement


def load_cached_json(path):
    if not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cached_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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
        default="LSE-SHEL",
        help="Only update a specific ticker",
    )
    parser.add_argument(
        "--tickers-csv",
        default=str((BASE_DIR / ".." / "ftse_tickers.csv").resolve()),
        help="Path to CSV with tickers (default: ftse_tickers.csv in repo root)",
    )
    parser.add_argument(
        "--use-csv",
        action="store_true",
        help="Load tickers from --tickers-csv instead of --ticker",
    )
    parser.add_argument(
        "--exchange",
        default="LSE",
        help="Exchange prefix for fiscal.ai tickers (default: LSE)",
    )
    parser.add_argument(
        "--out-json",
        default=str((BASE_DIR / ".." / "cached_financials.json").resolve()),
        help="Output JSON path (default: cached_financials.json in repo root)",
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
        "--no-slider",
        action="store_true",
        help="Skip adjusting the year range slider",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Reduce fixed sleeps and tighten waits (may be less stable)",
    )
    args = parser.parse_args()

    options = uc.ChromeOptions()
    if args.headless:
        options.add_argument("--headless")

    driver = uc.Chrome(options=options)
    driver.implicitly_wait(10)

    try:
        navigate_to_login(driver)
        print("Successfully logged in.")
        print(f"Current URL: {driver.current_url}")

        if args.use_csv:
            with open(args.tickers_csv, newline="") as f:
                tickers = [row[0] for row in csv.reader(f) if row]
        elif args.ticker:
            tickers = [args.ticker]
        else:
            tickers = []

        cached = load_cached_json(args.out_json)

        for t in tickers:
            if not t:
                continue
            if args.no_overwrite and t in cached:
                print(f"{t} already cached. Skipping.")
                continue
            try:
                financials = pull_financials(
                    driver,
                    t,
                    exchange=args.exchange,
                    expand_slider=not args.no_slider,
                    fast_mode=args.fast,
                )
                cached[t] = financials
                save_cached_json(args.out_json, cached)
                print(f"Saved cached financials for {t}")
            except Exception as e:
                print(f"Failed {t}: {e}")

        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
