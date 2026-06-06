import json
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    get_website_safe, FASEL_BASE_URL,
    get_latest_movies, get_latest_episodes,
    get_featured_content, get_most_viewed_movies
)

RATINGS_DIR = Path("./output/ratings")

def enrich_with_ratings(items, category="movies"):
    """Replace imdb_rating with fresh rating+votes from separate rating files."""
    for item in items:
        # Extract content ID from link (e.g., "/movies/12345" or "/anime/67890")
        link = item.get("link", "")
        if "/" in link:
            parts = link.rstrip("/").split("/")
            content_id = parts[-1] if parts[-1].isdigit() else None
        else:
            content_id = None

        if content_id:
            rating_file = RATINGS_DIR / category / f"{content_id}.json"
            if rating_file.exists():
                try:
                    with open(rating_file, "r", encoding="utf-8") as f:
                        rating_data = json.load(f)
                    # Overwrite with fresh data
                    item["imdb_rating"] = rating_data.get("rating")
                    item["votes"] = rating_data.get("votes")
                except:
                    pass  # keep old rating if file corrupt
            # else keep the scraped rating (already present)
        # Ensure content_type is set (for frontend)
        if "content_type" not in item:
            item["content_type"] = category
    return items

def scrape_trending():
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        print("Failed to fetch homepage")
        return
    soup = BeautifulSoup(resp.text, "html.parser")

    trending_movies = get_latest_movies(soup)       # from homepage grid
    trending_episodes = get_latest_episodes(soup)   # latest episodes
    featured = get_featured_content(soup)           # main slider
    most_viewed = get_most_viewed_movies(soup)      # most viewed slider

    # Enrich with fresh ratings & votes (using separate rating files)
    trending_movies = enrich_with_ratings(trending_movies, "movies")
    most_viewed = enrich_with_ratings(most_viewed, "movies")
    # For featured, items can be movies/anime/series – try all three categories
    for item in featured:
        # Determine category from link
        link = item.get("link", "")
        if "/anime" in link:
            cat = "anime"
        elif "/series" in link or "/episodes" in link:
            cat = "series"
        else:
            cat = "movies"
        # Enrich single item
        enriched = enrich_with_ratings([item], cat)
        item.update(enriched[0])  # update in place

    # Add timestamp
    now = datetime.now(timezone.utc).isoformat()

    with open("./output/trending-content.json", "w", encoding="utf-8") as fp:
        json.dump({
            "movies": trending_movies,
            "episodes": trending_episodes,
            "most_viewed": most_viewed,
            "generated_at": now
        }, fp, indent=4, ensure_ascii=False)

    with open("./output/featured-content.json", "w", encoding="utf-8") as fp:
        json.dump({
            "content": featured,
            "generated_at": now
        }, fp, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    scrape_trending()