import time
import json
import re
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
DATA_FILE = "dataset_fakulteti.json"


def setup_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def clean_text(text):
    if not text: return ""
    text = text.replace("\r", "").replace("\t", " ")
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


def load_existing_data():
    """Loads existing JSON data so we can append to it and check for duplicates."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def get_all_category_links(driver):
    driver.get("https://www.fakulteti.mk/")
    wait = WebDriverWait(driver, 10)
    category_urls = {}

    menu_items = driver.find_elements(By.CSS_SELECTOR, ".menu-categories-container ul > li:not(#ostanato)")
    for item in menu_items:
        try:
            link_el = item.find_element(By.TAG_NAME, "a")
            name = link_el.text.strip()
            url = link_el.get_attribute("href")
            if url: category_urls[name] = url
        except:
            pass

    try:
        ostanato_li = driver.find_element(By.ID, "ostanato")
        ActionChains(driver).move_to_element(ostanato_li).perform()
        time.sleep(1)

        tabs = driver.find_elements(By.CSS_SELECTOR, ".all-categories-tabs li")
        for i in range(len(tabs)):
            ostanato_li = driver.find_element(By.ID, "ostanato")
            ActionChains(driver).move_to_element(ostanato_li).perform()

            current_tabs = driver.find_elements(By.CSS_SELECTOR, ".all-categories-tabs li")
            tab_name = current_tabs[i].text.strip()
            current_tabs[i].click()
            time.sleep(1)

            first_post = driver.find_element(By.CSS_SELECTOR, ".tab-pane.active .category-latest-posts a")
            first_post_url = first_post.get_attribute("href")

            driver.execute_script(f"window.open('{first_post_url}', '_blank');")
            driver.switch_to.window(driver.window_handles[1])

            cat_link_el = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "post-category")))
            category_urls[tab_name] = cat_link_el.get_attribute("href")

            driver.close()
            driver.switch_to.window(driver.window_handles[0])
    except Exception as e:
        print(f"Error when scraping 'Ostanato' tab: {e}")

    return category_urls


def scrape_category(driver, category_name, url, existing_urls, full_dataset):
    print(f"\n--- Scraping Category: {category_name} ---")
    driver.get(url)
    wait = WebDriverWait(driver, 10)

    # Step 1: Expand content but check if the newest visible posts are already scraped
    # If the very first post on the page is already in our list, we might not need to expand at all.

    while True:
        # Check current visible links
        visible_elements = driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")
        visible_links = [el.get_attribute("href") for el in visible_elements]

        # If any of the visible links are already in our database, we stop clicking "Load More"
        if any(link in existing_urls for link in visible_links):
            print(f"  > Found existing posts in {category_name}. Stopping expansion.")
            break

        try:
            load_more = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-outline-blue")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", load_more)
            time.sleep(2)
        except:
            break

    # Step 2: Get all links and filter
    elements = driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")
    all_links = list(dict.fromkeys([el.get_attribute("href") for el in elements]))

    for link in all_links:
        if link in existing_urls:
            print(f"  > Reached already scraped content at: {link}. Skipping remaining.")
            break

        data = extract_post_data(driver, link)
        if data:
            data["main_category"] = category_name
            full_dataset.append(data)
            existing_urls.add(link)
            save_checkpoint(full_dataset)


def extract_post_data(driver, url):
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".single-post-title-wrapper h1")))

        title = driver.find_element(By.CSS_SELECTOR, ".single-post-title-wrapper h1").get_attribute("innerText")
        content_el = driver.find_element(By.CLASS_NAME, "single-post-content-container")
        raw_content = content_el.get_attribute("innerText")

        icons = driver.find_element(By.CLASS_NAME, "single-post-icons")
        date = icons.find_element(By.CSS_SELECTOR, ".date span").text.strip()

        tags_el = driver.find_elements(By.CSS_SELECTOR, ".tags-holder .single-post-tag")
        tags = [t.text.strip() for t in tags_el]

        return {
            "link": url,
            "title": clean_text(title),
            "date": date,
            "text": clean_text(raw_content),
            "tags": tags,
            "scraped_at": datetime.now().isoformat()
        }
    except:
        return None


def save_checkpoint(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def main():
    driver = setup_driver()
    try:
        # Load existing data from file
        full_dataset = load_existing_data()
        existing_urls = {post['link'] for post in full_dataset}
        print(f"Loaded {len(existing_urls)} existing posts from {DATA_FILE}")

        all_categories = get_all_category_links(driver)
        print(f"Found categories: {list(all_categories.keys())}")

        for name, url in all_categories.items():
            scrape_category(driver, name, url, existing_urls, full_dataset)

        print(f"\nScraping finished. Total posts in database: {len(full_dataset)}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()