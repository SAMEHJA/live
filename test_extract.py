"""
Test script for AbdoBest video extraction.
Run: python test_extract.py

Requirements:
    pip install playwright requests beautifulsoup4
    playwright install chromium
"""

import time
import json

TEST_URL = "https://www.fasel-hd.cam/episodes/%d9%85%d8%b3%d9%84%d8%b3%d9%84-marry-murderer-%d8%a7%d9%84%d9%85%d9%88%d8%b3%d9%85-%d8%a7%d9%84%d8%a3%d9%88%d9%84-%d8%a7%d9%84%d8%ad%d9%84%d9%82%d8%a9-1"  # Change ID to test different content

AD_DOMAINS = [
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com", "clickadu.com"
]


def test_extract(page_url: str, headless: bool = False):
    """
    Full extraction test with detailed diagnostics.
    Set headless=False to watch the browser and see what's happening visually.
    """
    from playwright.sync_api import sync_playwright

    captured_urls = []
    all_network_requests = []

    print(f"\n{'='*60}")
    print(f"Testing URL: {page_url}")
    print(f"Headless: {headless}")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="./chrome_test_profile",
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1280,720"
            ],
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # ── 1. Block ads ──────────────────────────────────────────────
        def block_ads(route, request):
            if any(domain in request.url for domain in AD_DOMAINS):
                route.abort()
                return
            route.continue_()
        page.route("**/*", block_ads)
        page.on("popup", lambda popup: popup.close())

        # ── 2. Intercept ALL network requests (for diagnostics) ───────
        def on_request(request):
            url = request.url
            if any(x in url for x in [".m3u8", ".mp4", ".ts", "stream", "video", "player", "embed"]):
                all_network_requests.append({"url": url, "type": request.resource_type})
                if ".m3u8" in url:
                    print(f"  [NETWORK] m3u8 found: {url}")
                    captured_urls.append(url)

        page.on("request", on_request)

        # ── 3. Load the page ──────────────────────────────────────────
        print("[1] Loading page...")
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"  [ERROR] Page load failed: {e}")
            context.close()
            return

        print("[2] Page loaded. Waiting 2s...")
        time.sleep(2)

        # ── 4. Diagnose iframes ───────────────────────────────────────
        print("\n[3] Checking iframes...")
        iframes_info = page.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            return Array.from(iframes).map(f => ({
                name: f.name,
                id: f.id,
                src: f.src,
                class: f.className
            }));
        }""")

        if iframes_info:
            print(f"  Found {len(iframes_info)} iframe(s):")
            for i, iframe in enumerate(iframes_info):
                print(f"    [{i}] name='{iframe['name']}' id='{iframe['id']}' src='{iframe['src'][:80]}' class='{iframe['class']}'")
        else:
            print("  [WARNING] No iframes found on page!")

        # ── 5. Check for video elements directly on page ──────────────
        print("\n[4] Checking for direct video elements...")
        videos = page.evaluate("""() => {
            const vids = document.querySelectorAll('video');
            return Array.from(vids).map(v => ({
                src: v.src,
                currentSrc: v.currentSrc,
                class: v.className
            }));
        }""")
        if videos:
            print(f"  Found {len(videos)} video element(s):")
            for v in videos:
                print(f"    src='{v['src']}' currentSrc='{v['currentSrc']}'")
        else:
            print("  No direct video elements found")

        # ── 6. Try the original iframe selector ──────────────────────
        print("\n[5] Trying original selector: iframe[name='player_iframe']...")
        iframe_elem = page.query_selector("iframe[name='player_iframe']")
        if iframe_elem:
            print("  [OK] Found player_iframe by name attribute")
            iframe = iframe_elem.content_frame()
        else:
            print("  [FAIL] player_iframe NOT found — trying fallbacks...")

            # Fallback: try by ID
            iframe_elem = page.query_selector("iframe#player_iframe")
            if iframe_elem:
                print("  [OK] Found by id='player_iframe'")
                iframe = iframe_elem.content_frame()
            else:
                # Fallback: first iframe
                iframe_elem = page.query_selector("iframe")
                if iframe_elem:
                    src = iframe_elem.get_attribute("src") or ""
                    print(f"  [FALLBACK] Using first iframe, src='{src[:80]}'")
                    iframe = iframe_elem.content_frame()
                else:
                    iframe = None

        # ── 7. Try clicking play in iframe ────────────────────────────
        if iframe:
            print("\n[6] Iframe found. Checking iframe content...")
            try:
                iframe.wait_for_selector("body", timeout=10000)

                # Check what's inside the iframe
                iframe_buttons = iframe.evaluate("""() => {
                    const btns = document.querySelectorAll('button, .jw-icon, .play, [class*="play"], video');
                    return Array.from(btns).slice(0, 10).map(b => ({
                        tag: b.tagName,
                        class: b.className,
                        id: b.id
                    }));
                }""")
                if iframe_buttons:
                    print(f"  Elements in iframe:")
                    for b in iframe_buttons:
                        print(f"    <{b['tag']}> class='{b['class']}' id='{b['id']}'")

                # Try clicking play
                print("\n[7] Clicking play button (7 attempts)...")
                play_selectors = [
                    ".jw-icon.jw-icon-display.jw-button-color.jw-reset",
                    ".jw-icon-display",
                    "[class*='play']",
                    "video",
                    "body"
                ]
                for attempt in range(7):
                    if captured_urls:
                        break
                    for sel in play_selectors:
                        try:
                            iframe.click(sel, force=True, timeout=2000)
                            print(f"  Attempt {attempt+1}: clicked '{sel}'")
                            break
                        except:
                            continue
                    time.sleep(1.5)
                    for pg in context.pages:
                        if pg != page:
                            pg.close()

            except Exception as e:
                print(f"  [ERROR] Iframe interaction failed: {e}")
        else:
            print("\n[6] No iframe found — trying to click play directly on page...")
            for attempt in range(5):
                if captured_urls:
                    break
                try:
                    page.click(".jw-icon-display", force=True, timeout=2000)
                    print(f"  Attempt {attempt+1}: clicked .jw-icon-display on main page")
                except:
                    try:
                        page.click("video", force=True, timeout=2000)
                        print(f"  Attempt {attempt+1}: clicked video on main page")
                    except:
                        pass
                time.sleep(1.5)

        # ── 8. Wait a bit more for any delayed m3u8 ───────────────────
        print("\n[8] Waiting up to 15s for m3u8 to appear...")
        for i in range(30):
            if captured_urls:
                break
            time.sleep(0.5)

        # ── 9. Print results ──────────────────────────────────────────
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}")

        if captured_urls:
            print(f"[SUCCESS] Captured {len(captured_urls)} m3u8 URL(s):")
            for u in captured_urls:
                print(f"  {u}")
        else:
            print("[FAILED] No m3u8 URL captured")
            print("\nAll video-related network requests seen:")
            if all_network_requests:
                for r in all_network_requests:
                    print(f"  [{r['type']}] {r['url']}")
            else:
                print("  None — the player may not have loaded at all")

        # ── 10. Save page HTML for inspection ────────────────────────
        html = page.content()
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nPage HTML saved to page_dump.html ({len(html)} chars)")
        print("Open it in a browser or search for 'iframe', 'player', 'm3u8' to debug")

        context.close()
        return captured_urls[0] if captured_urls else None


if __name__ == "__main__":
    # Set headless=False to watch the browser — recommended for first run
    result = test_extract(TEST_URL, headless=True)

    print(f"\n{'='*60}")
    if result:
        print(f"FINAL RESULT: {result}")
    else:
        print("FINAL RESULT: FAILED — check page_dump.html for clues")
    print(f"{'='*60}")
