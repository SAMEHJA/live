#!/usr/bin/env python3
import sys
"""
match_series_imdb.py – For series without IMDb ID, search IMDbAPI by title and compare
season/episode structure to find a match. Once matched, fetch rating and release date.
"""

import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import requests

sys.path.insert(0, str(Path(__file__).parent))
from Common import fetch_imdbapi_by_id, IMDBAPI_BASE_URL

# ========== CONFIGURATION ==========
OUTPUT_DIR = Path("./output")
EPISODES_BASE = OUTPUT_DIR / "episodes"
RATINGS_DIR = OUTPUT_DIR / "ratings"

# Delay between API calls to avoid rate limiting
DELAY_SECONDS = 1.5

# Match threshold (0.8 = 80% similarity)
MATCH_THRESHOLD = 0.8

# Categories to process
SERIES_CATEGORIES = ["series", "tvshows", "asian-series", "anime"]

PROGRESS_FILE = OUTPUT_DIR / "match_series_progress.txt"
# ===================================

def load_progress() -> set:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_progress(series_id: str):
    with open(PROGRESS_FILE, "a") as f:
        f.write(f"{series_id}\n")

def fetch_title_details(imdb_id: str) -> Optional[dict]:
    """Fetch full title details from IMDbAPI."""
    url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"  Error fetching {imdb_id}: {e}")
    return None

def fetch_seasons_and_episodes(imdb_id: str) -> Dict[int, int]:
    """
    Fetch season numbers and episode counts for a given IMDb ID.
    Returns dict: {season_number: episode_count}
    """
    seasons = {}
    # First get the list of seasons
    url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}/seasons"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            season_list = data.get("seasons", [])
            # Each season object may have "season" (number) and "episodeCount"
            for s in season_list:
                season_num = s.get("season")
                episode_count = s.get("episodeCount")
                if season_num is not None and episode_count is not None:
                    seasons[season_num] = episode_count
                else:
                    # Fallback: fetch episodes per season individually
                    episodes_url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}/episodes?season={season_num}"
                    ep_resp = requests.get(episodes_url, timeout=10)
                    if ep_resp.status_code == 200:
                        ep_data = ep_resp.json()
                        episodes = ep_data.get("episodes", [])
                        seasons[season_num] = len(episodes)
        else:
            # If /seasons endpoint fails, try to get seasons from /episodes?season=1,2,... up to a limit
            season_num = 1
            while True:
                episodes_url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}/episodes?season={season_num}"
                ep_resp = requests.get(episodes_url, timeout=10)
                if ep_resp.status_code != 200:
                    break
                ep_data = ep_resp.json()
                episodes = ep_data.get("episodes", [])
                if not episodes:
                    break
                seasons[season_num] = len(episodes)
                season_num += 1
    except Exception as e:
        print(f"  Error fetching seasons for {imdb_id}: {e}")
    return seasons

def compare_season_episode_maps(local_map: Dict[int, int], imdb_map: Dict[int, int]) -> float:
    """
    Compute similarity score between two season->episode_count maps.
    Score = (number of matching seasons * 0.5) + (average episode count match ratio * 0.5)
    """
    if not local_map or not imdb_map:
        return 0.0

    local_seasons = set(local_map.keys())
    imdb_seasons = set(imdb_map.keys())

    # Season overlap score
    intersection_seasons = local_seasons & imdb_seasons
    season_score = len(intersection_seasons) / max(len(local_seasons), len(imdb_seasons))

    # Episode count similarity for common seasons
    ep_scores = []
    for season in intersection_seasons:
        local_eps = local_map[season]
        imdb_eps = imdb_map[season]
        if local_eps == 0 and imdb_eps == 0:
            ep_scores.append(1.0)
        else:
            ratio = min(local_eps, imdb_eps) / max(local_eps, imdb_eps)
            ep_scores.append(ratio)
    episode_score = sum(ep_scores) / len(ep_scores) if ep_scores else 0.0

    # Combine: season presence 50%, episode count 50%
    return season_score * 0.5 + episode_score * 0.5

