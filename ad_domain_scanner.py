#!/usr/bin/env python3
"""
ad_domain_scanner.py
Discover new ad/tracker domains by scanning one or more URLs with a mobile user agent.
Supports:
  - Single URL: python ad_domain_scanner.py https://example.com
  - Multiple URLs: python ad_domain_scanner.py url1 url2 url3
  - File with URLs (one per line): python ad_domain_scanner.py --file urls.txt

Logs unrecognized domains to 'new_ad_domains.log' (appends) and prints them.
"""

import sys
import os
import argparse
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# ---------- Configuration ----------
# Known ad domains (start with your existing list; you can extend from Common.py if needed)
KNOWN_AD_DOMAINS = {
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com", "clickadu.com"
}

# Mobile user agent (iPhone 12 Pro)
MOBILE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"

# Output log file
LOG_FILE = "new_ad_domains.log"

# ---------- Helper functions ----------
def extract_domain(url: str) -> str:
    """Extract registered domain from a URL (e.g., sub.example.com -> example.com)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

def is_likely_ad(request) -> bool:
    """
    Heuristic to filter normal resources (fonts, CSS, etc.). 
    Returns True if the request is likely an ad/tracker.
    """
    ad_resource_types = ['image', 'media', 'script', 'xmlhttprequest']
    if request.resource_type not in ad_resource_types:
        return False
    url = request.url.lower()
    keywords = ['ads', 'track', 'analytics', 'banner', 'adserver', 'metrics', 'pixel', 'beacon', 'doubleclick']
    for kw in keywords:
        if kw in url:
            return True
    return False

# ---------- Main scanner ----------
def scan_url(target_url: str, discovered_set: set, headless: bool = True):
    """Scan a single URL, update discovered_set with new domains."""
    print(f"[*] Scanning {target_url} with mobile UA...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/playwright_ad_scan",  # temporary, reused across URLs
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 375, "height": 812},
            user_agent=MOBILE_USER_AGENT
        )
        page = context.new_page()
        
        def log_request(route, request):
            domain = extract_domain(request.url)
            if domain and domain not in KNOWN_AD_DOMAINS and is_likely_ad(request):
                if domain not in discovered_set:
                    discovered_set.add(domain)
                    print(f"[!] New potential ad domain: {domain} (from {request.url})")
                    # Append to log file immediately
                    with open(LOG_FILE, "a") as f:
                        f.write(f"{domain}\n")
            route.continue_()
        
        page.route("**/*", log_request)
        
        try:
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)  # extra time for lazy-loaded content
        except Exception as e:
            print(f"  ⚠️ Error loading {target_url}: {e}")
        finally:
            context.close()

# ---------- Main entry ----------
def main():
    parser = argparse.ArgumentParser(description="Scan URLs for ad domains")
    parser.add_argument("urls", nargs="*", help="One or more URLs to scan")
    parser.add_argument("--file", "-f", help="Text file containing URLs (one per line)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default True)")
    args = parser.parse_args()
    
    # Collect all URLs
    url_list = []
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        line = "https://" + line
                    url_list.append(line)
    if args.urls:
        for u in args.urls:
            if not u.startswith("http"):
                u = "https://" + u
            url_list.append(u)
    
    if not url_list:
        print("No URLs provided. Use: python ad_domain_scanner.py --file urls.txt")
        sys.exit(1)
    
    discovered = set()
    for url in url_list:
        scan_url(url, discovered, headless=args.headless)
    
    print(f"\n✅ Scan completed. Found {len(discovered)} new ad domains (logged in {LOG_FILE}).")

if __name__ == "__main__":
    main()