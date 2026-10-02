from playwright.sync_api import sync_playwright
import time

def compare():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        page = browser.new_page()
        page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000)
        time.sleep(6)
        
        # Take screenshot of official Google Chrome without any spoofing
        page.screenshot(path="native_chrome_creepjs.png", full_page=True)
        
        entropy_high_count = page.evaluate("() => document.querySelectorAll('.entropy-high').length")
        entropy_low_count = page.evaluate("() => document.querySelectorAll('.entropy-low').length")
        lies_count = page.evaluate("() => document.querySelectorAll('.lies, .bold-fail').length")
        
        print(f"原生纯净 Chrome 访问 CreepJS 结果:")
        print(f"  - 粉红色 (.entropy-high / 高信息熵) 徽章数量: {entropy_high_count}")
        print(f"  - 青绿色 (.entropy-low / 低信息熵) 徽章数量: {entropy_low_count}")
        print(f"  - 真实异常/伪造警告 (.lies / .bold-fail) 数量: {lies_count}")
        browser.close()

if __name__ == "__main__":
    compare()
