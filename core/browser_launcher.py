import asyncio
import threading
import os
import sys
import socket
import subprocess
import time
import urllib.request
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from .models import BrowserProfile, ProfileRunningStatus, ProxyConfig
from .profile_manager import ProfileManager
from .proxy_manager import ProxyManager
from .injections import generate_stealth_injection_script
from .cdp_injector import CDPInjector


def find_system_browser(preferred: Optional[str] = None) -> Optional[str]:
    """探测系统可用浏览器可执行文件 (优先使用定制 Native Hook 便携 Chromium 内核)"""
    candidate_roots = [
        Path(sys.executable).resolve().parent,
        Path(sys.executable).resolve().parent.parent,
        Path(__file__).resolve().parent.parent,
        Path(__file__).resolve().parent.parent.parent,
        Path(r"C:\Tools2\fingerbrowers"),
    ]
    seen_roots = set()
    unique_roots = []
    for r in candidate_roots:
        resolved = str(r)
        if resolved not in seen_roots and r.exists():
            seen_roots.add(resolved)
            unique_roots.append(r)

    # 1. 优先使用源码级商业防关联内核 (动态匹配 runtime/apostate 下版本号最高的内核)
    for root in unique_roots:
        apostate_dir = root / "runtime" / "apostate"
        if apostate_dir.exists():
            candidates = []
            for item in apostate_dir.glob("apostate-*-windows-x64"):
                exe = item / "chrome.exe"
                if exe.exists():
                    ver_str = item.name.split("-")[1] if "-" in item.name else "0"
                    try:
                        ver_tuple = [int(x) for x in ver_str.split(".")]
                    except Exception:
                        ver_tuple = [0]
                    candidates.append((ver_tuple, exe))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return str(candidates[0][1])

    # 2. 次选本地便携 Chromium 内核
    for root in unique_roots:
        local_runtime = root / "runtime" / "chrome-win" / "chrome.exe"
        if local_runtime.exists():
            return str(local_runtime)

    pref = (preferred or "").lower()
    
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    opera_candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
        r"C:\Program Files\Opera\launcher.exe",
        r"C:\Program Files (x86)\Opera\launcher.exe",
    ]
    brave_candidates = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]

    all_groups = []
    if "edge" in pref:
        all_groups = [edge_candidates, chrome_candidates, opera_candidates, brave_candidates]
    elif "opera" in pref:
        all_groups = [opera_candidates, chrome_candidates, edge_candidates, brave_candidates]
    elif "brave" in pref:
        all_groups = [brave_candidates, chrome_candidates, edge_candidates, opera_candidates]
    else:
        all_groups = [chrome_candidates, edge_candidates, opera_candidates, brave_candidates]

    for grp in all_groups:
        for p in grp:
            if os.path.exists(p):
                return p
    return None


