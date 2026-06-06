#!/usr/bin/env python3
"""
set_mal_id.py – Manually set or update MyAnimeList ID for a content item.
Updates the rating file in output/ratings/anime/ or output/ratings/anime-movies/ etc.
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"

def main():
    parser = argparse.ArgumentParser(description="Set MAL ID for a content item")
    parser.add_argument("--category", required=True, help="Category file name (e.g., anime.json, anime-movies.json)")
    parser.add_argument("--id", required=True, help="Content ID")
    parser.add_argument("--mal_id", required=True, help="MyAnimeList ID (integer, e.g., 274327)")
    args = parser.parse_args()

    # Validate MAL ID
    try:
        mal_id_int = int(args.mal_id)
        if mal_id_int <= 0:
            raise ValueError
    except ValueError:
        print(f"ERROR: Invalid MAL ID: {args.mal_id}. Must be a positive integer.")
        sys.exit(1)

    # Determine rating directory based on category stem
    category_stem = Path(args.category).stem
    rating_dir = RATINGS_DIR / category_stem
    rating_dir.mkdir(parents=True, exist_ok=True)

    rating_file = rating_dir / f"{args.id}.json"

    # Load existing rating data if any
    existing_data = None
    if rating_file.exists():
        with open(rating_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

    if existing_data:
        # Update existing rating file
        existing_data["mal_id"] = mal_id_int
        existing_data["source"] = "manual"
        existing_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        data = existing_data
        print(f"Updating existing rating file for {args.id}")
    else:
        # Create new rating file with minimal info
        data = {
            "content_id": args.id,
            "title": "Unknown (manual)",
            "year": None,
            "rating": None,
            "votes": 0,
            "source": "manual",
            "mal_id": mal_id_int,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        # Try to populate title and year from main JSON if available
        main_json = OUTPUT_DIR / args.category
        if main_json.exists():
            try:
                with open(main_json, "r", encoding="utf-8") as f:
                    main_data = json.load(f)
                if args.id in main_data:
                    item = main_data[args.id]
                    data["title"] = item.get("Title", "Unknown")
                    # ReleaseDate may be a year or full date; take first 4 digits if possible
                    release = item.get("ReleaseDate")
                    if release and isinstance(release, str) and release[:4].isdigit():
                        data["year"] = release[:4]
                    else:
                        data["year"] = None
            except Exception as e:
                print(f"Warning: Could not read main JSON for title: {e}")

    # Write the rating file
    with open(rating_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ MAL ID {mal_id_int} set for {args.category}/{args.id} in {rating_file}")

if __name__ == "__main__":
    main()