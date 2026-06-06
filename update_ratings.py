#!/usr/bin/env python3
"""
update_ratings.py – Flexible rating fetcher.
If --tmdb-first is used: tries TMDb to get IMDb ID, then fetches rating from IMDbAPI.
Otherwise uses the source order (--sources).
Supports --category to process only one JSON file.
Supports --ids to process only specific content IDs.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from Common import (
    get_tmdb_details, get_imdb_details, search_imdbapi_dev, get_tmdb_imdb_id,
    fetch_imdbapi_by_id, fetch_start_year
)

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"

# Delays (seconds) per source
DELAYS = {
    "imdbapi": 2.0,
    "tmdb": 0.04,
    "omdb": 0.5,
}
OMDB_DAILY_LIMIT = 1000
CURRENT_YEAR = datetime.now().year

CONTENT_FILES = {
    "movies.json": "movie",
    "dubbed-movies.json": "movie",
    "hindi.json": "movie",
    "asian-movies.json": "movie",
    "anime-movies.json": "movie",
    "anime.json": "tv",
    "series.json": "tv",
    "tvshows.json": "tv",
    "asian-series.json": "tv",
}

tmdb_cache: Dict[str, tuple] = {}
imdbapi_cache: Dict[str, tuple] = {}
omdb_calls_today = 0

def load_caches():
    global tmdb_cache, imdbapi_cache
    cache_dir = RATINGS_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmdb_cache_file = cache_dir / "tmdb_cache.json"
    if tmdb_cache_file.exists():
        with open(tmdb_cache_file, "r") as f:
            tmdb_cache = {k: tuple(v) for k, v in json.load(f).items()}
        print(f"[INFO] Loaded {len(tmdb_cache)} TMDb cache entries.")
    imdbapi_cache_file = cache_dir / "imdbapi_cache.json"
    if imdbapi_cache_file.exists():
        with open(imdbapi_cache_file, "r") as f:
            imdbapi_cache = {k: tuple(v) for k, v in json.load(f).items()}
        print(f"[INFO] Loaded {len(imdbapi_cache)} IMDbAPI cache entries.")

def save_caches():
    serializable_tmdb = {k: list(v) for k, v in tmdb_cache.items()}
    with open(RATINGS_DIR / "tmdb_cache.json", "w") as f:
        json.dump(serializable_tmdb, f, indent=2)
    serializable_imdbapi = {k: list(v) for k, v in imdbapi_cache.items()}
    with open(RATINGS_DIR / "imdbapi_cache.json", "w") as f:
        json.dump(serializable_imdbapi, f, indent=2)

def load_progress() -> Set[Tuple[str, str]]:
    processed = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        processed.add((parts[0], parts[1]))
    return processed

def save_progress(category: str, content_id: str):
    with open(PROGRESS_FILE, "a") as f:
        f.write(f"{category}|{content_id}\n")

def clean_title(raw_title: str) -> str:
    arabic_stop = ["فيلم", "مسلسل", "مترجم", "اون لاين", "اونلاين", "مدبلج", "الحلقة", "الفيلم"]
    cleaned = raw_title
    for word in arabic_stop:
        cleaned = re.sub(rf'\b{word}\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    cleaned = re.sub(r'[^\w\s\'\-,&:.]', ' ', cleaned, flags=re.UNICODE)
    cleaned = ' '.join(cleaned.split())
    return cleaned if cleaned else raw_title

def extract_year(title: str, release_date: Optional[str]) -> Optional[str]:
    if release_date:
        m = re.search(r'\b(19|20)\d{2}\b', release_date)
        if m:
            return m.group(0)
    m = re.search(r'\b(19|20)\d{2}\b', title)
    return m.group(0) if m else None

# ---- Source functions (fallback) ----
def fetch_tmdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in tmdb_cache:
        rating, votes, imdb_id = tmdb_cache[cache_key]
        if rating is not None:
            print(f"  [TMDb CACHE] '{cleaned}' -> rating={rating}, votes={votes}")
            return rating, votes, imdb_id, "tmdb"
    rating, votes = get_tmdb_details(cleaned, year, content_type)
    imdb_id = get_tmdb_imdb_id(cleaned, year, content_type)
    tmdb_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [TMDb] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [TMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "tmdb"

def fetch_imdbapi(cleaned: str, year: Optional[str]) -> tuple:
    cache_key = f"{cleaned}|{year}"
    if cache_key in imdbapi_cache:
        rating, votes, imdb_id = imdbapi_cache[cache_key]
        if rating is not None:
            print(f"  [IMDbAPI CACHE] '{cleaned}' -> rating={rating}, votes={votes}")
            return rating, votes, imdb_id, "imdbapi"
    time.sleep(DELAYS["imdbapi"])
    rating, votes, imdb_id = search_imdbapi_dev(cleaned, year, relaxed=False)
    if rating is None and year:
        print(f"  [IMDbAPI] Strict match failed, waiting 2s before relaxed...")
        time.sleep(2.0)
        rating, votes, imdb_id = search_imdbapi_dev(cleaned, year, relaxed=True)
    imdbapi_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [IMDbAPI] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [IMDbAPI] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "imdbapi"

def fetch_omdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    global omdb_calls_today
    if omdb_calls_today >= OMDB_DAILY_LIMIT:
        print(f"  [OMDb] Daily limit reached ({omdb_calls_today}) – skipping.")
        return None, 0, None, "omdb"
    time.sleep(DELAYS["omdb"])
    rating, votes, imdb_id, limit_reached = get_imdb_details(cleaned, year, content_type, known_imdb_id=None)
    omdb_calls_today += 1
    if limit_reached:
        print(f"  [OMDb] API limit reached – stopping further OMDb calls.")
        sys.exit(1)
    if rating is not None:
        print(f"  [OMDb] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [OMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "omdb"

def get_rating_from_sources(cleaned: str, year: Optional[str], content_type: str, sources: list) -> tuple:
    for src in sources:
        if src == "imdbapi":
            rating, votes, imdb_id, used = fetch_imdbapi(cleaned, year)
        elif src == "tmdb":
            rating, votes, imdb_id, used = fetch_tmdb(cleaned, year, content_type)
        elif src == "omdb":
            rating, votes, imdb_id, used = fetch_omdb(cleaned, year, content_type)
        else:
            raise ValueError(f"Unknown source: {src}")
        if rating is not None:
            return rating, votes, imdb_id, used
        time.sleep(0.5)
    return None, 0, None, "none"

def process_file(file_path: Path, content_type: str, processed_set: Set[Tuple[str, str]], sources: list, tmdb_first: bool, data: dict = None):
    print(f"\n[FILE] Processing {file_path.name} (type: {content_type}) - sources: {sources}, tmdb_first={tmdb_first}")
    if data is None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ERROR: Cannot load {file_path}: {e}")
            return

    if not isinstance(data, dict):
        print("  WARNING: Not a dictionary, skipping.")
        return

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (file_path.name, content_id) in processed_set:
            continue

        title = item.get("Title")
        if not title:
            save_progress(file_path.name, content_id)
            continue

        year = extract_year(title, item.get("ReleaseDate"))

        # Determine rating file path with parity split for movies
        category_stem = file_path.stem.split('.')[0]  # e.g., "movies", "series"
        base_dir = RATINGS_DIR / category_stem

        if category_stem in ["movies", "dubbed-movies", "hindi", "asian-movies", "anime-movies"]:
            # For movie categories, split into two folders based on ID parity
            # Even IDs go to movies/, odd IDs go to movies2/
            if int(content_id) % 2 == 0:
                rating_dir = RATINGS_DIR / "movies"
            else:
                rating_dir = RATINGS_DIR / "movies2"
        else:
            rating_dir = base_dir

        rating_dir.mkdir(parents=True, exist_ok=True)
        rating_file = rating_dir / f"{content_id}.json"

        # Load existing rating file (if any) – also check fallback location for movies
        existing_imdb_id = None
        existing_mal_id = None
        existing_source = None
        existing_rating = None
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                existing_rating = existing.get("rating")
                existing_source = existing.get("source")
                existing_imdb_id = existing.get("imdb_id")
                existing_mal_id = existing.get("mal_id")
            except:
                pass
        elif category_stem in ["movies", "dubbed-movies", "hindi", "asian-movies", "anime-movies"]:
            # Try the opposite folder (if migration happened)
            fallback_dir = RATINGS_DIR / ("movies" if int(content_id) % 2 != 0 else "movies2")
            fallback_file = fallback_dir / f"{content_id}.json"
            if fallback_file.exists():
                try:
                    with open(fallback_file, "r") as rf:
                        existing = json.load(rf)
                    existing_rating = existing.get("rating")
                    existing_source = existing.get("source")
                    existing_imdb_id = existing.get("imdb_id")
                    existing_mal_id = existing.get("mal_id")
                except:
                    pass

        # If MAL already handled this item, skip entirely — MAL takes priority
        if existing_mal_id:
            print(f"  SKIP {content_id}: has mal_id, MAL takes priority")
            save_progress(file_path.name, content_id)
            continue

        # If we already have a rating and it's from IMDbAPI, skip
        if existing_rating is not None and existing_rating not in (None, "N/A") and existing_source == "imdbapi":
            print(f"  SKIP {content_id}: already rated from IMDbAPI ({existing_rating})")
            save_progress(file_path.name, content_id)
            continue

        # If we have an IMDb ID, use it directly (upgrade path)
        if existing_imdb_id and existing_imdb_id.startswith("tt"):
            print(f"  [UPGRADE] {content_id}: using stored IMDb ID {existing_imdb_id} to fetch IMDb rating")
            rating, votes = fetch_imdbapi_by_id(existing_imdb_id)
            if rating is not None:
                rating_data = {
                    "content_id": content_id,
                    "title": title,
                    "year": year,
                    "rating": rating,
                    "votes": votes,
                    "source": "imdbapi",
                    "imdb_id": existing_imdb_id,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                with open(rating_file, "w", encoding="utf-8") as f:
                    json.dump(rating_data, f, indent=2, ensure_ascii=False)
                print(f"  SUCCESS (upgraded) {content_id}: rating={rating}, votes={votes}, source=imdbapi")
                save_progress(file_path.name, content_id)
                continue
            else:
                print(f"  [UPGRADE] Failed to fetch from IMDb ID {existing_imdb_id}, falling back to sources")

        # If we already have a numeric rating from other source, skip (no IMDb ID to upgrade)
        if existing_rating is not None and existing_rating not in (None, "N/A"):
            print(f"  SKIP {content_id}: already rated {existing_rating} (source: {existing_source}) – no IMDb ID to upgrade")
            save_progress(file_path.name, content_id)
            continue

        cleaned = clean_title(title)
        if year and int(year) > CURRENT_YEAR:
            print(f"  SKIP {content_id}: future year {year}")
            save_progress(file_path.name, content_id)
            continue

        rating = None
        votes = 0
        imdb_id = None
        source_used = None

        # ---- TMDb-first mode ----
        if tmdb_first:
            print(f"  [TMDb-first] Trying to get IMDb ID for '{title}'")
            tmdb_imdb_id = get_tmdb_imdb_id(cleaned, year, content_type) if year else None
            if not tmdb_imdb_id:
                tmdb_imdb_id = get_tmdb_imdb_id(cleaned, None, content_type)
            if tmdb_imdb_id:
                print(f"  [TMDb-first] Found IMDb ID: {tmdb_imdb_id}")
                time.sleep(DELAYS["imdbapi"])
                rating, votes = fetch_imdbapi_by_id(tmdb_imdb_id)
                if rating is not None:
                    source_used = "imdbapi (via TMDb)"
                    imdb_id = tmdb_imdb_id
                    print(f"  [IMDbAPI] Rating from ID: {rating}, votes={votes}")
                else:
                    print(f"  [TMDb-first] Rating fetch failed, falling back to source chain")
            else:
                print(f"  [TMDb-first] No IMDb ID found, falling back to source chain")

        # ---- Fallback to source chain if TMDb-first didn't succeed ----
        if rating is None:
            rating, votes, imdb_id, source_used = get_rating_from_sources(cleaned, year, content_type, sources)

        if rating is None:
            print(f"  FAILED {content_id}: no rating from any source")
            continue

        # For series/tv prefer the real first-aired year from IMDb over scraped title year
        final_year = year
        if imdb_id and imdb_id.startswith("tt") and content_type == "tv":
            start_year = fetch_start_year(imdb_id)
            if start_year:
                final_year = start_year
        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": final_year,
            "rating": rating,
            "votes": votes,
            "source": source_used,
            "imdb_id": imdb_id,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"  SUCCESS {content_id}: rating={rating}, votes={votes}, source={source_used}")

        save_progress(file_path.name, content_id)
        time.sleep(0.2)

def main():
    parser = argparse.ArgumentParser(description="Flexible rating fetcher")
    parser.add_argument("--sources", type=str, default="imdbapi,tmdb,omdb",
                        help="Comma-separated list of sources (imdbapi,tmdb,omdb). Default: imdbapi,tmdb,omdb")
    parser.add_argument("--category", type=str, help="Process only a specific category file (e.g., movies.json)")
    parser.add_argument("--tmdb-first", action="store_true",
                        help="Try TMDb to get IMDb ID first, then fetch rating from IMDbAPI. Fallback to --sources.")
    parser.add_argument("--ids", nargs="+", help="Space‑separated list of content IDs to process (e.g., 12345 67890)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")]
    valid_sources = {"imdbapi", "tmdb", "omdb"}
    for s in sources:
        if s not in valid_sources:
            print(f"ERROR: Invalid source '{s}'. Choose from {valid_sources}")
            sys.exit(1)

    print(f"Starting rating update. Sources: {sources}, TMDb-first: {args.tmdb_first}")
    load_caches()
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        if args.category and filename != args.category:
            continue
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            print(f"WARNING: {filename} not found, skipping.")
            continue

        if args.ids:
            # Load the full file and filter only requested IDs
            with open(file_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
            filtered_data = {cid: full_data[cid] for cid in args.ids if cid in full_data}
            if not filtered_data:
                print(f"WARNING: None of the requested IDs found in {filename}")
                continue
            process_file(file_path, media_type, processed, sources, args.tmdb_first, data=filtered_data)
        else:
            process_file(file_path, media_type, processed, sources, args.tmdb_first)

    save_caches()
    print(f"\nFinished. OMDb calls used today: {omdb_calls_today} / {OMDB_DAILY_LIMIT}")

if __name__ == "__main__":
    main()