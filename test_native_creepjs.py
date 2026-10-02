from playwright.sync_api import sync_playwright

def test_clean_chrome():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        page = browser.new_page()
        page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000)
        page.wait_for_timeout(4000)

        data = page.evaluate("""() => {
            const highEntropy = Array.from(document.querySelectorAll('.entropy-high')).map(e => {
                const parent = e.closest('div');
                const title = parent?.querySelector('h1, h2, h3, h4')?.innerText || 'Unknown';
                return { title: title.trim(), text: e.innerText.trim() };
            });
            const lies = Array.from(document.querySelectorAll('.lie, .tampered, [class*="lie"]')).map(e => e.innerText);
            return { highEntropy, lies };
        }""")

        print(f"原生干净 Chrome 下的粉红色 (.entropy-high) 标签总数: {len(data['highEntropy'])}")
        print("其中包含的粉红卡片模块样例:")
        for item in data['highEntropy'][:8]:
            print(f"  - [{item['title']}] 标签: {item['text']}")

        print(f"\n原生 Chrome 下的 Lies 篡改数: {len(data['lies'])}")
        browser.close()

if __name__ == "__main__":
    test_clean_chrome()
