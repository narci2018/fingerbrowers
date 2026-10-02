import asyncio
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import websockets
from .models import FingerprintConfig, ProxyConfig
from .injections import generate_stealth_injection_script

logger = logging.getLogger(__name__)


def build_client_hints_metadata(fp: FingerprintConfig) -> Optional[Dict[str, Any]]:
    """
    根据 FingerprintConfig 中的操作系统与浏览器动态构建符合 W3C User-Agent Client Hints 规范的 metadata。
    如果模拟非 Chromium 浏览器 (如 Firefox / Safari)，Client Hints 标准并不适用，返回 None。
    """
    ua = fp.user_agent
    browser_name = getattr(fp, "browser_name", "Chrome") or "Chrome"
    os_name = getattr(fp, "os_name", "Windows") or "Windows"
    os_version = getattr(fp, "os_version", "10.0") or "10.0"

    # 提取 Chrome / Edge / Opera 主版本
    chrome_match = re.search(r"Chrome/(\d+)", ua)
    edge_match = re.search(r"Edg[A-Za-z]*/(\d+)", ua)
    opera_match = re.search(r"OPR/(\d+)", ua)

    major_ver = "130"
    if chrome_match:
        major_ver = chrome_match.group(1)
    elif hasattr(fp, "browser_version") and fp.browser_version:
        major_ver = str(fp.browser_version).split('.')[0]

    # 判断是否为移动端
    is_mobile = "Mobile" in ua or os_name.lower() in ["android", "ios"]

    # 针对不同浏览器品牌组装 brands
    if "edge" in browser_name.lower():
        edge_ver = edge_match.group(1) if edge_match else major_ver
        brands = [
            {"brand": "Microsoft Edge", "version": edge_ver},
            {"brand": "Chromium", "version": major_ver},
            {"brand": "Not-A.Brand", "version": "24"}
        ]
        full_version_list = [
            {"brand": "Microsoft Edge", "version": f"{edge_ver}.0.0.0"},
            {"brand": "Chromium", "version": f"{major_ver}.0.0.0"},
            {"brand": "Not-A.Brand", "version": "24.0.0.0"}
        ]
    elif "opera" in browser_name.lower():
        opr_ver = opera_match.group(1) if opera_match else "114"
        brands = [
            {"brand": "Opera", "version": opr_ver},
            {"brand": "Chromium", "version": major_ver},
            {"brand": "Not-A.Brand", "version": "24"}
        ]
        full_version_list = [
            {"brand": "Opera", "version": f"{opr_ver}.0.0.0"},
            {"brand": "Chromium", "version": f"{major_ver}.0.0.0"},
            {"brand": "Not-A.Brand", "version": "24.0.0.0"}
        ]
    elif "firefox" in browser_name.lower() or "safari" in browser_name.lower():
        # Firefox 和 Safari 在 W3C 规范中不发送 sec-ch-ua 等 Client Hints 标头
        return None
    else:
        # Chrome
        brands = [
            {"brand": "Google Chrome", "version": major_ver},
            {"brand": "Chromium", "version": major_ver},
            {"brand": "Not-A.Brand", "version": "24"}
        ]
        full_version_list = [
            {"brand": "Google Chrome", "version": f"{major_ver}.0.0.0"},
            {"brand": "Chromium", "version": f"{major_ver}.0.0.0"},
            {"brand": "Not-A.Brand", "version": "24.0.0.0"}
        ]

    # 根据 OS 构建平台元数据
    platform_str = "Windows"
    platform_version = "10.0.0"
    architecture = "x86"
    bitness = "64"
    model = ""

    os_lower = os_name.lower()
    if "mac" in os_lower:
        platform_str = "macOS"
        platform_version = "14.5.0"
        architecture = "arm" if "arm" in ua.lower() else "x86"
        model = ""
    elif "android" in os_lower:
        platform_str = "Android"
        platform_version = "14.0.0"
        architecture = "arm"
        bitness = "64"
        model = "Pixel 8 Pro"
    elif "ios" in os_lower:
        platform_str = "iOS"
        platform_version = "17.5.0"
        architecture = "arm"
        bitness = "64"
        model = "iPhone"
    elif "linux" in os_lower:
        platform_str = "Linux"
        platform_version = "6.5.0"
        architecture = "x86"
        bitness = "64"
        model = ""
    else:
        # Windows
        platform_str = "Windows"
        if "11" in str(os_version):
            platform_version = "15.0.0"
        elif "8" in str(os_version):
            platform_version = "0.3.0"
        elif "7" in str(os_version):
            platform_version = "0.1.0"
        else:
            platform_version = "10.0.0"

    return {
        "brands": brands,
        "fullVersionList": full_version_list,
        "fullVersion": f"{major_ver}.0.0.0",
        "platform": platform_str,
        "platformVersion": platform_version,
        "architecture": architecture,
        "model": model,
        "mobile": is_mobile,
        "bitness": bitness
    }


