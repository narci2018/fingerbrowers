from playwright.sync_api import sync_playwright
import time

def test_turnstile_interactive():
    with sync_playwright() as p:
        # Launch Chrome exactly like a real user with genuine Chrome 153
        browser = p.chromium.launch(
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://ping0.cc/", timeout=60000)
        time.sleep(3)
        
        # Look for the turnstile challenge checkbox
        for f in page.frames:
            if "challenges.cloudflare.com" in f.url:
                print("Found challenge frame. Waiting for checkbox...")
                try:
                    # Look for checkbox input or label inside the frame
                    f.wait_for_selector("input[type='checkbox'], .ctp-checkbox-label, #challenge-stage", timeout=10000)
                    print("Found element inside frame! Clicking checkbox...")
                    el = f.query_selector("input[type='checkbox'], .ctp-checkbox-label")
                    if el:
                        el.click()
                    else:
                        f.click("body")
                    print("Clicked!")
                except Exception as e:
                    print("Could not click frame element:", e)
        
        print("Waiting 10 seconds to see if verification succeeds or fails...")
        time.sleep(10)
        print("Title:", page.title())
        print("URL:", page.url)
        page.screenshot(path="turnstile_click_result.png")
        browser.close()

if __name__ == "__main__":
    test_turnstile_interactive()
