#!/usr/bin/env python3
"""
FaselMoviesScraper.py – Unified scraper for all movie categories.
- Full scrape: goes through all pages, saves progress.
- Daily mode: after full scrape, checks only first N pages (default 5).
- Extracts numeric IDs when available to skip known items.
- Does NOT extract player token sources (lighter & faster).
"""

import json
import random
import re
import os
import time
import argparse
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres_both,
    extract_country, extract_runtime, extract_description,
    extract_release_date, extract_language
)

MOVIE_PATHS = ["movies", "dubbed-movies", "hindi", "asian-movies", "anime-movies"]
DAILY_SCAN_PAGES = 5

def load_progress(path: str) -> int:
    progress_file = f"./output/last_page_{path}.txt"
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(path: str, page_num: int):
    os.makedirs("./output", exist_ok=True)
    with open(f"./output/last_page_{path}.txt", "w") as f:
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

def scrape_category(path: str):
    print(f"\n{'='*60}")
    print(f"🎬 Processing category: {path}")
    print(f"{'='*60}")

    category_url = FASEL_BASE_URL + path
    total_pages = get_number_of_pages(category_url)
    last_page = load_progress(path)

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

    output_file = f"./output/{path}.json"
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            existing_movies = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_movies = {}

    existing_ids = set(existing_movies.keys())
    all_movies = existing_movies.copy()
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
            print("  ⚠️ No movie containers found")
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
            print("  ℹ️ No new movies on this page")
            continue

        detail_map = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(fetch_detail, url, failed_detail_urls): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_movies = {}
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

            movie_id = get_content_id(dsoup)
            if not movie_id:
                movie_id = numeric_id
                if not movie_id:
                    match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                    if match:
                        movie_id = match.group(1)
                    else:
                        movie_id = detail_url.split('/')[-2]
            # Skip if already exists — FaselHD rarely updates metadata,
            # so re-scraping existing items gains nothing and risks overwriting good data.
            if not movie_id or movie_id in existing_ids:
                continue

            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            genres_info = get_genres_both(dsoup)
            description = extract_description(dsoup)
            release_date = extract_release_date(dsoup)
            language = extract_language(dsoup)
            country = extract_country(dsoup)

            # No sources extraction – removed
            new_movies[movie_id] = {
                "Title": title,
                "Category": path,
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": country,
                "Description": description,
                "ReleaseDate": release_date,
                "Language": language,
                "last_scraped": datetime.now(timezone.utc).isoformat()
            }
            existing_ids.add(movie_id)

        if new_movies:
            all_movies.update(new_movies)
            print(f"  ✅ Page {page} done: added {len(new_movies)} movies, total {len(all_movies)}")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_movies, f, indent=4, ensure_ascii=False)
        else:
            print(f"  ℹ️ Page {page}: no new movies extracted")

        if not daily_mode:
            save_progress(path, page)

    if failed_detail_urls:
        print(f"\n🔄 Retrying {len(failed_detail_urls)} failed detail URLs for {path}...")
        for url in list(failed_detail_urls):
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                movie_id = get_content_id(dsoup) or extract_numeric_id(url)
                if not movie_id:
                    match = re.search(r'-(\d+)$', url.rstrip('/'))
                    movie_id = match.group(1) if match else url.split('/')[-2]
                if movie_id and movie_id not in existing_ids:
                    all_movies[movie_id] = {
                        "Title": "Unknown (retried)",
                        "Category": path,
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Description": extract_description(dsoup),
                        "ReleaseDate": extract_release_date(dsoup),
                        "Language": extract_language(dsoup),
                        "last_scraped": datetime.now(timezone.utc).isoformat()
                    }
            sleep(1)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_movies, f, indent=4, ensure_ascii=False)

    print(f"\n🏁 {path} finished. Total movies: {len(all_movies)}")

def main():
    parser = argparse.ArgumentParser(description="Scrape FaselHD movie categories")
    parser.add_argument("--category", type=str, choices=MOVIE_PATHS + ["all"], default="all",
                        help="Specific category to scrape. Default: all")
    args = parser.parse_args()

    if args.category == "all":
        paths = MOVIE_PATHS
    else:
        paths = [args.category]

    for path in paths:
        scrape_category(path)
    print("\n🎉 All requested movie categories processed successfully!")

if __name__ == "__main__":
    main()