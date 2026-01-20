import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def setup_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def get_all_post_links(driver, url):
    driver.get(url)
    wait = WebDriverWait(driver, 15)
    print("Step 1: Expanding all posts via 'Load More'...")

    while True:
        try:
            load_more_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-outline-blue")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
            time.sleep(1.5)
            driver.execute_script("arguments[0].click();", load_more_btn)
            print("  - Loading more content...")
            time.sleep(2.5)
        except:
            print("  - All content expanded.")
            break

    # Extracting all unique post links
    elements = driver.find_elements(By.CSS_SELECTOR, ".post-container a[href*='news']")
    links = []
    for el in elements:
        href = el.get_attribute("href")
        if href and href not in links:
            links.append(href)
    return links


def extract_post_data(driver, url):
    driver.get(url)
    wait = WebDriverWait(driver, 10)

    try:
        # Ensure the page title is loaded
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".single-post-title-wrapper h1")))

        # Structure the JSON object
        post_data = {
            "post_link": url,  # Saving the URL as requested
            "scraped_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "title": driver.find_element(By.CSS_SELECTOR, ".single-post-title-wrapper h1").text.strip(),
            "date_published": "N/A",
            "category": "N/A",
            "full_text": "",
            "sub_categories": []
        }

        # Date & Category
        try:
            icons = driver.find_element(By.CLASS_NAME, "single-post-icons")
            post_data["date_published"] = icons.find_element(By.CSS_SELECTOR, ".date span").text.strip()
            post_data["category"] = icons.find_element(By.CLASS_NAME, "post-category").text.replace("Категорија:",
                                                                                                    "").strip()
        except:
            pass

        # Content
        content = driver.find_element(By.CLASS_NAME, "single-post-content-container")
        post_data["full_text"] = content.text.strip()

        # Tags (Sub-categories)
        tags = driver.find_elements(By.CSS_SELECTOR, ".tags-holder .single-post-tag")
        post_data["sub_categories"] = [t.text.strip() for t in tags]

        return post_data

    except Exception as e:
        print(f"  [!] Failed to scrape {url}: {e}")
        return None


def main():
    base_url = "https://www.fakulteti.mk/category/nasha-tema"
    driver = setup_driver()
    results = []
    output_file = "fakulteti_posts.json"

    try:
        links = get_all_post_links(driver, base_url)
        print(f"Step 2: Starting extraction for {len(links)} links...")

        for i, link in enumerate(links, 1):
            data = extract_post_data(driver, link)
            if data:
                results.append(data)
                print(f"  [{i}/{len(links)}] Scraped: {data['title'][:50]}...")

                # SAVE TO JSON (Incremental/Checkpoint)
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)

            time.sleep(1)  # Delay to prevent getting blocked

    finally:
        print(f"\nFinished! Total posts saved to {output_file}: {len(results)}")
        driver.quit()


if __name__ == "__main__":
    main()