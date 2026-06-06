import json
import logging
import os
import random
import re
import time
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional, Callable, Union, List, Dict
from urllib.parse import quote, unquote, urlparse, urljoin
from PIL import Image
import requests
from bs4 import BeautifulSoup, ResultSet, Tag
from requests import Response
from requests.exceptions import ConnectionError, TooManyRedirects, ReadTimeout, ChunkedEncodingError

# ----------------------------------------------------------------------
#  Logging configuration
# ----------------------------------------------------------------------
logging.basicConfig(
    filename='scraper_errors.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ----------------------------------------------------------------------
#  Stealth fetching – Scrapling (primary) + curl_cffi (fallback)
#  NO Playwright here – this is thread‑safe.
# ----------------------------------------------------------------------
try:
    from scrapling.fetchers import StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    print("Warning: scrapling not installed. Run: pip install scrapling[all]")

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("Warning: curl_cffi not installed. Run: pip install curl_cffi")

# Playwright ONLY for video extraction – will be imported only inside that function.
# Not imported at top level to avoid greenlet issues.

# ----------------------------------------------------------------------
#  Constants & settings
# ----------------------------------------------------------------------
DEBUG = True                       # Set False for production runs
REQUEST_DELAY = 2.0                # seconds between page requests
JITTER = 0.5                       # random ± seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
IMPERSONATIONS = ["chrome", "chrome110", "chrome124", "edge101", "safari15_5"]

FASEL_BASE_URL = "https://www.fasel-hd.cam/"

# For other sites (leave as is)
CIMA_NOW_SELECTOR = ("class name", "owl-head.owl-loaded.owl-drag")
FILE_NAMES = ["movies", "anime", "asian-series", "series", "tvshows", "arabic-series", "arabic-movies"]
HDW_FILE_NAMES = ["hdwmovies", "series", "arabic-movies", "arabic-series"]
DEFAULT_HDW_SELECTOR = ("class name", "top-brand")

AKWAM_GENRES = {
    "87": "Ramadan", "30": "Animated", "18": "Action", "71": "Dubbed",
    "72": "Netflix", "20": "Comedy", "35": "Thriller", "34": "Mystery",
    "33": "Family", "88": "Kids", "32": "Sports", "25": "War", "89": "Short",
    "43": "Fantasy", "24": "Science Fiction", "31": "Musical", "29": "Biography",
    "28": "Documentary", "27": "Romance", "26": "History", "23": "Drama",
    "22": "Horror", "21": "Crime", "19": "Adventure", "91": "Western"
}

CIMA_NOW_GENRES = {
    "تشويق": "Suspense", "درامي": "Drama", "اكشن": "Action", "رعب": "Horror",
    "كوميدى": "Comedy", "مغامرة": "Adventure", "ترفيهي": "Entertainment",
    "غنائي": "Musical", "مسابقات": "Competitions", "اجتماعي": "Social",
    "جريمة": "Crime", "اثارة": "Thriller", "رومانسى": "Romance",
    "عائلي": "Family", "كوميدي": "Comedy", "درامى": "Drama"
}

# Genre mapping for FaselHD (Arabic -> English)
FASEL_GENRE_MAP = {
    "أكشن": "Action",
    "اكشن": "Action",
    "دراما": "Drama",
    "كوميدي": "Comedy",
    "كوميدى": "Comedy",
    "رعب": "Horror",
    "إثارة": "Thriller",
    "اثارة": "Thriller",
    "مغامرات": "Adventure",
    "مغامرة": "Adventure",
    "خيال علمي": "Science Fiction",
    "جريمة": "Crime",
    "رومانسية": "Romance",
    "رومانسي": "Romance",
    "رومانسى": "Romance",
    "تاريخي": "History",
    "سيرة ذاتية": "Biography",
    "وثائقي": "Documentary",
    "عائلي": "Family",
    "رياضي": "Sports",
    "حرب": "War",
    "غموض": "Mystery",
    "فانتازيا": "Fantasy",
    "موسيقى": "Music",
    "موسيقي": "Music",
    "أنميشن": "Animation",
    "انيميشن": "Animation",
    "غربي": "Western",
    "مسابقات": "Competitions",
    "تلفزيون الواقع": "Reality-TV",
    "ترفيهي": "Entertainment",
    "اجتماعي": "Social",
}

try:
    with open("./output/image-indices.json", "r") as fp:
        IMAGE_SOURCES = json.load(fp)
except FileNotFoundError:
    IMAGE_SOURCES = {}

cookie_lock = Lock()
headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,ar;q=0.8",
}

