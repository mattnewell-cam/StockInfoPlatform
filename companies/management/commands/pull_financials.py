from html.parser import HTMLParser
from bs4 import BeautifulSoup
import requests
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

url = "https://quickfs.net"

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 30)

driver.get(f"{url}/login")

time.sleep(0.5)
driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys("matthew_newell@outlook.com")
driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys("supergas02")
driver.find_element(By.ID, "submitLoginFormBtn").click()

time.sleep(1)
driver.get(f"{url}/company/WJG:LN")
time.sleep(0.5)
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

    time.sleep(1.5)
    financials = driver.find_element(By.CSS_SELECTOR, "table")

    rows = financials.find_elements(By.CSS_SELECTOR, "tr")

    for r in rows[:5]:
        cells = [c.text for c in r.find_elements(By.CSS_SELECTOR, "th, td")]
        print(cells)

    rows_by_statement[k] = [[c.text for c in r.find_elements(By.CSS_SELECTOR, "th, td")] for r in rows]

print(rows_by_statement)