#!/usr/bin/env python3
"""
backfill.py – Unified backfill script.

Tasks:
1. descriptions – fills missing 'Description' fields and adds 'last_scraped' for all categories except movies.
2. movies      – ONE‑PASS backfill for movies: fetches each movie page once and extracts Description and last_scraped.
3. all         – runs descriptions (non‑movie) and movies.

Usage:
    python backfill.py --descriptions
    python backfill.py --movies
    python backfill.py --all
"""

import argparse
import json
import os
import time
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    get_website_safe, extract_description,
    REQUEST_DELAY
)

# ========== SIGNAL HANDLER – force exit on Ctrl+C ==========
def _exit_gracefully(signum, frame):
    print("\n⚠️ Interrupted. Exiting now...")
    sys.exit(0)

signal.signal(signal.SIGINT, _exit_gracefully)
signal.signal(signal.SIGTERM, _exit_gracefully)
# ===========================================================

# ========== CONFIGURATION ==========
# Files for description backfill (series, anime, etc. – NOT movies)
DESCRIPTION_FILES = {
    "anime.json": "anime",
    "series.json": "series",
    "tvshows.json": "tvshows",
    "asian-series.json": "asian-series",
}

# Only movie categories for the combined movie task
MOVIE_FILES = {
    "movies.json": "movies",
    "dubbed-movies.json": "movies",
    "hindi.json": "movies",
    "asian-movies.json": "movies",
    "anime-movies.json": "movies",
}

# Backfill settings
MAX_WORKERS = 6
SAVE_INTERVAL = 6          # save main JSON after this many updates
BATCH_DELAY = 2             # seconds between batches
# ===================================

def load_progress(progress_file: str) -> set:
    """Load the set of already-completed item IDs from a plain text file (one ID per line)."""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return {line.strip() for line in f if line.strip()}
        except Exception:
            pass
    return set()

def save_progress(progress_file: str, done_ids: set):
    """Atomically write completed item IDs to a plain text file (one ID per line)."""
    tmp = progress_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for item_id in sorted(done_ids):
            f.write(item_id + "\n")
    os.replace(tmp, progress_file)

def get_detail_url_for_item(item_id: str, item_data: dict, is_movie: bool = False) -> str:
    """
    Construct the correct detail page URL for a given item.
    For series: use stored 'SeasonsUrl' if present, else construct from Category + ID.
    For movies: use ?p=ID (works reliably), ignoring the Category path.
    """
    # First, try to use SeasonsUrl (if present, for any category)
    if "SeasonsUrl" in item_data and item_data["SeasonsUrl"]:
        return item_data["SeasonsUrl"]
    
    # For movies, use the query parameter (proven to work)
    if is_movie:
        return f"https://www.fasel-hd.cam/?p={item_id}"
    
    # For non‑movies, fallback to category path
    category_path = item_data.get("Category", "")
    if category_path:
        return f"https://www.fasel-hd.cam/{category_path}/{item_id}/"
    
    # Last resort – also works for some movies but not series
    return f"https://www.fasel-hd.cam/?p={item_id}"

def fetch_description(item_id: str, detail_url: str) -> str:
    """Fetch a single detail page and return its description."""
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        return extract_description(soup)
    return ""

def fetch_movie_data(item_id: str, detail_url: str) -> str:
    """Alias for fetch_description (same logic)."""
    return fetch_description(item_id, detail_url)

# ----------------------------------------------------------------------
# Description backfill (for non‑movie categories)
# ----------------------------------------------------------------------
def backfill_descriptions_for_file(json_path: Path, category: str):
    print(f"\n📖 Backfilling descriptions & last_scraped for {json_path.name}")
    if not json_path.exists():
        print(f"  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)

    # Use .txt extension for progress files
    progress_file = str(json_path).replace(".json", "_desc_progress.txt")
    done_ids = load_progress(progress_file)

    # Items that already have a non-empty description AND last_scraped are considered fully done
    already_done = {
        item_id for item_id, item_data in items
        if item_data.get("Description") and item_data.get("last_scraped")
    }
    done_ids |= already_done

    # Items not yet in done_ids need processing (even if they have an empty description)
    remaining = [(item_id, item_data) for item_id, item_data in items if item_id not in done_ids]
    print(f"  {len(already_done)} already have valid description + last_scraped, {len(remaining)} remaining / {total} total")

    if not remaining:
        print(f"  ✅ Nothing to do for {json_path.name}")
        if os.path.exists(progress_file):
            os.remove(progress_file)
        return

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _save_json():
        tmp = str(json_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, str(json_path))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(remaining), MAX_WORKERS):
            batch = remaining[i:i + MAX_WORKERS]
            futures = {}
            for item_id, item_data in batch:
                detail_url = get_detail_url_for_item(item_id, item_data, is_movie=False)
                futures[executor.submit(fetch_description, item_id, detail_url)] = (item_id, item_data)

            for future in as_completed(futures):
                item_id, item_data = futures[future]
                desc = future.result()
                with lock:
                    changed = False

                    # If we got a non-empty description and the current one is missing/empty
                    if desc and not item_data.get("Description"):
                        item_data["Description"] = desc
                        updated_count += 1
                        print(f"  [{i+1}/{len(remaining)}] ✅ {item_id} – description ({len(desc)} chars)", flush=True)
                        changed = True
                    elif not desc and not item_data.get("Description"):
                        # No description on page, and item has no description (None or empty)
                        item_data["Description"] = ""
                        print(f"  [{i+1}/{len(remaining)}] ⚠️  No description for {item_id}", flush=True)
                        changed = True
                    else:
                        # Item already has a description (non-empty) – just report skip
                        print(f"  [{i+1}/{len(remaining)}] ⏭️  Skip {item_id} – already has description", flush=True)

                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        changed = True

                    # ALWAYS mark this ID as done, regardless of changes
                    done_ids.add(item_id)
                    save_progress(progress_file, done_ids)

                    if changed and updated_count > 0 and updated_count % SAVE_INTERVAL == 0:
                        _save_json()
                        print(f"  💾 Saved JSON (updated {updated_count} items so far)", flush=True)

            time.sleep(BATCH_DELAY)

    _save_json()

    # Clean up progress file only if all items are done (this will happen after the loop finishes)
    if len(done_ids) >= total:
        if os.path.exists(progress_file):
            os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: updated {updated_count} items (descriptions and/or last_scraped).")

