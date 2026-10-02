from playwright.sync_api import sync_playwright
import time
from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher

mgr = ProfileManager()
profiles = mgr.list_profiles()
p = profiles[0]

launcher = BrowserLauncher(mgr)
status = launcher.start_profile(p.id, headless=False)
print("Started profile on CDP port:", status.cdp_port)
time.sleep(2)

try:
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{status.cdp_port}")
        context = browser.contexts[0]
        page = context.new_page()
        
        # Log all console messages and failed network requests
        page.on("console", lambda msg: print(f"[CONSOLE {msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"[PAGE ERROR]: {err}"))
        page.on("response", lambda resp: print(f"[RESPONSE]: {resp.status} {resp.url[:90]}") if "cloudflare" in resp.url or "challenge" in resp.url else None)
        
        print("Navigating to https://ping0.cc/ ...")
        page.goto("https://ping0.cc/", timeout=60000)
        time.sleep(5)
        
        # Find the Turnstile iframe
        for f in page.frames:
            if "challenges.cloudflare.com" in f.url:
                print("Found Turnstile frame:", f.url)
                # Check frame content
                content = f.content()
                print("Frame content snippet:", content[:300])
                
        # Wait a bit and take a screenshot
        time.sleep(6)
        page.screenshot(path="ping0_console_test.png")
finally:
    launcher.stop_profile(p.id)
