import os
import ctypes
import random
import uuid
from typing import Optional, Dict, Any, List, Tuple
from .models import FingerprintConfig

def get_host_chrome_version() -> str:
    """自动探测宿主机 Chrome 真实内核版本（使用 winreg 注册表毫秒级读取，杜绝任何外部弹窗与耗时）"""
    try:
        import winreg
        for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            for path, val_name in [
                (r"Software\Google\Chrome\BLBeacon", "version"),
                (r"SOFTWARE\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}", "pv"),
                (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", None)
            ]:
                try:
                    with winreg.OpenKey(root, path) as k:
                        v, _ = winreg.QueryValueEx(k, val_name)
                        if v and isinstance(v, str) and "." in v:
                            return v.strip()
                except Exception:
                    pass
    except Exception:
        pass
    return "153.0.8010.53"

HOST_CHROME_VERSION = get_host_chrome_version()
HOST_CHROME_MAJOR = HOST_CHROME_VERSION.split('.')[0] if '.' in HOST_CHROME_VERSION else "153"

# 探测宿主真实硬件
HOST_CPU_CORES = os.cpu_count() or 12
HOST_MEMORY_GB = 32

def get_host_screen():
    try:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return (w, h, w, h - 48, 1.0)
    except Exception:
        pass
    return (1920, 1200, 1920, 1152, 1.0)

HOST_SCREEN = get_host_screen()
HOST_GPU_VENDOR = "Google Inc. (NVIDIA)"
HOST_GPU_RENDERER = "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 (0x00002786) Direct3D11 vs_5_0 ps_5_0, D3D11)"

# 预设的各操作系统配置
OS_PRESETS: Dict[str, Dict[str, Any]] = {
    # Windows 系列
    "win11": {
        "os_name": "Windows",
        "os_version": "11.0",
        "platform": "Win32",
        "ua_platform": "Windows NT 10.0; Win64; x64",
        "platform_version": "15.0.0",  # Win11 在 Client Hints 中的 platformVersion 为 13+ 或 15.0.0
        "label": "Windows 11 (64-bit)"
    },
    "win10": {
        "os_name": "Windows",
        "os_version": "10.0",
        "platform": "Win32",
        "ua_platform": "Windows NT 10.0; Win64; x64",
        "platform_version": "10.0.0",
        "label": "Windows 10 (64-bit)"
    },
    "win8": {
        "os_name": "Windows",
        "os_version": "6.3",
        "platform": "Win32",
        "ua_platform": "Windows NT 6.3; Win64; x64",
        "platform_version": "0.3.0",
        "label": "Windows 8.1 (64-bit)"
    },
    "win7": {
        "os_name": "Windows",
        "os_version": "6.1",
        "platform": "Win32",
        "ua_platform": "Windows NT 6.1; Win64; x64",
        "platform_version": "0.1.0",
        "label": "Windows 7 (64-bit)"
    },
    # macOS
    "macos": {
        "os_name": "macOS",
        "os_version": "14.5",
        "platform": "MacIntel",
        "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
        "platform_version": "14.5.0",
        "label": "macOS Sonoma (14.5)"
    },
    # Linux
    "linux": {
        "os_name": "Linux",
        "os_version": "x86_64",
        "platform": "Linux x86_64",
        "ua_platform": "X11; Linux x86_64",
        "platform_version": "6.5.0",
        "label": "Linux (x86_64 Ubuntu/Debian)"
    },
    # Android (移动端)
    "android": {
        "os_name": "Android",
        "os_version": "14",
        "platform": "Linux armv81",
        "ua_platform": "Linux; Android 14; Pixel 8 Pro",
        "platform_version": "14.0.0",
        "mobile": True,
        "model": "Pixel 8 Pro",
        "label": "Android 14 (Google Pixel 8 Pro)"
    },
    # iOS (移动端)
    "ios": {
        "os_name": "iOS",
        "os_version": "17.5",
        "platform": "iPhone",
        "ua_platform": "iPhone; CPU iPhone OS 17_5 like Mac OS X",
        "platform_version": "17.5.0",
        "mobile": True,
        "model": "iPhone",
        "label": "iOS 17.5 (iPhone)"
    }
}

# 移动端常用分辨率
MOBILE_RESOLUTIONS = {
    "android": (412, 915, 412, 915, 2.625),
    "ios": (393, 852, 393, 852, 3.0)
}

# 浏览器内核与版本预设
BROWSER_PRESETS: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "name": "Chrome",
        "default_version": HOST_CHROME_MAJOR,
        "supported_versions": [HOST_CHROME_MAJOR, "130", "128", "125", "120"],
        "label": "Google Chrome"
    },
    "edge": {
        "name": "Edge",
        "default_version": HOST_CHROME_MAJOR,
        "supported_versions": [HOST_CHROME_MAJOR, "130", "128", "125", "120"],
        "label": "Microsoft Edge"
    },
    "firefox": {
        "name": "Firefox",
        "default_version": "131.0",
        "supported_versions": ["131.0", "130.0", "128.0", "120.0"],
        "label": "Mozilla Firefox"
    },
    "safari": {
        "name": "Safari",
        "default_version": "17.5",
        "supported_versions": ["17.5", "17.4", "16.6"],
        "label": "Apple Safari"
    },
    "opera": {
        "name": "Opera",
        "default_version": "114",
        "supported_versions": ["114", "110", "106"],
        "label": "Opera Browser"
    }
}


