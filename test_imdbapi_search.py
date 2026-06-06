#!/usr/bin/env python3
"""
Test IMDbAPI search with strict vs relaxed scoring.
Does not modify any production files.
"""

import sys
from pathlib import Path

# Add current directory to path to import Common
sys.path.insert(0, str(Path(__file__).parent))

# We'll temporarily monkey-patch search_imdbapi_dev to add relaxed parameter
# But since the original doesn't have it, we'll copy the function locally for testing.

import requests
import time

IMDBAPI_BASE_URL = "https://api.imdbapi.dev"
DEBUG_IMDBAPI = True

def search_imdbapi_dev_local(title: str, year=None, max_retries=3, relaxed=False):
    """Local copy of the (to-be) improved function."""
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
                    # Debug: show best score and threshold
                    print(f"  [DEBUG] Best score={best_score}, required={required_score}, match={best_match.get('primaryTitle') if best_match else None}")
                    return (None, 0, None)
            
            elif resp.status_code == 429:
                wait = 5 * (2 ** attempt)
                print(f"  Rate limited, retry after {wait}s")
                time.sleep(wait)
                continue
            elif resp.status_code in (500,502,503,504):
                wait = 2 ** attempt
                print(f"  Server error {resp.status_code}, retry after {wait}s")
                time.sleep(wait)
                continue
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:100]}")
                return (None, 0, None)
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return (None, 0, None)
    return (None, 0, None)

def main():
    test_title = "Yiya Murano: Muerte a la hora del té"
    test_year = "2026"
    
    print(f"Testing title: {test_title} (year={test_year})")
    
    print("\n--- Strict search (score >=5) ---")
    rating, votes, imdb_id = search_imdbapi_dev_local(test_title, test_year, relaxed=False)
    if rating:
        print(f"✅ Found: rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"❌ Not found")
    
    print("\n--- Relaxed search (any best match) ---")
    rating, votes, imdb_id = search_imdbapi_dev_local(test_title, test_year, relaxed=True)
    if rating:
        print(f"✅ Found: rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"❌ Not found")
    
    print("\n--- Control: Search with English title ---")
    english_title = "Yiya Murano: Death at Tea Time"
    rating, votes, imdb_id = search_imdbapi_dev_local(english_title, test_year, relaxed=False)
    if rating:
        print(f"✅ Found: rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"❌ Not found")

if __name__ == "__main__":
    main()