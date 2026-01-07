import time
import json
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://quickfs.net"

def pull_financials(ticker):

    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, 30)

    driver.get(f"{URL}/login")

    driver.implicitly_wait(10)
    driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys("matthew_newell@outlook.com")
    driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys("supergas02")
    driver.find_element(By.ID, "submitLoginFormBtn").click()

    time.sleep(1.5)
    driver.get(f"{URL}/company/{ticker}:LN")
    driver.implicitly_wait(10)
    dropdown_buttons = driver.find_elements(By.CLASS_NAME, "dropdown-toggle")

    statement_dropdown = dropdown_buttons[0]
    units_dropdown = dropdown_buttons[1]

    units_dropdown.click()
    thousands_button = driver.find_element(By.ID, "thousands")
    thousands_button.click()

    rows_by_statement = {
        "IS": None,
        "BS": None,
        "CF": None,
    }

    for k, v in rows_by_statement.items():
        statement_dropdown.click()
        button = driver.find_element(By.ID, k.lower())
        button.click()

        driver.implicitly_wait(10)
        financials = driver.find_element(By.CSS_SELECTOR, "table")

        rows = financials.find_elements(By.CSS_SELECTOR, "tr")

        # This bit is a little slow, could probably be sped up by not using Selenium here
        c_rows = []
        for r in rows:
            cells = [c.text for c in r.find_elements(By.CSS_SELECTOR, "th, td")]
            if any(cells[1:]):  # Gets rid of blank spacer rows and header rows
                c_rows.append(cells)
                print(cells)

        rows_by_statement[k] = c_rows

    driver.close()
    return rows_by_statement


def cache_bulk_financials(tickers):

    all_financials = {}

    for t in tickers:
        try:
            financials = pull_financials(t)
        except Exception as e:
            print(f"Fetching financials failed for {t}, cause: {e}")
            continue

        all_financials[t] = financials

    with open("../cached_financials.json", "w", encoding="utf-8") as f:
        json.dump(all_financials, f, ensure_ascii=False)



with open("../tickers.csv") as f:
    tickers = [l[0] for l in list(csv.reader(f))]

cache_bulk_financials(tickers)


