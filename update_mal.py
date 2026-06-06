#!/usr/bin/env python3
"""
update_mal.py – Enrich anime entries with MyAnimeList metadata.

For each item in anime.json and anime-movies.json:
  1. Clean title (strip Arabic prefix/suffix, extract season number)
  2. Search MAL API by base title
  3. Pick the result matching the correct season via sequel chain
  4. If confident match:
     - Update main JSON: Number Of Episodes, Runtime, EpisodeDuration,
       Country, Genres, GenresAr, Status, and add AiringSeason (e.g., "spring 2017")
       (ReleaseDate is NOT overwritten)
     - Write/update ratings/anime/{id}.json: rating, votes, source=mal,
       mal_id, mal_rank, mal_popularity, mal_studios, mal_title_en,
       mal_title_jp, mal_season, mal_year. Preserves existing imdb_id.
  5. If no confident match: skip, leave existing data untouched.

Usage:
    python update_mal.py
    python update_mal.py --category anime.json
    python update_mal.py --ids 274327 298229
    python update_mal.py --force   # re-process already matched items
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────
MAL_CLIENT_ID  = "25643e22a590c6626b5d87ce465f26bd"
MAL_BASE       = "https://api.myanimelist.net/v2"
DELAY          = 1.0          # seconds between MAL requests
MATCH_THRESHOLD = 0.6         # title similarity threshold (0-1)

OUTPUT_DIR  = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "mal_update_progress.txt"

ANIME_FILES = {
    "anime.json":        "tv",
    "anime-movies.json": "movie",
}

HEADERS = {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}

# ── Season mapping (Arabic + English ordinals) ────────────────────────
SEASON_MAP = {
    # Arabic
    "الأول": 1, "الاول": 1,
    "الثاني": 2, "الثانية": 2,
    "الثالث": 3, "الثالثة": 3,
    "الرابع": 4, "الرابعة": 4,
    "الخامس": 5, "الخامسة": 5,
    "السادس": 6, "السادسة": 6,
    "السابع": 7, "السابعة": 7,
    "الثامن": 8, "الثامنة": 8,
    "التاسع": 9, "التاسعة": 9,
    "العاشر": 10, "العاشرة": 10,
    "الحادي عشر": 11, "الثاني عشر": 12,
    "الثالث عشر": 13, "الرابع عشر": 14,
    "الخامس عشر": 15,
    # English ordinals (full words)
    "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15,
}

# MAL status → Arabic
STATUS_AR = {
    "finished_airing":  "مكتمل",
    "currently_airing": "مستمر",
    "not_yet_aired":    "قادم",
}

GENRE_AR = {
    # Core
    "Action": "أكشن", "Adventure": "مغامرة", "Comedy": "كوميديا", "Drama": "دراما",
    "Fantasy": "فانتازيا", "Horror": "رعب", "Mystery": "غموض", "Romance": "رومانسية",
    "Sci-Fi": "خيال علمي", "Slice of Life": "شريحة من الحياة", "Sports": "رياضة",
    "Supernatural": "خارق للطبيعة", "Thriller": "إثارة", "Mecha": "ميكا", "Music": "موسيقى",
    "Psychological": "نفسي", "Ecchi": "إيتشي", "Harem": "حريم", "Isekai": "إيسيكاي",
    "Shounen": "شونين", "Shoujo": "شوجو", "Seinen": "سينين", "Josei": "جوسيي",
    "Kids": "أطفال", "Historical": "تاريخي", "Military": "عسكري", "School": "مدرسة",
    "Magic": "سحر", "Demons": "شياطين", "Game": "ألعاب", "Vampire": "مصاصو دماء",
    "Space": "فضاء", "Martial Arts": "فنون قتالية", "Super Power": "قوى خارقة",
    "Award Winning": "حائز على جوائز", "Suspense": "تشويق", "Racing": "سباق",

    # Survival / Dark
    "Survival": "بقاء", "Gore": "دماء وعنف", "Dark Fantasy": "فانتازيا مظلمة",
    "Post-Apocalyptic": "ما بعد الكارثة", "Psychological Thriller": "إثارة نفسية",

    # Parody & Comedy
    "Parody": "محاكاة ساخرة", "Gag Humor": "فكاهة تهريجية", "Satire": "هجاء",

    # Historical / Cultural
    "Samurai": "ساموراي", "Ninja": "نينجا", "Wuxia": "ووشيا", "Xianxia": "شيانشيا",
    "Cultivation": "زراعة الروح", "Steampunk": "بخار بنك", "Cyberpunk": "سايبربانك",

    # Profession / Setting
    "Cooking": "طبخ", "Gourmet": "طعام فاخر", "Medical": "طبي", "Police": "شرطة",
    "Detective": "تحري", "Workplace": "مكان عمل", "Showbiz": "استعراض",
    "Otaku Culture": "ثقافة الأوتاكو", "Visual Arts": "فنون بصرية", "Performances": "عروض",
    "Idols (Female)": "آيدول (إناث)", "Idols (Male)": "آيدول (ذكور)",

    # Relationships / Gender
    "Love Polygon": "مثلث حب", "Reverse Harem": "حريم معكوس", "Boys Love": "بويز لاڤ",
    "Girls Love": "غيرلز لاڤ", "Yuri": "يوري", "Yaoi": "ياوي", "Gender Bender": "تبديل جنسي",
    "Romantic Subtext": "رومانسية ضمنية", "Adult Cast": "شخصيات بالغة",

    # Unique tropes
    "Mahou Shoujo": "فتاة ساحرة", "CGDCT": "فتيات لطيفات تفعل أشياء لطيفة",
    "Childcare": "رعاية أطفال", "Delinquents": "مشاغبون", "Organized Crime": "جريمة منظمة",
    "Yakuza": "ياكوزا", "High Stakes Game": "لعبة عالية المخاطر", "Strategy Game": "لعبة استراتيجية",
    "Video Game": "لعبة فيديو", "Time Travel": "سفر عبر الزمن", "Reincarnation": "تقمص",
    "Anthropomorphic": "مجسم", "Pets": "حيوانات أليفة",

    # Mature / Niche
    "Erotica": "إثارة جنسية", "Avant Garde": "طليعي", "Political": "سياسي",

    # Other
    "Educational": "تعليمي",
}


# ── Progress ──────────────────────────────────────────────────────────
def load_progress() -> set:
    if PROGRESS_FILE.exists():
        return set(PROGRESS_FILE.read_text(encoding="utf-8").splitlines())
    return set()

def save_progress(content_id: str):
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(content_id + "\n")


# ── Title cleaning ────────────────────────────────────────────────────
def extract_season_number(title: str) -> Optional[int]:
    """
    Extract season number from title.
    Supports:
      - Arabic: "الموسم 2", "الموسم الثاني"
      - English: "season 2", "S2", "2nd season", "3rd season", "second season"
    Returns None if no season info found.
    """
    # 1. Arabic "الموسم" followed by a digit
    m = re.search(r'الموسم\s+(\d+)', title)
    if m:
        return int(m.group(1))

    # 2. Arabic ordinal word (e.g., "الموسم الثاني")
    m = re.search(r'الموسم\s+([\u0600-\u06FF\s]+?)(?:\s|$)', title)
    if m:
        word = m.group(1).strip()
        for k, v in SEASON_MAP.items():
            if k in word:
                return v

    # 3. English "2nd season", "3rd season", "4th season" (with st/nd/rd/th)
    m = re.search(r'(?i)(\d+)(?:st|nd|rd|th)\s+season', title)
    if m:
        return int(m.group(1))

    # 4. English "season 2"
    m = re.search(r'(?i)season\s+(\d+)', title)
    if m:
        return int(m.group(1))

    # 5. English "S2"
    m = re.search(r'(?i)s(\d+)', title)
    if m:
        return int(m.group(1))

    # 6. English full ordinal word + "season" (e.g., "second season")
    m = re.search(r'(?i)\b(' + '|'.join(SEASON_MAP.keys()) + r')\s+season\b', title)
    if m:
        word = m.group(1).lower()
        return SEASON_MAP.get(word)

    return None


def clean_title_for_search(title: str) -> str:
    """Strip Arabic anime prefix and season suffix, keep Latin title."""
    title = re.sub(r'^[أا]نمي\s*', '', title.strip())
    title = re.sub(r'\s*[-–]\s*الموسم.*$', '', title)
    title = re.sub(r'\s+الموسم.*$', '', title)
    # Also remove English season suffixes (so they don't pollute search)
    title = re.sub(r'(?i)\s+season\s+\d+', '', title)
    title = re.sub(r'(?i)\s+s\d+', '', title)
    title = re.sub(r'(?i)\s+\d+(?:st|nd|rd|th)\s+season', '', title)
    title = re.sub(r'(?i)\s+\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+season\b', '', title)
    title = re.sub(r'[\u0600-\u06FF]+', '', title)
    title = re.sub(r'[\s\-–:]+$', '', title)
    title = ' '.join(title.split())
    return title.strip()


# ── MAL API helpers ───────────────────────────────────────────────────
def mal_search(query: str, limit: int = 5) -> list:
    """Search MAL for anime by title. Returns list of results."""
    try:
        resp = requests.get(
            f"{MAL_BASE}/anime",
            headers=HEADERS,
            params={
                "q": query,
                "limit": limit,
                "fields": "id,title,alternative_titles,num_episodes,start_date,mean,num_scoring_users,status,genres,studios,rank,popularity,media_type,related_anime,average_episode_duration,num_list_users"
            },
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception as e:
        print(f"  [MAL] Search error: {e}")
    return []


def mal_get(mal_id: int) -> Optional[dict]:
    """Fetch full MAL entry by ID."""
    try:
        resp = requests.get(
            f"{MAL_BASE}/anime/{mal_id}",
            headers=HEADERS,
            params={
                "fields": "id,title,alternative_titles,num_episodes,start_date,mean,num_scoring_users,status,genres,studios,rank,popularity,media_type,related_anime,average_episode_duration,start_season"
            },
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"  [MAL] Fetch error for {mal_id}: {e}")
    return None


def title_similarity(a: str, b: str) -> float:
    """Simple token overlap similarity between two strings."""
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))


def find_first_season(entry: dict) -> dict:
    """
    Follow prequels until the first season (no prequel). Returns the first season entry.
    If traversal fails, returns the original entry.
    """
    current = entry
    while True:
        prequels = [
            r for r in current.get("related_anime", [])
            if r.get("relation_type") == "prequel"
        ]
        if not prequels:
            return current
        prev_id = prequels[0]["node"]["id"]
        time.sleep(DELAY)
        current = mal_get(prev_id)
        if not current:
            return entry  # fallback to original


def find_season_in_chain(base_result: dict, target_season: int) -> Optional[dict]:
    """
    Go back to the first season, then move forward to the target season.
    Returns the entry for the target season, or None if traversal fails.
    """
    if target_season <= 1:
        # Even for season 1, we return the first season (which may be the base or earlier)
        first = find_first_season(base_result)
        return first

    # Find the first season in the chain
    first = find_first_season(base_result)

    # Now move forward from the first season
    current = first
    for step in range(1, target_season):
        sequels = [
            r for r in current.get("related_anime", [])
            if r.get("relation_type") == "sequel"
        ]
        if not sequels:
            return None
        next_id = sequels[0]["node"]["id"]
        time.sleep(DELAY)
        current = mal_get(next_id)
        if not current:
            return None
    return current


def find_mal_match(clean_title: str, season: int) -> Optional[dict]:
    """
    Search MAL and return the best matching entry for the given season.
    Returns None if no confident match found.
    """
    results = mal_search(clean_title)
    if not results:
        return None

    # Find best title match from search results
    best = None
    best_score = 0.0
    for r in results:
        node = r["node"]
        titles_to_check = [node.get("title", "")]
        alt = node.get("alternative_titles", {})
        if alt.get("en"):
            titles_to_check.append(alt["en"])
        for syn in alt.get("synonyms", []):
            titles_to_check.append(syn)

        for t in titles_to_check:
            # Normalize: remove punctuation, lowercase, strip trailing TV/year metadata
            def normalize(s):
                s = re.sub(r',?\s*TV\s*\d{4}', '', s)
                s = re.sub(r'[^\w\s]', '', s.lower())
                return s
            clean_query = normalize(clean_title)
            clean_candidate = normalize(t)

            # Token overlap score
            q_tokens = set(clean_query.split())
            c_tokens = set(clean_candidate.split())
            if not q_tokens or not c_tokens:
                sim = 0.0
            else:
                sim = len(q_tokens & c_tokens) / max(len(q_tokens), len(c_tokens))

            # Boost for English alternative title that appears in the local title
            alt_en = alt.get("en", "")
            if alt_en and alt_en.lower() in clean_title.lower() and sim >= 0.3:
                sim = min(sim + 0.4, 1.0)   # boost, cap at 1.0

            if sim > best_score:
                best_score = sim
                best = node

    if best_score < MATCH_THRESHOLD:
        print(f"  [MAL] No confident match for '{clean_title}' (best={best_score:.2f})")
        return None

    print(f"  [MAL] Matched '{best.get('title')}' (sim={best_score:.2f})")

    # Fetch full details for the matched entry
    time.sleep(DELAY)
    full_base = mal_get(best["id"])
    if not full_base:
        return None

    # Use the chain to get the correct seasonal entry
    seasonal = find_season_in_chain(full_base, season)
    if seasonal:
        print(f"  [MAL] Found season {season} entry: '{seasonal.get('title')}'")
    else:
        print(f"  [MAL] Could not traverse to season {season}, using base entry")
        seasonal = full_base

    return seasonal


# ── Format helpers ────────────────────────────────────────────────────
def format_episode_duration(seconds: Optional[int]) -> Optional[str]:
    """Convert seconds to Arabic duration string: '24 دقيقة'"""
    if not seconds or seconds <= 0:
        return None
    minutes = round(seconds / 60)
    if minutes <= 0:
        return None
    return f"{minutes} دقيقة"


def format_release_date(start_date: Optional[str]) -> Optional[str]:
    """Return YYYY or YYYY-MM-DD from MAL start_date string."""
    if not start_date:
        return None
    # MAL returns YYYY-MM-DD or YYYY-MM or YYYY
    parts = start_date.split("-")
    if len(parts) >= 3:
        return start_date  # full date
    if len(parts) == 1:
        return parts[0]  # just year
    return start_date


def extract_year(start_date: Optional[str]) -> Optional[str]:
    if not start_date:
        return None
    return start_date[:4]


# ── Main processing ───────────────────────────────────────────────────
def process_file(file_path: Path, processed: set, force: bool, ids_filter: Optional[list]):
    print(f"\n{'='*60}")
    print(f"🎌 Processing {file_path.name}")
    print(f"{'='*60}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ERROR: Cannot load {file_path}: {e}")
        return

    if not isinstance(data, dict):
        print("  WARNING: Not a dict, skipping.")
        return

    ratings_dir = RATINGS_DIR / "anime"
    ratings_dir.mkdir(parents=True, exist_ok=True)

    modified = False
    items = list(data.items())
    if ids_filter:
        items = [(k, v) for k, v in items if k in ids_filter]

    for content_id, item in items:
        if not isinstance(item, dict):
            continue

        progress_key = f"{file_path.name}|{content_id}"
        if not force and progress_key in processed:
            continue

        title = item.get("Title", "")
        if not title:
            save_progress(progress_key)
            continue

        rating_file = ratings_dir / f"{content_id}.json"

        # Load existing rating data
        existing_rating_data = {}
        if rating_file.exists():
            try:
                existing_rating_data = json.loads(rating_file.read_text(encoding="utf-8"))
            except:
                pass

        # Skip if already has mal_id and not forcing
        if not force and existing_rating_data.get("mal_id"):
            print(f"  SKIP {content_id}: already has mal_id={existing_rating_data['mal_id']}")
            save_progress(progress_key)
            continue

        clean = clean_title_for_search(title)
        if not clean:
            print(f"  SKIP {content_id}: no Latin title to search")
            save_progress(progress_key)
            continue

        season = extract_season_number(title)
        if season is None:
            season = 1
        print(f"\n  [{content_id}] '{clean}' (season {season})")

        time.sleep(DELAY)
        mal_entry = find_mal_match(clean, season)

        if not mal_entry:
            print(f"  SKIP {content_id}: no MAL match")
            save_progress(progress_key)
            continue

        # ── Update main JSON fields (preserve ReleaseDate) ──────────────────
        num_eps = mal_entry.get("num_episodes")
        if num_eps and num_eps > 0:
            item["Number Of Episodes"] = num_eps
            item["Number Of Episodes Text"] = num_eps

        ep_duration_sec = mal_entry.get("average_episode_duration")
        ep_duration_str = format_episode_duration(ep_duration_sec)
        if ep_duration_str:
            item["EpisodeDuration"] = ep_duration_str
            # Runtime as integer minutes for movies
            item["Runtime"] = round(ep_duration_sec / 60) if ep_duration_sec else item.get("Runtime")

        # ── AiringSeason from MAL start_season (e.g., "spring 2017") ─────────
        start_season_obj = mal_entry.get("start_season", {})
        season_name = start_season_obj.get("season", "")   # "spring", "summer", etc.
        season_year = start_season_obj.get("year", "")     # 2017
        if season_name and season_year:
            item["AiringSeason"] = f"{season_name} {season_year}"
        elif season_year:
            item["AiringSeason"] = str(season_year)
        # If no season info, leave the field out (do not overwrite existing)

        # Country — real anime is always Japan
        item["Country"] = "Japan"

        # Status
        mal_status = mal_entry.get("status")
        if mal_status and mal_status in STATUS_AR:
            item["Status"] = STATUS_AR[mal_status]

        # Genres — MAL genres are clean English
        mal_genres = [g["name"] for g in mal_entry.get("genres", []) if "name" in g]
        if mal_genres:
            item["Genres"] = mal_genres
            item["GenresAr"] = [GENRE_AR.get(g, g) for g in mal_genres]

        modified = True

        # ── Update / write rating file (same as before) ──────────────────────
        mal_score = mal_entry.get("mean")
        mal_votes = mal_entry.get("num_scoring_users", 0)
        mal_id    = mal_entry.get("id")
        alt       = mal_entry.get("alternative_titles", {})
        # SAFETY CHECK: studios may be missing or not a list of dicts
        studios = []
        for s in mal_entry.get("studios", []):
            if isinstance(s, dict) and "name" in s:
                studios.append(s["name"])
            elif isinstance(s, str):
                studios.append(s)

        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": extract_year(mal_entry.get("start_date")) or item.get("ReleaseDate", "")[:4],
            "rating": str(mal_score) if mal_score else existing_rating_data.get("rating"),
            "votes": mal_votes or existing_rating_data.get("votes", 0),
            "source": "mal",
            "mal_id": mal_id,
            "mal_rank": mal_entry.get("rank"),
            "mal_popularity": mal_entry.get("popularity"),
            "mal_studios": studios,
            "mal_title_en": alt.get("en") or "",
            "mal_title_jp": alt.get("ja") or "",
            "mal_season": f"{season_name} {season_year}".strip() if season_name or season_year else "",
            "mal_year": extract_year(mal_entry.get("start_date")),
            # Preserve existing imdb_id if present
            "imdb_id": existing_rating_data.get("imdb_id"),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        rating_file.write_text(
            json.dumps(rating_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  ✅ {content_id}: mal_id={mal_id}, score={mal_score}, eps={num_eps}")
        save_progress(progress_key)

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\n  💾 Saved {file_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Enrich anime with MAL metadata")
    parser.add_argument("--category", type=str, choices=list(ANIME_FILES.keys()),
                        help="Process only one file")
    parser.add_argument("--ids", nargs="+",
                        help="Space-separated content IDs to process")
    parser.add_argument("--force", action="store_true",
                        help="Re-process already matched items")
    args = parser.parse_args()

    processed = load_progress()

    for filename in ANIME_FILES:
        if args.category and filename != args.category:
            continue
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            print(f"WARNING: {filename} not found, skipping.")
            continue
        process_file(file_path, processed, args.force, args.ids)

    print("\n🏁 Done.")


if __name__ == "__main__":
    main()