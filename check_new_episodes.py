#!/usr/bin/env python3
"""
check_new_episodes.py – Fast episode-drop detector using live feeds.
(Updated for Fasel HTML change, Akwam kept)
"""

import argparse
import json
import re
import random
import subprocess
import sys
import time
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from Common import (
    DEBUG, FASEL_BASE_URL, AKWAM_BASE_URL,
    REQUEST_DELAY, JITTER,
    get_website_safe, get_paginated_url,
)

OUTPUT_DIR   = Path("./output")
EPISODES_DIR = OUTPUT_DIR / "episodes"

# ─────────────────────────────────────────────────────────────────────────────
# Fasel feeds (updated selector)
# ─────────────────────────────────────────────────────────────────────────────
FASEL_FEEDS = [
    (FASEL_BASE_URL.rstrip("/") + "/episodes",      "episodes",           ["series", "tvshows"]),
    (FASEL_BASE_URL.rstrip("/") + "/tvepisodes",    "tvepisodes",         ["tvshows"]),
    (FASEL_BASE_URL.rstrip("/") + "/anime-episodes","anime-episodes",     ["anime"]),
    (FASEL_BASE_URL.rstrip("/") + "/asian-episodes","asian-episodes",     ["asian-series"]),
]

AKWAM_RECENT_URL = AKWAM_BASE_URL.rstrip("/") + "/recent"

# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def stored_max_fasel(category: str, series_id: str, season: int) -> int:
    ep_file = EPISODES_DIR / category / f"{series_id}.json"
    if not ep_file.exists():
        return 0
    data = _load_json(ep_file)
    if not data:
        return 0
    seasons = data.get("seasons", {})
    season_data = seasons.get(str(season)) or seasons.get(season)
    if not season_data:
        return 0
    episodes = season_data.get("episodes", []) if isinstance(season_data, dict) else season_data
    if not episodes:
        return 0
    numbers = []
    for ep in episodes:
        url = ep.get("url", ep) if isinstance(ep, dict) else ep
        m = re.search(r'/episode-?(\d+)', str(url))
        if m:
            numbers.append(int(m.group(1)))
        elif isinstance(ep, dict) and ep.get("number") is not None:
            numbers.append(int(ep["number"]))
    return max(numbers) if numbers else len(episodes)

def stored_max_akwam(series_id: str) -> int:
    ep_file = EPISODES_DIR / "arabic-series" / f"{series_id}.json"
    if not ep_file.exists():
        return 0
    data = _load_json(ep_file)
    episodes = data.get("episodes", [])
    if not episodes:
        return 0
    numbers = [int(ep["number"]) for ep in episodes if isinstance(ep, dict) and ep.get("number") is not None]
    return max(numbers) if numbers else len(episodes)

def id_in_category_json(category: str, series_id: str) -> bool:
    return series_id in _load_json(OUTPUT_DIR / f"{category}.json")

# ─────────────────────────────────────────────────────────────────────────────
# Fasel feed scanner (FIXED)
# ─────────────────────────────────────────────────────────────────────────────
def scan_fasel_feed(feed_url: str, candidates: list, pages: int) -> dict:
    seen = {}
    for page in range(1, pages + 1):
        url = get_paginated_url(feed_url, page)
        resp = get_website_safe(url)
        if not resp:
            print(f"    ⚠️  {url} – fetch failed")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("#postList .postDiv") or soup.select(".postDiv")
        if not cards:
            print(f"    ⚠️  No cards found at {url}")
            continue
        print(f"    📄 Page {page}: {len(cards)} cards")
        for card in cards:
            link = card.find("a", href=True)
            if not link:
                continue
            ep_url = link["href"]
            m = re.search(r'/(?:episodes|anime-episodes|asian-episodes|tvepisodes)/(\d+)/season-(\d+)/episode-(\d+)', ep_url)
            if not m:
                m = re.search(r'/(?:episodes|anime-episodes|asian-episodes|tvepisodes)/(\d+)', ep_url)
                if m:
                    series_id = m.group(1)
                    season = 1
                    ep_num = 0
                else:
                    continue
            else:
                series_id, season, ep_num = m.groups()
                season = int(season)
                ep_num = int(ep_num)

            title_elem = card.select_one(".h1") or card.select_one(".entry-title")
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # DEBUG: print what we found
            print(f"      → {series_id} S{season} ep{ep_num}  ({title[:50]})")

            key = f"{series_id}|{season}"
            existing = seen.get(key)
            if not existing or ep_num > existing["live_ep"]:
                seen[key] = {
                    "id": series_id,
                    "season": season,
                    "live_ep": ep_num,
                    "candidates": candidates,
                    "title": title,
                }
        if page < pages:
            time.sleep(max(0.5, REQUEST_DELAY + random.uniform(-JITTER, JITTER)))
    return seen

def diff_fasel(seen: dict) -> list:
    changed = []
    for key, info in seen.items():
        series_id = info["id"]
        season = info["season"]
        live_ep = info["live_ep"]
        candidates = info["candidates"]
        resolved = candidates[0]
        if len(candidates) > 1:
            for cat in candidates:
                if id_in_category_json(cat, series_id):
                    resolved = cat
                    break
        stored = stored_max_fasel(resolved, series_id, season)
        if live_ep > stored:
            changed.append({
                "id": series_id,
                "category": resolved,
                "season": season,
                "live_ep": live_ep,
                "stored": stored,
                "reason": "new_episode" if stored > 0 else "not_yet_stored",
                "title": info["title"],
                "source": "fasel",
            })
    return changed

