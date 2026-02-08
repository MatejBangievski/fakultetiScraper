import asyncio
import aiohttp
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup

DATA_FILE = "dataset_fakulteti.jsonl"
API_URL = "https://www.fakulteti.mk/webui/api/v1/PostManagementHandler.ashx"
BASE_URL = "https://www.fakulteti.mk"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.fakulteti.mk/",
    "X-Requested-With": "XMLHttpRequest"
}


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

async def get_categories(session):
    log("Scanning homepage source for category patterns...")
    categories = {}
    try:
        async with session.get(BASE_URL, headers=HEADERS) as resp:
            html = await resp.text()

            # 1. Pattern for main categories: id="nasha-tema"
            # We look for li tags with an id that doesn't start with 'tab-'
            main_pattern = r'<li\s+id="([^"|tab-][^"]+)"'
            main_slugs = re.findall(main_pattern, html)

            # 2. Pattern for nested categories: id="tab-ekonomija"
            nested_pattern = r'id="tab-([^"]+)"'
            nested_slugs = re.findall(nested_pattern, html)

            # Combine all unique slugs
            all_slugs = list(set(main_slugs + nested_slugs))

            # Remove 'ostanato' if it got caught in the net
            if "ostanato" in all_slugs: all_slugs.remove("ostanato")

            # Map slugs to readable names (Capitalizing the slug for the log)
            for slug in all_slugs:
                categories[slug.replace("-", " ").title()] = slug

        if categories:
            log(f"Discovery complete. Found {len(categories)} categories: {list(categories.values())}")
        else:
            # Final fallback: If the regex fails, the site is likely serving
            log("Regex found nothing. Using verified manual fallback list.")
            return {
                "Наша тема": "nasha-tema", "Образование": "obrazovanie", "Наука": "nauka",
                "Култура": "kultura", "Здравје": "zdravje", "Технологија": "tehnologija",
                "Колумни": "kolumni", "Живот": "zhivot", "Кариера": "kariera",
                "Настани": "nastani", "Економија": "ekonomija", "Забава": "zabava"
            }
    except Exception as e:
        log(f"Discovery error: {e}")
    return categories


async def fetch_full_article_text(session, url):
    try:
        async with session.get(url, headers=HEADERS, timeout=10) as resp:
            if resp.status == 200:
                html = await resp.text()
                soup = BeautifulSoup(html, 'lxml')
                content_div = soup.select_one(".single-post-content-container")
                if content_div:
                    for s in content_div(["script", "style"]): s.decompose()
                    return content_div.get_text(separator="\n", strip=True)
    except:
        pass
    return ""


async def process_category(session, cat_name, cat_slug):
    log(f"Processing Category: {cat_name} ({cat_slug})")
    offset = 0
    total_for_cat = 0

    while True:
        params = {
            "command": "GetTaxonomyPosts",
            "taxonomy": "category",
            "term": cat_slug,
            "offset": str(offset),
            "limit": "20",
            "includeTop": "true"
        }

        try:
            async with session.get(API_URL, headers=HEADERS, params=params) as resp:
                if resp.status != 200: break
                posts = await resp.json()
                if not posts or len(posts) == 0: break

                for post in posts:
                    url = post.get('url', '')
                    if url and not url.startswith('http'): url = BASE_URL + url

                    content = await fetch_full_article_text(session, url)

                    entry = {
                        "title": post.get('title'),
                        "url": url,
                        # "description": post.get('description'),
                        "publish_date": post.get('publicationDate'),
                        "category_name": post.get('category', {}).get('name', cat_name),
                        "content": content
                    }

                    with open(DATA_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    total_for_cat += 1

                log(f"  Scraped {total_for_cat} items from {cat_name} (Offset: {offset})")
                offset += 20
                await asyncio.sleep(0.3)
        except Exception as e:
            log(f"  Error in {cat_name}: {e}")
            break


async def main():
    log("=== SCRAPER STARTED ===")
    async with aiohttp.ClientSession() as session:
        categories = await get_categories(session)
        if not categories:
            log("CRITICAL: No categories found. Check if site is blocking requests.")
            return

        for name, slug in categories.items():
            await process_category(session, name, slug)
    log("=== ALL DONE ===")


if __name__ == "__main__":
    asyncio.run(main())