import argparse
import csv
import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

URL = "https://quickfs.net"

BASE_DIR = Path(__file__).resolve().parent
CACHE_PATH = (BASE_DIR / ".." / "cached_financials.json").resolve()


def wait_for(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def wait_clickable(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


def safe_click(driver, element):
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def login(driver, retries=2):
    last_exc = None
    for _ in range(retries):
        try:
            driver.get(f"{URL}/login")
            email = wait_for(driver, By.CSS_SELECTOR, "input[type='email']", timeout=20)
            password = wait_for(driver, By.CSS_SELECTOR, "input[type='password']", timeout=20)
            email.clear()
            email.send_keys("matthew_newell@outlook.com")
            password.clear()
            password.send_keys("supergas02")
            submit = wait_clickable(driver, By.ID, "submitLoginFormBtn", timeout=20)
            safe_click(driver, submit)
            WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.ID, "submitLoginFormBtn")))
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(1.5)
    raise last_exc


def is_unknown_ticker(page_text):
    text = page_text.lower()
    return ("unknown symbol" in text and "logged for future addition" in text) or (
        "unknown ticker" in text and "future addition" in text
    )

def is_login_page(page_text):
    text = page_text.lower()
    return "submitloginformbtn" in text or "login" in text and "password" in text


def pull_financials(driver, ticker):

    driver.get(f"{URL}/company/{ticker}:LN")
    driver.implicitly_wait(10)
    wait_for(driver, By.TAG_NAME, "body", timeout=8)
    page_text = driver.page_source
    if is_unknown_ticker(page_text):
        raise RuntimeError(f"{ticker} not found on QuickFS.")
    try:
        WebDriverWait(driver, 2).until(lambda d: is_unknown_ticker(d.page_source))
        raise RuntimeError(f"{ticker} not found on QuickFS.")
    except TimeoutException:
        pass
    if is_login_page(page_text):
        login(driver)
        driver.get(f"{URL}/company/{ticker}:LN")
        wait_for(driver, By.TAG_NAME, "body", timeout=15)
        page_text = driver.page_source
    if is_unknown_ticker(page_text):
        raise RuntimeError(f"{ticker} not found on QuickFS.")
    try:
        def ready_or_missing(d):
            if len(d.find_elements(By.CLASS_NAME, "dropdown-toggle")) >= 2:
                return True
            page_text = d.page_source
            if is_unknown_ticker(page_text):
                raise RuntimeError(f"{ticker} not found on QuickFS.")
            if "not found" in page_text or "company not found" in page_text:
                raise RuntimeError(f"{ticker} not found on QuickFS.")
            return False

        WebDriverWait(driver, 5).until(ready_or_missing)
    except TimeoutException:
        page_text = driver.page_source
        if is_unknown_ticker(page_text):
            raise RuntimeError(f"{ticker} not found on QuickFS.")
        raise RuntimeError("Dropdowns not found; page may not have loaded or ticker invalid.")

    dropdown_buttons = driver.find_elements(By.CLASS_NAME, "dropdown-toggle")
    if len(dropdown_buttons) < 2:
        raise RuntimeError("Missing statement or units dropdowns.")

    statement_dropdown = dropdown_buttons[0]
    units_dropdown = dropdown_buttons[1]

    safe_click(driver, units_dropdown)
    thousands_button = wait_clickable(driver, By.ID, "thousands", timeout=10)
    safe_click(driver, thousands_button)

    rows_by_statement = {
        "IS": None,
        "BS": None,
        "CF": None,
    }

    for k in rows_by_statement:
        attempt = 0
        while attempt < 2:
            try:
                statement_dropdown = driver.find_elements(By.CLASS_NAME, "dropdown-toggle")[0]
                safe_click(driver, statement_dropdown)
                button = wait_clickable(driver, By.ID, k.lower(), timeout=10)
                safe_click(driver, button)

                financials = wait_for(driver, By.CSS_SELECTOR, "table", timeout=15)
                WebDriverWait(driver, 15).until(
                    lambda d: len(financials.find_elements(By.CSS_SELECTOR, "tr")) > 1
                )

                rows = financials.find_elements(By.CSS_SELECTOR, "tr")

                c_rows = []
                for r in rows:
                    cells = [c.text for c in r.find_elements(By.CSS_SELECTOR, "th, td")]
                    if any(cells[1:]):
                        c_rows.append(cells)

                if not c_rows or len(c_rows[0]) < 2:
                    raise RuntimeError(f"{ticker} {k} returned empty rows.")

                rows_by_statement[k] = c_rows
                break
            except StaleElementReferenceException:
                attempt += 1
                time.sleep(0.5)
                if attempt >= 2:
                    raise

    for key, rows in rows_by_statement.items():
        if not rows or len(rows[0]) < 2:
            raise RuntimeError(f"{ticker} missing data for {key}.")

    return rows_by_statement


def load_cache(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(path, data):
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp_path.replace(path)


def cache_bulk_financials(tickers, cache_path, overwrite=False, retry_once=True):
    all_financials = load_cache(cache_path)

    def start_driver():
        driver = webdriver.Chrome()
        WebDriverWait(driver, 30)
        login(driver)
        return driver

    driver = start_driver()

    for t in tickers:
        t = t.strip()
        if not t:
            continue
        if t in all_financials and not overwrite:
            print(f"{t} already cached. Skipping.")
            continue
        try:
            financials = pull_financials(driver, t)
        except Exception as e:
            if "not found on quickfs" in str(e).lower():
                print(f"{t} not found on QuickFS. Skipping.")
                continue
            try:
                if is_unknown_ticker(driver.page_source):
                    print(f"{t} not found on QuickFS. Skipping.")
                    continue
            except Exception:
                pass
            if retry_once:
                try:
                    msg = str(e).lower()
                    if "no such window" in msg or "invalid session" in msg or "disconnected" in msg:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = start_driver()
                    print(f"Retrying {t} after error: {e}")
                    financials = pull_financials(driver, t)
                except Exception as retry_exc:
                    print(f"Fetching financials failed for {t}, cause: {retry_exc}")
                    continue
            else:
                print(f"Fetching financials failed for {t}, cause: {e}")
                continue

        all_financials[t] = financials
        save_cache(cache_path, all_financials)

    try:
        driver.quit()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Fetch QuickFS financials and update cache.")
    parser.add_argument(
        "--tickers-csv",
        default=str((BASE_DIR / ".." / "ftse_tickers.csv").resolve()),
        help="Path to CSV with tickers (default: ftse_tickers.csv in repo root)",
    )
    parser.add_argument(
        "--cache-path",
        default=str(CACHE_PATH),
        help="Path to cached_financials.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing cached tickers",
    )
    args = parser.parse_args()

    with open(args.tickers_csv) as f:
        tickers = [l[0] for l in list(csv.reader(f))]

    cache_bulk_financials(tickers, Path(args.cache_path), overwrite=args.overwrite)


if __name__ == "__main__":
    main()


