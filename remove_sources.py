#!/usr/bin/env python3
"""
remove_sources.py — strips the 'Sources' field from all movie JSON files.
"""

import json
from pathlib import Path

FILES = [
    "movies.json",
    "dubbed-movies.json",
    "hindi.json",
    "asian-movies.json",
    "anime-movies.json",
]

for filename in FILES:
    path = Path("./output") / filename
    if not path.exists():
        print(f"⚠️  Not found, skipping: {path}")
        continue

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    removed = sum(1 for item in data.values() if "Sources" in item)
    for item in data.values():
        item.pop("Sources", None)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"✅ {filename}: removed Sources from {removed} items")

print("\nDone.")
