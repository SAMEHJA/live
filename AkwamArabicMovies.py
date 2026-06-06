#!/usr/bin/env python3
"""
AkwamArabicMovies.py – Arabic movies scraper for akwam.it
- Listing page  : /movies?section=29&...&page=N
  Cards live in .entry-box.entry-box-1 — ID from data-id on the fav button
  or extracted from the movie URL slug /movie/{id}/...
- Detail page   : /movie/{id}/{slug}
  Full metadata extracted with selectors confirmed from real HTML.
- Watch link    : go.akwam.it/watch/{link_id}
- Download link : go.akwam.it/link/{link_id}
- Output        : ./output/arabic-movies.json
- Progress      : ./output/akwam_movies_progress.txt  (one movie-id per line)
"""

import json, os, re, time, random, threading, sys
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from Common import DEBUG, get_website_safe, AKWAM_BASE_URL, normalize_akwam_url

# ======== CONFIGURATION ========
REQUEST_DELAY = 2.0
JITTER        = 0.3
MAX_WORKERS   = 4
PROGRESS_FILE = "./output/akwam_movies_progress.txt"
OUTPUT_FILE   = "./output/arabic-movies.json"
SECTION_ID    = "29"   # 29=عربي  30=اجنبي  31=هندي  32=تركي  33=اسيوي
LISTING_URL   = (
    f"{AKWAM_BASE_URL}/movies"
    f"?section={SECTION_ID}&category=0&rating=0&year=0"
    f"&language=0&formats=0&quality=0"
)
# =================================

progress_lock = threading.Lock()
movies_lock   = threading.Lock()


# ── I/O helpers ───────────────────────────────────────────────────────────

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return {l.strip() for l in f if l.strip()}
    return set()

def save_progress(movie_id):
    with progress_lock:
        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
            f.write(movie_id + "\n")

def load_existing():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_all(all_movies):
    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_movies, f, indent=2, ensure_ascii=False)


# ── Listing page parser ────────────────────────────────────────────────────
# Confirmed card structure from real HTML (section=29 listing):
#
#   <div class="entry-box entry-box-1">
#     <div class="labels d-flex">
#       <span class="label rating">7.0</span>
#       <span class="label quality">WEB-DL</span>
#     </div>
#     <div class="entry-image">
#       <a href="/movie/11066/سوار" class="box">
#         <img data-src="https://img.downet.net/thumb/178x260/uploads/L6xpF.jpg" …/>
#     </div>
#     <div class="entry-body …">
#       <a class="add-to-fav" data-type="movie" data-id="11066">…</a>
#       <h3 class="entry-title …"><a href="…">سوار</a></h3>
#       <span class="badge badge-pill badge-secondary">2025</span>
#       <span class="badge badge-pill badge-light">دراما</span>
#     </div>
#   </div>

def parse_listing_page(soup):
    movies = []
    for card in soup.select(".entry-box.entry-box-1"):
        # ID from data-id attribute on the fav button
        fav_btn  = card.select_one("[data-id]")
        movie_id = fav_btn["data-id"].strip() if fav_btn else None

        # Detail URL + fallback ID extraction
        link_tag   = card.select_one("a.box")
        detail_url = ""
        if link_tag and link_tag.get("href"):
            href = link_tag["href"]
            detail_url = href if href.startswith("http") else AKWAM_BASE_URL + href
            if not movie_id:
                m = re.search(r"/movie/(\d+)/", detail_url)
                if m:
                    movie_id = m.group(1)

        if not movie_id:
            continue

        title_tag = card.select_one(".entry-title a") or card.select_one(".entry-title")
        title     = title_tag.get_text(strip=True) if title_tag else ""

        img    = card.select_one("img[data-src]")
        image  = img["data-src"] if img else (img.get("src", "") if img else "")

        rating_tag  = card.select_one(".label.rating")
        quality_tag = card.select_one(".label.quality")
        rating  = rating_tag.get_text(strip=True)  if rating_tag  else ""
        quality = quality_tag.get_text(strip=True) if quality_tag else ""

        badges = card.select(".badge")
        year   = badges[0].get_text(strip=True) if len(badges) > 0 else ""
        genre  = badges[1].get_text(strip=True) if len(badges) > 1 else ""

        movies.append({
            "id": movie_id, "title": title, "url": detail_url,
            "image": image, "rating": rating, "quality": quality,
            "year": year, "genre": genre,
        })
    return movies


def get_next_page_url(soup, base_url):
    a = soup.select_one('a.page-link[rel="next"]')
    if a and a.get("href"):
        return urljoin(base_url, a["href"])
    for a in soup.select("a.page-link"):
        if "التالي" in a.get_text():
            return urljoin(base_url, a["href"])
    return None


# ── Detail page parser ────────────────────────────────────────────────────
# Confirmed selectors from real HTML (/movie/10913/بث-مباشر):
#
#   Title      : h1.entry-title
#   Poster     : .movie-cover .col-lg-3 img (or .col-md-4 img)
#   Rating     : span.mx-2  → "10 / 7.0"  (take after "/")
#   PG badge   : span.badge-info           → "PG13 اشراف عائلي"
#   Info rows  : div.font-size-16 > span   → "اللغة : العربية" etc.
#   Genres     : a.badge.badge-light
#   Description: .widget-body .text-white.font-size-18  (story section)
#   Links      : [data-server][data-quality] divs inside #downloads
#                  a.link-show     → watch URL
#                  a.link-download → download URL
#                  span.font-size-14.mr-auto → file size

def _info_span(soup, keyword):
    """Extract the value after the colon from a labelled info span."""
    for span in soup.select("div.font-size-16 span"):
        text = span.get_text(strip=True)
        if keyword in text:
            parts = text.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else text
    return ""


