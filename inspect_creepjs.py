from playwright.sync_api import sync_playwright
import time
import json

def inspect_creepjs():
    with sync_playwright() as p:
        # 启动普通的 Chromium，模拟用户当前的环境
        browser = p.chromium.launch(
            headless=True,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = browser.new_context()
        page = context.new_page()
        print("Navigating to CreepJS...")
        page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000)
        page.wait_for_timeout(5000)

        # 检查页面中所有红色/粉红色/带有 lie 或 tampered 的模块
        lies = page.evaluate("""() => {
            const results = [];
            // 查找所有带背景色为粉红/浅红的卡片
            const cards = document.querySelectorAll('.block-entry, .col-six, .col-four, div');
            cards.forEach(el => {
                const bg = window.getComputedStyle(el).backgroundColor;
                // rgb(255, 230, 230) 或类似红色
                if (bg.includes('255,') && !bg.includes('255, 255, 255')) {
                    const title = el.querySelector('h1, h2, h3, h4, h5, .title')?.innerText || el.innerText.substring(0, 30);
                    results.push({
                        title: title.trim(),
                        bg: bg,
                        text: el.innerText.substring(0, 200).replace(/\\n+/g, ' ')
                    });
                }
            });

            // 查找页面上的 lie 标记
            const lieElements = document.querySelectorAll('.lie, .tampered, [class*="lie"], [class*="tamper"]');
            const lieList = [];
            lieElements.forEach(el => {
                lieList.push({
                    text: el.innerText,
                    parent: el.parentElement?.innerText.substring(0, 150).replace(/\\n+/g, ' ')
                });
            });

            // 查找 FP ID 与各个 section 的 header 颜色
            const sections = [];
            document.querySelectorAll('div > h2, div > h3, div > h4').forEach(h => {
                const p = h.parentElement;
                const bg = window.getComputedStyle(p).backgroundColor;
                sections.push({
                    name: h.innerText,
                    bg: bg,
                    classes: p.className
                });
            });

            return { lies: lieList, redBlocks: results, sections: sections };
        }""")

        print("\n=== LIES DETECTED ===")
        print(json.dumps(lies['lies'], indent=2, ensure_ascii=False))

        print("\n=== SECTIONS BACKGROUNDS ===")
        for s in lies['sections']:
            print(f"Section: {s['name']} | BG: {s['bg']} | Class: {s['classes']}")

        browser.close()

if __name__ == "__main__":
    inspect_creepjs()