class FingerprintGenerator:
    """自动生成逼真、无冲突、自洽的跨系统与跨浏览器指纹配置"""

    @classmethod
    def get_supported_os_list(cls) -> List[Dict[str, Any]]:
        return [
            {"id": k, "name": v["os_name"], "version": v["os_version"], "label": v["label"]}
            for k, v in OS_PRESETS.items()
        ]

    @classmethod
    def get_supported_browser_list(cls) -> List[Dict[str, Any]]:
        return [
            {"id": k, "name": v["name"], "default_version": v["default_version"], "supported_versions": v["supported_versions"], "label": v["label"]}
            for k, v in BROWSER_PRESETS.items()
        ]

    @classmethod
    def build_user_agent(
        cls,
        os_key: str = "win10",
        browser_key: str = "chrome",
        browser_version: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """构建真实标准的 User-Agent 字符串"""
        os_info = OS_PRESETS.get(os_key.lower()) or OS_PRESETS["win10"]
        b_key = browser_key.lower()
        b_info = BROWSER_PRESETS.get(b_key) or BROWSER_PRESETS["chrome"]

        ver = str(browser_version) if browser_version else str(b_info["default_version"])
        platform_part = os_info["ua_platform"]

        # 格式化 UA 字符串
        if b_key == "chrome":
            major = ver.split('.')[0]
            if os_info.get("mobile"):
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36"
            else:
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"

        elif b_key == "edge":
            major = ver.split('.')[0]
            if os_info.get("mobile"):
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36 EdgA/{major}.0.0.0"
            else:
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36 Edg/{major}.0.0.0"

        elif b_key == "firefox":
            if os_info.get("mobile"):
                ua = f"Mozilla/5.0 (Android; Mobile; rv:{ver}) Gecko/{ver} Firefox/{ver}"
            else:
                ua = f"Mozilla/5.0 ({platform_part}; rv:{ver}) Gecko/20100101 Firefox/{ver}"

        elif b_key == "safari":
            if os_info.get("mobile"):
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{ver} Mobile/15E148 Safari/604.1"
            else:
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{ver} Safari/605.1.15"

        elif b_key == "opera":
            major = ver.split('.')[0]
            chrome_ref = HOST_CHROME_MAJOR
            if os_info.get("mobile"):
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ref}.0.0.0 Mobile Safari/537.36 OPR/{major}.0.0.0"
            else:
                ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ref}.0.0.0 Safari/537.36 OPR/{major}.0.0.0"
        else:
            ua = f"Mozilla/5.0 ({platform_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{HOST_CHROME_MAJOR}.0.0.0 Safari/537.36"

        return ua, b_info["name"], ver

    @classmethod
    def generate(
        cls,
        locale_preference: Optional[str] = "zh-CN",
        os_platform: Optional[str] = "win10",
        browser_type: Optional[str] = "chrome",
        browser_version: Optional[str] = None
    ) -> FingerprintConfig:
        """根据操作系统与浏览器偏好生成自洽指纹"""
        os_key = (os_platform or "win10").lower()
        if os_key not in OS_PRESETS:
            # 兼容传入 "Windows", "macos", 等
            found = False
            for k, v in OS_PRESETS.items():
                if k in os_key or v["os_name"].lower() in os_key:
                    os_key = k
                    found = True
                    break
            if not found:
                os_key = "win10"

        os_info = OS_PRESETS[os_key]
        b_key = (browser_type or "chrome").lower()
        if b_key not in BROWSER_PRESETS:
            b_key = "chrome"

        ua, b_name, b_ver = cls.build_user_agent(os_key, b_key, browser_version)

        seed = int(uuid.uuid4().int % 1000000)

        from .geoip_service import GeoIPService
        geo = GeoIPService.get_geo_defaults(locale_preference or "zh-CN")
        languages = geo["languages"]
        tz = geo["timezone"]

        from .font_packs import get_font_profile
        persona = "macos" if "mac" in os_key else ("linux" if "linux" in os_key else "windows")
        font_config = get_font_profile(persona)

        # 映射原生平台人格 (platform_persona) 与硬件指纹一致性
        if "mac" in os_key:
            persona = "macos"
            anchor = "macos-metal-apple-850a91233555"
            cores = 8
            ram_gb = 16
            res = (2560, 1600, 2560, 1575, 2.0)
            gpu_vendor = "Google Inc. (Apple)"
            gpu_renderer = "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)"
            envelope = {
                "platform": {
                    "name": "macOS",
                    "navigator_platform": "MacIntel",
                    "version": os_info.get("platform_version", "14.5.0"),
                    "architecture": "arm",
                    "bitness": "64",
                    "model": "",
                    "mobile": False
                },
                "browser": {
                    "user_agent": ua
                },
                "cpu": {
                    "logical_cores": cores
                },
                "memory": {
                    "total_bytes": ram_gb * 1024 * 1024 * 1024
                },
                "gpu": {
                    "unmasked_vendor": gpu_vendor,
                    "unmasked_renderer": gpu_renderer
                },
                "screen": {
                    "width": res[0],
                    "height": res[1],
                    "avail_width": res[2],
                    "avail_height": res[3],
                    "device_pixel_ratio": res[4],
                    "color_depth": 24
                },
                "fonts": get_font_profile("macos")
            }
        elif "linux" in os_key and not os_info.get("mobile"):
            persona = "linux"
            anchor = "linux-vulkan-nvidia-adf287b8f0ee"
            cores = min(HOST_CPU_CORES, 8)
            ram_gb = min(HOST_MEMORY_GB, 16)
            res = HOST_SCREEN
            gpu_vendor = HOST_GPU_VENDOR
            gpu_renderer = HOST_GPU_RENDERER
            envelope = None
        elif os_info.get("mobile"):
            persona = "android" if "android" in os_key else "ios"
            anchor = None
            cores = 8
            ram_gb = 8
            res = MOBILE_RESOLUTIONS.get(os_key, (412, 915, 412, 915, 2.625))
            gpu_vendor = HOST_GPU_VENDOR
            gpu_renderer = HOST_GPU_RENDERER
            envelope = None
        else:
            persona = "windows"
            anchor = "windows-d3d11-intel-79dfeb5b4f99"
            cores = HOST_CPU_CORES
            ram_gb = HOST_MEMORY_GB
            res = HOST_SCREEN
            gpu_vendor = HOST_GPU_VENDOR
            gpu_renderer = HOST_GPU_RENDERER
            envelope = None

        return FingerprintConfig(
            user_agent=ua,
            os_name=os_info["os_name"],
            os_version=os_info["os_version"],
            platform=os_info["platform"],
            browser_name=b_name,
            browser_version=b_ver,
            screen_width=res[0],
            screen_height=res[1],
            screen_avail_width=res[2],
            screen_avail_height=res[3],
            device_scale_factor=res[4],
            color_depth=24,
            hardware_concurrency=cores,
            device_memory=ram_gb,
            languages=languages,
            timezone=tz,
            webgl_vendor=gpu_vendor,
            webgl_renderer=gpu_renderer,
            noise_seed=seed,
            canvas_noise_enabled=True,
            audio_noise_enabled=True,
            webrtc_policy="disable_non_proxied_udp",
            # 商业级防指纹内核 16 项原生参数细粒度绑定
            platform_persona=persona,
            fingerprint_anchor=anchor,
            webrtc_ip=None,
            webrtc_udp="disable",
            noise_enabled=True,
            explain_enabled=False,
            custom_envelope=envelope
        )

