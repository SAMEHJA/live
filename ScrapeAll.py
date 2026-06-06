import os
import subprocess
from time import perf_counter
from datetime import date, datetime

start_time = perf_counter()

os.makedirs("./output", exist_ok=True)

def run_script(script_name, description=""):
    """Run a Python script, return True if success, False if failed."""
    print(f"\n▶️ Running {script_name} ... {description}")
    result = subprocess.run(["python", script_name])
    if result.returncode != 0:
        print(f"❌ {script_name} failed (exit code {result.returncode})")
        with open("./output/failed_scripts.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - {script_name} failed\n")
        return False
    print(f"✅ {script_name} finished successfully")
    return True

print("==========================================")
print("Starting FaselHD scraping pipeline")
print("==========================================")

# ------------------------------------------------------------------
# STEP 1 – Scrape new content (metadata only, no ratings)
# ------------------------------------------------------------------
print("\n[Phase 1] Scraping fresh metadata from FaselHD")
scripts = [
    "FaselMoviesScraper.py",
    "FaselAnimeScraper.py",
    "FaselSeriesScraper.py",
]

failures = []
for script in scripts:
    if not run_script(script):
        failures.append(script)

# ------------------------------------------------------------------
# STEP 2 – Fetch ratings (TMDb primary, OMDb fallback)
# ------------------------------------------------------------------
print("\n[Phase 2] Fetching/updating ratings (TMDb → OMDb)")
if not run_script("update_ratings.py"):
    failures.append("update_ratings.py")

# ------------------------------------------------------------------
# STEP 3 – Update episodes and series status
# ------------------------------------------------------------------
print("\n[Phase 3] Checking for new episodes and updating status")
if not run_script("update_episodes.py"):
    failures.append("update_episodes.py")

# ------------------------------------------------------------------
# STEP 4 – (Optional) Clean metadata (normalise genres, country, runtime)
# ------------------------------------------------------------------
print("\n[Phase 4] Running post‑processing clean (optional)")
if os.path.exists("clean_metadata.py"):
    run_script("clean_metadata.py", "(normalises genres, country, runtime)")
else:
    print("⚠️ clean_metadata.py not found – skipping")

# ------------------------------------------------------------------
# STEP 5 – Build lightweight search index
# ------------------------------------------------------------------
print("\n[Phase 5] Generating all-content.json index")
if os.path.exists("AllContentIndexer.py"):
    run_script("AllContentIndexer.py")
else:
    print("⚠️ AllContentIndexer.py not found – skipping")

# ------------------------------------------------------------------
# (Optional) One‑time backfill – comment out after first run
# ------------------------------------------------------------------
# print("\n[Phase 6] Backfilling missing metadata (one‑time, skip later)")
# if os.path.exists("backfill_metadata.py"):
#     run_script("backfill_metadata.py", "fills missing fields from TMDb")
# else:
#     print("⚠️ backfill_metadata.py not found – skipping")

# ------------------------------------------------------------------
# Finalise
# ------------------------------------------------------------------
end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print("\n" + "="*50)
if failures:
    print(f"⚠️ Some scripts failed: {', '.join(failures)}")
    print(f"Check ./output/failed_scripts.log for details.")
else:
    print("✅ All scripts completed successfully.")
print(f"Total time: {round((end_time - start_time) / 60)} minutes")