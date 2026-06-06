import json
import os
from os import remove, listdir
import requests
from os import environ
from hashlib import md5

# List of all JSON files produced by the unified scrapers + trending
OUTPUT_FILES = [
    "movies.json", "dubbed-movies.json", "hindi.json", "asian-movies.json", "anime-movies.json",
    "anime.json", "series.json", "tvshows.json", "asian-series.json",
    "trending-content.json", "featured-content.json"
]

ALL_FILES = OUTPUT_FILES + ["all-content.json", "last-scraped.txt", "image-indices.json", "file-hashes.json"]

def main() -> None:
    file_hashes = {}

    # Clean up temporary image files (scraped images stored as .jpg/.webp)
    for file in listdir("./output"):
        if file.endswith(".jpg") or file.endswith(".webp"):
            try:
                remove(f"./output/{file}")
            except:
                continue

    # Load existing image indices
    try:
        with open('./output/image-indices.json', 'r') as fp:
            image_indices = json.load(fp)
    except FileNotFoundError:
        image_indices = {}

    # Process each content JSON
    for filename in OUTPUT_FILES:
        filepath = f'./output/{filename}'
        if not os.path.exists(filepath):
            print(f"Warning: {filename} not found, skipping...")
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as fp:
                content = json.load(fp)
        except json.JSONDecodeError:
            print(f"Warning: {filename} is not valid JSON, skipping...")
            continue

        # Determine category from filename (for image indices)
        category = filename.replace(".json", "")

        for key, item in content.items():
            # Store image source mapping (for legacy or frontend)
            if "Image Source" in item:
                image_indices[f"{key}-{category}"] = item["Image Source"]

            # Clean genres: remove entries containing '%' or '/'
            if "Genres" in item and isinstance(item["Genres"], list):
                clean_genres = [g for g in item["Genres"] if "%" not in g and g != "/"]
                if clean_genres != item["Genres"]:
                    item["Genres"] = clean_genres
            else:
                item["Genres"] = []

            # (Optional) TMDb ID fetching – disabled by default to save API calls
            # if "TMDb ID" not in item or item["TMDb ID"] is None:
            #     params = {"query": item["Title"], "api_key": environ.get("TMDB_API_KEY")}
            #     request_url = "https://api.themoviedb.org/3/search/movie" if "movie" in category else "https://api.themoviedb.org/3/search/tv"
            #     try:
            #         resp = requests.get(request_url, params=params, timeout=10)
            #         resp.raise_for_status()
            #         tmdb_id = resp.json()["results"][0]["id"] if resp.json()["results"] else None
            #         item["TMDb ID"] = tmdb_id
            #     except:
            #         item["TMDb ID"] = None

        # Special handling for series: remove entries with no seasons (if they exist)
        if category in ["series", "tvshows", "asian-series", "anime"]:
            for key in list(content.keys()):
                if "Number Of Episodes" in content[key] and content[key]["Number Of Episodes"] == 0:
                    # This is likely a movie misclassified, but we keep it? We'll delete.
                    del content[key]
                elif "SeasonsUrl" not in content[key]:
                    # No episode data, maybe not a series
                    del content[key]

        # For movies: no deletion (keep even if Source is empty; video extraction is on-demand)
        # (The old deletion block is removed.)

        # Write back cleaned content
        with open(filepath, 'w', encoding='utf-8') as fp:
            json.dump(content, fp, indent=4, ensure_ascii=False)

    # Save updated image indices
    with open('./output/image-indices.json', 'w', encoding='utf-8') as fp:
        json.dump(image_indices, fp, indent=4, ensure_ascii=False)

    # Calculate file hashes for change detection
    for file in ALL_FILES:
        filepath = f"./output/{file}"
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                name = file.split(".")[0]
                if file.endswith(".json"):
                    content = json.load(fp)
                    file_hashes[name] = md5(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()
                else:
                    file_hashes[name] = md5(fp.read().encode("utf-8")).hexdigest()
        except (json.JSONDecodeError, IOError):
            continue

    with open("./output/file-hashes.json", "w") as fp:
        json.dump(file_hashes, fp, indent=4)


if __name__ == '__main__':
    main()