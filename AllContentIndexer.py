import json
import os
import re

# All content JSON files produced by scrapers (excluding trending/featured)
CONTENT_FILES = [
    "movies.json", "dubbed-movies.json", "hindi.json", "asian-movies.json", "anime-movies.json",
    "anime.json", "series.json", "tvshows.json", "asian-series.json"
]

# Map filename → category key (must match app's CATEGORIES keys exactly)
FILENAME_TO_CATEGORY = {
    "movies.json":        "movies",
    "dubbed-movies.json": "dubbed-movies",
    "hindi.json":         "hindi",
    "asian-movies.json":  "asian-movies",
    "anime-movies.json":  "anime-movies",
    "anime.json":         "anime",
    "series.json":        "series",
    "tvshows.json":       "tvshows",
    "asian-series.json":  "asian-series",
}

def extract_year_from_item(item: dict) -> str:
    """Extract year from ReleaseDate or fallback to Title."""
    release_date = item.get("ReleaseDate")
    if release_date and isinstance(release_date, str):
        m = re.search(r'\b(19|20)\d{2}\b', release_date)
        if m:
            return m.group(0)
    title = item.get("Title", "")
    m = re.search(r'\b(19|20)\d{2}\b', title)
    return m.group(0) if m else ""

def main() -> None:
    all_content = []

    for filename in CONTENT_FILES:
        filepath = f"./output/{filename}"
        if not os.path.exists(filepath):
            print(f"Warning: {filename} not found, skipping...")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        content_type = FILENAME_TO_CATEGORY.get(filename, filename.replace(".json", ""))

        for item_id, item in data.items():
            entry = {
                "id": item_id,
                "title": item.get("Title", ""),
                "image": item.get("Image Source", ""),
                "category": content_type,
                "genres": item.get("Genres", []),
                "year": extract_year_from_item(item),
                "last_scraped": item.get("last_scraped")   # may be None
            }
            all_content.append(entry)

    # Write as a plain array — no wrapper object needed
    with open("./output/all-content.json", "w", encoding="utf-8") as fp:
        json.dump(all_content, fp, indent=4, ensure_ascii=False)

    print(f"✅ all-content.json generated with {len(all_content)} items.")

if __name__ == "__main__":
    main()