# ----------------------------------------------------------------------
#  Ad domain helper (for discovery logging)
# ----------------------------------------------------------------------
def extract_domain(url: str) -> str:
    """Extract registered domain from a URL (e.g., sub.example.com -> example.com)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

# ----------------------------------------------------------------------
#  Core fetching function (synchronous, thread‑safe: Scrapling + curl_cffi)
# ----------------------------------------------------------------------
def get_website_safe(webpage_url: str, max_retries: int = MAX_RETRIES) -> Optional[Response]:
    """Fetch a page using Scrapling (stealth) or fallback to curl_cffi."""
    if SCRAPLING_AVAILABLE:
        for attempt in range(max_retries):
            try:
                resp = StealthyFetcher.fetch(
                    webpage_url,
                    headless=True,
                    wait_for_selector=".blockMovie, .postDiv, body",
                    timeout=60000
                )
                if resp and resp.status == 200:
                    html = resp.body.decode('utf-8') if hasattr(resp, 'body') else resp.text
                    if html:
                        fake = requests.Response()
                        fake.status_code = 200
                        fake._content = html.encode('utf-8')
                        return fake
            except Exception as e:
                if DEBUG:
                    print(f"Scrapling error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(BACKOFF_FACTOR ** attempt)
        if DEBUG:
            print("Scrapling failed, falling back to curl_cffi")

    if CURL_CFFI_AVAILABLE:
        for attempt in range(max_retries):
            imp = IMPERSONATIONS[attempt % len(IMPERSONATIONS)]
            try:
                r = curl_requests.get(webpage_url, impersonate=imp, timeout=30)
                if r.status_code == 200:
                    fake = requests.Response()
                    fake.status_code = 200
                    fake._content = r.content
                    return fake
            except Exception as e:
                if DEBUG:
                    print(f"curl_cffi error: {e}")
            if attempt < max_retries - 1:
                time.sleep(BACKOFF_FACTOR ** attempt)

    logging.warning(f"Failed to fetch {webpage_url}")
    return None

# ----------------------------------------------------------------------
#  Pagination helpers
# ----------------------------------------------------------------------
def get_paginated_url(category_url: str, page: int) -> str:
    base = re.sub(r'/page/\d+/?$', '', category_url.rstrip('/'))
    return base if page == 1 else f"{base}/page/{page}/"

def get_number_of_pages(url: str) -> int:
    resp = get_website_safe(url)
    if not resp:
        return 1
    soup = BeautifulSoup(resp.text, "html.parser")
    pagination = soup.select_one("ul.pagination")
    if pagination:
        last_link = pagination.find("a", string="»")
        if last_link and last_link.get("href"):
            m = re.search(r'/page/(\d+)', last_link["href"])
            if m:
                return int(m.group(1))
        numbers = [int(a.text.strip()) for a in pagination.find_all("a", class_="page-link") if a.text.strip().isdigit()]
        if numbers:
            return max(numbers)
    max_page = 1
    for a in soup.find_all('a', href=True):
        m = re.search(r'/page/(\d+)', a['href'])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page if max_page > 1 else 1

# ----------------------------------------------------------------------
#  Metadata extraction from detail pages (Fasel)
# ----------------------------------------------------------------------
def clean_genre(genre: str) -> str:
    try:
        decoded = unquote(genre)
        return decoded if '%' not in decoded else genre
    except:
        return genre

def get_content_id(soup: BeautifulSoup) -> Optional[str]:
    try:
        return remove_arabic_chars(soup.find("i", class_="fas fa-dot-circle").parent.text.replace(":", "").replace("#", ""))
    except AttributeError:
        return None

def get_content_format(soup: BeautifulSoup) -> str:
    try:
        cf = soup.find("i", class_="fas fa-play-circle").find_next_sibling().text
        return cf if cf.isascii() else "N/A"
    except AttributeError:
        return "N/A"

def get_genres_both(soup: BeautifulSoup) -> dict:
    try:
        genre_tags = soup.find("i", class_="far fa-folders").find_next_siblings("a")
        raw_genres = [tag["href"].split("/")[-1].capitalize() for tag in genre_tags]
        ar_genres = [clean_genre(g) for g in raw_genres]
        en_genres = [FASEL_GENRE_MAP.get(g, g) for g in ar_genres]
        return {"ar": ar_genres, "en": en_genres}
    except AttributeError:
        return {"ar": [], "en": []}

def clean_iframe_source(iframe_src):
    if not iframe_src or "=" not in iframe_src:
        return ""
    try:
        return iframe_src.split("=")[2].replace("&img", "")
    except (IndexError, AttributeError):
        return ""

def remove_arabic_chars(s: str) -> str:
    return s.encode("ascii", "ignore").decode().strip()

def remove_year(title: str) -> str:
    if title[-4:].isdigit() and len(title) > 4:
        title = title.replace(title[-5:], "")
    return title

def get_content_title(soup_result: ResultSet) -> str:
    title = remove_year(remove_arabic_chars(soup_result.find("div", class_="h1").text))
    return title

def extract_country(soup: BeautifulSoup) -> Optional[str]:
    flag_icon = soup.find('i', class_='far fa-flag')
    if flag_icon:
        parent_span = flag_icon.find_parent('span')
        if parent_span:
            link = parent_span.find('a', rel='tag')
            if link:
                return link.text.strip()
    text = soup.get_text()
    match = re.search(r'دول الأنتاج\s*:\s*([^\n]+)', text)
    return match.group(1).strip() if match else None

def extract_runtime(soup: BeautifulSoup) -> Optional[int]:
    clock = soup.find('i', class_='far fa-clock')
    if clock:
        parent = clock.find_parent('span')
        if parent:
            m = re.search(r'(\d+)', parent.get_text())
            if m:
                return int(m.group(1))
    meta = soup.find('meta', attrs={'itemprop': 'duration'})
    if meta and meta.get('content'):
        dur = meta['content']
        m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
        if m:
            h = int(m.group(1)) if m.group(1) else 0
            mn = int(m.group(2)) if m.group(2) else 0
            return h * 60 + mn
    return None

# ----------------------------------------------------------------------
#  Image upload (Imgur)
# ----------------------------------------------------------------------
def upload_image(image_url: str, content_id: str, get_image: Callable[[str], Response]) -> str:
    if DEBUG:
        print(content_id)
    if content_id in IMAGE_SOURCES:
        return IMAGE_SOURCES[content_id]
    if not image_url:
        return "https://imgpile.com/images/TPDrVl.jpg"
    image = get_image(image_url)
    image_path = f"./output/{content_id}"
    if ".webp" in image_url:
        with open(image_path + ".webp", "wb") as f:
            f.write(image.content)
        jpg = Image.open(image_path + ".webp").convert("RGB")
        jpg.save(image_path + ".jpg", "jpeg")
        with open(image_path + ".jpg", "rb") as f:
            b64 = f.read()
    else:
        b64 = b64encode(image.content).decode("utf8")
    imgur_headers = {"Authorization": f"Client-ID {os.environ.get('IMGUR_CLIENT_ID')}"}
    data = {"image": b64}
    try:
        res = requests.post("https://api.imgur.com/3/image", headers=imgur_headers, data=data)
        return res.json()["data"]["link"]
    except Exception:
        return "https://imgpile.com/images/TPDrVl.jpg"

# ----------------------------------------------------------------------
#  Video source extraction (on‑demand) – uses Playwright
# ----------------------------------------------------------------------
TEMP_PROFILE = os.path.abspath("./chrome_fresh_profile")
AD_DOMAINS = [
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com", "clickadu.com"
]

def get_video_stream_url(page_url: str, headless: bool = True, max_attempts: int = 7) -> Optional[str]:
    from playwright.sync_api import sync_playwright
    captured_url = None
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=TEMP_PROFILE,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1280,720"
            ],
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        def block_ads(route, request):
            if any(domain in request.url for domain in AD_DOMAINS):
                route.abort()
                return
            route.continue_()
        page.route("**/*", block_ads)
        page.on("popup", lambda popup: popup.close())

        if DEBUG:
            print(f"[Video] Loading {page_url}")
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)

        iframe = page.frame(name="player_iframe")
        if not iframe:
            iframe_elem = page.query_selector("iframe[name='player_iframe']")
            if iframe_elem:
                iframe = iframe_elem.content_frame()
        if not iframe:
            if DEBUG:
                print("[Video] Could not find player iframe")
            context.close()
            return None

        try:
            iframe.wait_for_selector("body", timeout=15000)
        except:
            context.close()
            return None

        play_selector = ".jw-icon.jw-icon-display.jw-button-color.jw-reset"
        video_selector = "video"

        def intercept(route, request):
            nonlocal captured_url
            domain = extract_domain(request.url)
            if domain and domain not in AD_DOMAINS:
                with open("new_ad_domains.log", "a") as log:
                    log.write(f"{domain}\n")
                if DEBUG:
                    print(f"[AdDiscovery] New potential ad domain: {domain}")
            if ".m3u8" in request.url:
                if "master.m3u8" in request.url:
                    captured_url = request.url
                    if DEBUG:
                        print(f"[Video] MASTER m3u8: {captured_url}")
                elif captured_url is None and "playlist.m3u8" in request.url:
                    captured_url = request.url
                    if DEBUG:
                        print(f"[Video] Fallback playlist: {captured_url}")
            route.continue_()
        page.route("**/*", intercept)

        for attempt in range(max_attempts):
            if captured_url:
                break
            if DEBUG:
                print(f"[Video] Click attempt {attempt+1}")
            try:
                iframe.click(play_selector, force=True, timeout=3000)
            except:
                try:
                    iframe.click(video_selector, force=True)
                except:
                    pass
            time.sleep(1.5)
            for p in context.pages:
                if p != page:
                    p.close()

        for _ in range(30):
            if captured_url:
                break
            time.sleep(0.5)

        context.close()
        return captured_url

def extract_video_source(page_url: str, headless: bool = True) -> str:
    url = get_video_stream_url(page_url, headless=headless)
    return url if url else ""

# ----------------------------------------------------------------------
#  Convenience sync functions for metadata scraping (FaselHD)
# ----------------------------------------------------------------------
def get_latest_movies(soup: BeautifulSoup) -> List[dict]:
    movies = []
    divs = soup.select(".blockMovie") or soup.select(".postDiv")
    for div in divs:
        link = div.find("a")
        if not link:
            continue
        img = link.find("img")
        img_src = img.get("data-src") or img.get("src", "") if img else ""
        title_elem = link.find("div", class_="h5") or link.find("div", class_="h1")
        title = title_elem.text.strip() if title_elem else ""
        quality_span = link.find("span", class_="quality")
        quality = quality_span.text.strip() if quality_span else ""
        imdb_span = link.find("span", class_="pImdb") or link.find("span", class_="bimdb")
        imdb_rating = None
        if imdb_span:
            try:
                imdb_rating = float(imdb_span.text.strip())
            except:
                pass
        views_span = link.find("span", class_="pViews") or link.find("span", class_="bviews")
        views = 0
        if views_span:
            views_text = views_span.text.strip().replace("٬", "").replace(",", "")
            try:
                views = int(views_text)
            except:
                pass
        movies.append({
            "title": title,
            "link": link["href"],
            "image": img_src,
            "quality": quality,
            "imdb_rating": imdb_rating,
            "views": views,
            "content_type": "movies"
        })
    return movies

def get_latest_episodes(soup: BeautifulSoup) -> List[dict]:
    episodes = []
    for ep in soup.select(".epDivHome"):
        link_tag = ep.find("a", class_="epHomeImg")
        content_div = ep.find("div", class_="epHomeContent")
        link = ""
        image = ""
        if link_tag:
            link = link_tag.get("href", "")
            img = link_tag.find("img")
            image = img.get("data-src") or img.get("src", "") if img else ""
        elif content_div and content_div.find("a"):
            link = content_div.find("a").get("href", "")
        if not link:
            continue
        title = ""
        if content_div:
            title_div = content_div.find("div", class_="h4")
            if title_div:
                title = title_div.text.strip()
        if not title:
            title_div = ep.find("div", class_="h4")
            if title_div:
                title = title_div.text.strip()
        status_span = ep.find("span", class_="epStatus")
        status = status_span.text.strip() if status_span else ""
        content_type = "series"
        if "anime-episodes" in link:
            content_type = "anime"
        elif "asian-episodes" in link:
            content_type = "asian-series"
        episodes.append({
            "title": title,
            "link": link,
            "image": image,
            "status": status,
            "content_type": content_type
        })
    return episodes

def get_featured_content(soup: BeautifulSoup) -> List[dict]:
    featured = []
    for slide in soup.select(".swiper-slide"):
        title_div = slide.find("div", class_="h1 mb-1")
        if not title_div:
            continue
        a = title_div.find("a")
        if not a:
            continue
        title = a.text.strip()
        link = a.get("href", "")
        poster = slide.find("div", class_="poster")
        img_url = ""
        if poster:
            img = poster.find("img")
            img_url = img.get("src", "") if img else ""
        if not img_url:
            slide_img = slide.find("div", class_="slideImg")
            if slide_img and slide_img.get("style"):
                style = slide_img.get("style", "")
                if "url(" in style:
                    img_url = style.split("url(")[1].split(")")[0].strip("\"'")
        imdb_span = slide.find("span", class_="imdbRate")
        imdb = None
        if imdb_span:
            try:
                imdb = float(imdb_span.text.strip())
            except:
                pass
        categories = [c.text.strip() for c in slide.select(".slideCats span")]
        desc = ""
        p = slide.find("p")
        if p:
            desc = p.text.strip()
        content_type = "movies"
        if "/anime" in link:
            content_type = "anime"
        elif "/asian" in link:
            content_type = "asian-series"
        elif "/series" in link or "/episodes" in link:
            content_type = "series"
        featured.append({
            "title": title,
            "link": link,
            "image": img_url,
            "imdb_rating": imdb,
            "categories": categories,
            "description": desc,
            "content_type": content_type
        })
    return featured

def get_most_viewed_movies(soup: BeautifulSoup) -> List[dict]:
    most_viewed = []
    slider = soup.select_one('.viewsOrderSlider')
    if not slider:
        return most_viewed
    items = slider.select('.itemviews')
    for item in items:
        post_div = item.select_one('.postDiv')
        if not post_div:
            continue
        link_tag = post_div.find('a')
        if not link_tag:
            continue
        link = link_tag.get('href', '')
        title_elem = post_div.select_one('.h1')
        title = title_elem.text.strip() if title_elem else 'Unknown'
        img = post_div.find('img')
        img_src = img.get('data-src', img.get('src', '')) if img else ''
        quality_span = post_div.select_one('.quality')
        quality = quality_span.text.strip() if quality_span else ''
        imdb_span = post_div.select_one('.pImdb')
        imdb_rating = None
        if imdb_span:
            try:
                imdb_rating = float(imdb_span.text.strip())
            except:
                pass
        views_span = post_div.select_one('.pViews')
        views = 0
        if views_span:
            views_text = views_span.text.strip().replace('٬', '').replace(',', '')
            try:
                views = int(views_text)
            except:
                pass
        most_viewed.append({
            "title": title,
            "link": link,
            "image": img_src,
            "quality": quality,
            "imdb_rating": imdb_rating,
            "views": views,
        })
    return most_viewed

def get_latest_movies_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_movies(soup)

def get_latest_episodes_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_episodes(soup)

def get_featured_content_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_featured_content(soup)

def get_all_homepage_content() -> dict:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return {"movies": [], "episodes": [], "featured": []}
    soup = BeautifulSoup(resp.text, "html.parser")
    return {
        "movies": get_latest_movies(soup),
        "episodes": get_latest_episodes(soup),
        "featured": get_featured_content(soup)
    }

def get_category_page_rendered(category_url: str, page: int = 1) -> List[dict]:
    url = get_paginated_url(category_url, page)
    resp = get_website_safe(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_movies(soup)

def get_seasons_url_from_detail(detail_url: str) -> str:
    if any(prefix in detail_url for prefix in ['/seasons/', '/tvseasons/', '/asian_seasons/']):
        return detail_url

    resp = get_website_safe(detail_url)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    season_div = soup.select_one('#seasonList .seasonDiv')
    if not season_div:
        return detail_url

    onclick = season_div.get('onclick')
    if not onclick:
        return detail_url

    import re
    match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
    if match:
        season_url = match.group(1)
        if season_url.startswith('?'):
            return FASEL_BASE_URL.rstrip('/') + season_url
        elif season_url.startswith('/'):
            return FASEL_BASE_URL.rstrip('/') + season_url
        else:
            return season_url

    return detail_url

# ----------------------------------------------------------------------
#  Description extraction
# ----------------------------------------------------------------------
def extract_description(soup: BeautifulSoup) -> str:
    selectors = ['.singleDesc p', '.desc p', '.film-description']
    for selector in selectors:
        desc_elem = soup.select_one(selector)
        if desc_elem and desc_elem.text.strip():
            return desc_elem.text.strip()
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        return meta_desc['content'].strip()
    return ""

# ----------------------------------------------------------------------
#  Helper functions for extra anime metadata (FaselHD)
# ----------------------------------------------------------------------
def extract_status(soup: BeautifulSoup) -> str:
    check_icons = soup.find_all('i', class_='far fa-check-double')
    if len(check_icons) >= 1:
        parent = check_icons[0].find_parent('span')
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            if ':' in text:
                return text.split(':', 1)[1].strip()
    return ""

def extract_viewing_level(soup: BeautifulSoup) -> str:
    for span in soup.find_all('span'):
        icon = span.find('i', class_='far fa-check-double')
        if icon:
            text = span.get_text(separator=' ', strip=True)
            if 'مستوى المشاهدة' in text or 'فئة المشاهدة' in text:
                if ':' in text:
                    parts = text.split(':', 1)
                    if len(parts) > 1:
                        return parts[1].strip()
                else:
                    return text.replace('مستوى المشاهدة', '').replace('فئة المشاهدة', '').strip()
    return ""

def extract_language(soup: BeautifulSoup) -> str:
    icon = soup.find('i', class_='fal fa-language')
    if icon:
        parent = icon.find_parent('span')
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            if ':' in text:
                return text.split(':', 1)[1].strip()
    return ""

def extract_release_date(soup: BeautifulSoup) -> str:
    icon = soup.find('i', class_='far fa-calendar-alt')
    if icon:
        parent = icon.find_parent('span')
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            if ':' in text:
                return text.split(':', 1)[1].strip()
    return ""

def extract_episode_duration(soup: BeautifulSoup) -> str:
    icon = soup.find('i', class_='far fa-clock')
    if icon:
        parent = icon.find_parent('span')
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            if ':' in text:
                return text.split(':', 1)[1].strip()
    return ""

def extract_episode_count_text(soup: BeautifulSoup) -> int:
    icon = soup.find('i', class_='far fa-film')
    if icon:
        parent = icon.find_parent('span')
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            if ':' in text:
                count_part = text.split(':', 1)[1].strip()
                match = re.search(r'(\d+)', count_part)
                if match:
                    return int(match.group(1))
    return 0

def extract_sources(soup: BeautifulSoup) -> List[str]:
    sources = []
    for li in soup.select('.tabs-ul li'):
        onclick = li.get('onclick', '')
        match = re.search(r"player_iframe\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
        if match:
            sources.append(match.group(1))
    return sources

# ----------------------------------------------------------------------
#  Season and episode extraction helpers (FaselHD)
# ----------------------------------------------------------------------
def extract_seasons_from_page(soup: BeautifulSoup, base_url: str) -> List[dict]:
    seasons = []
    season_divs = soup.select('#seasonList .seasonDiv')
    for div in season_divs:
        title_div = div.select_one('.title')
        if not title_div:
            continue
        title_text = title_div.text.strip()
        match = re.search(r'(\d+)', title_text)
        if not match:
            continue
        season_num = int(match.group(1))
        onclick = div.get('onclick', '')
        url_match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
        if not url_match:
            continue
        season_url = url_match.group(1)
        if not season_url.startswith('http'):
            season_url = base_url.rstrip('/') + season_url
        img = div.find('img')
        poster = ''
        if img:
            poster = img.get('data-src') or img.get('src', '')
        seasons.append({
            'number': season_num,
            'page_url': season_url,
            'poster': poster
        })
    return seasons

def extract_episodes_from_season_page(soup: BeautifulSoup) -> List[str]:
    episode_urls = []
    ep_links = soup.select('#epAll a')
    for a in ep_links:
        href = a.get('href')
        if href:
            if href.startswith('/'):
                href = FASEL_BASE_URL.rstrip('/') + href
            episode_urls.append(href)
    if not episode_urls:
        for block in soup.select('.epDiv, .episode-item, .episodeDiv'):
            link = block.find('a', href=True)
            if link:
                href = link['href']
                if href.startswith('/'):
                    href = FASEL_BASE_URL.rstrip('/') + href
                episode_urls.append(href)
    return list(dict.fromkeys(episode_urls))

# ----------------------------------------------------------------------
#  IMDb rating helper using OMDb API (via omdb library)
# ----------------------------------------------------------------------
import omdb  # requires 'pip install omdb'

OMDB_API_KEY = "b7fc5b44"
OMDB_BASE_URL = "http://www.omdbapi.com/"
IMDB_CACHE = {}

# Set the API key globally for the omdb module
omdb.set_default('apikey', OMDB_API_KEY)

def fetch_imdb_rating_by_id(imdb_id: str) -> Optional[str]:
    """Fetch rating using IMDb ID via omdb library."""
    if not imdb_id or not imdb_id.startswith('tt'):
        return None
    if imdb_id in IMDB_CACHE:
        cached = IMDB_CACHE[imdb_id]
        if isinstance(cached, str):
            return cached
        if isinstance(cached, dict) and 'rating' in cached:
            return cached['rating']
    try:
        data = omdb.imdbid(imdb_id, timeout=10)
        if data and data.get('response') == True:
            rating = data.get('imdb_rating')
            if rating and rating != 'N/A':
                IMDB_CACHE[imdb_id] = rating
                return rating
    except Exception as e:
        print(f"OMDb error for ID {imdb_id}: {e}")
    IMDB_CACHE[imdb_id] = None
    return None

def search_imdb_by_title(title: str, year: Optional[str] = None, content_type: str = "movie") -> Optional[str]:
    """Search OMDb by title/year/type using direct lookup via raw requests. Returns IMDb ID or None."""
    # Clean title (remove punctuation)
    # Normalize smart quotes, keep apostrophes, commas, periods, colons, dashes, ampersands
    title_temp = title.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    cleaned = re.sub(r'[^\w\s\'\-,\.:&]', ' ', title_temp, flags=re.UNICODE).strip()
    
    # Map content_type to OMDb type parameter
    omdb_type = None
    if content_type == "movie":
        omdb_type = "movie"
    elif content_type in ("tv", "series"):
        omdb_type = "series"
    
    # Direct lookup with title, year, type
    if year:
        url = f"{OMDB_BASE_URL}?t={cleaned}&y={year}&apikey={OMDB_API_KEY}"
        if omdb_type:
            url += f"&type={omdb_type}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get('Response') == 'True':
                return data.get('imdbID')
        except Exception as e:
            print(f"OMDb direct lookup error for '{cleaned} ({year})': {e}")
        return None
    
    # Only if no year was provided, try search (less accurate)
    url = f"{OMDB_BASE_URL}?s={cleaned}&apikey={OMDB_API_KEY}"
    if omdb_type:
        url += f"&type={omdb_type}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('Response') == 'True':
            results = data.get('Search', [])
            if results:
                return results[0].get('imdbID')
    except Exception as e:
        print(f"OMDb search error: {e}")
    return None

def get_imdb_rating(title: str, year: Optional[str] = None, content_type: str = "movie", known_imdb_id: Optional[str] = None) -> Optional[str]:
    """Return rating as string or None."""
    if known_imdb_id and known_imdb_id.startswith('tt'):
        return fetch_imdb_rating_by_id(known_imdb_id)
    imdb_id = search_imdb_by_title(title, year, content_type)
    if imdb_id:
        return fetch_imdb_rating_by_id(imdb_id)
    return None

def get_imdb_details(title: str, year: Optional[str] = None, content_type: str = "movie", known_imdb_id: Optional[str] = None) -> tuple:
    """
    Return (rating, votes, imdb_id, limit_reached) using raw requests.
    """
    imdb_id = known_imdb_id
    if not imdb_id:
        imdb_id = search_imdb_by_title(title, year, content_type)
    if not imdb_id:
        return (None, None, None, False)

    # Check cache
    if imdb_id in IMDB_CACHE:
        cached = IMDB_CACHE[imdb_id]
        if isinstance(cached, dict) and 'rating' in cached and 'votes' in cached:
            return (cached['rating'], cached['votes'], imdb_id, False)
        elif isinstance(cached, str):
            return (cached, 0, imdb_id, False)

    url = f"{OMDB_BASE_URL}?i={imdb_id}&apikey={OMDB_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('Response') == 'True':
            rating = data.get('imdbRating')
            votes_str = data.get('imdbVotes', '0')
            votes = int(votes_str.replace(',', '')) if votes_str and votes_str != 'N/A' else 0
            if rating and rating != 'N/A':
                IMDB_CACHE[imdb_id] = {'rating': rating, 'votes': votes}
                return (rating, votes, imdb_id, False)
        else:
            error = data.get('Error', '')
            if 'limit' in error.lower():
                print(f"⚠️ OMDb API limit reached: {error}")
                return (None, None, imdb_id, True)
    except Exception as e:
        print(f"OMDb error for {imdb_id}: {e}")
    IMDB_CACHE[imdb_id] = {'rating': None, 'votes': None}
    return (None, None, imdb_id, False)

# ----------------------------------------------------------------------
#  TMDb API helpers
# ----------------------------------------------------------------------
TMDB_API_KEY = "4b02f35b5faa266f6cb773e25ab50b7a"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_CACHE = {}

def _clean_title_tmdb(raw_title: str) -> str:
    arabic_stop = ["فيلم", "مسلسل", "مترجم", "اون لاين", "اونلاين", "مدبلج", "الحلقة", "الفيلم"]
    cleaned = raw_title
    for word in arabic_stop:
        cleaned = re.sub(rf'\b{word}\b', '', cleaned, flags=re.IGNORECASE)
    # Normalize smart/curly quotes to straight ones
    cleaned = cleaned.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    # Keep letters (including accented), numbers, spaces, and allowed punctuation: ' , - & : .
    # Remove all other punctuation (e.g., ! @ # $ % ^ * ( ) + = { } [ ] \ | / ~)
    cleaned = re.sub(r'[^\w\s\'\-,&:.]', ' ', cleaned, flags=re.UNICODE)
    cleaned = ' '.join(cleaned.split())
    return cleaned if cleaned else raw_title

def search_tmdb(title: str, year: Optional[str] = None, media_type: str = "movie") -> Optional[int]:
    search_url = f"{TMDB_BASE_URL}/search/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "en-US"
    }
    if year:
        if media_type == "movie":
            params["year"] = year
        else:
            params["first_air_date_year"] = year
    try:
        resp = requests.get(search_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("total_results", 0) > 0:
            return data["results"][0]["id"]
    except Exception as e:
        print(f"TMDb search error for '{title}': {e}")
    return None

def fetch_tmdb_rating(tmdb_id: int, media_type: str) -> tuple:
    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rating = data.get("vote_average")
        votes = data.get("vote_count", 0)
        if rating:
            return (str(round(rating, 1)), votes)
        return (None, 0)
    except Exception as e:
        print(f"TMDb fetch error for ID {tmdb_id}: {e}")
        return (None, 0)

def get_tmdb_details(title: str, year: Optional[str] = None, content_type: str = "movie") -> tuple:
    cleaned = _clean_title_tmdb(title)
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in TMDB_CACHE:
        return TMDB_CACHE[cache_key]

    tmdb_id = search_tmdb(cleaned, year, content_type)
    if not tmdb_id:
        TMDB_CACHE[cache_key] = (None, 0)
        return (None, 0)

    rating, votes = fetch_tmdb_rating(tmdb_id, content_type)
    TMDB_CACHE[cache_key] = (rating, votes)
    return rating, votes

def get_tmdb_imdb_id(title: str, year: Optional[str] = None, media_type: str = "movie") -> Optional[str]:
    """Search TMDb and return IMDb ID (tt...), or None if not found."""
    cleaned = _clean_title_tmdb(title)
    tmdb_id = search_tmdb(cleaned, year, media_type)
    if not tmdb_id:
        return None
    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}/external_ids"
    params = {"api_key": TMDB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        imdb_id = data.get("imdb_id")
        return imdb_id if imdb_id else None
    except Exception as e:
        print(f"  ⚠️ TMDb external ID error for '{title}': {e}")
        return None

def fetch_runtime_from_tmdb(imdb_id: str) -> Optional[int]:
    """
    Given an IMDb ID, find the corresponding TMDb entry and return runtime in minutes.
    For movies, returns the movie runtime.
    For TV series, returns the typical episode runtime (first value from episode_run_time array).
    Returns None if not found.
    """
    if not imdb_id or not imdb_id.startswith('tt'):
        return None
    # Use TMDb find endpoint
    url = f"{TMDB_BASE_URL}/find/{imdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "external_source": "imdb_id"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Check movies first
        movie_results = data.get("movie_results", [])
        if movie_results:
            tmdb_id = movie_results[0]["id"]
            detail_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
            detail_resp = requests.get(detail_url, params={"api_key": TMDB_API_KEY})
            detail_resp.raise_for_status()
            runtime = detail_resp.json().get("runtime")
            return runtime if runtime else None
        # Then TV series
        tv_results = data.get("tv_results", [])
        if tv_results:
            tmdb_id = tv_results[0]["id"]
            detail_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
            detail_resp = requests.get(detail_url, params={"api_key": TMDB_API_KEY})
            detail_resp.raise_for_status()
            episode_run_time = detail_resp.json().get("episode_run_time", [])
            if episode_run_time:
                return episode_run_time[0]  # typical episode runtime in minutes
        return None
    except Exception as e:
        print(f"  TMDb runtime fetch error for {imdb_id}: {e}")
        return None

# ----------------------------------------------------------------------
#  IMDBAPI.dev API Helpers (with retries)
# ----------------------------------------------------------------------
IMDBAPI_BASE_URL = "https://api.imdbapi.dev"

# Set this to True to see full response text on errors
DEBUG_IMDBAPI = True

def search_imdbapi_dev(title: str, year: Optional[str] = None, max_retries: int = 3, relaxed: bool = False) -> tuple:
    """
    Search IMDbAPI.dev for a title and return (rating, votes, imdb_id).
    If relaxed=True, accept best match regardless of score (score >= -1).
    Otherwise requires best_score >= 5.
    """
    params = {
        "query": title,
        "limit": 10,
        "sortBy": "SORT_BY_USER_RATING_COUNT",
        "sortOrder": "DESC"
    }
    if year:
        params["startYear"] = year
        params["endYear"] = year

    url = f"{IMDBAPI_BASE_URL}/search/titles"
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                titles = data.get("titles", [])
                if not titles:
                    return (None, 0, None)
                
                best_match = None
                best_score = -1
                for t in titles:
                    t_title = t.get("primaryTitle", "")
                    t_year = t.get("startYear")
                    score = 0
                    if title.lower() == t_title.lower():
                        score += 10
                    elif title.lower() in t_title.lower() or t_title.lower() in title.lower():
                        score += 5
                    if year and t_year and int(year) == t_year:
                        score += 3
                    if t.get("rating", {}).get("aggregateRating") is not None:
                        score += 1
                    if score > best_score:
                        best_score = score
                        best_match = t
                
                required_score = -1 if relaxed else 5
                if best_match and best_score >= required_score:
                    imdb_id = best_match.get("id")
                    rating_info = best_match.get("rating", {})
                    avg_rating = rating_info.get("aggregateRating")
                    vote_count = rating_info.get("voteCount", 0)
                    if avg_rating is not None:
                        rating_str = str(round(float(avg_rating), 1))
                        return (rating_str, vote_count, imdb_id)
                    else:
                        return (None, 0, imdb_id)
                else:
                    return (None, 0, None)
            
            # Rate limit and error handling (unchanged)
            elif resp.status_code == 429:
                wait = 5 * (2 ** attempt)
                print(f"  [IMDbAPI] Rate limited (429), retry {attempt+1}/{max_retries} after {wait}s")
                if DEBUG_IMDBAPI:
                    print(f"  Response: {resp.text[:200]}")
                time.sleep(wait)
                continue
            
            elif resp.status_code in (500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"  [IMDbAPI] Server error {resp.status_code}, retry {attempt+1}/{max_retries} after {wait}s")
                if DEBUG_IMDBAPI:
                    print(f"  Response: {resp.text[:200]}")
                time.sleep(wait)
                continue
            
            else:
                print(f"  [IMDbAPI] HTTP {resp.status_code} for '{title}'")
                if DEBUG_IMDBAPI:
                    print(f"  Response: {resp.text[:500]}")
                return (None, 0, None)
        
        except requests.exceptions.Timeout:
            print(f"  [IMDbAPI] Timeout for '{title}', attempt {attempt+1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return (None, 0, None)
        except Exception as e:
            print(f"  [IMDbAPI] Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return (None, 0, None)
    
    return (None, 0, None)

def fetch_imdbapi_by_id(imdb_id: str) -> tuple:
    """Fetch rating and votes for a known IMDb ID using IMDbAPI.dev."""
    if not imdb_id or not imdb_id.startswith("tt"):
        return (None, 0)
    url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rating_info = data.get("rating", {})
            avg_rating = rating_info.get("aggregateRating")
            vote_count = rating_info.get("voteCount", 0)
            if avg_rating is not None:
                return (str(round(float(avg_rating), 1)), vote_count)
    except Exception as e:
        print(f"  [IMDbAPI] Direct fetch error for {imdb_id}: {e}")
    return (None, 0)

def fetch_start_year(imdb_id: str) -> str | None:
    """
    Fetch the first-aired / release year for a title from IMDbAPI.
    Returns a 4-digit string e.g. "2021", or None if unavailable.
    """
    if not imdb_id or not imdb_id.startswith("tt"):
        return None
    url = f"{IMDBAPI_BASE_URL}/titles/{imdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            year = data.get("startYear") or data.get("releaseYear") or data.get("year")
            if year:
                return str(year)[:4]
    except Exception as e:
        print(f"  [IMDbAPI] fetch_start_year error for {imdb_id}: {e}")
    return None


# ======================================================================
#  AKWAM SPECIFIC HELPERS (clean & simple)
# ======================================================================
AKWAM_BASE_URL    = "https://akwam.it"       # ← update here if domain changes again
AKWAM_GO_URL      = "https://go.akwam.it"   # shortener / watch+download links
# Legacy domains – kept so normalize_akwam_url can rewrite saved links
AKWAM_LEGACY_DOMAINS = ["akwam.com.co", "go.akwam.com.co", "akw.cam"]

def normalize_akwam_url(url: str) -> str:
    """Rewrite any saved akwam link from old domains to the current live domain.
    Safe to call even if the URL is already on the new domain or is empty.
    """
    if not url:
        return url
    for legacy in AKWAM_LEGACY_DOMAINS:
        if legacy in url:
            replacement = AKWAM_GO_URL.replace("https://", "") if legacy.startswith("go.") else AKWAM_BASE_URL.replace("https://", "")
            return url.replace(legacy, replacement)
    return url

def akwam_extract_series_list(soup: BeautifulSoup, base_url: str = None) -> List[dict]:
    """Extract basic series info from a listing page."""
    if base_url is None:
        base_url = AKWAM_BASE_URL
    series_list = []
    cards = soup.select('.entry-box') or soup.select('.col-lg-auto.col-md-4.col-6')
    for card in cards:
        link_tag = card.select_one('.entry-image a')
        if not link_tag:
            continue
        series_url = urljoin(base_url, link_tag.get('href', ''))
        series_id = series_url.split('/')[-2] if '/series/' in series_url else None
        if not series_id:
            continue

        title_elem = card.select_one('.entry-title a')
        title = title_elem.get_text(strip=True) if title_elem else ''

        year_elem = card.select_one('.badge-secondary')
        year = year_elem.get_text(strip=True) if year_elem else None

        rating_elem = card.select_one('.label.rating')
        rating = None
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True).replace('icon-star', '').strip()
            match = re.search(r'([\d.]+)', rating_text)
            if match:
                rating = float(match.group(1))

        img_tag = card.select_one('.entry-image img')
        img_src = img_tag.get('data-src') or img_tag.get('src', '') if img_tag else ''
        if img_src and not img_src.startswith('http'):
            img_src = urljoin(base_url, img_src)

        series_list.append({
            'id': series_id,
            'title': title,
            'year': year,
            'rating': rating,
            'image': img_src,
            'url': series_url
        })
    return series_list

def akwam_extract_series_metadata(soup: BeautifulSoup, base_url: str = None) -> dict:
    """Extract all metadata from a series detail page (excluding episodes)."""
    if base_url is None:
        base_url = AKWAM_BASE_URL
    metadata = {}

    # Title
    title_elem = soup.select_one('h1.entry-title')
    metadata['title'] = title_elem.get_text(strip=True) if title_elem else ''

    # Rating & votes (Akwam's own rating)
    rating, votes = _akwam_extract_rating(soup)
    metadata['rating'] = rating
    metadata['votes'] = votes

    # Basic info
    info_rows = soup.select('.movie-cover .row .col-lg-7 .font-size-16')
    for row in info_rows:
        text = row.get_text(strip=True)
        if 'انتاج :' in text:
            metadata['country'] = text.split(':', 1)[1].strip()
        elif 'السنة :' in text:
            metadata['year'] = text.split(':', 1)[1].strip()
        elif 'اللغة :' in text:
            metadata['language'] = text.split(':', 1)[1].strip()
        elif 'الجودة :' in text:
            metadata['quality'] = text.split(':', 1)[1].strip()
        elif 'مدة' in text:
            metadata['runtime'] = text.split(':', 1)[1].strip()

    # Genres
    genres_ar = [a.get_text(strip=True) for a in soup.select('.movie-cover .badge-light')]
    seen = set()
    metadata['genres_ar'] = [g for g in genres_ar if not (g in seen or seen.add(g))]
    metadata['genres_en'] = [FASEL_GENRE_MAP.get(g, g) for g in metadata['genres_ar']]

    metadata['description'] = extract_description(soup)

    # Dates
    date_spans = soup.select('.font-size-14.text-muted span')
    for span in date_spans:
        text = span.get_text(strip=True)
        if 'تـ الإضافة :' in text:
            metadata['date_added'] = _parse_akwam_date(text.split(':', 1)[1].strip())
        elif 'تـ اخر تحديث :' in text:
            metadata['date_updated'] = _parse_akwam_date(text.split(':', 1)[1].strip())

    # Cast
    metadata['cast'] = [a.get_text(strip=True) for a in soup.select('.entry-box-3 .entry-title a')]

    # ---------- External IDs (TMDb / IMDb) – always present, null if missing ----------
    metadata['tmdb_url'] = None
    metadata['tmdb_id'] = None
    metadata['imdb_url'] = None
    metadata['imdb_id'] = None

    rating_container = soup.select_one('.font-size-16.text-white.mt-2.d-flex')
    if rating_container:
        for link in rating_container.find_all('a', href=True):
            href = link['href']
            if 'themoviedb.org' in href:
                metadata['tmdb_url'] = href
                match = re.search(r'/(?:tv|movie)/(\d+)', href)
                if match:
                    metadata['tmdb_id'] = match.group(1)
            elif 'imdb.com' in href or 'elcinema.com' in href:
                metadata['imdb_url'] = href
                imdb_match = re.search(r'tt\d{7,8}', href)
                if imdb_match:
                    metadata['imdb_id'] = imdb_match.group(0)
    # Fallback search if not found in the rating container
    if metadata['tmdb_url'] is None:
        tmdb_link = soup.find('a', href=re.compile(r'themoviedb\.org'))
        if tmdb_link:
            metadata['tmdb_url'] = tmdb_link['href']
            match = re.search(r'/(?:tv|movie)/(\d+)', tmdb_link['href'])
            if match:
                metadata['tmdb_id'] = match.group(1)
    if metadata['imdb_url'] is None:
        imdb_link = soup.find('a', href=re.compile(r'imdb\.com/title/tt\d+'))
        if imdb_link:
            metadata['imdb_url'] = imdb_link['href']
            match = re.search(r'tt\d{7,8}', imdb_link['href'])
            if match:
                metadata['imdb_id'] = match.group(0)
    # -----------------------------------------------------------------

    # Episodes (basic list)
    episodes = []
    for block in soup.select('#series-episodes .bg-primary2'):
        ep_link = block.find('a', href=True)
        if ep_link:
            href = ep_link['href'].strip()
            if href.startswith('/%20'):
                href = href[3:]
            elif href.startswith('/ '):
                href = href[2:]
            ep_url = urljoin(base_url, href)
            episodes.append({
                'number': None,
                'title': ep_link.get_text(strip=True),
                'url': ep_url
            })
    metadata['episodes'] = episodes
    metadata['episode_count'] = len(episodes)

    metadata['is_ramadan'] = 'رمضان' in metadata['genres_ar']

    poster = soup.select_one('.movie-cover .container .col-lg-3 img')
    metadata['poster'] = urljoin(base_url, poster.get('src', '')) if poster else ''

    trailer_btn = soup.select_one('.btn-light[data-fancybox]')
    metadata['trailer_url'] = trailer_btn.get('href', '') if trailer_btn else ''

    return metadata

def _akwam_extract_rating(soup: BeautifulSoup) -> tuple:
    script = soup.find('script', type='application/ld+json')
    if script:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Movie' and 'AggregateRating' in item:
                        rating = item['AggregateRating'].get('ratingValue')
                        votes = item['AggregateRating'].get('ratingCount')
                        if rating:
                            return float(rating), int(votes) if votes else 0
            elif data.get('@type') == 'Movie' and 'AggregateRating' in data:
                rating = data['AggregateRating'].get('ratingValue')
                votes = data['AggregateRating'].get('ratingCount')
                if rating:
                    return float(rating), int(votes) if votes else 0
        except:
            pass
    rating_elem = soup.select_one('.label.rating')
    if rating_elem:
        rating_text = rating_elem.get_text(strip=True).replace('icon-star', '').strip()
        match = re.search(r'([\d.]+)', rating_text)
        if match:
            return float(match.group(1)), 0
    return None, 0

def _parse_akwam_date(date_str: str) -> str:
    """Convert Arabic date like 'الثلاثاء 09 04 2024 - 07:50 مساءاً' to ISO."""
    cleaned = re.sub(r'^(الأحد|الإثنين|الثلاثاء|الأربعاء|الخميس|الجمعة|السبت)\s+', '', date_str)
    cleaned = cleaned.replace('مساءاً', '').replace('صباحاً', '').strip()
    match = re.search(r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})', cleaned)
    if match:
        day, month, year, hour, minute = match.groups()
        hour = int(hour)
        minute = int(minute)
        if 'مساءاً' in date_str and hour < 12:
            hour += 12
        return f"{year}-{int(month):02d}-{int(day):02d}T{hour:02d}:{minute:02d}:00"
    return date_str

def akwam_extract_episode_sources(soup: BeautifulSoup) -> List[dict]:
    """Extract download/watch URLs from an episode page (go.akwam.it links)."""
    quality_map = {'tab-5': '1080p', 'tab-4': '720p', 'tab-3': '480p'}
    sources = []
    for tab_id, quality in quality_map.items():
        tab = soup.select_one(f'#{tab_id}')
        if not tab:
            continue
        download_link = tab.select_one('.link-download')
        if not download_link:
            continue
        watch_link = tab.select_one('.link-show')
        size_elem = download_link.select_one('.font-size-14')
        size_mb = None
        if size_elem:
            size_text = size_elem.get_text(strip=True)
            match = re.search(r'([\d.]+)\s*MB', size_text)
            if match:
                size_mb = float(match.group(1))
        sources.append({
            'quality': quality,
            'watch_url': watch_link.get('href') if watch_link else None,
            'download_url': download_link.get('href'),
            'size_mb': size_mb
        })
    return sources

# ----------------------------------------------------------------------
#  Legacy functions – Akwam, HDW, CimaNow (unchanged)
# ----------------------------------------------------------------------
def split_into_ranges(num_ranges: int, end: int, start: int = 0) -> list:
    step = (end - start) // num_ranges
    ranges = []
    for i in range(num_ranges):
        b = start + step * i
        e = end if i == num_ranges - 1 else start + step * (i + 1)
        if (b+1, e+1) not in ranges and b+1 != e+1:
            ranges.append((b+1, e+1))
    return ranges

def fix_url(url: str) -> str:
    return quote(url.split("?")[0]).replace("%3A", ":")

def akwam_get_website_safe(url: str) -> Response:
    while True:
        try:
            return requests.get(url)
        except (ConnectionError, ChunkedEncodingError):
            continue

def akwam_get_last_page_number(url: str) -> int:
    soup = BeautifulSoup(akwam_get_website_safe(url).content, "html.parser")
    return int(soup.find_all("a", class_="page-link")[-3].text)

def split_anchor_links(response: Response) -> list:
    soup = BeautifulSoup(response.content, "html.parser")
    links = [a["href"] for a in soup.find_all("a", class_="icn play")]
    ranges = split_into_ranges(6, len(links))
    return [links[r[0]-1 : r[1]-1] for r in ranges]

def akwam_get_genres(soup: BeautifulSoup) -> list:
    tags = soup.find_all("a", class_="badge badge-pill badge-light ml-2")
    try:
        ids = [t["href"].split("=")[-1] for t in tags]
        return [AKWAM_GENRES[i] for i in ids]
    except:
        return []

def hdw_get_last_page_number(url: str, selector=None) -> int:
    resp = get_website_safe(url)
    soup = BeautifulSoup(resp.content, "html.parser")
    return int(soup.find_all("a", class_="page-link")[-2].text)

def hdw_get_image_source(div: Tag) -> str:
    return div.find_previous_sibling("a").find("img")["src"]

def hdw_get_rating(div: Tag) -> Optional[str]:
    try:
        return div.find_previous_sibling("a").find("span", class_="float-left yellow").text.replace(",", ".").strip()
    except:
        return None

def hdw_get_genres(div: Tag) -> list:
    return [g.strip() for g in div.find("span", class_="content-views").text.split(", ")]

def get_tmdb_id(title: str, genre: str) -> Optional[str]:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return None
    url = "https://api.themoviedb.org/3/search/movie" if genre == "movies" else "https://api.themoviedb.org/3/search/tv"
    params = {"query": title, "api_key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
        return resp.json().get("results", [{}])[0].get("id")
    except:
        return None

def cima_now_get_last_page(soup: BeautifulSoup) -> int:
    return int(soup.find_all("ul")[-1].find_all("li")[-1].text)

def cima_now_get_sources(soup: BeautifulSoup) -> list:
    anchors = soup.find("ul", {"id": "download"}).find("li").find_all("a")
    return [{a.text.split()[0]: a["href"]} for a in anchors]