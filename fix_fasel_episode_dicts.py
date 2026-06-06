#!/usr/bin/env python3
"""
fix_fasel_episode_dicts.py – Convert dicts with 'url' to plain string.
Delete any dict without 'url' (e.g., {"sources": [...]}).
Keeps all plain strings.
"""

import json
import argparse
from pathlib import Path

CATEGORIES = ["series", "tvshows", "asian-series", "anime"]
BASE = Path("./output/episodes")

def clean_episodes_list(episodes, dry_run=False, verbose=False):
    """
    Returns new list, and a dict with counts of conversions & deletions.
    """
    new_list = []
    converted = 0
    deleted = 0
    for ep in episodes:
        if isinstance(ep, dict):
            if "url" in ep and ep["url"]:
                # Valid dict: convert to plain URL string
                new_list.append(ep["url"])
                converted += 1
            else:
                # Dict without 'url' (e.g., {"sources": [...]}) -> delete
                deleted += 1
                if verbose and dry_run:
                    print(f"      Would delete dict without url: {ep}")
        else:
            # Already a string or other non-dict – keep as is
            new_list.append(ep)
    return new_list, converted, deleted

def fix_file(file_path: Path, dry_run: bool, verbose: bool) -> bool:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False
    seasons = data.get("seasons", {})

    for season_num, season_val in list(seasons.items()):
        if isinstance(season_val, dict) and "episodes" in season_val:
            old_eps = season_val["episodes"]
            if not isinstance(old_eps, list):
                continue
            new_eps, converted, deleted = clean_episodes_list(old_eps, dry_run, verbose)
            if new_eps != old_eps:
                data["seasons"][season_num]["episodes"] = new_eps
                modified = True
                if verbose and dry_run:
                    print(f"    Season {season_num}: converted {converted}, deleted {deleted}")
        elif isinstance(season_val, list):
            new_eps, converted, deleted = clean_episodes_list(season_val, dry_run, verbose)
            if new_eps != season_val:
                data["seasons"][season_num] = new_eps
                modified = True
                if verbose and dry_run:
                    print(f"    Season {season_num} (plain list): converted {converted}, deleted {deleted}")

    if not modified:
        return False

    if dry_run:
        print(f"🔍 Would fix: {file_path.relative_to(BASE)}")
        return True

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✓ Fixed: {file_path.relative_to(BASE)}")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per‑season details")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY RUN – no changes\n")
    else:
        print("🛠️  FIXING FILES – converting valid dicts, deleting dicts without 'url'\n")

    total_fixed = 0
    for cat in CATEGORIES:
        folder = BASE / cat
        if not folder.exists():
            continue
        json_files = list(folder.glob("*.json"))
        if not json_files:
            continue
        print(f"\n📁 {cat} – {len(json_files)} files")
        for fp in sorted(json_files):
            if fix_file(fp, args.dry_run, args.verbose):
                total_fixed += 1

    if args.dry_run:
        print(f"\n✅ Preview: {total_fixed} file(s) would be fixed.")
        print("   Run without --dry-run to apply changes.")
    else:
        print(f"\n✅ Done: fixed {total_fixed} file(s).")

if __name__ == "__main__":
    main()