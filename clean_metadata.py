import json
import os
import shutil
import re
import logging
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Files to clean (all metadata JSONs produced by scrapers)
FILES_TO_CLEAN = [
    "movies.json",
    "dubbed-movies.json",
    "hindi.json",
    "asian-movies.json",
    "anime-movies.json",
    "anime.json",
    "series.json",
    "tvshows.json",
    "asian-series.json"
]

# Only FaselHD files get year backfill — Akwam files use "year" (lowercase)
# and are already populated. Do NOT include arabic-movies.json / arabic-series.json.
FASEL_FILES = FILES_TO_CLEAN  # currently all FILES_TO_CLEAN are FaselHD

# Files eligible for ratings-based year backfill
SERIES_FILES = [
    "series.json",
    "tvshows.json",
    "asian-series.json",
    "anime.json",
]

# Files that have MAL rating data with mal_season
ANIME_FILES = [
    "anime.json",
    "anime-movies.json",
]

# Year extraction bounds.
# Lower bound: 1920 covers silent-era classics that FaselHD occasionally carries.
# Upper bound: hard-cap at MAX_YEAR_CAP to block sci-fi plot years in titles
#              like "2049", "2077", "2150" etc.
YEAR_LOWER = 1920
MAX_YEAR_CAP = datetime.now().year + 2   # e.g. 2028 as of 2026

# Country normalisation
COUNTRY_REPLACEMENTS = {
    "Also known as": "International",
    "United States": "USA",
    "United Kingdom": "UK",
    "U.S.": "USA",
    "U.K.": "UK",
    "N/A": None,
    "": None,
}

