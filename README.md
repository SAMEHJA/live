# 🎬 NoFasel Scraper

A complete, production‑ready Python library that scrapes movie and series metadata from [FaselHD](https://www.fasel-hd.cam/) and extracts the actual video stream (`.m3u8`) for download or streaming.

## ✨ Features

- ✅ Bypasses Cloudflare using **Scrapling** (stealth browser) + **curl_cffi** fallback – no Playwright in metadata fetching.
- 🎞️ Scrapes **movies, anime, series, TV shows, Asian series**.
- 📝 Extracts **titles, images, quality, runtime, country, dual‑language genres** (English & Arabic decoded).
- 💾 Saves data as **JSON files** (`movies.json`, `anime.json`, `series.json`, `tvshows.json`, `asian-series.json`, `trending-content.json`, `featured-content.json`, `all-content.json`).
- ⏸️ **Resumable full scrape** (for the initial run) – stop and continue later using `last_page_*.txt`.
- ⚡ **Incremental daily update** scripts that start from page 1 and stop when all IDs are known – fast.
- 🎥 **On‑demand video source extraction** (`.m3u8`) using Playwright – no pre‑scraping of video URLs.
- 🧹 **Post‑processing** that does **not** delete movies with empty `"Source"`.
- 🛠️ **Separate manual cleaning script** (`clean_metadata.py`) for normalising country names and genre hyphens.
- 🔄 **Sequential orchestrator** (`ScrapeAll_incremental.py`) for daily updates.

## 📋 Requirements

- 🐍 Python 3.12+
- 🌐 Google Chrome (for Playwright video extraction)

## 🚀 Installation

```bash
git clone https://github.com/yourusername/no-fasel-scrapers.git
cd no-fasel-scrapers
pip install -r requirements.txt
playwright install chromium
```

## 🧪 Usage

### 🔁 Full scrape (one‑time seed)

Run the full pipeline to build the initial JSON files:

```bash
python ScrapeAll.py
```

Or run individual scrapers:

```bash
python FaselMoviesScraper.py      # resumable
python FaselAnimeScraper.py
python FaselSeriesScraper.py
```

### 📆 Daily incremental updates

After the full scrape, run the incremental script (takes minutes):

```bash
python ScrapeAll_incremental.py
```

This script starts from page 1 and stops when all IDs are already known – no duplicate work.

### 🧽 Post‑processing

After scraping, run the following to generate trending content, clean metadata, and build a unified index:

```bash
python TrendingScraper.py
python Postprocessing.py
python AllContentIndexer.py
```

### 🎯 On‑demand video source extraction

To get the direct `.m3u8` stream URL for a given movie page (without downloading), use:

```python
from fasel_downloader_final import capture_m3u8
stream_url = capture_m3u8("https://www.fasel-hd.cam/movies/...")
```

For downloading with quality selection:

```bash
python fasel_downloader_final.py "https://www.fasel-hd.cam/movies/..." --quality 1080p
```

Quality options: `best`, `1080p`, `720p`, `480p`, `360p`. Add `--headless` for silent operation.

## 📁 File Structure

| File | Purpose |
|------|---------|
| **🎛️ GUI Launcher** |
| `scraper_gui_pro.pyw` | Graphical control panel – launches all scrapers, update scripts, ratings, MAL, clean‑up, and manual ID setters. |
| **🌐 Core Scraping** |
| `Common.py` | Core fetching + extraction (thread‑safe) |
| `FaselMoviesScraper.py` | Full resumable movie scraper (one‑time seed) |
| `FaselAnimeScraper.py` | Full resumable anime scraper |
| `FaselSeriesScraper.py` | Full resumable series scraper |
| `AkwamArabicSeries.py` | Scrapes Arabic series from Akwam |
| **🔄 Incremental Updates** |
| `FaselMoviesIncremental.py` | Daily movie updates – stops when all IDs known |
| `FaselAnimeIncremental.py` | Daily anime updates |
| `FaselSeriesIncremental.py` | Daily series updates |
| `ScrapeAll_incremental.py` | Runs all incremental scrapers sequentially |
| **📺 Episode Management** |
| `update_episodes.py` | Updates episodes for all series (respects 50/day limit) |
| `update_specific_episodes.py` | Fetches episodes for user‑specified series IDs |
| `check_new_episodes.py` | Scans latest episode feeds and triggers updates |
| **⭐ Ratings & Metadata Enrichment** |
| `update_ratings.py` | Fetches ratings from IMDbAPI, TMDb, OMDb with fallback order |
| `update_runtime.py` | Fetches runtime from multiple sources |
| `update_mal.py` | Enriches anime with MyAnimeList data (episodes, score, rank, season) |
| `match_series_imdb.py` | Matches series to IMDb IDs using title + episode structure |
| `set_imdb_id.py` | Manually set IMDb ID for any content item |
| `set_mal_id.py` | Manually set MyAnimeList ID for anime items |
| **🧹 Post‑Processing** |
| `TrendingScraper.py` | Extracts homepage trending content |
| `Postprocessing.py` | Cleans, adds TMDb IDs, generates hashes |
| `AllContentIndexer.py` | Creates unified `all-content.json` |
| `clean_metadata.py` | Normalises countries, genres, years, Arabic translations |
| `sort_output.py` | Sorts JSON files by release date (newest first) |
| **📦 Dependencies** |
| `requirements.txt` | All dependencies (Scrapling, curl_cffi, Playwright, etc.) |

## 🗺️ Next Steps for Your Project

1. 🏃 **Run the full scrape once** (using the resumable scripts) – let it run overnight or over a weekend. You can stop and resume anytime.
2. 🔄 **After the full scrape, switch to `ScrapeAll_incremental.py`** for daily updates (takes minutes).
3. ⏰ **Set up a cron job** (or Windows Task Scheduler) to run the incremental script daily.
4. ⚛️ **Build your React frontend** to consume the JSON files (or an API on top of them).
5. ▶️ **For video playback**, call `extract_video_source(page_url)` from your backend when a user clicks “Play”.

## 🔮 Future Enhancements (Parked)

- 🎌 Group anime seasons using external metadata (MyAnimeList) or title‑based heuristics.
- 🌐 Proxy rotation and persistent browser session (optional).
- 🗄️ SQLite storage instead of JSON files.

## 🤝 Contributing

Thanks for taking the time to contribute!

#### Prerequisites

Before you start, please note that the ability to use the following technologies is **required**:

- 🐍 Python
- 🕸️ Web scraping (BeautifulSoup, Scrapling, Playwright)

## ⚖️ DMCA Disclaimer

The developers of this application **do not** have any affiliation with the content available in the app. It is collected from sources freely available through any web browser.

<h4 align='center'>© 2026 OGKushhh</h4>