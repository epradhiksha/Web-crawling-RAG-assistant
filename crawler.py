# crawler.py
# Responsible for:
# Crawling pages
# Discovering relevant URLs
# Fetching content
# Extracting useful information

import json
import os
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

START_URL = "https://www.bankofamerica.com/credit-cards/"
REQUEST_DELAY = 3
PAGE_TIMEOUT = 15



ignore_text = [
    "apply now",
    "learn more",
    "see if you prequalify",
    "sign in",
    "close",
    "location",
    "contact us",
    "help",
    "appointment",
    "manage your credit card account",
    "terms & conditions",
    "compare",
    "view sample credit card agreements",
    "view all cards",
    "credit card home",
    "card details",
]

ignore_url_substrings = [
    "terms-and-conditions",
    "credit-card-agreements",
    "compare-credit-cards",
    "#students",
    "#buildCredit",
    "login",
    "sign-in",
    "secure.",
]




def normalize_url(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}/"


def check(text, href):
    if not text or not href:
        return False
    if "bankofamerica.com/credit-cards" not in href:
        return False
    if any(bad in href for bad in ignore_url_substrings):
        return False
    if any(ig in text.lower() for ig in ignore_text):
        return False
    if "card" not in text.lower() and "credit" not in text.lower():
        return False

    return True


def load_page(driver, url, wait_for=(By.TAG_NAME, "a")):
    time.sleep(REQUEST_DELAY)
    try:
        driver.get(url)
        WebDriverWait(driver, PAGE_TIMEOUT).until(
            EC.presence_of_all_elements_located(wait_for)
        )
        return True
    except Exception as e:
        return False


def get_url(driver, url, seen_urls):
    linkList = []
    if not load_page(driver, url):
        return linkList

    for link in driver.find_elements(By.TAG_NAME, "a"):
        text = link.text.strip()
        href = link.get_attribute("href")
        if not href:
            continue
        href = normalize_url(href)
        if href in seen_urls:
            continue
        if check(text, href):
            seen_urls.add(href)
            linkList.append({
                "text": text,
                "source url": href
            })
    return linkList


def crawler(driver):
    if not load_page(driver, START_URL):
        return []

    category_urls = []
    for link in driver.find_elements(By.TAG_NAME, "a"):
        text = link.text.strip()
        href = link.get_attribute("href")
        if not href or not text:
            continue
        if "cards" in urlparse(href).path and check(text, href):
            href = normalize_url(href)
            if href not in category_urls:
                category_urls.append(href)

    main_link_list = []
    seen_urls = set()
    for cat_url in category_urls:
        cards = get_url(driver, cat_url, seen_urls)
        main_link_list.extend(cards)

    # Only individual product pages hold card details
    return [p for p in main_link_list if "/credit-cards/products/" in p["source url"]]


def category_from_url(url):
    slug = urlparse(url).path.rstrip("/").split("/")[-1]   # cash-back-credit-card
    slug = slug.replace("-credit-card", "").replace("-credit-cards", "")
    return slug.replace("-", " ").title()


def safe_text(driver, by, value):
    try:
        return driver.find_element(by, value).text.strip()
    except Exception:
        return ""


def safe_texts(driver, by, value):
    return [e.text.strip() for e in driver.find_elements(by, value) if e.text.strip()]


def details(driver, page):
    url = page["source url"]
    if not load_page(driver, url, wait_for=(By.TAG_NAME, "body")):
        return None

    return {
        "card_name": page["text"],
        "category": category_from_url(url),
        "description": safe_text(driver, By.ID, "cardDetailsCcModule"),
        "features": safe_texts(driver, By.CLASS_NAME, "feature-content"),
        "benefits": safe_texts(driver, By.CLASS_NAME, "benefit-content"),
        "rates_fees": safe_text(
            driver, By.CSS_SELECTOR, "[data-magellan-destination='interestRatesFeesCcModule']"
        ),
        "source_url": url,
    }


def scrape_all(driver):
    pages = crawler(driver)
    results = []
    for i, p in enumerate(pages, 1):
        record = details(driver, p)
        if record is None:
            continue
        # Do not keep pages where nothing useful was extracted
        if not (record["description"] or record["features"] or record["benefits"] or record["rates_fees"]):
            continue
        results.append(record)
    return results


if __name__ == "__main__":
    driver = webdriver.Chrome()
    try:
        results = scrape_all(driver)
    finally:
        driver.quit()

    with open("scraped_cards.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(results)} raw records to scraped_cards.json")

