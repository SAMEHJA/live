#!/usr/bin/env python3
"""
update_runtime.py – Convert runtime to integer minutes using multiple sources.
Supports --sources imdbapi,tmdb,omdb (any order), --category, and --ids.
Parses existing runtime strings first, then tries API sources.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Tuple, Set
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from Common import fetch_imdbapi_by_id, OMDB_BASE_URL, OMDB_API_KEY, fetch_runtime_from_tmdb
import requests

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "runtime_update_progress.txt"

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

DELAYS = {
    "imdbapi": 1.0,
    "tmdb": 0.2,
    "omdb": 0.5,
}

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

def parse_runtime_string(runtime_str) -> Optional[int]:
    if runtime_str is None:
        return None
    if isinstance(runtime_str, int):
        return runtime_str if runtime_str > 0 else None
    runtime_str = str(runtime_str).strip().lower()
    if not runtime_str or runtime_str == "n/a":
        return None
    match = re.search(r'(\d+)\s*h(?:ours?)?\s*(?:(\d+)\s*m(?:in)?)?', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes
    match = re.search(r'(\d+)\s*m(?:in)?', runtime_str)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d{2}):(\d{2}):(\d{2})', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return hours * 60 + minutes
    match = re.search(r'(\d+)\s*س\s*(?:(\d+)\s*د)?', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes
    match = re.search(r'(\d+)\s*د', runtime_str)
    if match:
        return int(match.group(1))
    return None

def fetch_runtime_imdbapi(imdb_id: str) -> Optional[int]:
    url = f"https://api.imdbapi.dev/titles/{imdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            runtime_seconds = data.get("runtimeSeconds")
            if runtime_seconds:
                return runtime_seconds // 60
    except Exception as e:
        print(f"  IMDbAPI error for {imdb_id}: {e}")
    return None

def fetch_runtime_omdb(imdb_id: str) -> Optional[int]:
    url = f"{OMDB_BASE_URL}?i={imdb_id}&apikey={OMDB_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('Response') == 'True':
            runtime_str = data.get('Runtime', '')
            return parse_runtime_string(runtime_str)
    except Exception as e:
        print(f"  OMDb error for {imdb_id}: {e}")
    return None

def fetch_runtime_tmdb(imdb_id: str) -> Optional[int]:
    return fetch_runtime_from_tmdb(imdb_id)

def process_file(file_path: Path, content_type: str, processed_set: Set[Tuple[str, str]], sources: list, data: dict = None):
    print(f"\n[FILE] Processing {file_path.name} (sources: {sources})")
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

    modified = False
    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (file_path.name, content_id) in processed_set:
            continue

        if "runtime_minutes" in item and item["runtime_minutes"] is not None:
            print(f"  SKIP {content_id}: already has runtime_minutes={item['runtime_minutes']}")
            save_progress(file_path.name, content_id)
            continue

        # Determine rating file path with fallback for movies
        category_stem = file_path.stem.split('.')[0]  # e.g., "movies", "series"
        base_dir = RATINGS_DIR / category_stem

        if category_stem == "movies":
            rating_file = base_dir / f"{content_id}.json"
            if not rating_file.exists():
                rating_file = RATINGS_DIR / "movies2" / f"{content_id}.json"
        else:
            rating_file = base_dir / f"{content_id}.json"

        # Ensure parent directory exists (for movies2 case)
        rating_file.parent.mkdir(parents=True, exist_ok=True)

        imdb_id = None
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    rating_data = json.load(rf)
                    imdb_id = rating_data.get("imdb_id")
            except:
                pass

        runtime_minutes = None
        existing_runtime = item.get("Runtime") or item.get("runtime") or item.get("EpisodeDuration")
        if existing_runtime:
            runtime_minutes = parse_runtime_string(existing_runtime)
            if runtime_minutes:
                print(f"  PARSED {content_id}: '{existing_runtime}' -> {runtime_minutes} min")

        if not runtime_minutes and imdb_id and imdb_id.startswith("tt"):
            for src in sources:
                if src == "imdbapi":
                    runtime_minutes = fetch_runtime_imdbapi(imdb_id)
                elif src == "tmdb":
                    runtime_minutes = fetch_runtime_tmdb(imdb_id)
                elif src == "omdb":
                    runtime_minutes = fetch_runtime_omdb(imdb_id)
                else:
                    continue
                if runtime_minutes:
                    print(f"  FETCHED {content_id}: from {src} -> {runtime_minutes} min")
                    break
                time.sleep(DELAYS.get(src, 1.0))
            if not runtime_minutes:
                print(f"  FAILED {content_id}: no runtime from sources {sources}")

        if runtime_minutes:
            item["runtime_minutes"] = runtime_minutes
            modified = True
        else:
            print(f"  SKIP {content_id}: no runtime available")
        save_progress(file_path.name, content_id)

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  UPDATED {file_path.name}")

def main():
    parser = argparse.ArgumentParser(description="Update runtime (convert to minutes) using multiple sources")
    parser.add_argument("--sources", type=str, default="imdbapi,tmdb,omdb",
                        help="Comma-separated sources in priority order (imdbapi, tmdb, omdb). Default: imdbapi,tmdb,omdb")
    parser.add_argument("--category", type=str, help="Process only a specific category file (e.g., movies.json)")
    parser.add_argument("--ids", nargs="+", help="Space‑separated list of content IDs to process (e.g., 12345 67890)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")]
    valid = {"imdbapi", "tmdb", "omdb"}
    for s in sources:
        if s not in valid:
            print(f"ERROR: Invalid source '{s}'. Choose from {valid}")
            sys.exit(1)

    print(f"Starting runtime update with sources: {sources}")
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        if args.category and filename != args.category:
            continue
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            print(f"WARNING: {filename} not found, skipping.")
            continue

        if args.ids:
            with open(file_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
            filtered_data = {cid: full_data[cid] for cid in args.ids if cid in full_data}
            if not filtered_data:
                print(f"WARNING: None of the requested IDs found in {filename}")
                continue
            process_file(file_path, media_type, processed, sources, data=filtered_data)
        else:
            process_file(file_path, media_type, processed, sources)

    print("\nDone.")

if __name__ == "__main__":
    main()