def backfill_all_descriptions():
    for filename, category in DESCRIPTION_FILES.items():
        file_path = Path("./output") / filename
        backfill_descriptions_for_file(file_path, category)

# ----------------------------------------------------------------------
# COMBINED MOVIE BACKFILL (description + last_scraped in one pass)
# ----------------------------------------------------------------------
def backfill_movies_combined(json_path: Path, category: str):
    print(f"\n🎬 Combined movie backfill (desc + last_scraped) for {json_path.name}")
    if not json_path.exists():
        print(f"  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)

    # Use .txt extension for progress files
    progress_file = str(json_path).replace(".json", "_movie_progress.txt")
    done_ids = load_progress(progress_file)

    already_done = {
        item_id for item_id, item_data in items
        if item_data.get("Description") and item_data.get("last_scraped")
    }
    done_ids |= already_done

    remaining = [(item_id, item_data) for item_id, item_data in items if item_id not in done_ids]
    print(f"  {len(already_done)} already have valid description + last_scraped, {len(remaining)} remaining / {total} total")

    if not remaining:
        print(f"  ✅ Nothing to do for {json_path.name}")
        if os.path.exists(progress_file):
            os.remove(progress_file)
        return

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _save_json():
        tmp = str(json_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, str(json_path))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(remaining), MAX_WORKERS):
            batch = remaining[i:i + MAX_WORKERS]
            futures = {}
            for item_id, item_data in batch:
                detail_url = get_detail_url_for_item(item_id, item_data, is_movie=True)
                futures[executor.submit(fetch_movie_data, item_id, detail_url)] = (item_id, item_data)

            for future in as_completed(futures):
                item_id, item_data = futures[future]
                description = future.result()
                with lock:
                    changed = False

                    if description and not item_data.get("Description"):
                        item_data["Description"] = description
                        updated_count += 1
                        print(f"  [{i+1}/{len(remaining)}] ✅ {item_id} ({len(description)} chars)", flush=True)
                        changed = True
                    elif not description and not item_data.get("Description"):
                        item_data["Description"] = ""
                        print(f"  [{i+1}/{len(remaining)}] ⚠️  No description for {item_id}", flush=True)
                        changed = True
                    else:
                        print(f"  [{i+1}/{len(remaining)}] ⏭️  Skip {item_id} – already has description", flush=True)

                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        changed = True

                    done_ids.add(item_id)
                    save_progress(progress_file, done_ids)

                    if changed and updated_count > 0 and updated_count % SAVE_INTERVAL == 0:
                        _save_json()
                        print(f"  💾 Saved JSON (updated {updated_count} items so far)", flush=True)

            time.sleep(BATCH_DELAY)

    _save_json()

    if len(done_ids) >= total:
        if os.path.exists(progress_file):
            os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: updated {updated_count} movies (description + last_scraped).")

def backfill_all_movies():
    print("\n🎬 Starting combined movie backfill (description + last_scraped)...")
    for filename, category in MOVIE_FILES.items():
        file_path = Path("./output") / filename
        backfill_movies_combined(file_path, category)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified backfill script")
    parser.add_argument(
        "--task",
        choices=["descriptions", "movies", "all"],
        default="all",
        help="Which backfill task to run. Default: all"
    )
    args = parser.parse_args()

    if args.task in ("descriptions", "all"):
        print("="*60)
        print("📖 Running description + last_scraped backfill (non‑movie categories)...")
        print("="*60)
        backfill_all_descriptions()

    if args.task in ("movies", "all"):
        print("\n" + "="*60)
        print("🎬 Running combined movie backfill (description + last_scraped)...")
        print("="*60)
        backfill_all_movies()

    print("\n✅ All requested backfill tasks completed.")

if __name__ == "__main__":
    main()