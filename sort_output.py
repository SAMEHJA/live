#!/usr/bin/env python3
"""
sort_output.py – Sort all category JSON dicts into pre-sorted arrays.

Reads:   ./output/{category}.json          (dict keyed by id)
Writes:  ./output/sorted/{category}.json   (array, newest-first)

Sort order:
  1. ReleaseDate desc  (year wins)
  2. last_scraped desc (tiebreaker for same-year items)

trending and featured are skipped — they're already structured objects,
not item dicts, and are served as-is from app.py.

Run after scraping:
    python sort_output.py
    python sort_output.py --category movies   (single category)
"""

import json
import os
import argparse
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("./output")
SORTED_DIR = OUTPUT_DIR / "sorted"

# All sortable categories — includes both Fasel and Akwam
CATEGORIES = [
    "movies",
    "dubbed-movies",
    "hindi",
    "asian-movies",
    "anime-movies",
    "anime",
    "series",
    "tvshows",
    "asian-series",
    "arabic-series",
]

CURRENT_YEAR = datetime.now().year


def _parse_year(val) -> int:
    """Extract a 4-digit year as int. Returns 0 if unparseable."""
    if not val:
        return 0
    try:
        n = int(str(val)[:4])
        # Sanity-cap: reject sci-fi plot years and obviously wrong values
        if 1900 <= n <= CURRENT_YEAR + 2:
            return n
    except (ValueError, TypeError):
        pass
    return 0


def sort_category(category: str) -> bool:
    """
    Load ./output/{category}.json, sort it, write to ./output/sorted/{category}.json.
    Returns True on success, False if file not found or invalid.
    """
    input_path = OUTPUT_DIR / f"{category}.json"
    output_path = SORTED_DIR / f"{category}.json"

    if not input_path.exists():
        print(f"  ⚠️  {category}.json not found, skipping.")
        return False

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ❌ Failed to load {category}.json: {e}")
        return False

    if not isinstance(data, dict):
        print(f"  ⚠️  {category}.json is not a dict (already an array?), skipping.")
        return False

    items = list(data.values())

    # Stamp id onto each item if missing (arabic-series stores id inside metadata,
    # fasel items may not have it embedded)
    for item_id, item in data.items():
        if isinstance(item, dict) and "id" not in item:
            item["id"] = item_id

    # Schwartzian transform — compute sort keys once, not once per comparison
    tagged = []
    for item in items:
        if not isinstance(item, dict):
            continue
        year = _parse_year(item.get("ReleaseDate") or item.get("Year") or item.get("year"))
        scraped = item.get("last_scraped") or ""
        tagged.append((item, year, scraped))

    tagged.sort(key=lambda x: (x[1], x[2]), reverse=True)
    sorted_items = [t[0] for t in tagged]

    SORTED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sorted_items, f, ensure_ascii=False)
    except OSError as e:
        print(f"  ❌ Failed to write {output_path}: {e}")
        return False

    print(f"  ✅ {category}: {len(sorted_items)} items → sorted/{category}.json")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sort output JSON dicts into pre-sorted arrays.")
    parser.add_argument(
        "--category",
        type=str,
        choices=CATEGORIES,
        help="Sort a single category only. Default: all.",
    )
    args = parser.parse_args()

    targets = [args.category] if args.category else CATEGORIES

    print(f"\n{'='*50}")
    print(f"  sort_output.py — {len(targets)} categor{'y' if len(targets) == 1 else 'ies'}")
    print(f"{'='*50}")

    success = 0
    for cat in targets:
        if sort_category(cat):
            success += 1

    print(f"\n🏁 Done. {success}/{len(targets)} sorted successfully.")
    print(f"   Output: {SORTED_DIR.resolve()}\n")


if __name__ == "__main__":
    main()
