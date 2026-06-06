# 📘 NoFasel Scraper – Complete Unified Guide

This document explains **everything** about the project: architecture, scripts, data flow, outputs, automation, API, and deployment.  
Save as `GUIDE.txt` or `README_FULL.txt`.

---

## 1. Project Overview

A production‑ready Python system that:

- Scrapes **ALL movies, anime, series, TV shows, and Asian series** from FaselHD.
- Extracts **metadata** (title, image, genres, description, country, runtime, release date, language, status, viewing level, episode duration, episode count).
- Fetches **IMDb‑style ratings** (rating + vote count) from **TMDb** (primary), with fallback to **IMDBAPI.dev** and **OMDb** (rarely used).
- Stores **episodes** separately (in `./output/episodes/`), one JSON per series.
- Serves everything via a **Flask API** with **global view counters** (persistent storage).
- Designed for **daily automation** (resumable, incremental, respects rate limits).

---

## 2. Repository Structure

```
project/
├── Common.py                     # Shared functions: fetching, parsing, APIs
├── FaselMoviesScraper.py         # Scrapes all movie categories
├── FaselAnimeScraper.py          # Scrapes anime series (with episodes)
├── FaselSeriesScraper.py         # Scrapes series, tvshows, asian-series
├── FaselTvShowsScraper.py        # (Optional) dedicated TV shows scraper
├── update_ratings.py             # Fetches ratings (TMDb → IMDBAPI.dev → OMDb)
├── update_episodes.py            # Checks all series for new episodes, updates status
├── clean_metadata.py             # Normalises genres, country, runtime, release date
├── AllContentIndexer.py          # Builds lightweight search index (all-content.json)
├── TrendingScraper.py            # (Optional) extracts homepage trending/featured
├── ScrapeAll.py                  # Orchestrator: runs scrapers → ratings → episodes
├── app.py                        # Flask API (metadata, episodes, ratings, view counter)
├── backfill_metadata.py          # (One‑time) fills missing fields using TMDb
├── requirements.txt              # Python dependencies
├── .gitignore                    # Ignores output/, baks/, etc.
└── output/                       # All generated data (created at runtime)
    ├── *.json                    # Main metadata files
    ├── episodes/                 # Episode files (per series)
    ├── ratings/                  # Rating files (per content ID)
    ├── all-content.json          # Search index
    ├── trending-content.json     # Homepage trending (if generated)
    ├── featured-content.json     # Homepage featured slider
    ├── imdb_id_map.json          # Mapping Fasel ID → IMDb ID (from OMDb)
    ├── tmdb_cache.json           # Cache for TMDb responses
    ├── omdb_cache.json           # Cache for OMDb responses
    ├── last_scraped.txt          # Date of last full pipeline run
    ├── last_page_*.txt           # Progress files (one per category)
    └── rating_update_progress.txt # Resume file for update_ratings.py
```

---

## 3. What Each Scraper Scrapes

| Script | Categories | Output JSON | Episodes? | Fields (key examples) |
|--------|-----------|-------------|-----------|----------------------|
| `FaselMoviesScraper.py` | `movies`, `dubbed-movies`, `hindi`, `asian-movies`, `anime-movies` | `movies.json`, `dubbed-movies.json`, `hindi.json`, `asian-movies.json`, `anime-movies.json` | No | Title, Category, Image Source, Source, Genres, GenresAr, Format, Runtime, Country, Description, ReleaseDate, Language, last_scraped |
| `FaselAnimeScraper.py` | `anime` (series only) | `anime.json` | Yes → `episodes/anime/{id}.json` | Same as movies + Type, Number Of Episodes, Status, ViewingLevel, EpisodeDuration, SeasonsUrl |
| `FaselSeriesScraper.py` | `series`, `tvshows`, `asian-series` | `series.json`, `tvshows.json`, `asian-series.json` | Yes → `episodes/{category}/{id}.json` | Same as anime (status, viewing level, seasons, etc.) |
| `FaselTvShowsScraper.py` | `tvshows` (dedicated, if needed) | `tvshows.json` | Yes | Same as series |

> Note: `FaselSeriesScraper.py` already includes `tvshows`. The dedicated script is optional.

---

## 4. Rating System (`update_ratings.py`)

- **Primary**: TMDb API (free, ~40 req/sec, no daily limit).  
- **Fallback 1**: IMDBAPI.dev (no API key, but rate‑limited – we add delay 0.5s).  
- **Fallback 2**: OMDb API (1000 requests/day, rarely used).  

**Output** per content ID: `./output/ratings/{category}/{id}.json`  
Example:
```json
{
  "content_id": "148151",
  "title": "The Batman",
  "year": "2022",
  "rating": "7.8",
  "votes": 123456,
  "source": "tmdb",
  "last_updated": "2026-05-04T10:00:00Z"
}
```