def load_series_main_json(category: str) -> dict:
    """Load main JSON for a category (e.g., series.json)."""
    path = OUTPUT_DIR / f"{category}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_episode_structure(category: str, series_id: str) -> Dict[int, int]:
    """Load season -> episode count from episode JSON file."""
    ep_file = EPISODES_BASE / category / f"{series_id}.json"
    if not ep_file.exists():
        return {}
    with open(ep_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    seasons = data.get("seasons", {})
    season_map = {}
    for season_num, season_data in seasons.items():
        if isinstance(season_data, dict):
            episodes = season_data.get("episodes", [])
            season_map[int(season_num)] = len(episodes)
        elif isinstance(season_data, list):
            # plain list (anime format)
            season_map[int(season_num)] = len(season_data)
    return season_map

def search_imdbapi_by_title(title: str, year: Optional[str] = None) -> List[dict]:
    """Search IMDbAPI and return list of candidates (each with 'id', 'primaryTitle', 'startYear')."""
    params = {
        "query": title,
        "limit": 10,
        "sortBy": "SORT_BY_USER_RATING_COUNT",
        "sortOrder": "DESC"
    }
    if year:
        params["startYear"] = year
        params["endYear"] = year
    url = f"{IMDBAPI_BASE_URL}/search/titles"
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            titles = data.get("titles", [])
            candidates = []
            for t in titles:
                candidates.append({
                    "id": t.get("id"),
                    "primaryTitle": t.get("primaryTitle"),
                    "startYear": t.get("startYear")
                })
            return candidates
    except Exception as e:
        print(f"  Search error for '{title}': {e}")
    return []

def process_series(category: str, series_id: str, series_data: dict, processed_set: set):
    if series_id in processed_set:
        return

    # Check if already has IMDb ID in rating file
    rating_file = RATINGS_DIR / category / f"{series_id}.json"
    if rating_file.exists():
        with open(rating_file, "r") as f:
            rating_data = json.load(f)
        if rating_data.get("imdb_id"):
            print(f"  SKIP {series_id}: already has IMDb ID {rating_data['imdb_id']}")
            save_progress(series_id)
            return

    title = series_data.get("Title")
    if not title:
        save_progress(series_id)
        return

    year = None
    release_date = series_data.get("ReleaseDate")
    if release_date and len(release_date) >= 4:
        year = release_date[:4]

    print(f"\n🔍 Processing {category}/{series_id}: {title} (year={year})")

    # Load local episode structure
    local_season_map = load_episode_structure(category, series_id)
    if not local_season_map:
        print(f"  ⚠️ No episode data for {series_id}, cannot match.")
        save_progress(series_id)
        return

    # Search IMDbAPI for candidates
    candidates = search_imdbapi_by_title(title, year)
    if not candidates:
        print(f"  ❌ No candidates found for '{title}'")
        save_progress(series_id)
        return

    best_match = None
    best_score = 0.0
    for cand in candidates:
        cand_id = cand["id"]
        print(f"    Checking candidate: {cand['primaryTitle']} ({cand['startYear']}) [{cand_id}]")
        imdb_season_map = fetch_seasons_and_episodes(cand_id)
        if not imdb_season_map:
            print(f"      No season/episode data for {cand_id}")
            continue
        score = compare_season_episode_maps(local_season_map, imdb_season_map)
        print(f"      Similarity score: {score:.2f}")
        if score > best_score:
            best_score = score
            best_match = cand_id
        time.sleep(DELAY_SECONDS)  # be polite

    if best_match and best_score >= MATCH_THRESHOLD:
        print(f"  ✅ MATCH found: {best_match} (score {best_score:.2f})")
        # Fetch rating and release date using IMDb ID
        rating, votes = fetch_imdbapi_by_id(best_match)
        # Also fetch full title details for release date
        title_details = fetch_title_details(best_match)
        release_date_imdb = None
        if title_details:
            rd = title_details.get("releaseDate")
            if rd and rd.get("year"):
                release_date_imdb = f"{rd['year']}-{rd.get('month',1):02d}-{rd.get('day',1):02d}"
        # Update rating file
        rating_data = {
            "content_id": series_id,
            "title": title,
            "year": year,
            "rating": rating,
            "votes": votes,
            "source": "imdbapi_match",
            "imdb_id": best_match,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        rating_file.parent.mkdir(parents=True, exist_ok=True)
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"    Saved rating (source=imdbapi_match)")

        # Optionally update main JSON's ReleaseDate if missing
        main_json_path = OUTPUT_DIR / f"{category}.json"
        if main_json_path.exists() and release_date_imdb and not series_data.get("ReleaseDate"):
            with open(main_json_path, "r", encoding="utf-8") as f:
                main_data = json.load(f)
            if series_id in main_data and not main_data[series_id].get("ReleaseDate"):
                main_data[series_id]["ReleaseDate"] = release_date_imdb
                with open(main_json_path, "w", encoding="utf-8") as f:
                    json.dump(main_data, f, indent=4, ensure_ascii=False)
                print(f"    Updated main JSON ReleaseDate to {release_date_imdb}")
    else:
        print(f"  ❌ No match above threshold ({best_score:.2f} < {MATCH_THRESHOLD})")

    save_progress(series_id)

def main():
    parser = argparse.ArgumentParser(description="Match series by season/episode structure using IMDbAPI")
    parser.add_argument("--category", type=str, choices=SERIES_CATEGORIES, help="Limit to a specific category")
    args = parser.parse_args()

    categories = [args.category] if args.category else SERIES_CATEGORIES

    processed = load_progress()

    for cat in categories:
        print(f"\n{'='*60}")
        print(f"📺 Processing category: {cat}")
        print(f"{'='*60}")
        main_json = OUTPUT_DIR / f"{cat}.json"
        if not main_json.exists():
            print(f"  {cat}.json not found, skipping.")
            continue
        with open(main_json, "r", encoding="utf-8") as f:
            series_dict = json.load(f)

        total = len(series_dict)
        count = 0
        for series_id, series_data in series_dict.items():
            if series_id in processed:
                continue
            process_series(cat, series_id, series_data, processed)
            count += 1
            if count % 10 == 0:
                print(f"  Progress: {count}/{total} processed in {cat}")
            time.sleep(DELAY_SECONDS)  # delay between series

    print("\n✅ Done.")

if __name__ == "__main__":
    main()