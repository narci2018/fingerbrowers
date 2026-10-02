import os
import sys
import time
import socket
import threading
import subprocess
import urllib.request
import logging
from pathlib import Path

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# 配置标准文件日志
LOG_FILE = APP_DIR / "gui_launcher.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

logging.info("PhantomBrowser 启动中...")

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8998


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def start_api_server():
    """在后台线程运行 FastAPI 控制面"""
    try:
        import uvicorn
        from api.server import app
        logging.info("正在启动 Uvicorn 后台服务...")
        config = uvicorn.Config(
            app=app,
            host=SERVER_HOST,
            port=SERVER_PORT,
            log_config=None,
            access_log=False
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        logging.error(f"Uvicorn 启动失败: {e}", exc_info=True)


def is_server_healthy() -> bool:
    try:
        req = urllib.request.Request(f"http://{SERVER_HOST}:{SERVER_PORT}/health")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_server(timeout: int = 15) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(f"http://{SERVER_HOST}:{SERVER_PORT}/health")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    # 确保前端网页服务挂载就绪
                    try:
                        req_gui = urllib.request.Request(f"http://{SERVER_HOST}:{SERVER_PORT}/")
                        with urllib.request.urlopen(req_gui, timeout=0.5) as resp_gui:
                            if resp_gui.status == 200:
                                logging.info("FastAPI 后台服务及 GUI 首页已完全就绪！")
                                return True
                    except Exception:
                        pass
        except Exception:
            time.sleep(0.05)
    return False


def launch_window(url: str):
    """调起独立桌面窗口 (优先系统级 Edge 独立 App 模式，轻量极速原生渲染)"""
    session_dir = APP_DIR / "data" / "gui_session"
    session_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]

    for exe in candidates:
        if os.path.exists(exe):
            logging.info(f"使用独立桌面视窗引擎: {exe}")
            cmd = [
                exe,
                f"--app={url}",
                f"--user-data-dir={str(session_dir)}",
                "--window-size=1280,820",
                "--window-position=120,80",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--disable-features=msEdgeSync,msSingleSignOn,msEdgeWelcomeDialog,msImplicitSignIn,msFreMarketing,SearchEngineChoice",
                "--disable-signin-promo",
                "--disable-search-engine-choice-screen",
                "--disable-background-networking"
            ]
            try:
                if sys.platform == "win32":
                    from core.browser_launcher import Win32Popen
                    proc = Win32Popen(cmd)
                else:
                    proc = subprocess.Popen(cmd)
                logging.info(f"独立桌面视窗已成功启动，PID: {proc.pid}")
                t0 = time.time()
                proc.wait()
                elapsed = time.time() - t0
                if elapsed < 2.0:
                    logging.info(f"视窗启动器在 {elapsed:.2f}s 内返回，保持后台服务长效监听...")
                    while True:
                        time.sleep(1)
                else:
                    logging.info("用户关闭了桌面视窗，退出程序。")
                return
            except Exception as e:
                logging.error(f"视窗启动失败: {e}", exc_info=True)

    # 备用方案：系统默认浏览器
    import webbrowser
    logging.info("使用系统默认浏览器打开 GUI")
    webbrowser.open(url)
    while True:
        time.sleep(1)


def main():
    if not is_server_healthy():
        if is_port_in_use(SERVER_PORT):
            logging.warning("检测到端口被占用但服务未就绪，等待清理后重新绑定...")
            time.sleep(0.5)

        t = threading.Thread(target=start_api_server, daemon=True)
        t.start()
        if not wait_for_server(15):
            logging.error("无法启动后台服务，程序退出。")
            return
    else:
        logging.info("服务端口 8998 已在运行且健康，复用现有服务。")

    gui_url = f"http://{SERVER_HOST}:{SERVER_PORT}/"
    try:
        launch_window(gui_url)
    finally:
        try:
            from api.server import launcher
            launcher.stop_all()
        except Exception:
            pass


if __name__ == "__main__":
    main()