class Win32Popen:
    """Windows 下显式绑定 WinSta0\\Default 物理桌面并兼容 subprocess.Popen 接口的进程包装器"""
    def __init__(self, args, cwd=None, env=None):
        import ctypes
        from ctypes import wintypes

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        cmd_str = subprocess.list2cmdline(args)
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.lpDesktop = "WinSta0\\Default"
        si.dwFlags = 1  # STARTF_USESHOWWINDOW
        si.wShowWindow = 1  # SW_SHOWNORMAL

        # 构建独立的 Windows Unicode 环境变量块 (消除全局 os.environ 竞态)
        env_block = None
        creation_flags = 0
        if env is not None:
            creation_flags |= 0x00000400  # CREATE_UNICODE_ENVIRONMENT
            env_str = "\0".join(f"{k}={v}" for k, v in env.items()) + "\0\0"
            env_block = ctypes.c_wchar_p(env_str)

        pi = PROCESS_INFORMATION()
        ret = ctypes.windll.kernel32.CreateProcessW(
            None,
            cmd_str,
            None,
            None,
            False,
            creation_flags,
            env_block,
            cwd,
            ctypes.byref(si),
            ctypes.byref(pi)
        )
        if not ret:
            err = ctypes.GetLastError()
            raise RuntimeError(f"Win32 CreateProcessW failed with error code {err}")

        self._hProcess = pi.hProcess
        self._hThread = pi.hThread
        self.pid = pi.dwProcessId
        self.returncode = None
        ctypes.windll.kernel32.CloseHandle(pi.hThread)

        # 绑定 Windows Job Object (确保父进程意外退出时，Windows 自动回收所有 Chromium 子进程，杜绝孤儿进程)
        self._hJob = None
        try:
            self._hJob = ctypes.windll.kernel32.CreateJobObjectW(None, None)
            if self._hJob:
                class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                    _fields_ = [
                        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD),
                    ]
                class IO_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("ReadOperationCount", ctypes.c_uint64),
                        ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64),
                        ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64),
                        ("OtherTransferCount", ctypes.c_uint64),
                    ]
                class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                    _fields_ = [
                        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryLimit", ctypes.c_size_t),
                        ("PeakJobMemoryLimit", ctypes.c_size_t),
                    ]
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                ctypes.windll.kernel32.SetInformationJobObject(
                    self._hJob, 9, ctypes.byref(info), ctypes.sizeof(info)
                )
                ctypes.windll.kernel32.AssignProcessToJobObject(self._hJob, pi.hProcess)
        except Exception:
            self._hJob = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        import ctypes
        code = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetExitCodeProcess(self._hProcess, ctypes.byref(code)):
            if code.value == 259:  # STILL_ACTIVE
                return None
            self.returncode = code.value
            return self.returncode
        return -1

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        import ctypes
        ms = int(timeout * 1000) if timeout is not None else 0xFFFFFFFF
        ctypes.windll.kernel32.WaitForSingleObject(self._hProcess, ms)
        return self.poll()

    def terminate(self):
        if hasattr(self, "_hProcess") and self._hProcess:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(self._hProcess, 1)
            self.poll()

    def kill(self):
        self.terminate()

    def __del__(self):
        try:
            if hasattr(self, "_hJob") and self._hJob:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._hJob)
        except Exception:
            pass
        try:
            if hasattr(self, "_hProcess") and self._hProcess:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._hProcess)
        except Exception:
            pass