**Features**:
- Resumable (progress stored in `rating_update_progress.txt`).
- Caches results (`tmdb_cache.json`).
- Skips items with existing non‑null rating.
- Exits gracefully when daily limit reached (OMDb).
- Respects polite delays.

---

## 5. Episodes & Status (`update_episodes.py`)

- Reads all series/anime JSONs.
- For each series, fetches the season hub and all season pages.
- Compares stored episode URLs with current ones.
- **Appends** new episodes to the episode JSON file.
- Updates `Status` field in the main JSON:
  - If new episodes found → set to `"مستمر"` (ongoing).
  - After episode check, if Fasel’s detail page says `"مكتمل"` (completed) and no new episodes were added → update status.
- Adds a `last_updated` timestamp at the root of each episode JSON.

**Output** example (`episodes/series/12345.json`):
```json
{
  "content_id": "12345",
  "category": "series",
  "seasons": {
    "1": {
      "poster": "https://...",
      "episodes": ["https://.../episode-1", "https://.../episode-2"]
    }
  },
  "last_updated": "2026-05-04T10:00:00Z"
}
```

---

## 6. Metadata Cleaning (`clean_metadata.py`)

- Converts hyphenated genres (`Science-Fiction` → `Science Fiction`).
- Normalises country names (`United States` → `USA`, `United Kingdom` → `UK`).
- Converts runtime strings to integers.
- Normalises release date: `20242025` → `2024-2025`; removes unrealistic single years (e.g., `2077` → `""`).
- Cleans viewing level: if multiple values (`"+13, TV-14"`), takes first (`"+13"`).
- Backs up original files to `./baks/` before modification.

Run manually after scraping (or include in pipeline).

---

## 7. Search Index (`AllContentIndexer.py`)

- Reads all main JSON files.
- Extracts `id`, `title`, `image`, `category`, `genres`, `year`, `last_scraped`.
- Outputs `./output/all-content.json`:
```json
{
  "content": [
    {
      "id": "298006",
      "title": "فيلم Apex 2026 مترجم",
      "image": "https://...",
      "category": "movie",
      "genres": ["Thriller", "Action"],
      "year": "2026",
      "last_scraped": "2026-05-04T10:00:00Z"
    }
  ],
  "total": 12500
}
```
- Used for client‑side search and browse pages.

---

## 8. Orchestrator (`ScrapeAll.py`)

Executes the daily pipeline in correct order:

1. `FaselMoviesScraper.py`
2. `FaselAnimeScraper.py`
3. `FaselSeriesScraper.py`
4. `update_ratings.py`
5. `update_episodes.py`
6. (Optional) `clean_metadata.py`
7. (Optional) `AllContentIndexer.py`

One‑time backfill scripts are commented out. Run daily via cron or Task Scheduler.

---

## 9. API (`app.py`)

Flask server that serves:

| Endpoint | Description |
|----------|-------------|
| `/api/movies`, `/api/dubbed-movies`, `/api/hindi`, `/api/asian-movies`, `/api/anime-movies` | Metadata for each movie category (optional ID param). |
| `/api/anime`, `/api/series`, `/api/tvshows`, `/api/asian-series` | Metadata for series. |
| `/api/episodes/{category}/{id}` | Episode list for a series. |
| `/api/anime-episodes/{id}` | Anime episodes. |
| `/api/ratings/{category}/{id}` | Rating + vote count. |
| `/api/all-content` | Search index (all-content.json). |
| `/api/search?q=...` | Server‑side search (filters in memory). |
| `/api/trending`, `/api/featured` | Homepage content (if generated). |
| `POST /api/view/{category}/{id}` | Increment global view counter (body: `{"increment_by": N}`). |
| `GET /api/view/{category}/{id}` | Get current view count. |
| `POST /extract` | Extract `.m3u8` video stream from a FaselHD page URL. |
| `/health` | Health check. |

**View counter** uses persistent storage at `/data/view_counts.json` (on Hugging Face Spaces) with file locking (`portalocker`).

**Data directory**: default `./data`, but can be overridden with `DATA_DIR` environment variable. On HF Spaces, mount persistent storage to `/data`.

---

## 10. Automation & Deployment

### Local Automation (Windows)

- Use **Task Scheduler** to run `ScrapeAll.py` daily at 3 AM.
- Or use a batch file:  
  ```batch
  cd C:\path\to\project
  python ScrapeAll.py
  cd ..
  ```

### Hugging Face Spaces