# English → Arabic genre map (used only if TRANSLATE_MISSING = True)
EN_TO_AR_GENRE = {
    "Action": "أكشن",
    "Comedy": "كوميدي",
    "Drama": "دراما",
    "Horror": "رعب",
    "Thriller": "إثارة",
    "Adventure": "مغامرة",
    "Crime": "جريمة",
    "Romance": "رومانسية",
    "Science Fiction": "خيال علمي",
    "Fantasy": "فانتازيا",
    "Animation": "أنميشن",
    "Documentary": "وثائقي",
    "Biography": "سيرة ذاتية",
    "History": "تاريخي",
    "Music": "موسيقى",
    "Family": "عائلي",
    "Mystery": "غموض",
    "War": "حرب",
    "Western": "غربي",
    "Sport": "رياضي",
    "Reality-TV": "تلفزيون الواقع",
    "News": "أخبار",
    "Talk-Show": "برامج حوارية",
    "Game-Show": "برامج مسابقات",
    "Musical": "موسيقي",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def backup_file(file_path: str) -> None:
    """Create a backup copy in ./baks/ folder before modifying."""
    if not os.path.exists(file_path):
        return
    baks_dir = Path("./baks")
    baks_dir.mkdir(exist_ok=True)
    filename = os.path.basename(file_path)
    backup_path = baks_dir / f"{filename}.bak"
    shutil.copy2(file_path, backup_path)
    logging.info(f"Backup created: {backup_path}")

def clean_genre_string(genre: str) -> str:
    """Replace hyphens with spaces in a single genre string."""
    return genre.replace("-", " ")

def clean_genre_list(genres: list) -> list:
    """Apply hyphen→space replacement to each genre in the list."""
    if not genres:
        return genres
    return [clean_genre_string(g) for g in genres]

def clean_country(country: str) -> Optional[str]:
    """Normalise country name; return None for invalid."""
    if not country or country == "N/A":
        return None
    return COUNTRY_REPLACEMENTS.get(country, country)

def clean_runtime(runtime):
    """Ensure runtime is int or None."""
    if runtime is None:
        return None
    if isinstance(runtime, int):
        return runtime
    if isinstance(runtime, str):
        cleaned = re.sub(r'[^0-9]', '', runtime)
        if cleaned.isdigit():
            return int(cleaned)
    return None

def clean_release_date(date_str: str) -> str:
    """
    Normalise release date string.
    Converts "20242025" -> "2024-2025"
    Converts "2024 2025" -> "2024-2025"
    Also if the string is a single 4‑digit year outside realistic range, return empty string.
    """
    if not isinstance(date_str, str):
        return date_str
    # Handle concatenated years: 20242025 -> 2024-2025
    match = re.fullmatch(r'^(\d{4})(\d{4})$', date_str.strip())
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    # Handle years separated by whitespace or non-digit
    match = re.search(r'(\d{4})\s*[^\d]?\s*(\d{4})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    # If it's a single 4-digit year, validate it
    match = re.fullmatch(r'^\s*(\d{4})\s*$', date_str)
    if match:
        year = int(match.group(1))
        current_year = datetime.now().year
        if not (1900 <= year <= current_year + 4):
            return ""  # remove unrealistic year
    return date_str

def translate_missing_arabic_genres(data: dict) -> bool:
    """
    If GenresAr is empty or identical to Genres (English), replace GenresAr
    with translated Arabic using the map. Returns True if changed.
    """
    genres_en = data.get("Genres", [])
    genres_ar = data.get("GenresAr", [])
    if not genres_ar or genres_ar == genres_en:
        translated = [EN_TO_AR_GENRE.get(g, g) for g in genres_en]
        data["GenresAr"] = translated
        return True
    return False


# ─── Year backfill ────────────────────────────────────────────────────────────

def extract_year_from_title(title: str) -> Optional[str]:
    """
    Find the best candidate release year embedded in a movie/series title.

    Strategy:
      1. First try to fix common scraper typos — 5-digit runs that are a valid
         4-digit year with one extra digit (e.g. "20223" → 2022 or 2023).
      2. Also match years that are glued directly to surrounding text with no
         space (e.g. "Yara2021", "Live or Let Die2020").
      3. Collect all 4-digit candidates, keep only those in [YEAR_LOWER, MAX_YEAR_CAP].
      4. Return the LAST (rightmost) valid match — appended years are almost
         always the release year, e.g. "Dune Part Two 2024".
      5. Return None if nothing valid found.

    Examples:
        "Dune Part Two 2024"            → "2024"
        "مسلسل الاختيار 2022"           → "2022"
        "Batman v Superman 2016"        → "2016"
        "Yara2021"                      → "2021"  (glued, no space)
        "Live or Let Die2020"           → "2020"  (glued, no space)
        "Little Dixie 20223"            → "2022"  (5-digit typo, first 4 valid)
        "She Done Him Wrong 1933"       → "1933"  (YEAR_LOWER now 1920)
        "Blade Runner 2049"             → None    (2049 > MAX_YEAR_CAP)
        "فيلم روبوكوب 2077"             → None    (2077 > cap)
        "2001: A Space Odyssey"         → "2001"
    """
    if not title or not isinstance(title, str):
        return None

    candidates = []

    # ── Pass 1: standard isolated 4-digit years (word-boundary or non-digit fence)
    for m in re.finditer(r'(?<!\d)(\d{4})(?!\d)', title):
        y = int(m.group(1))
        if YEAR_LOWER <= y <= MAX_YEAR_CAP:
            candidates.append((m.start(), y))

    # ── Pass 2: 5-digit typos — try both the first 4 and last 4 digits
    # e.g. "20223" → try 2022 and 0223; "20192" → try 2019 and 0192
    for m in re.finditer(r'(?<!\d)(\d{5})(?!\d)', title):
        s = m.group(1)
        for fragment in (s[:4], s[1:]):
            y = int(fragment)
            if YEAR_LOWER <= y <= MAX_YEAR_CAP:
                candidates.append((m.start(), y))
                break  # take only first valid fragment per 5-digit run

    if not candidates:
        return None

    # Sort by position so "last" = rightmost in the string
    candidates.sort(key=lambda x: x[0])
    return str(candidates[-1][1])


def is_release_date_empty(value) -> bool:
    """Return True if ReleaseDate is missing, None, or an empty/whitespace string."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def backfill_year_from_title(
    file_name: str,
    dry_run: bool = True,
    max_preview: int = 30,
) -> dict:
    """
    For every entry in file_name whose ReleaseDate is empty/missing,
    attempt to extract a year from the Title and set ReleaseDate to it.

    Args:
        file_name:   JSON filename inside ./output/ (e.g. "movies.json")
        dry_run:     If True, print what WOULD change but don't write anything.
        max_preview: Max number of sample rows to print in dry-run mode.

    Returns:
        A summary dict with counts.
    """
    file_path = f"./output/{file_name}"
    if not os.path.exists(file_path):
        logging.warning(f"{file_path} not found, skipping backfill.")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total          = len(data)
    already_has    = 0   # already has a non-empty ReleaseDate
    backfilled     = 0   # would be / was filled from title
    no_year_found  = 0   # empty ReleaseDate AND no year in title
    previewed      = 0
    no_year_titles = []  # collect a sample of titles we couldn't fix

    tag = "[DRY RUN] " if dry_run else ""

    print(f"\n{'='*60}")
    print(f"{tag}Year backfill: {file_name}")
    print(f"{'='*60}")
    if dry_run:
        print(f"  Showing up to {max_preview} would-be changes.\n")

    for content_id, content in data.items():
        current_date = content.get("ReleaseDate")

        if not is_release_date_empty(current_date):
            already_has += 1
            continue

        title = content.get("Title", "")
        year  = extract_year_from_title(title)

        if year is None:
            no_year_found += 1
            no_year_titles.append(title)
            continue

        # We have a year to apply
        backfilled += 1

        if dry_run:
            if previewed < max_preview:
                old_display = repr(current_date) if current_date is not None else "missing"
                print(f"  [{content_id}] \"{title}\"")
                print(f"    ReleaseDate: {old_display}  →  \"{year}\"")
                previewed += 1
            elif previewed == max_preview:
                print(f"  ... (further matches omitted, showing first {max_preview})")
                previewed += 1
        else:
            content["ReleaseDate"] = year

    # ── Write changes (live run only) ────────────────────────────────────────
    if not dry_run and backfilled > 0:
        backup_file(file_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  {'[DRY RUN] ' if dry_run else ''}Results for {file_name}")
    print(f"  Total entries      : {total}")
    print(f"  Already have year  : {already_has}  ({already_has*100//total if total else 0}%)")
    print(f"  {'Would backfill' if dry_run else 'Backfilled'} from title : {backfilled}  ({backfilled*100//total if total else 0}%)")
    print(f"  No year found      : {no_year_found}  ({no_year_found*100//total if total else 0}%)")
    if not dry_run and backfilled > 0:
        print(f"  ✅ Saved to {file_path}  (backup in ./baks/)")
    elif dry_run:
        print(f"  ℹ️  No files written (dry run).")

    # Show a sample of titles we couldn't fix so you can spot patterns
    if no_year_titles:
        sample = no_year_titles[:10]
        print(f"\n  Sample titles with NO extractable year ({len(no_year_titles)} total):")
        for t in sample:
            print(f"    • {t}")

    print(f"{'─'*60}\n")

    return {
        "file": file_name,
        "total": total,
        "already_has": already_has,
        "backfilled": backfilled,
        "no_year_found": no_year_found,
    }


# ─── Existing cleaning logic (unchanged) ──────────────────────────────────────

def clean_json_file(file_name: str, translate_missing_ar: bool = False) -> None:
    """Load, clean, and save a JSON file (replace hyphens, normalise country/runtime/release date)."""
    file_path = f"./output/{file_name}"
    if not os.path.exists(file_path):
        logging.warning(f"{file_path} not found, skipping.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in {file_path}: {e}")
        return

    # Backup original to ./baks/
    backup_file(file_path)

    modified = False
    for content_id, content in data.items():
        # Replace hyphens in genres
        if "Genres" in content and isinstance(content["Genres"], list):
            new_genres = clean_genre_list(content["Genres"])
            if new_genres != content["Genres"]:
                content["Genres"] = new_genres
                modified = True
        if "GenresAr" in content and isinstance(content["GenresAr"], list):
            new_ar_genres = clean_genre_list(content["GenresAr"])
            if new_ar_genres != content["GenresAr"]:
                content["GenresAr"] = new_ar_genres
                modified = True

        # Optional: fill missing Arabic genres
        if translate_missing_ar and "Genres" in content:
            if translate_missing_arabic_genres(content):
                modified = True

        # Clean country
        if "Country" in content:
            new_country = clean_country(content["Country"])
            if new_country != content["Country"]:
                content["Country"] = new_country
                modified = True

        # Clean runtime
        if "Runtime" in content:
            new_runtime = clean_runtime(content["Runtime"])
            if new_runtime != content["Runtime"]:
                content["Runtime"] = new_runtime
                modified = True

        # Clean release date
        if "ReleaseDate" in content:
            new_date = clean_release_date(content["ReleaseDate"])
            if new_date != content["ReleaseDate"]:
                content["ReleaseDate"] = new_date
                modified = True

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Cleaned and saved {file_path}")
    else:
        logging.info(f"No changes needed for {file_path}")


# ─── Ratings-based year backfill ──────────────────────────────────────────────

def backfill_year_from_ratings(file_name: str, ratings_dir: Path = Path("./output/ratings")) -> dict:
    """
    For every entry in file_name whose ReleaseDate is empty/missing,
    look up its rating file and copy the 'year' field to ReleaseDate.
    """
    file_path = Path(f"./output/{file_name}")
    if not file_path.exists():
        logging.warning(f"{file_path} not found, skipping.")
        return {}

    category_stem = file_name.replace(".json", "")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total       = len(data)
    backfilled  = 0
    skipped     = 0
    no_rating   = 0

    print("\n" + "="*60)
    print(f"Ratings year backfill: {file_name}")
    print(f"{'='*60}")

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if not is_release_date_empty(item.get("ReleaseDate")):
            skipped += 1
            continue

        # find rating file — anime-movies not included but handle gracefully
        rating_file = ratings_dir / category_stem / f"{content_id}.json"
        if not rating_file.exists():
            no_rating += 1
            continue

        try:
            with open(rating_file, "r", encoding="utf-8") as rf:
                rating_data = json.load(rf)
        except Exception:
            no_rating += 1
            continue

        year = rating_data.get("year") or rating_data.get("mal_year")
        if not year:
            no_rating += 1
            continue

        # validate year
        try:
            y = int(str(year)[:4])
            if not (1900 <= y <= datetime.now().year + 2):
                no_rating += 1
                continue
            year = str(y)
        except (ValueError, TypeError):
            no_rating += 1
            continue

        item["ReleaseDate"] = year
        backfilled += 1
        print(f"  [{content_id}] set ReleaseDate = {year}")

    if backfilled > 0:
        backup_file(str(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"  Total: {total} | Already had year: {skipped} | Backfilled: {backfilled} | No rating: {no_rating}")
    if backfilled > 0:
        print(f"  ✅ Saved {file_path}")

    return {"file": file_name, "total": total, "skipped": skipped, "backfilled": backfilled, "no_rating": no_rating}



# ─── Airing season backfill ───────────────────────────────────────────────────

def backfill_airing_season_from_ratings(file_name: str, ratings_dir: Path = Path("./output/ratings")) -> dict:
    """
    For every anime/anime-movies entry, copy mal_season from its rating file
    to AiringSeason in the main JSON (e.g. "spring 2019" -> "Spring 2019").
    Skips entries that already have AiringSeason set.
    """
    file_path = Path(f"./output/{file_name}")
    if not file_path.exists():
        logging.warning(f"{file_path} not found, skipping.")
        return {}

    category_stem = file_name.replace(".json", "")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total      = len(data)
    backfilled = 0
    skipped    = 0
    no_season  = 0

    print(f"\n{'='*60}")
    print(f"AiringSeason backfill: {file_name}")
    print(f"{'='*60}")

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue

        # Skip if already populated
        if item.get("AiringSeason"):
            skipped += 1
            continue

        rating_file = ratings_dir / category_stem / f"{content_id}.json"
        if not rating_file.exists():
            no_season += 1
            continue

        try:
            with open(rating_file, "r", encoding="utf-8") as rf:
                rating_data = json.load(rf)
        except Exception:
            no_season += 1
            continue

        mal_season = (rating_data.get("mal_season") or "").strip()
        if not mal_season:
            no_season += 1
            continue

        # Capitalize season word: "spring 2019" -> "Spring 2019"
        parts = mal_season.split(None, 1)
        airing_season = f"{parts[0].capitalize()} {parts[1]}" if len(parts) == 2 else mal_season.capitalize()

        item["AiringSeason"] = airing_season
        backfilled += 1
        print(f"  [{content_id}] AiringSeason = {airing_season}")

    if backfilled > 0:
        backup_file(str(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"  Total: {total} | Already set: {skipped} | Backfilled: {backfilled} | No MAL season: {no_season}")
    if backfilled > 0:
        print(f"  ✅ Saved {file_path}")

    return {"file": file_name, "total": total, "skipped": skipped, "backfilled": backfilled, "no_season": no_season}


# ─── Entry points ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clean metadata JSON files produced by the scrapers."
    )
    parser.add_argument(
        "--backfill-year",
        action="store_true",
        help="Extract release year from Title and fill empty ReleaseDate fields.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview year backfill changes without writing any files. "
             "Only meaningful together with --backfill-year.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Limit processing to specific file(s), e.g. --files movies.json anime.json. "
             "Defaults to all FILES_TO_CLEAN.",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=30,
        metavar="N",
        help="Max number of sample changes to print in dry-run mode (default: 30).",
    )
    parser.add_argument(
        "--backfill-from-ratings",
        action="store_true",
        help="For series/anime with empty ReleaseDate, copy year from their ratings file.",
    )
    parser.add_argument(
        "--backfill-airing-season",
        action="store_true",
        help="Copy mal_season from ratings files to AiringSeason field in anime/anime-movies JSON.",
    )
    parser.add_argument(
        "--translate-genres",
        action="store_true",
        help="Fill missing Arabic genre translations (GenresAr).",
    )
    args = parser.parse_args()

    target_files = args.files if args.files else FILES_TO_CLEAN

    # ── Step 1: standard cleaning pass ────────────────────────────────────────
    if not args.backfill_year or not args.dry_run:
        # Always run standard cleaning unless we're in a pure dry-run backfill
        # preview (where the user just wants to see the year changes).
        for file_name in target_files:
            clean_json_file(file_name, translate_missing_ar=args.translate_genres)

    # ── Step 2: year backfill (optional) ──────────────────────────────────────
    if args.backfill_year:
        fasel_targets = [f for f in target_files if f in FASEL_FILES]
        if not fasel_targets:
            print("No FaselHD files in target list — nothing to backfill.")
        else:
            totals = {"total": 0, "already_has": 0, "backfilled": 0, "no_year_found": 0}
            for file_name in fasel_targets:
                summary = backfill_year_from_title(
                    file_name,
                    dry_run=args.dry_run,
                    max_preview=args.preview_limit,
                )
                for k in totals:
                    totals[k] += summary.get(k, 0)

            if len(fasel_targets) > 1:
                print(f"\n{'='*60}")
                print(f"  GRAND TOTAL across {len(fasel_targets)} files")
                print(f"  Total entries      : {totals['total']}")
                print(f"  Already have year  : {totals['already_has']}")
                print(f"  {'Would backfill' if args.dry_run else 'Backfilled'} : {totals['backfilled']}")
                print(f"  No year found      : {totals['no_year_found']}")
                print(f"{'='*60}\n")

    # ── Step 3: year backfill from ratings files ──────────────────────────────
    if args.backfill_from_ratings:
        ratings_dir = Path("./output/ratings")
        series_targets = [f for f in target_files if f in SERIES_FILES]
        if not series_targets:
            print("No series files in target list — nothing to backfill from ratings.")
        else:
            for file_name in series_targets:
                backfill_year_from_ratings(file_name, ratings_dir)

    # ── Step 4: airing season backfill for anime ──────────────────────────────
    if args.backfill_airing_season:
        ratings_dir = Path("./output/ratings")
        anime_targets = [f for f in target_files if f in ANIME_FILES]
        if not anime_targets:
            print("No anime files in target list — nothing to backfill.")
        else:
            for file_name in anime_targets:
                backfill_airing_season_from_ratings(file_name, ratings_dir)

    logging.info("Metadata cleaning complete.")


if __name__ == "__main__":
    main()
