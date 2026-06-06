import requests
import time
from datetime import datetime

API_URL = "https://ogkushhh-abdobest.hf.space/health"
INTERVAL_MINUTES = 4  # Ping every 4 minutes

def ping():
    try:
        start = time.time()
        response = requests.get(API_URL, timeout=10)
        latency = int((time.time() - start) * 1000)
        print(f"[{datetime.now().isoformat()}] ✅ {response.status_code} ({latency}ms)")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ {str(e)}")

if __name__ == "__main__":
    print(f"🔄 Keep‑alive started. Pinging {API_URL} every {INTERVAL_MINUTES} minutes.")
    while True:
        ping()
        time.sleep(INTERVAL_MINUTES * 60)