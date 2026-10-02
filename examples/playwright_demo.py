import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher
from core.injections import generate_stealth_injection_script

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[WARN] Playwright 未安装或尚未完成安装，请先 pip install playwright")
    sys.exit(1)


def run_demo():
    print("=== 指纹浏览器 + Playwright 自动化联动测试 ===")
    profile_mgr = ProfileManager()
    launcher = BrowserLauncher(profile_mgr)

    # 1. 创建或获取演示环境
    profiles = profile_mgr.list_profiles()
    if not profiles:
        print("[1/5] 创建测试 Profile: 'Demo-Environment' (zh-CN)...")
        profile = profile_mgr.create_profile("Demo-Environment", group="Testing", locale="zh-CN")
    else:
        profile = profiles[0]
        print(f"[1/5] 使用已有 Profile: {profile.name} ({profile.id})")

    # 2. 启动浏览器环境
    print("[2/5] 启动隔离浏览器并打开 CDP 端口...")
    status = launcher.start_profile(profile.id, headless=False)
    print(f"      - 进程 PID: {status.pid}")
    print(f"      - CDP 端点: {status.ws_endpoint}")

    try:
        # 3. 使用 Playwright 挂载到运行中的浏览器
        print("[3/5] Playwright 挂载到 CDP WebSocket...")
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(status.ws_endpoint)
            # 获取默认上下文
            context = browser.contexts[0]
            
            # 注入针对该 Profile 种子量身定制的 Stealth 脚本
            stealth_js = generate_stealth_injection_script(profile.fingerprint)
            context.add_init_script(stealth_js)

            page = context.new_page()
            
            # 4. 访问测试页验证
            print("[4/5] 正在打开指纹与 WebDriver 验证页面...")
            page.goto("https://bot.sannysoft.com", timeout=30000)
            page.wait_for_timeout(4000)

            # 打印当前浏览器上下文识别出的 navigator 属性
            eval_result = page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    languages: navigator.languages,
                    screenWidth: screen.width,
                    screenHeight: screen.height,
                    userAgent: navigator.userAgent
                };
            }""")
            print("\n--- 页面实时指纹探测结果 ---")
            for k, v in eval_result.items():
                print(f"  {k}: {v}")
            print("----------------------------\n")
            
            print("[5/5] 测试完成，保持浏览器 5 秒供观察...")
            page.wait_for_timeout(5000)
    finally:
        print("关闭指纹浏览器进程...")
        launcher.stop_profile(profile.id)
        print("测试流程圆满结束！")


if __name__ == "__main__":
    run_demo()