def parse_detail_page(soup, movie_id, listing_data):
    # Title
    title_tag = soup.select_one("h1.entry-title")
    title = title_tag.get_text(strip=True) if title_tag else listing_data.get("title", "")

    # Poster (full-res image in the detail header)
    cover_img = soup.select_one(".movie-cover .col-lg-3 img, .movie-cover .col-md-4 img")
    poster = (cover_img.get("src") or cover_img.get("data-src", "")) if cover_img else ""
    if not poster:
        poster = listing_data.get("image", "")

    # Rating  "10 / 7.0"  → "7.0"
    rating_span = soup.select_one(".font-size-16 .mx-2")
    rating = ""
    if rating_span:
        raw    = rating_span.get_text(strip=True)
        parts  = raw.split("/")
        rating = parts[-1].strip()

    # PG / viewing level badge
    pg_badge      = soup.select_one("span.badge-info")
    viewing_level = pg_badge.get_text(strip=True) if pg_badge else ""

    # Labelled info rows
    language = _info_span(soup, "اللغة")
    quality  = _info_span(soup, "جودة")
    country  = _info_span(soup, "انتاج")
    year     = _info_span(soup, "السنة")
    runtime  = _info_span(soup, "مدة")
    added_on = _info_span(soup, "تـ الإضافة")

    # Genres
    genres = [a.get_text(strip=True) for a in soup.select("a.badge.badge-light")]

    # Description (story section)
    desc_tag    = soup.select_one(".widget-body .text-white.font-size-18")
    description = ""
    if desc_tag:
        first_p = desc_tag.find("p")
        if first_p:
            description = first_p.get_text(strip=True)
        else:
            description = desc_tag.get_text(separator=" ", strip=True)

    # Watch & download links (one entry per quality server block)
    links = []
    for server_div in soup.select("[data-server][data-quality]"):
        watch_a    = server_div.select_one("a.link-show")
        download_a = server_div.select_one("a.link-download")
        size_span  = server_div.select_one("a.link-download .font-size-14")

        watch_url    = watch_a["href"]    if watch_a    and watch_a.get("href")    else ""
        download_url = download_a["href"] if download_a and download_a.get("href") else ""
        file_size    = size_span.get_text(strip=True) if size_span else ""

        # Quality label from the tab heading that corresponds to this block
        tab_content = server_div.find_parent(class_="tab-content")
        tab_label   = ""
        if tab_content and tab_content.get("id"):
            tab_a = soup.select_one(f'a[href="#{tab_content["id"]}"]')
            tab_label = tab_a.get_text(strip=True) if tab_a else ""

        if watch_url or download_url:
            links.append({
                "server":        server_div.get("data-server", ""),
                "quality_id":    server_div.get("data-quality", ""),
                "quality_label": tab_label,
                "watch_url":     watch_url,
                "download_url":  download_url,
                "size":          file_size,
            })

    return {
        "id":            movie_id,
        "title":         title,
        "poster":        poster,
        "rating":        rating,
        "viewing_level": viewing_level,
        "language":      language,
        "quality":       quality,
        "country":       country,
        "year":          year,
        "runtime":       runtime,
        "added_on":      added_on,
        "genres":        genres,
        "description":   description,
        "links":         links,
        "url":           listing_data.get("url", ""),
        "category":      "arabic-movies",
        "section":       SECTION_ID,
    }


# ── Per-movie worker ──────────────────────────────────────────────────────

def process_movie(listing_data, all_movies):
    movie_id = listing_data["id"]
    title    = listing_data.get("title", movie_id)
    url      = listing_data.get("url", "")

    resp = get_website_safe(url)
    if not resp or resp.status_code != 200:
        print(f"    ❌ Failed: {title}")
        return False

    soup     = BeautifulSoup(resp.text, "html.parser")
    metadata = parse_detail_page(soup, movie_id, listing_data)

    with movies_lock:
        all_movies[movie_id] = metadata
        save_all(all_movies)

    save_progress(movie_id)
    print(f"    ✅ {title} ({movie_id}) – {len(all_movies)} total")
    return True


# ── Main loop ─────────────────────────────────────────────────────────────

def scrape_arabic_movies():
    print("🚀 Starting Akwam Arabic Movies Scraper")
    print(f"   Listing : {LISTING_URL}")
    print(f"   Output  : {OUTPUT_FILE}\n")

    processed_ids = load_progress()
    all_movies    = load_existing()
    current_url   = LISTING_URL
    page_num      = 1

    while True:
        print(f"📄 Page {page_num}: {current_url}")
        resp = get_website_safe(current_url)
        if not resp or resp.status_code != 200:
            print("  ❌ Failed to fetch listing page, stopping.")
            break

        soup        = BeautifulSoup(resp.text, "html.parser")
        page_movies = parse_listing_page(soup)

        if not page_movies:
            print("  No movie cards found – stopping.")
            break

        new_movies = [m for m in page_movies if m["id"] not in processed_ids]
        print(f"  {len(page_movies)} cards on page, {len(new_movies)} new.")

        if new_movies:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futures = {ex.submit(process_movie, m, all_movies): m for m in new_movies}
                for fut in as_completed(futures):
                    m = futures[fut]
                    try:
                        fut.result()
                    except Exception as exc:
                        print(f"  ❌ Error on '{m['title']}': {exc}")
                        save_progress(m["id"])  # skip on next run

        next_url = get_next_page_url(soup, AKWAM_BASE_URL)
        if not next_url:
            print("  No next page – done.")
            break

        current_url = next_url
        page_num   += 1
        time.sleep(REQUEST_DELAY + random.uniform(-JITTER, JITTER))

    print(f"\n🏁 Done. Total Arabic movies: {len(all_movies)}")
    print(f"   Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    scrape_arabic_movies()
