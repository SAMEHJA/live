#!/usr/bin/env python3
"""
remove_episode_sources.py — strips the 'Sources' field from every episode
in all episode JSON files (series, tvshows, asian-series, anime).
"""

import json
from pathlib import Path

EPISODES_BASE = Path("./output/episodes")
EPISODE_CATEGORIES = [
    "series",
    "tvshows",
    "asian-series",
    "anime",
]

for category in EPISODE_CATEGORIES:
    cat_dir = EPISODES_BASE / category
    if not cat_dir.exists():
        print(f"⚠️  Directory not found, skipping: {cat_dir}")
        continue

    for ep_file in cat_dir.glob("*.json"):
        try:
            with open(ep_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {ep_file}: {e}")
            continue

        changed = False
        # Handle files with seasons structure
        if "seasons" in data:
            for season_num, season_data in data["seasons"].items():
                episodes = season_data.get("episodes", [])
                for ep in episodes:
                    if isinstance(ep, dict) and "Sources" in ep:
                        del ep["Sources"]
                        changed = True

        # Handle files with a flat episodes list (just in case)
        if "episodes" in data and isinstance(data["episodes"], list):
            for ep in data["episodes"]:
                if isinstance(ep, dict) and "Sources" in ep:
                    del ep["Sources"]
                    changed = True

        if changed:
            with open(ep_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"✅ {ep_file.relative_to(EPISODES_BASE)}: cleaned Sources")
        else:
            print(f"ℹ️  {ep_file.relative_to(EPISODES_BASE)}: no Sources to remove")

print("\nDone.")