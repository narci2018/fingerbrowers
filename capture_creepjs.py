from playwright.sync_api import sync_playwright

def capture_creepjs():
    with sync_playwright() as p:
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
        page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000)
        page.wait_for_timeout(4000)
        
        info = page.evaluate("""() => {
            const items = [];
            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const style = window.getComputedStyle(el);
                const color = style.color;
                const bg = style.backgroundColor;
                // 检测任何红色/粉色系
                if (bg.startsWith('rgba(255') || bg.startsWith('rgb(255') || color.startsWith('rgb(255') || color.startsWith('rgba(255')) {
                    if (el.innerText && el.innerText.length < 100) {
                        items.push({
                            tag: el.tagName,
                            class: el.className,
                            color: color,
                            bg: bg,
                            text: el.innerText.trim()
                        });
                    }
                }
            });
            return items;
        }""")

        import json
        with open("creepjs_colors.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        print(f"Captured {len(info)} colored elements.")
        browser.close()

if __name__ == "__main__":
    capture_creepjs()