# ─────────────────────────────────────────────────────────────────────────────
# Akwam /recent scanner (unchanged, but keep as is)
# ─────────────────────────────────────────────────────────────────────────────
def scan_akwam_feed(pages: int) -> list:
    stored_series = _load_json(OUTPUT_DIR / "arabic-series.json")
    seen = {}
    for page in range(1, pages + 1):
        url = get_paginated_url(AKWAM_RECENT_URL, page)
        resp = get_website_safe(url)
        if not resp:
            print(f"    ⚠️  {url} – fetch failed")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        cards_raw = soup.select(".entry-box") or soup.select(".col-lg-auto.col-md-4.col-6")
        print(f"    📄 Page {page}: {len(cards_raw)} cards")
        for card in cards_raw:
            series_link = card.select_one("a[href*='/series/']")
            ep_link = card.select_one("a[href*='/episode/']")
            if not series_link and not ep_link:
                continue
            series_id = None
            if series_link:
                href = series_link.get("href", "")
                m = re.search(r'/series/([^/]+)', href)
                if m:
                    series_id = m.group(1).strip("/")
            ep_num = 0
            if ep_link:
                href = ep_link.get("href", "")
                # Better regex: match -ep-15 or -episode-15 or -الحلقة-15
                m = re.search(r'(?:ep|episode)[^\d]*(\d+)', href, re.IGNORECASE)
                if not m:
                    m = re.search(r'(?:الحلقة)[^\d]*(\d+)', href)
                if m:
                    ep_num = int(m.group(1))
            title_tag = card.select_one(".entry-title") or card.select_one("h3,h4")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if series_id:
                prev = seen.get(series_id, {})
                if ep_num > prev.get("live_ep", 0):
                    seen[series_id] = {"live_ep": ep_num, "title": title}
        if page < pages:
            time.sleep(max(0.5, REQUEST_DELAY + random.uniform(-JITTER, JITTER)))
    changed = []
    for series_id, info in seen.items():
        live_ep = info["live_ep"]
        stored_ep = stored_max_akwam(series_id)
        if stored_ep == 0:
            stored_ep = int((stored_series.get(series_id) or {}).get("episode_count", 0) or 0)
        if live_ep > stored_ep:
            changed.append({
                "id": series_id,
                "category": "arabic-series",
                "season": 1,
                "live_ep": live_ep,
                "stored": stored_ep,
                "reason": "new_episode" if series_id in stored_series else "not_yet_stored",
                "title": info["title"],
                "source": "akwam",
            })
    return changed

# ─────────────────────────────────────────────────────────────────────────────
# Main (with optional --skip-akwam)
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fast episode-drop detector via live feeds")
    parser.add_argument("--pages", type=int, default=7, help="Pages to scan per feed (default 7)")
    parser.add_argument("--fasel-only", action="store_true")
    parser.add_argument("--akwam-only", action="store_true")
    parser.add_argument("--out", type=str, default="./output/changed_episodes.txt",
                        help="Write changed IDs to file (default: ./output/changed_episodes.txt)")
    parser.add_argument("--no-update", action="store_true", help="Detect only — do NOT run update_specific_episodes.py")
    args = parser.parse_args()

    all_changed = []

    if not args.akwam_only:
        for feed_url, segment, candidates in FASEL_FEEDS:
            label = feed_url.split("/")[-1]
            print(f"\n📡 Fasel /{label}  (candidates: {candidates})")
            seen = scan_fasel_feed(feed_url, candidates, args.pages)
            all_changed.extend(diff_fasel(seen))

    if not args.fasel_only:
        print(f"\n📡 Akwam /recent")
        all_changed.extend(scan_akwam_feed(args.pages))

    # Deduplicate
    seen_keys = set()
    deduped = []
    for item in all_changed:
        key = f"{item['source']}:{item['category']}:{item['id']}"
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(item)
    all_changed = deduped

    print(f"\n{'='*68}")
    if not all_changed:
        print("✅ No new episodes detected.")
        return

    print(f"🎯 {len(all_changed)} series with new/missing episodes:\n")
    update_ids = []
    for item in all_changed:
        prefixed = f"{item['category']}:{item['id']}"
        update_ids.append(prefixed)
        title_str = f"  ({item['title'][:30]})" if item["title"] else ""
        print(f"  [{item['source']:5}]  {prefixed:42s}  S{item['season']:02d}  stored={item['stored']:>4}  live≥{item['live_ep']:<4}  {item['reason']}{title_str}")

    ids_joined = " ".join(update_ids)
    print(f"\n📋 Update command:\n  python update_specific_episodes.py --ids {ids_joined}\n")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(update_ids) + "\n", encoding="utf-8")
    print(f"💾 Changed IDs saved to {out_path}")

    if not args.no_update:
        print(f"\n🚀 Launching update_specific_episodes.py for {len(update_ids)} series ...")
        cmd = [sys.executable, "update_specific_episodes.py", "--file", str(out_path)]
        sys.exit(subprocess.run(cmd).returncode)
    else:
        print(f"   Run: python update_specific_episodes.py --file {out_path}")

if __name__ == "__main__":
    main()