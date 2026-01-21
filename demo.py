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
STATE_FILE = "dataset_fakulteti_state.json"


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
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\r", "").replace("\t", " ")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def load_scraper_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"Failed to load scraper state: {e}")
        return {}


def update_scraper_state(category, link, date):
    state = load_scraper_state()
    state[category] = {
        "latest_link": link,
        "latest_date": date
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_all_category_links():
    log("Fetching category links (Ostanato included)...")
    driver = setup_driver()
    wait = WebDriverWait(driver, 10)
    category_urls = {}

    try:
        driver.get("https://www.fakulteti.mk/")
        menu_items = driver.find_elements(
            By.CSS_SELECTOR, ".menu-categories-container ul > li:not(#ostanato)"
        )
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
                ActionChains(driver).move_to_element(
                    driver.find_element(By.ID, "ostanato")
                ).perform()

                current_tab = driver.find_elements(
                    By.CSS_SELECTOR, ".all-categories-tabs li"
                )[i]

                tab_name = current_tab.text.strip()
                current_tab.click()
                time.sleep(0.5)

                first_post = driver.find_element(
                    By.CSS_SELECTOR,
                    ".tab-pane.active .category-latest-posts a"
                ).get_attribute("href")

                driver.execute_script(f"window.open('{first_post}', '_blank');")
                driver.switch_to.window(driver.window_handles[1])

                category_urls[tab_name] = wait.until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "post-category")
                    )
                ).get_attribute("href")

                driver.close()
                driver.switch_to.window(driver.window_handles[0])

        except Exception as e:
            log(f"Ostanato Error: {e}")

    finally:
        driver.quit()

    return category_urls


def scrape_category(driver, category_name, url, category_state):
    log(f"--- Category: {category_name} ---")
    driver.get(url)
    wait = WebDriverWait(driver, 10)

    latest_link = None
    if category_state:
        latest_link = category_state.get("latest_link")

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".post-container")))
    except:
        log("  [WARN] No posts found initially.")

    click_count = 0
    checked_index = 0

    while True:
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR, ".post-container a[href*='news']"
            )
            current_total = len(elements)

            if latest_link:
                start_check = max(0, checked_index - 5)
                for i in range(start_check, current_total):
                    try:
                        href = elements[i].get_attribute("href")
                        if href == latest_link:
                            log(f"  [STOP] Latest known post reached at item {i}.")
                            raise StopIteration
                    except StopIteration:
                        raise
                    except:
                        continue

            checked_index = current_total

            load_more = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-outline-blue"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", load_more
            )
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", load_more)

            wait.until(
                lambda d: len(
                    d.find_elements(By.CSS_SELECTOR, ".post-container")
                ) > current_total
            )

            click_count += 1
            if click_count % 5 == 0:
                log(f"  [CLICK {click_count}] Expanded to {current_total} posts...")

            if click_count > 100:
                log("  [STOP] Reached expansion limit (safety stop).")
                break

        except StopIteration:
            break
        except Exception:
            break

    log("  [COLLECT] Gathering links...")
    all_elements = driver.find_elements(
        By.CSS_SELECTOR, ".post-container a[href*='news']"
    )

    new_links = []
    for el in all_elements:
        try:
            href = el.get_attribute("href")
            if href == latest_link:
                break
            if href and href not in new_links:
                new_links.append(href)
        except:
            continue

    if not new_links:
        log("  [SKIP] No new content.")
        return

    log(f"  [EXTRACT] Saving {len(new_links)} items...")
    extracted_items = []

    for link in reversed(new_links):
        data = extract_post_data(driver, link)
        if data:
            data["main_category"] = category_name
            with open(DATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            extracted_items.append(data)
            print(f"    [+] {data['title'][:50]}...")

    if extracted_items:
        newest = extracted_items[-1]
        update_scraper_state(
            category_name,
            newest["link"],
            newest["date"]
        )


def extract_post_data(driver, url):
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 5)
        wait.until(lambda d: d.find_element(By.TAG_NAME, "h1"))

        return {
            "link": url,
            "title": clean_text(
                driver.find_element(By.TAG_NAME, "h1").get_attribute("innerText")
            ),
            "text": clean_text(
                driver.find_element(
                    By.CLASS_NAME, "single-post-content-container"
                ).get_attribute("innerText")
            ),
            "tags": [
                t.text.strip()
                for t in driver.find_elements(By.CSS_SELECTOR, ".single-post-tag")
            ],
            "date": driver.find_element(
                By.CSS_SELECTOR, ".date span"
            ).get_attribute("innerText").strip(),
            "scraped_at": datetime.now().isoformat()
        }
    except:
        return None


def main():
    log("=== SCRAPER STARTING ===")
    state = load_scraper_state()
    categories = get_all_category_links()

    for name, url in categories.items():
        driver = setup_driver()
        try:
            scrape_category(driver, name, url, state.get(name))
        except Exception as e:
            log(f"CRITICAL ERROR scraping category '{name}': {e}")
        finally:
            try:
                driver.quit()
            except:
                pass

    log("=== ALL CATEGORIES SYNCED ===")


if __name__ == "__main__":
    main()