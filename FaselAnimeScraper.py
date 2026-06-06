#!/usr/bin/env python3
"""
FaselAnimeScraper.py – Unified scraper for anime series.
- Full scrape: goes through all pages, saves progress.
- Daily mode: after full scrape, only first N pages (default 5).
- Extracts numeric IDs when available to skip known items.
- Does NOT extract player token sources (lighter & faster).
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
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres_both,
    extract_country, extract_runtime, extract_description,
    extract_status, extract_viewing_level, extract_language,
    extract_release_date, extract_episode_duration,
    extract_episode_count_text
)

DAILY_SCAN_PAGES = 5

def load_progress() -> int:
    progress_file = "./output/last_page_anime.txt"
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(page_num: int):
    os.makedirs("./output", exist_ok=True)
    with open("./output/last_page_anime.txt", "w") as f:
        f.write(str(page_num))

def extract_numeric_id(url: str) -> str:
    match = re.search(r'[?&]p=(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/(\d+)/?$', url)
    if match:
        return match.group(1)
    return None

def extract_episodes_from_detail_page(soup: BeautifulSoup) -> list:
    episode_links = []
    ep_all = soup.select_one('#epAll, .epAll')
    if not ep_all:
        return episode_links
    for a in ep_all.find_all('a', href=True):
        href = a['href'].strip()
        if href and ('episodes' in href or '/?p=' in href):
            episode_links.append(href)
    return episode_links

def save_episodes_for_anime(anime_id: str, episodes: list):
    if not episodes:
        return
    episodes_dir = "./output/episodes/anime"
    os.makedirs(episodes_dir, exist_ok=True)
    file_path = os.path.join(episodes_dir, f"{anime_id}.json")
    output = {
        "content_id": anime_id,
        "category": "anime",
        "seasons": {1: episodes}
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved {len(episodes)} episodes for anime/{anime_id}")

def fetch_detail(detail_url: str, failed_set: set):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        failed_set.add(detail_url)
        return None, None

def scrape_anime():
    print(f"\n{'='*60}")
    print(f"🎌 Processing anime")
    print(f"{'='*60}")

    category_url = FASEL_BASE_URL + "anime"
    total_pages = get_number_of_pages(category_url)
    last_page = load_progress()

    full_scrape_completed = (last_page == total_pages and total_pages > 0)
    if full_scrape_completed:
        pages_to_scan = min(DAILY_SCAN_PAGES, total_pages)
        print(f"✅ Daily mode: scanning first {pages_to_scan} page(s).")
        start_page = 1
        end_page = pages_to_scan
        daily_mode = True
    else:
        start_page = last_page + 1
        end_page = total_pages
        print(f"📄 Full scrape mode: resuming from page {start_page} to {end_page}")
        daily_mode = False

    output_file = "./output/anime.json"
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            existing_anime = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_anime = {}

    existing_ids = set(existing_anime.keys())
    all_anime = existing_anime.copy()
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

        soup = BeautifulSoup(main.text, "html.parser")
        divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
               soup.select('.blockMovie') or \
               soup.select('.postDiv')
        if not divs:
            print("  ⚠️ No anime containers found")
            continue

        detail_urls = []
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            numeric_id = extract_numeric_id(detail_url)
            if numeric_id and numeric_id in existing_ids:
                continue
            detail_urls.append(detail_url)

        if not detail_urls:
            print("  ℹ️ No new anime on this page")
            continue

        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_detail, url, failed_detail_urls): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_anime = {}
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            numeric_id = extract_numeric_id(detail_url)
            if numeric_id and numeric_id in existing_ids:
                continue

            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            dsoup = BeautifulSoup(detail_html, "html.parser")

            anime_id = get_content_id(dsoup)
            if not anime_id:
                anime_id = numeric_id
                if not anime_id:
                    match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                    if match:
                        anime_id = match.group(1)
                    else:
                        anime_id = detail_url.split('/')[-2]
            # Skip if already exists — FaselHD rarely updates metadata,
            # so re-scraping existing items gains nothing and risks overwriting good data.
            if not anime_id or anime_id in existing_ids:
                continue

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            episode_urls = extract_episodes_from_detail_page(dsoup)
            episode_count = len(episode_urls)
            content_type = "Series" if episode_count > 0 else "Movie"

            if episode_urls:
                save_episodes_for_anime(anime_id, episode_urls)

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

            # No sources extraction – removed
            new_anime[anime_id] = {
                "Title": title,
                "Category": "anime",
                "Type": content_type,
                "Number Of Episodes": episode_count,
                "Number Of Episodes Text": episode_count_text,
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
                "Description": description,
                "SeasonsUrl": detail_url,
                "Status": status,
                "ViewingLevel": viewing_level,
                "Language": language,
                "ReleaseDate": release_date,
                "EpisodeDuration": episode_duration,
                "last_scraped": datetime.now(timezone.utc).isoformat()
            }
            existing_ids.add(anime_id)

        if new_anime:
            all_anime.update(new_anime)
            print(f"  ✅ Page {page} done: added {len(new_anime)} anime, total {len(all_anime)}")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_anime, f, indent=4, ensure_ascii=False)
        else:
            print(f"  ℹ️ Page {page}: no new anime extracted")

        if not daily_mode:
            save_progress(page)

    if failed_detail_urls:
        print(f"\n🔄 Retrying {len(failed_detail_urls)} failed detail URLs for anime...")
        for url in list(failed_detail_urls):
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                anime_id = get_content_id(dsoup) or extract_numeric_id(url)
                if not anime_id:
                    match = re.search(r'-(\d+)$', url.rstrip('/'))
                    anime_id = match.group(1) if match else url.split('/')[-2]
                if anime_id and anime_id not in existing_ids:
                    all_anime[anime_id] = {
                        "Title": "Unknown (retried)",
                        "Category": "anime",
                        "Type": "Movie",
                        "Number Of Episodes": 0,
                        "Number Of Episodes Text": 0,
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Description": extract_description(dsoup),
                        "SeasonsUrl": url,
                        "Status": extract_status(dsoup),
                        "ViewingLevel": extract_viewing_level(dsoup),
                        "Language": extract_language(dsoup),
                        "ReleaseDate": extract_release_date(dsoup),
                        "EpisodeDuration": extract_episode_duration(dsoup),
                        "last_scraped": datetime.now(timezone.utc).isoformat()
                    }
            sleep(1)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_anime, f, indent=4, ensure_ascii=False)

    print(f"\n🏁 Anime finished. Total anime: {len(all_anime)}")

if __name__ == "__main__":
    scrape_anime()