class CDPInjector:
    """
    负责通过 CDP 协议为整个浏览器实例注入 Stealth 增强与 Client Hints / Screen / Timezone / Geolocation 覆盖。
    使用 Target.setAutoAttach 确保对所有现有页面、新建标签页、Iframe 和 Worker 全局生效。
    支持自动代理认证（Fetch.continueWithAuth）。
    支持离线 Cookie 启动时自动注入（Network.setCookies）。
    """

    def __init__(
        self,
        ws_url: Optional[str] = None,
        fp: Optional[FingerprintConfig] = None,
        proxy_config: Optional[ProxyConfig] = None,
        profile_id: Optional[str] = None,
        user_data_path: Optional[Path] = None,
        geo_info: Optional[Dict[str, Any]] = None,
        ws_endpoint: Optional[str] = None,
        proc: Optional[Any] = None,
        initial_url: Optional[str] = None,
    ):
        self.ws_url = ws_url or ws_endpoint or ""
        self.fp = fp
        self.proxy_config = proxy_config
        self.profile_id = profile_id
        self.user_data_path = user_data_path
        self.geo_info = geo_info
        self.proc = proc
        self.initial_url = initial_url
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._last_page_session: Optional[str] = None

    def start(self):
        """在后台线程中维持 CDP 守护与自动注入"""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def navigate(self, url: str) -> bool:
        """通过当前活跃页面或新建标签页导航到目标网址"""
        if not self._loop or not self._loop.is_running():
            return False
        async def _do():
            if self._ws and self._last_page_session:
                try:
                    await self._ws.send(json.dumps({
                        "id": 99991,
                        "sessionId": self._last_page_session,
                        "method": "Page.navigate",
                        "params": {"url": url}
                    }))
                    return
                except Exception:
                    pass
            if self._ws:
                try:
                    await self._ws.send(json.dumps({
                        "id": 99992,
                        "method": "Target.createTarget",
                        "params": {"url": url}
                    }))
                except Exception:
                    pass
        asyncio.run_coroutine_threadsafe(_do(), self._loop)
        return True

    def _run_loop(self):
        asyncio.run(self._cdp_worker())

    async def _cdp_worker(self):
        self._loop = asyncio.get_running_loop()
        initial_navigated = False
        # 准备全套注入脚本
        stealth_script = generate_stealth_injection_script(self.fp)

        # 准备底层 Client Hints 原生结构
        ua_metadata = build_client_hints_metadata(self.fp)

        # 检查是否为移动端
        is_mobile = "Mobile" in self.fp.user_agent or getattr(self.fp, "os_name", "").lower() in ["android", "ios"]

        # 检查是否有离线待注入 Cookie
        pending_cookies = []
        if self.user_data_path:
            p_file = self.user_data_path / "pending_cookies.json"
            if p_file.exists():
                try:
                    with open(p_file, "r", encoding="utf-8") as f:
                        pending_cookies = json.load(f)
                except Exception as e:
                    logger.debug(f"Read pending cookies error: {e}")

        cookies_injected = False
        retry_count = 0

        while not self._stop_event.is_set() and retry_count < 10:
            if self.proc and self.proc.poll() is not None:
                break
            try:
                async with websockets.connect(self.ws_url, max_size=10*1024*1024) as ws:
                    self._ws = ws
                    msg_id = 1

                    # 1. 开启全局 Target 自动挂载 (仅顶层页面，避免进入 cross-origin challenge iframe)
                    auto_attach_cmd = {
                        "id": msg_id,
                        "method": "Target.setAutoAttach",
                        "params": {
                            "autoAttach": True,
                            "waitForDebuggerOnStart": False,
                            "flatten": True
                        }
                    }
                    await ws.send(json.dumps(auto_attach_cmd))
                    msg_id += 1

                    # 2. 如果存在待注入的 Cookie，下发 Network.setCookies
                    if pending_cookies and not cookies_injected:
                        cdp_cookies = []
                        for c in pending_cookies:
                            item = {
                                "name": c.get("name"),
                                "value": c.get("value", ""),
                                "domain": c.get("domain", ""),
                                "path": c.get("path", "/"),
                                "secure": c.get("secure", False),
                                "httpOnly": c.get("httpOnly", False),
                            }
                            exp = c.get("expires") or c.get("expirationDate")
                            if exp:
                                item["expires"] = float(exp)
                            if c.get("sameSite"):
                                item["sameSite"] = c["sameSite"]
                            cdp_cookies.append(item)

                        if cdp_cookies:
                            await ws.send(json.dumps({
                                "id": msg_id,
                                "method": "Network.setCookies",
                                "params": {"cookies": cdp_cookies}
                            }))
                            msg_id += 1
                            cookies_injected = True
                            # 注入成功后删除待注入文件
                            if self.user_data_path:
                                try:
                                    (self.user_data_path / "pending_cookies.json").unlink(missing_ok=True)
                                except Exception:
                                    pass

                    # 3. 持续监听所有新建的 session 并下发覆盖
                    while not self._stop_event.is_set():
                        raw_msg = await ws.recv()
                        data = json.loads(raw_msg)
                        method = data.get("method", "")

                        # 当有新页面或 Target 附着时
                        if method == "Target.attachedToTarget":
                            target_info = data.get("params", {}).get("targetInfo", {})
                            target_type = target_info.get("type", "")
                            target_url = target_info.get("url", "")
                            session_id = data.get("params", {}).get("sessionId")

                            is_page = (target_type == "page")
                            is_worker = (target_type in ("worker", "service_worker", "shared_worker"))
                            if not is_page and not is_worker:
                                continue
                            if "challenges.cloudflare.com" in target_url or "challenge-platform" in target_url:
                                continue

                            if session_id:
                                # 平台与架构对齐 (macOS 必须保证为 MacIntel，彻底消灭 Worker 与主页面 Mac(Win32) 矛盾)
                                is_mac = "mac" in (self.fp.os_name or "").lower() or "macintosh" in (self.fp.user_agent or "").lower()
                                target_platform = "MacIntel" if is_mac else (self.fp.platform or "Win32")

                                emulation_params = {
                                    "userAgent": self.fp.user_agent,
                                    "acceptLanguage": ",".join(self.fp.languages),
                                    "platform": target_platform
                                }
                                if ua_metadata is not None:
                                    emulation_params["userAgentMetadata"] = ua_metadata

                                if is_page:
                                    # 主页面下发 Page.enable
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Page.enable"
                                    }))
                                    msg_id += 1

                                    # 原生 C++ 级下发 User-Agent 及 Client Hints 覆盖
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Emulation.setUserAgentOverride",
                                        "params": emulation_params
                                    }))
                                    msg_id += 1
                                elif is_worker:
                                    # Worker 深度覆盖：确保 Web Worker / ServiceWorker 线程与主页面完全自洽一致
                                    try:
                                        await ws.send(json.dumps({
                                            "id": msg_id,
                                            "sessionId": session_id,
                                            "method": "Network.setUserAgentOverride",
                                            "params": emulation_params
                                        }))
                                        msg_id += 1
                                    except Exception:
                                        pass
                                    try:
                                        await ws.send(json.dumps({
                                            "id": msg_id,
                                            "sessionId": session_id,
                                            "method": "Emulation.setUserAgentOverride",
                                            "params": emulation_params
                                        }))
                                        msg_id += 1
                                    except Exception:
                                        pass
                                    continue

                                # 2. 如果是移动端 (Android / iOS)，开启设备触控与屏幕指标仿真
                                if is_mobile:
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Emulation.setDeviceMetricsOverride",
                                        "params": {
                                            "width": int(self.fp.screen_width),
                                            "height": int(self.fp.screen_height),
                                            "deviceScaleFactor": float(self.fp.device_scale_factor or 2.0),
                                            "mobile": True
                                        }
                                    }))
                                    msg_id += 1

                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Emulation.setTouchEmulationEnabled",
                                        "params": {
                                            "enabled": True,
                                            "maxTouchPoints": 5
                                        }
                                    }))
                                    msg_id += 1

                                # 3. 原生 C++ 级注入时区
                                await ws.send(json.dumps({
                                    "id": msg_id,
                                    "sessionId": session_id,
                                    "method": "Emulation.setTimezoneOverride",
                                    "params": {
                                        "timezoneId": self.fp.timezone
                                    }
                                }))
                                msg_id += 1

                                # 4. 原生 C++ 级注入地理位置坐标对齐 (若已知经纬度)
                                if self.geo_info and self.geo_info.get("latitude") is not None:
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Emulation.setGeolocationOverride",
                                        "params": {
                                            "latitude": float(self.geo_info["latitude"]),
                                            "longitude": float(self.geo_info["longitude"]),
                                            "accuracy": float(self.geo_info.get("accuracy", 100))
                                        }
                                    }))
                                    msg_id += 1

                                # 5. 如果有自定义脚本才注入，否则保持原生环境零污染
                                if stealth_script and stealth_script.strip():
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Page.addScriptToEvaluateOnNewDocument",
                                        "params": {
                                            "source": stealth_script
                                        }
                                    }))
                                    msg_id += 1

                                # 6. 如果配置了带账号密码的代理，开启 Fetch.enable 以自动响应认证
                                if self.proxy_config and self.proxy_config.username:
                                    await ws.send(json.dumps({
                                        "id": msg_id,
                                        "sessionId": session_id,
                                        "method": "Fetch.enable",
                                        "params": {
                                            "handleAuthRequests": True
                                        }
                                    }))
                                    msg_id += 1

                                # 7. 记录活跃页面会话，且如果配置了启动目标网址尚未跳转，直接在当前页面下发 Page.navigate
                                self._last_page_session = session_id
                                if is_page and self.initial_url and not initial_navigated and self.initial_url.strip() and self.initial_url != "about:blank":
                                    try:
                                        await ws.send(json.dumps({
                                            "id": msg_id,
                                            "sessionId": session_id,
                                            "method": "Page.navigate",
                                            "params": {"url": self.initial_url}
                                        }))
                                        msg_id += 1
                                        initial_navigated = True
                                    except Exception as e:
                                        logger.debug(f"Initial navigate error: {e}")

                        # 当浏览器代理要求身份认证时，自动响应账密
                        elif method == "Fetch.authRequired":
                            session_id = data.get("sessionId")
                            req_id = data.get("params", {}).get("requestId")
                            if req_id and self.proxy_config and self.proxy_config.username:
                                await ws.send(json.dumps({
                                    "id": msg_id,
                                    "sessionId": session_id,
                                    "method": "Fetch.continueWithAuth",
                                    "params": {
                                        "requestId": req_id,
                                        "authChallengeResponse": {
                                            "response": "ProvideCredentials",
                                            "username": self.proxy_config.username,
                                            "password": self.proxy_config.password or ""
                                        }
                                    }
                                }))
                                msg_id += 1

            except Exception as e:
                if self.proc and self.proc.poll() is not None:
                    break
                retry_count += 1
                await asyncio.sleep(0.5)
