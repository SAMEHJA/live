# test_egydead_stream_v2.py
import sys
import time
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Common import DEBUG, TEMP_PROFILE, AD_DOMAINS

def get_egydead_stream_url(page_url: str, headless: bool = False) -> str:
    from playwright.sync_api import sync_playwright
    
    captured_url = None
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=TEMP_PROFILE,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        
        # Block ads
        def block_ads(route, request):
            if any(domain in request.url for domain in AD_DOMAINS):
                route.abort()
                return
            route.continue_()
        page.route("**/*", block_ads)
        
        # Intercept m3u8 from the very beginning
        def intercept(route, request):
            nonlocal captured_url
            if ".m3u8" in request.url:
                captured_url = request.url
                print(f"[INTERCEPT] Found m3u8: {captured_url}")
            route.continue_()
        page.route("**/*", intercept)
        
        print(f"[INFO] Loading {page_url}")
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for page to be ready
        page.wait_for_timeout(2000)
        
        # 1. Click the main watch button
        watch_btn = page.query_selector('button[type="submit"]:has-text("المشاهده")')
        if watch_btn:
            print("[INFO] Clicking watch button")
            watch_btn.click()
            page.wait_for_timeout(3000)  # Wait for iframe to appear
        else:
            print("[WARN] No watch button found")
        
        # 2. Wait for any iframe to appear (the player)
        try:
            # Wait for iframe element in the DOM
            iframe_elem = page.wait_for_selector('iframe', timeout=10000)
            print("[INFO] Iframe found, retrieving content frame")
            # Get the frame
            iframe = iframe_elem.content_frame()
            if iframe:
                print("[INFO] Switched to iframe")
                # Wait for video element inside iframe
                iframe.wait_for_selector('video', timeout=10000)
                print("[INFO] Video element inside iframe detected")
                
                # Try clicking play button inside iframe
                play_btn = iframe.query_selector('.jw-icon-display, .play-button, .vjs-big-play-button, .mejs-playpause-button')
                if play_btn:
                    print("[INFO] Clicking play button inside iframe")
                    play_btn.click()
                    page.wait_for_timeout(3000)
                else:
                    # If no explicit play button, click the video itself
                    video = iframe.query_selector('video')
                    if video:
                        print("[INFO] Clicking video element")
                        video.click()
                        page.wait_for_timeout(3000)
            else:
                print("[WARN] Could not get content frame")
        except Exception as e:
            print(f"[ERROR] Iframe handling: {e}")
        
        # 3. Also try server tabs if present (after click, new iframe might have different src)
        servers = page.query_selector_all('.serversList li, .server-list li')
        if servers:
            print(f"[INFO] Found {len(servers)} server tabs, clicking first")
            servers[0].click()
            page.wait_for_timeout(5000)  # Allow new iframe to load
            # Re-check for iframe again
            try:
                new_iframe = page.wait_for_selector('iframe', timeout=5000)
                if new_iframe:
                    iframe = new_iframe.content_frame()
                    if iframe:
                        iframe.wait_for_selector('video', timeout=5000)
                        # Click play again
                        iframe.click('video', force=True)
                        page.wait_for_timeout(2000)
            except:
                pass
        
        # 4. Wait for interception
        for _ in range(20):  # up to 10 seconds
            if captured_url:
                break
            page.wait_for_timeout(500)
        
        context.close()
        return captured_url if captured_url else ""

if __name__ == "__main__":
    test_url = "https://tv8.egydead.live/avatar-3-fire-and-ash-2025-1080p-web-dl/"
    print("="*50)
    print(f"Testing: {test_url}")
    print("="*50)
    result = get_egydead_stream_url(test_url, headless=False)
    if result:
        print(f"\n✅ SUCCESS:\n{result}")
    else:
        print("\n❌ FAILED: No m3u8 captured")