import time
import json
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

DATA_FILE = "dataset_fakulteti.jsonl"


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def clean_text(text):
    if not text: return ""
    text = text.replace("\r", "").replace("\t", " ")
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return "\n".join(lines)


def get_category_markers():
    markers = {}
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return markers
    log("Scanning dataset for existing category markers...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                markers[item["main_category"]] = item["link"]
            except:
                continue
    return markers


def get_all_category_links():
    log("Fetching category links (Ostanato included)...")
    driver = setup_driver()
    wait = WebDriverWait(driver, 10)
    category_urls = {}

    try:
        driver.get("https://www.fakulteti.mk/")
        menu_items = driver.find_elements(By.CSS_SELECTOR, ".menu-categories-container ul > li:not(#ostanato)")
        for item in menu_items:
            try:
                link_el = item.find_element(By.TAG_NAME, "a")
                category_urls[link_el.text.strip()] = link_el.get_attribute("href")
            except:
                pass

        try:
            ostanato_li = driver.find_element(By.ID, "ostanato")
            ActionChains(driver).move_to_element(ostanato_li).perform()
            time.sleep(1)
            tabs = driver.find_elements(By.CSS_SELECTOR, ".all-categories-tabs li")
            for i in range(len(tabs)):
                ActionChains(driver).move_to_element(driver.find_element(By.ID, "ostanato")).perform()
                current_tab = driver.find_elements(By.CSS_SELECTOR, ".all-categories-tabs li")[i]
                tab_name = current_tab.text.strip()
                current_tab.click()
                time.sleep(0.5)
                first_post = driver.find_element(By.CSS_SELECTOR,
                                                 ".tab-pane.active .category-latest-posts a").get_attribute("href")
                driver.execute_script(f"window.open('{first_post}', '_blank');")
                driver.switch_to.window(driver.window_handles[1])
                category_urls[tab_name] = wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, "post-category"))).get_attribute("href")
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
        except Exception as e:
            log(f"Ostanato Error: {e}")
    finally:
        driver.quit()
    return category_urls


def scrape_category(driver, category_name, url, marker):
    log(f"--- Category: {category_name} ---")
    driver.get(url)
    wait = WebDriverWait(driver, 7)


    click_count = 0
    while True:
        visible_links = [el.get_attribute("href") for el in
                         driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")]
        if marker and marker in visible_links:
            log(f"  [STOP] Marker reached.")
            break
        try:
            load_more = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-outline-blue")))
            before_count = len(driver.find_elements(By.CSS_SELECTOR, ".post-container"))
            start_time = time.time()
            driver.execute_script("arguments[0].click();", load_more)
            wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".post-container")) > before_count)
            click_count += 1
            log(f"  [CLICK {click_count}] Expanded in {time.time() - start_time:.2f}s")
        except:
            break


    all_elements = driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")
    new_links = []
    for el in all_elements:
        href = el.get_attribute("href")
        if href == marker: break
        if href not in new_links: new_links.append(href)

    if not new_links:
        log(f"  [SKIP] No new content.")
        return


    log(f"  [EXTRACT] Saving {len(new_links)} items...")
    for link in reversed(new_links):
        data = extract_post_data(driver, link)
        if data:
            data["main_category"] = category_name
            with open(DATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            print(f"    [+] {data['title'][:50]}...")


def extract_post_data(driver, url):
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 5)
        wait.until(lambda d: d.find_element(By.TAG_NAME, "h1"))

        return {
            "link": url,
            "title": clean_text(driver.find_element(By.TAG_NAME, "h1").get_attribute("innerText")),
            "date": driver.find_element(By.CSS_SELECTOR, ".date span").get_attribute("innerText").strip(),
            "text": clean_text(
                driver.find_element(By.CLASS_NAME, "single-post-content-container").get_attribute("innerText")),
            "tags": [t.text.strip() for t in driver.find_elements(By.CSS_SELECTOR, ".single-post-tag")],
            "scraped_at": datetime.now().isoformat()
        }
    except:
        return None


def main():
    log("=== TURBO SCRAPER STARTING ===")
    markers = get_category_markers()
    categories = get_all_category_links()

    for name, url in categories.items():
        driver = setup_driver()
        try:
            scrape_category(driver, name, url, markers.get(name))
        finally:
            driver.quit()

    log("=== ALL CATEGORIES SYNCED ===")


if __name__ == "__main__":
    main()