def get_free_port() -> int:
    """获取本地可用未占用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class BrowserLauncher:
    """浏览器实例管理器（支持标准 Chromium、Chrome、Edge 以及自定义编译的内核）"""

    def __init__(
        self,
        profile_manager: ProfileManager,
        proxy_manager: Optional[ProxyManager] = None,
        subscription_manager: Optional[Any] = None
    ):
        self.profile_mgr = profile_manager
        self.proxy_mgr = proxy_manager or ProxyManager()
        if subscription_manager is None:
            from .subscription_manager import SubscriptionManager
            self.subscription_mgr = SubscriptionManager()
        else:
            self.subscription_mgr = subscription_manager
        # profile_id -> (subprocess.Popen, cdp_port, ws_endpoint)
        self.running_processes: Dict[str, Tuple[subprocess.Popen, int, str]] = {}

    def get_status(self, profile_id: str) -> ProfileRunningStatus:
        profile = self.profile_mgr.get_profile(profile_id)
        name = profile.name if profile else "Unknown"

        if profile_id in self.running_processes:
            proc, port, ws, *_ = self.running_processes[profile_id]
            if proc.poll() is None:
                return ProfileRunningStatus(
                    profile_id=profile_id,
                    name=name,
                    is_running=True,
                    pid=proc.pid,
                    cdp_port=port,
                    ws_endpoint=ws,
                    http_endpoint=f"http://127.0.0.1:{port}"
                )
            else:
                # 进程已自行退出，清理状态
                del self.running_processes[profile_id]

        return ProfileRunningStatus(
            profile_id=profile_id,
            name=name,
            is_running=False
        )

    def start_profile(self, profile_id: str, headless: bool = False, initial_url: Optional[str] = None) -> ProfileRunningStatus:
        """启动指定的指纹浏览器环境"""
        # 如果已经运行，直接返回状态
        current = self.get_status(profile_id)
        if current.is_running:
            return current

        profile = self.profile_mgr.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        # 确定浏览器内核路径 (优先寻找 profile 所属浏览器类型，如 Edge/Chrome/Opera/Brave)
        pref_browser = getattr(profile.fingerprint, "browser_name", "") or ""
        browser_exe = profile.custom_browser_path or find_system_browser(preferred=pref_browser)
        if not browser_exe or not os.path.exists(browser_exe):
            raise FileNotFoundError("No valid Chromium/Chrome/Edge browser executable found on system.")

        # 准备独立沙箱数据目录
        user_data_path = self.profile_mgr.get_user_data_path(profile.id)
        cdp_port = get_free_port()

        # 组装底层防检测启动环境变量 (进程级隔离字典，彻底解决并发全局 os.environ 竞态污染)
        fp = profile.fingerprint
        child_env = dict(os.environ)
        if hasattr(fp, "noise_seed") and fp.noise_seed:
            child_env["PHANTOM_FP_SEED"] = str(fp.noise_seed)
        if hasattr(fp, "hardware_concurrency") and fp.hardware_concurrency:
            child_env["PHANTOM_CPU_CORES"] = str(fp.hardware_concurrency)
        if hasattr(fp, "device_memory") and fp.device_memory:
            child_env["PHANTOM_RAM_GB"] = str(fp.device_memory)
        if hasattr(fp, "screen_width") and fp.screen_width:
            child_env["PHANTOM_SCREEN_WIDTH"] = str(fp.screen_width)
        if hasattr(fp, "screen_height") and fp.screen_height:
            child_env["PHANTOM_SCREEN_HEIGHT"] = str(fp.screen_height)

        args = [
            browser_exe,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={str(user_data_path)}",
            f"--lang={','.join(fp.languages)}",
            f"--window-size={fp.screen_width},{fp.screen_height}",
            # 防检测通用参数 (坚决杜绝 --no-sandbox，彻底消除顶部黄条警告与自动化沙箱泄漏)
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-infobars",
            "--password-store=basic",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=RendererCodeIntegrity",
            # WebRTC 泄露控制策略
            f"--webrtc-ip-handling-policy={fp.webrtc_policy}",
        ]

        # 商业级防指纹内核 (Apostate C++ 源码级防关联补丁支持) 原生开关集成
        is_anti_detect_kernel = "apostate" in str(browser_exe).lower()
        if is_anti_detect_kernel:
            seed = str(getattr(fp, "noise_seed", "") or "888888")
            
            # 强化 macOS 与系统人格判定逻辑 (覆盖 platform_persona、os_name、platform 及 UA)
            is_mac = (
                "mac" in (getattr(fp, "platform_persona", "") or "").lower() or
                "mac" in (getattr(fp, "os_name", "") or "").lower() or
                "mac" in (getattr(fp, "platform", "") or "").lower() or
                "macintosh" in (getattr(fp, "user_agent", "") or "").lower()
            )
            is_linux = "linux" in (getattr(fp, "os_name", "") or "").lower() or "linux" in (getattr(fp, "platform", "") or "").lower()
            platform = "macos" if is_mac else ("linux" if is_linux else "windows")

            if is_mac:
                fp.platform = "MacIntel"
                fp.os_name = "macOS"

            # 真实硬件探针一致性保护
            max_cores = os.cpu_count() or 8
            cores = min(int(fp.hardware_concurrency or 8), max_cores) if not is_mac else min(int(fp.hardware_concurrency or 8), 12)
            
            # 探测宿主机物理内存 GB
            host_mem_gb = 16
            try:
                import ctypes
                from ctypes import wintypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                                ("sullAvailExtendedVirtual", ctypes.c_uint64)]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    host_mem_gb = int(stat.ullTotalPhys / (1024 ** 3))
            except Exception:
                pass
            
            # 合理对齐标准设备内存桶 (2, 4, 8, 16, 32)
            requested_mem = int(fp.device_memory or (16 if is_mac else 8))
            safe_mem = requested_mem if requested_mem <= host_mem_gb else (16 if host_mem_gb >= 16 else (8 if host_mem_gb >= 8 else 4))

            # 所有人格统一走底层 --apostate-profile JSON 载荷
            # 严格注入 Platform、Client Hints、CPU、RAM、GPU 显卡、Retina/DPR、系统语音、音频缓冲、网络与全量字体白名单，
            # 让 Python 层负责生成自洽 envelope，内核负责原生执行，彻底消除各平台指纹自相矛盾。
            from .envelope_builder import build_unified_envelope, encode_envelope_payload
            
            envelope = getattr(fp, "custom_envelope", None)
            if not envelope:
                envelope = build_unified_envelope(
                    platform_persona=fp.platform_persona or platform,
                    user_agent=fp.user_agent,
                    cpu_cores=cores,
                    memory_gb=safe_mem,
                    gpu_vendor=fp.webgl_vendor,
                    gpu_renderer=fp.webgl_renderer,
                    screen_width=fp.screen_width,
                    screen_height=fp.screen_height,
                    screen_avail_width=fp.screen_avail_width,
                    screen_avail_height=fp.screen_avail_height,
                    device_pixel_ratio=fp.device_scale_factor or (2.0 if is_mac else 1.0),
                    os_version=getattr(fp, "os_version", "10.0.0"),
                    languages=fp.languages,
                    timezone=fp.timezone
                )

            env_b64 = encode_envelope_payload(envelope)
            args.append(f"--user-agent={fp.user_agent}")
            args.extend([
                f"--apostate-profile={env_b64}",
                f"--fingerprint={seed}",
                f"--fingerprint-platform={platform}"
            ])
            
            # 全管线默认启用底层确定性微噪（Canvas、Audio、WebGL readback 亚像素混淆）
            if getattr(fp, "canvas_noise_enabled", True) or getattr(fp, "noise_enabled", True):
                args.append("--fingerprint-noise")
            if getattr(fp, "timezone", ""):
                args.append(f"--fingerprint-timezone={fp.timezone}")
            if getattr(fp, "languages", None) and len(fp.languages) > 0:
                args.append(f"--fingerprint-locale={fp.languages[0]}")
            if getattr(fp, "fingerprint_anchor", ""):
                args.append(f"--fingerprint-anchor={fp.fingerprint_anchor}")

            # WebRTC 穿透与 IP 绑定
            if getattr(fp, "webrtc_ip", ""):
                args.append(f"--fingerprint-webrtc-ip={fp.webrtc_ip}")
            if getattr(fp, "webrtc_udp", ""):
                args.append(f"--fingerprint-webrtc-udp={fp.webrtc_udp}")

            # 诊断分析报告开关
            if getattr(fp, "explain_enabled", False):
                args.append("--fingerprint-explain")
        else:
            args.append(f"--user-agent={fp.user_agent}")



        if headless:
            args.append("--headless=new")

        # 代理支持 (支持订阅节点 sub_node_id、独立代理 proxy_id 与嵌入代理 profile.proxy)
        proxy_cfg: Optional[ProxyConfig] = None
        if profile.sub_node_id and self.subscription_mgr:
            proxy_cfg = self.subscription_mgr.get_profile_proxy(profile.sub_node_id, profile.id)
        if not proxy_cfg and profile.proxy_id and self.proxy_mgr:
            p_item = self.proxy_mgr.get_proxy(profile.proxy_id)
            if p_item:
                proxy_cfg = p_item.to_proxy_config()
        if not proxy_cfg and profile.proxy and profile.proxy.enabled:
            proxy_cfg = profile.proxy

        if proxy_cfg and proxy_cfg.enabled:
            proxy_arg = proxy_cfg.to_chrome_arg()
            if proxy_arg:
                args.append(proxy_arg)

        # 附加用户自定义参数
        if profile.custom_args:
            args.extend(profile.custom_args)

        # 附加启动目标网址 (无则展示默认防关联欢迎页/空白页)
        target_url = initial_url or "about:blank"
        args.append(target_url)

        # 启动浏览器进程 (显式绑定 WinSta0\Default 物理桌面并声明 SW_SHOWNORMAL，确保物理屏幕正常弹出前台视窗)
        if sys.platform == "win32":
            try:
                proc = Win32Popen(args, env=child_env)
            except Exception:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 1
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                    env=child_env
                )
        else:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env
            )

        # 等待 CDP 端口就绪，提取 WebSocketDebuggerUrl
        ws_endpoint = ""
        max_retries = 30
        for _ in range(max_retries):
            if proc.poll() is not None:
                raise RuntimeError("Browser process terminated immediately on launch.")
            try:
                url = f"http://127.0.0.1:{cdp_port}/json/version"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    data = json.loads(resp.read().decode())
                    ws_endpoint = data.get("webSocketDebuggerUrl", "")
                    if ws_endpoint:
                        break
            except Exception:
                time.sleep(0.2)

        if not ws_endpoint:
            proc.kill()
            raise TimeoutError(f"Failed to connect to browser CDP port {cdp_port} within timeout.")

        # 启动 CDP 自动守护注入器（确保所有打开的网页、Worker、标签页自动注入 Stealth 与 Client Hints 对齐，并自动响应代理认证）
        geo_info = None
        try:
            from .geoip_service import GeoIPService
            geo_info = GeoIPService.resolve_profile_target_geo(profile, self.proxy_mgr, self.subscription_mgr)
        except Exception:
            pass

        injector = CDPInjector(
            ws_endpoint=ws_endpoint,
            fp=profile.fingerprint,
            proxy_config=proxy_cfg,
            profile_id=profile.id,
            user_data_path=user_data_path,
            geo_info=geo_info,
            proc=proc,
            initial_url=initial_url
        )
        injector.start()
        self.running_processes[profile_id] = (proc, cdp_port, ws_endpoint, injector)

        # 如果指定了初始目标网址且非 about:blank，通过 CDP 协议打开该网址并优雅替换初始空白页
        if initial_url and initial_url.strip() and initial_url != "about:blank":
            try:
                time.sleep(0.3)
                list_url = f"http://127.0.0.1:{cdp_port}/json/list"
                with urllib.request.urlopen(urllib.request.Request(list_url), timeout=2.0) as resp:
                    targets = json.loads(resp.read().decode())
                blank_ids = [t["id"] for t in targets if t.get("type") == "page"]

                # 开启目标测试网址
                new_url = f"http://127.0.0.1:{cdp_port}/json/new?{initial_url}"
                urllib.request.urlopen(urllib.request.Request(new_url, method="PUT"), timeout=3.0)

                # 关闭先前的空白页
                for b_id in blank_ids:
                    try:
                        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/close/{b_id}", method="PUT"), timeout=1.0)
                    except Exception:
                        pass
            except Exception as e:
                pass

        return ProfileRunningStatus(
            profile_id=profile_id,
            name=profile.name,
            is_running=True,
            pid=proc.pid,
            cdp_port=cdp_port,
            ws_endpoint=ws_endpoint,
            http_endpoint=f"http://127.0.0.1:{cdp_port}",
            started_at=time.strftime("%Y-%m-%d %H:%M:%S")
        )

    def stop_profile(self, profile_id: str) -> bool:
        """关闭指定的指纹浏览器环境"""
        if profile_id not in self.running_processes:
            return True
        proc, _, _, injector = self.running_processes[profile_id]
        if injector:
            injector.stop()
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        finally:
            if profile_id in self.running_processes:
                del self.running_processes[profile_id]
            if self.subscription_mgr:
                try:
                    self.subscription_mgr.release_profile_proxy(profile_id)
                except Exception:
                    pass
        return True

    def stop_all(self):
        """关闭所有运行中的实例"""
        for pid in list(self.running_processes.keys()):
            self.stop_profile(pid)
