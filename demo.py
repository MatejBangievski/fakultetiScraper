import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


def setup_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def get_all_post_links(driver, url):
    driver.get(url)
    wait = WebDriverWait(driver, 15)
    print("Expanding page content...")

    while True:
        try:
            # Look for the button specifically by class
            load_more_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-outline-blue")))

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
            time.sleep(1.5)  # Wait for scroll
            driver.execute_script("arguments[0].click();", load_more_btn)

            print("Clicked 'See More'...")
            time.sleep(2.5)  # Give the site time to inject new HTML
        except TimeoutException:
            print("Reached the end or button disappeared.")
            break

    # UPDATED SELECTOR:
    # This targets any link inside the post-container that contains 'news' in the URL
    elements = driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")
    links = []
    for el in elements:
        href = el.get_attribute("href")
        if href and href not in links:
            links.append(href)

    return links


def extract_post_data(driver, url):
    print(f"Scraping: {url}")
    driver.get(url)
    wait = WebDriverWait(driver, 10)

    data = {
        "url": url,
        "scraped_date": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }

    try:
        # Wait for the main title to appear to ensure page loaded
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".single-post-title-wrapper h1")))

        # Title
        data["title"] = driver.find_element(By.CSS_SELECTOR, ".single-post-title-wrapper h1").text.strip()

        # Date & Category
        try:
            icons_div = driver.find_element(By.CLASS_NAME, "single-post-icons")
            data["date"] = icons_div.find_element(By.CSS_SELECTOR, ".date span").text.strip()
            data["category"] = icons_div.find_element(By.CLASS_NAME, "post-category").text.replace("Категорија:",
                                                                                                   "").strip()
        except:
            data["date"] = "N/A"
            data["category"] = "N/A"

        # Content (Full Text)
        content_container = driver.find_element(By.CLASS_NAME, "single-post-content-container")
        data["full_text"] = content_container.text.strip()

        # Tags
        tags_elements = driver.find_elements(By.CSS_SELECTOR, ".tags-holder .single-post-tag")
        data["tags"] = [tag.text.strip() for tag in tags_elements]

    except Exception as e:
        print(f"Error on {url}: {e}")
        return None

    return data


def main():
    base_url = "https://www.fakulteti.mk/category/nasha-tema"
    driver = setup_driver()
    all_data = []

    try:
        # Step 1: Collect Links
        links = get_all_post_links(driver, base_url)
        print(f"Found {len(links)} links.")

        if not links:
            print("No links found. Checking selector...")
            # Fallback: Print some page text to debug if links are 0
            return

        # Step 2: Extract
        for link in links:
            post_info = extract_post_data(driver, link)
            if post_info:
                all_data.append(post_info)
            time.sleep(1)

        # Step 3: Save
        with open("scraped_posts.json", "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
        print(f"Saved {len(all_data)} posts.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()