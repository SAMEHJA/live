#!/usr/bin/env python3
"""
backfill_rating_years.py – One-time fix for series rating files.

For each rating file under ratings/{series categories}/,
fetches the correct first-aired year from IMDbAPI using the stored imdb_id
and overwrites the 'year' field if it differs.

Run once after this script is no longer needed.

Usage:
    python backfill_rating_years.py
    python backfill_rating_years.py --dry-run     # preview only, no writes
    python backfill_rating_years.py --category series
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from Common import fetch_start_year

RATINGS_DIR = Path("./output/ratings")
DELAY = 0.5  # seconds between IMDb requests

# Only series categories — movies use release year which is correct
SERIES_CATEGORIES = ["series", "tvshows", "asian-series"]


def process_category(category: str, dry_run: bool):
    cat_dir = RATINGS_DIR / category
    if not cat_dir.exists():
        print(f"  {category}/ not found, skipping.")
        return

    files = list(cat_dir.glob("*.json"))
    print(f"\n{'='*60}")
    print(f"  {category}: {len(files)} rating files")
    print(f"{'='*60}")

    updated = 0
    skipped = 0
    no_imdb = 0
    same = 0

    for rating_file in files:
        try:
            with open(rating_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            skipped += 1
            continue

        imdb_id = data.get("imdb_id")
        if not imdb_id or not imdb_id.startswith("tt"):
            no_imdb += 1
            continue

        current_year = data.get("year")
        time.sleep(DELAY)
        start_year = fetch_start_year(imdb_id)

        if not start_year:
            skipped += 1
            continue

        if start_year == str(current_year):
            same += 1
            continue

        # Guard: if new year is later than existing year, likely wrong IMDb match
        if current_year and int(start_year) > int(str(current_year)):
            print(f"  SUSPECT [{data.get('content_id')}] {data.get('title', '')[:40]} | {current_year} → {start_year} (flagged as suspect match)")
            if not dry_run:
                data["match_suspect"] = True
                data["last_updated"] = datetime.now(timezone.utc).isoformat()
                with open(rating_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            skipped += 1
            continue

        print(f"  [{data.get('content_id')}] {data.get('title', '')[:40]} | {current_year} → {start_year}")

        if not dry_run:
            data["year"] = start_year
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(rating_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        updated += 1

    print(f"\n  Updated: {updated} | Same: {same} | No IMDb ID: {no_imdb} | Skipped: {skipped}")
    if dry_run and updated > 0:
        print(f"  (dry-run — no files written)")


def main():
    parser = argparse.ArgumentParser(description="Backfill correct first-aired year into series rating files")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--category", type=str, choices=SERIES_CATEGORIES,                        help="Process only one category")
    args = parser.parse_args()

    targets = [args.category] if args.category else SERIES_CATEGORIES

    print(f"{'DRY RUN — ' if args.dry_run else ''}Backfilling year in rating files for: {', '.join(targets)}")

    for cat in targets:
        process_category(cat, args.dry_run)

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
