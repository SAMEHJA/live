#!/usr/bin/env python3
"""
set_imdb_id.py – Manually set or update IMDb ID for a content item.
Updates the rating file. For movies, writes to output/ratings/movies/ (not movies2).
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"

def main():
    parser = argparse.ArgumentParser(description="Set IMDb ID for a content item")
    parser.add_argument("--category", required=True, help="Category file name (e.g., movies.json)")
    parser.add_argument("--id", required=True, help="Content ID")
    parser.add_argument("--imdb_id", required=True, help="IMDb ID (e.g., tt1234567)")
    args = parser.parse_args()

    if not args.imdb_id.startswith("tt") or not args.imdb_id[2:].isdigit():
        print(f"ERROR: Invalid IMDb ID format: {args.imdb_id}. Must start with 'tt' followed by digits.")
        sys.exit(1)

    category_stem = Path(args.category).stem
    base_dir = RATINGS_DIR / category_stem

    # For movies, write to movies/ (the main folder). The balancing script will later move extras to movies2.
    rating_dir = base_dir
    if category_stem == "movies":
        rating_dir = RATINGS_DIR / "movies"

    rating_dir.mkdir(parents=True, exist_ok=True)
    rating_file = rating_dir / f"{args.id}.json"

    # Load existing data if any (try both movies and movies2)
    existing_data = None
    if rating_file.exists():
        with open(rating_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    elif category_stem == "movies":
        fallback_file = RATINGS_DIR / "movies2" / f"{args.id}.json"
        if fallback_file.exists():
            with open(fallback_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            print(f"Found existing rating in movies2/, will overwrite in movies/")

    if existing_data:
        existing_data["imdb_id"] = args.imdb_id
        existing_data["source"] = "manual"
        existing_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        data = existing_data
    else:
        data = {
            "content_id": args.id,
            "title": "Unknown (manual)",
            "year": None,
            "rating": None,
            "votes": 0,
            "source": "manual",
            "imdb_id": args.imdb_id,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        # Try to get title from main JSON if possible
        main_json = OUTPUT_DIR / args.category
        if main_json.exists():
            try:
                with open(main_json, "r", encoding="utf-8") as f:
                    main_data = json.load(f)
                if args.id in main_data:
                    data["title"] = main_data[args.id].get("Title", "Unknown")
                    data["year"] = main_data[args.id].get("ReleaseDate") or None
            except:
                pass

    with open(rating_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ IMDb ID {args.imdb_id} set for {args.category}/{args.id} in {rating_file.parent}")

if __name__ == "__main__":
    main()