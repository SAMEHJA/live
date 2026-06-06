#!/usr/bin/env python3
"""
Standalone scraper for FaselHD asian-series.
Uses Common.py for helpers, but includes its own episode saving.
Shares the same progress file as FaselSeriesScraper.py:
  ./output/last_page_asian-series.txt
Stops automatically on 404 or empty pages.
"""

import json
import random
import re
import os
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup

# Import from Common (only what exists)
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres_both,
    extract_country, extract_runtime, extract_description,
    extract_status, extract_viewing_level, extract_language,
    extract_release_date, extract_episode_duration,
    extract_episode_count_text, extract_sources,
    get_seasons_url_from_detail, extract_seasons_from_page,
    extract_episodes_from_season_page
)

# ========== CONFIGURATION ==========
CATEGORY = "asian-series"
DAILY_SCAN_PAGES = 5

# Reuse the same progress file as FaselSeriesScraper.py
PROGRESS_FILE = f"./output/last_page_{CATEGORY}.txt"

OUTPUT_FILE = f"./output/{CATEGORY}.json"
EPISODES_DIR = f"./output/episodes/{CATEGORY}"
# ===================================

def load_progress() -> int:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(page_num: int):
    os.makedirs("./output", exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(page_num))

def extract_numeric_id(url: str) -> str:
    match = re.search(r'[?&]p=(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/(\d+)/?$', url)
    if match:
        return match.group(1)
    return None

def fetch_detail(detail_url: str, failed_set: set):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        failed_set.add(detail_url)
        return None, None