1. Create a new Space with **Docker** or **Python**.
2. Upload all scripts, `requirements.txt`, and `Dockerfile` (if needed).
3. Enable **Persistent Storage** (mounts `/data`).
4. Set environment variables (e.g., `TMDB_API_KEY`, `DATA_DIR=/data`).
5. Add a `Dockerfile`:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   RUN playwright install chromium && playwright install-deps
   COPY . .
   ENV PORT=7860
   CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "8"]
   ```
6. The Space will run the API. Run the scrapers via cron‑job.org calling a protected endpoint (e.g., a simple script that executes `ScrapeAll.py`). Alternatively, run scrapers locally and sync data to Space using `hf upload` or manual file upload.

### Cron‑job.org (for scheduling scrapers)

- Set up a public endpoint that triggers `ScrapeAll.py` (e.g., a tiny Flask app with secret token).
- Create a cron job that calls that endpoint daily.

---

## 11. Important Notes & Best Practices

- **First run**: Delete all `last_page_*.txt` files to start full scrape from page 1. It may take many hours.
- **Daily runs**: After first full scrape, the scrapers enter **daily mode** and only scan the first `DAILY_SCAN_PAGES` (default 5) pages – very fast.
- **Rate limits**: TMDb = ~40 req/sec, IMDBAPI.dev = aggressive (we use 0.5s delay), OMDb = 1000/day. The hybrid rating script respects all.
- **Viewing level**: Fixed in `Common.py` to look for “مستوى المشاهدة” text – no more genres mixed in.
- **Year validation**: Years outside 1900 – current year + 4 are rejected. Spurious years like 2077 become `None`.
- **Episodes**: The `update_episodes.py` script **ignores** the `Status` field when checking for new episodes – prevents the “completed with new episodes” loophole.
- **Backups**: `clean_metadata.py` creates `.bak` files in `./baks/` – you can delete them after verifying changes.
- **Logs**: `scraper_errors.log` records warnings; `failed_scripts.log` from `ScrapeAll.py` records script failures.

---

## 12. Troubleshooting

| Symptom | Likely cause | Solution |
|---------|--------------|----------|
| Scraper stops early (page 61) | Incremental stop on empty page | Fixed in latest files – no early stop any more. |
| Many `None` ratings | Title not found in TMDb / IMDBAPI.dev | Check cleaned title, or wait for future releases. |
| `429` errors from IMDBAPI.dev | Rate limit | Script already adds delay; falls back to OMDb. |
| API returns 404 for ratings | Rating file missing | Run `update_ratings.py` again; it will create missing ones. |
| View counter file not writable | Persistent storage not mounted | Enable persistent storage on HF Spaces. |
| `extract_video_source` fails | Playwright not installed or Chrome missing | Run `playwright install chromium` after `pip install`. |

---

## 13. Example Workflow for a New User

```bash
# 1. Clone repository
git clone https://github.com/yourusername/no-fasel-scrapers.git
cd no-fasel-scrapers

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Set API keys (in Common.py or as env vars)
#    - TMDB_API_KEY = "your_key"
#    - OMDB_API_KEY = "b7fc5b44" (optional fallback)
#    - IMDBAPI.dev works without key.

# 4. Run the full pipeline (first run – may take hours)
python ScrapeAll.py

# 5. After first run, set up daily automation (Task Scheduler or HF Space).
```

---

## 14. File Output Summary

| File | Content | Generated by |
|------|---------|---------------|
| `movies.json` | All movies (main category) | `FaselMoviesScraper.py` |
| `dubbed-movies.json` | Dubbed movies | same |
| `hindi.json` | Hindi movies | same |
| `asian-movies.json` | Asian movies | same |
| `anime-movies.json` | Anime movies | same |
| `anime.json` | Anime series | `FaselAnimeScraper.py` |
| `series.json` | Series | `FaselSeriesScraper.py` |
| `tvshows.json` | TV shows | same or dedicated script |
| `asian-series.json` | Asian series | same |
| `episodes/{category}/*.json` | Episode lists per series | `update_episodes.py` |
| `ratings/{category}/*.json` | Rating + votes per content | `update_ratings.py` |
| `all-content.json` | Search index | `AllContentIndexer.py` |
| `trending-content.json` | Homepage trending | `TrendingScraper.py` |
| `featured-content.json` | Homepage featured | same |
| `view_counts.json` | Global view counts | `app.py` (runtime) |
| `imdb_id_map.json` | Fasel ID → IMDb ID | `update_ratings.py` (from OMDb) |
| `tmdb_cache.json` | Cached TMDb responses | `update_ratings.py` |
| `last_page_*.txt` | Progress markers | scrapers |
| `rating_update_progress.txt` | Resume for ratings | `update_ratings.py` |
| `episode_update_progress.txt` | Resume for episodes | `update_episodes.py` |
| `last-scraped.txt` | Date of last success | `ScrapeAll.py` |

---

## 15. Final Words

This system is modular, resumable, incremental, and ready for daily automation.  
It respects website and API limits, separates ratings from metadata, and provides a full API for frontend consumption.  

For questions or improvements, refer to the scripts’ docstrings and the `#` comments inside.  

**End of Guide**