def save_episodes_local(category: str, series_id: str, seasons_data: dict):
    """Local episode saver (not needed from Common)."""
    if not seasons_data:
        return
    os.makedirs(EPISODES_DIR, exist_ok=True)
    file_path = os.path.join(EPISODES_DIR, f"{series_id}.json")
    output = {
        "content_id": series_id,
        "category": category,
        "seasons": seasons_data
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved episodes for {category}/{series_id} ({len(seasons_data)} seasons)")

def scrape_asian_series():
    print(f"\n{'='*60}")
    print(f"📺 Scraping category: {CATEGORY}")
    print(f"{'='*60}")

    category_url = FASEL_BASE_URL + CATEGORY
    total_pages = get_number_of_pages(category_url)
    last_page = load_progress()

    full_scrape_completed = (last_page == total_pages and total_pages > 0)
    if full_scrape_completed:
        pages_to_scan = min(DAILY_SCAN_PAGES, total_pages)
        print(f"✅ Full scrape completed. Daily mode: scanning first {pages_to_scan} page(s).")
        start_page = 1
        end_page = pages_to_scan
        daily_mode = True
    else:
        start_page = last_page + 1
        end_page = total_pages
        print(f"📄 Full scrape mode: resuming from page {start_page} to {end_page}")
        daily_mode = False

    # Load existing series data
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_series = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_series = {}

    existing_ids = set(existing_series.keys())
    all_series = existing_series.copy()
    failed_detail_urls = set()

    for page in range(start_page, end_page + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        print(f"\n📄 Page {page}/{total_pages}: {page_url}")

        main = get_website_safe(page_url)
        if not main:
            print("  ❌ Failed to fetch list page, skipping")
            continue
        if main.status_code == 404:
            print(f"  ⚠️ Page {page} returned 404 – stopping pagination.")
            break

        soup = BeautifulSoup(main.text, "html.parser")
        divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
               soup.select('.blockMovie') or \
               soup.select('.postDiv')
        if not divs:
            print("  ⚠️ No series containers – assuming end of pages.")
            break

        detail_urls = []
        for div in divs:
            link = div.find("a")
            if link:
                detail_url = link["href"]
                numeric_id = extract_numeric_id(detail_url)
                if numeric_id and numeric_id in existing_ids:
                    continue
                detail_urls.append(detail_url)

        if not detail_urls:
            print("  ℹ️ No new series on this page")
            continue

        # Fetch detail pages in parallel
        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_detail, url, failed_detail_urls): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_series = {}
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            dsoup = BeautifulSoup(detail_html, "html.parser")

            series_id = get_content_id(dsoup)
            if not series_id:
                series_id = extract_numeric_id(detail_url)
                if not series_id:
                    match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                    if match:
                        series_id = match.group(1)
                    else:
                        series_id = detail_url.split('/')[-2]
            if not series_id or series_id in existing_ids:
                continue

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            genres_info = get_genres_both(dsoup)
            description = extract_description(dsoup)
            status = extract_status(dsoup)
            viewing_level = extract_viewing_level(dsoup)
            language = extract_language(dsoup)
            release_date = extract_release_date(dsoup)
            episode_duration = extract_episode_duration(dsoup)
            episode_count_text = extract_episode_count_text(dsoup)
            sources = extract_sources(dsoup)

            seasons_hub_url = get_seasons_url_from_detail(detail_url)
            seasons_with_episodes = {}
            if seasons_hub_url:
                if seasons_hub_url == detail_url:
                    hub_soup = dsoup
                else:
                    hub_resp = get_website_safe(seasons_hub_url)
                    hub_soup = BeautifulSoup(hub_resp.text, 'html.parser') if hub_resp else None
                if hub_soup:
                    seasons_list = extract_seasons_from_page(hub_soup, FASEL_BASE_URL)
                    for season in seasons_list:
                        season_num = season['number']
                        season_url = season['page_url']
                        poster = season['poster']
                        season_resp = get_website_safe(season_url)
                        if season_resp:
                            season_soup = BeautifulSoup(season_resp.text, 'html.parser')
                            episode_urls = extract_episodes_from_season_page(season_soup)
                            if episode_urls:
                                seasons_with_episodes[season_num] = {
                                    "poster": poster,
                                    "episodes": episode_urls
                                }
                        time.sleep(REQUEST_DELAY / 2)

            if seasons_with_episodes:
                save_episodes_local(CATEGORY, series_id, seasons_with_episodes)

            new_series[series_id] = {
                "Title": title,
                "Category": CATEGORY,
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
                "Description": description,
                "SeasonsUrl": seasons_hub_url,
                "Status": status,
                "ViewingLevel": viewing_level,
                "Language": language,
                "ReleaseDate": release_date,
                "EpisodeDuration": episode_duration,
                "Number Of Episodes Text": episode_count_text,
                "last_scraped": datetime.now(timezone.utc).isoformat()
            }
            existing_ids.add(series_id)

        if new_series:
            all_series.update(new_series)
            print(f"  ✅ Page {page} done: added {len(new_series)} series, total {len(all_series)}")
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_series, f, indent=4, ensure_ascii=False)
        else:
            print(f"  ℹ️ Page {page}: no new series extracted")

        if not daily_mode:
            save_progress(page)

    # Retry failed detail URLs once
    if failed_detail_urls:
        print(f"\n🔄 Retrying {len(failed_detail_urls)} failed detail URLs...")
        for url in list(failed_detail_urls):
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                series_id = get_content_id(dsoup) or extract_numeric_id(url)
                if not series_id:
                    match = re.search(r'-(\d+)$', url.rstrip('/'))
                    series_id = match.group(1) if match else url.split('/')[-2]
                if series_id and series_id not in existing_ids:
                    all_series[series_id] = {
                        "Title": "Unknown (retried)",
                        "Category": CATEGORY,
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Description": extract_description(dsoup),
                        "SeasonsUrl": get_seasons_url_from_detail(url),
                        "Status": extract_status(dsoup),
                        "ViewingLevel": extract_viewing_level(dsoup),
                        "Language": extract_language(dsoup),
                        "ReleaseDate": extract_release_date(dsoup),
                        "EpisodeDuration": extract_episode_duration(dsoup),
                        "Number Of Episodes Text": extract_episode_count_text(dsoup),
                        "last_scraped": datetime.now(timezone.utc).isoformat()
                    }
            sleep(1)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_series, f, indent=4, ensure_ascii=False)

    print(f"\n🏁 {CATEGORY} finished. Total series: {len(all_series)}")

if __name__ == "__main__":
    scrape_asian_series()