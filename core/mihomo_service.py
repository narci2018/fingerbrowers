import copy
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from .models import SubscriptionNode


def get_free_port(start: int = 28000, end: int = 35000) -> int:
    """获取一个未被占用的本地空闲端口"""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


class MihomoService:
    """Mihomo (Clash Meta) 内核服务管理器
    提供全协议代理支持: VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC, WireGuard, HTTP, SOCKS5
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(os.getcwd())

        self.bin_path = self._find_binary()
        self.data_dir = self.base_dir / "data" / "mihomo"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._ready: bool = False
        self.status_message: str = "正在后台就绪核心引擎与 GeoIP 资产库..."
        self._init_event = threading.Event()

        # 记录各 Profile 独立代理隧道进程 {profile_id: subprocess.Popen}
        self._active_tunnels: Dict[str, subprocess.Popen] = {}
        self._tunnel_ports: Dict[str, int] = {}

        # 启动后台守护线程进行核心资产准备与就绪探测，绝对不卡住应用启动与 GUI 渲染
        self._init_thread = threading.Thread(target=self._async_init, daemon=True, name="MihomoAsyncInit")
        self._init_thread.start()

    def _async_init(self):
        """后台异步准备 GeoIP 数据库与核心二进制校验"""
        try:
            self._ensure_geo_assets()
            if self.bin_path.exists():
                self._ready = True
                self.status_message = "核心网络引擎已就绪"
                logging.info(f"Mihomo 核心服务与 GeoIP 资产库后台加载就绪: {self.bin_path}")
            else:
                self._ready = False
                self.status_message = f"未找到内核二进制文件: {self.bin_path}"
                logging.warning(self.status_message)
        except Exception as e:
            self._ready = False
            self.status_message = f"核心组件准备异常: {e}"
            logging.error(f"Mihomo 异步初始化失败: {e}", exc_info=True)
        finally:
            self._init_event.set()

    def is_ready(self) -> bool:
        return self._ready

    def wait_until_ready(self, timeout: float = 3.0) -> bool:
        if self._ready:
            return True
        return self._init_event.wait(timeout=timeout)

    def _link_or_copy(self, src: Path, dst: Path):
        """优先使用 NTFS 硬链接（毫秒级、0额外磁盘占用），若跨卷或失败则回退到快速复制"""
        if dst.exists():
            return
        try:
            os.link(src, dst)
        except Exception:
            try:
                shutil.copy(src, dst)
            except Exception:
                pass

    def _find_binary(self) -> Path:
        """寻找 mihomo.exe 可执行文件"""
        # 1. 优先找项目内 bin/mihomo.exe
        p1 = self.base_dir / "bin" / "mihomo.exe"
        if p1.exists():
            return p1

        # 2. 找 PyInstaller 打包目录 (sys._MEIPASS)
        if hasattr(sys, "_MEIPASS"):
            meipass_p = Path(sys._MEIPASS) / "bin" / "mihomo.exe"
            if meipass_p.exists():
                return meipass_p
            meipass_root = Path(sys._MEIPASS) / "mihomo.exe"
            if meipass_root.exists():
                return meipass_root

        # 3. 找同级目录
        p3 = self.base_dir / "mihomo.exe"
        if p3.exists():
            return p3

        # 4. 找 C:\Tools2\.androidcheck\src-tauri\binaries\mihomo.exe 作为兜底
        p4 = Path(r"C:\Tools2\.androidcheck\src-tauri\binaries\mihomo.exe")
        if p4.exists():
            return p4

        return p1

    def _ensure_geo_assets(self):
        """确保 Country.mmdb 和 ASN.mmdb 资源就绪"""
        bin_dir = self.base_dir / "bin"
        for name in ["Country.mmdb", "ASN.mmdb"]:
            target = self.data_dir / name
            if not target.exists():
                src = bin_dir / name
                if src.exists():
                    self._link_or_copy(src, target)
                else:
                    src2 = Path(r"C:\Tools2\freesub\runtime") / name
                    if src2.exists():
                        self._link_or_copy(src2, target)

    def build_proxy_dict(self, node: SubscriptionNode, proxy_tag: str) -> dict:
        """为 Mihomo 准备代理配置字典"""
        if node.raw_config and isinstance(node.raw_config, dict):
            p = copy.deepcopy(node.raw_config)
            p["name"] = proxy_tag
            return p

        # 基础回退构建
        proto = node.type.lower()
        if "sock" in proto:
            p_type = "socks5"
        elif proto in ("http", "https"):
            p_type = "http"
        else:
            p_type = proto

        p = {
            "name": proxy_tag,
            "type": p_type,
            "server": node.host,
            "port": node.port,
            "udp": True
        }
        if proto == "https":
            p["tls"] = True
        if node.username:
            p["username"] = node.username
        if node.password:
            p["password"] = node.password
        return p

    # ==========================================
    # 批量测延迟 (并发 REST API)
    # ==========================================

    def test_nodes_latency(
        self,
        nodes: List[SubscriptionNode],
        timeout_ms: int = 3000
    ) -> Dict[str, Dict[str, Any]]:
        """使用 Mihomo 内核并发测试所有节点真实往返时延 (RTT ms)"""
        results: Dict[str, Dict[str, Any]] = {}
        if not nodes:
            return results

        if not self._ready:
            self.wait_until_ready(timeout=4.0)

        if not self.bin_path.exists():
            logging.error(f"Mihomo binary not found at {self.bin_path}")
            return {n.id: {"status": "failed", "latency_ms": None} for n in nodes}

        test_dir = self.data_dir / f"test_lat_{int(time.time()*1000)}"
        test_dir.mkdir(parents=True, exist_ok=True)

        # 快速硬链/拷贝 mmdb 到测试目录
        for name in ["Country.mmdb", "ASN.mmdb"]:
            f = self.data_dir / name
            if f.exists():
                self._link_or_copy(f, test_dir / name)

        ctrl_port = get_free_port(31000, 32000)
        mixed_port = get_free_port(ctrl_port + 1, 33000)

        # 构建代理清单与 ID 映射
        node_map: Dict[str, SubscriptionNode] = {}
        proxies_config: List[dict] = []
        for idx, node in enumerate(nodes):
            tag = f"n_{idx}"
            node_map[tag] = node
            proxies_config.append(self.build_proxy_dict(node, tag))

        config = {
            "mixed-port": mixed_port,
            "external-controller": f"127.0.0.1:{ctrl_port}",
            "mode": "rule",
            "log-level": "warning",
            "dns": {
                "enable": True,
                "nameserver": ["223.5.5.5", "119.29.29.29", "https://dns.alidns.com/dns-query"],
                "fallback": ["8.8.8.8", "1.1.1.1"]
            },
            "proxies": proxies_config
        }

        cfg_file = test_dir / "config.yaml"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

        proc = None
        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                [str(self.bin_path), "-d", str(test_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            # 等待 API 就绪
            api_ready = False
            for _ in range(25):
                time.sleep(0.1)
                try:
                    r = requests.get(f"http://127.0.0.1:{ctrl_port}/version", timeout=0.5)
                    if r.status_code == 200:
                        api_ready = True
                        break
                except Exception:
                    pass

            if not api_ready:
                logging.error("Mihomo test controller failed to start")
                return {n.id: {"status": "failed", "latency_ms": None} for n in nodes}

            # 并发探测各节点延迟
            def test_single_tag(tag: str) -> Tuple[str, Optional[int]]:
                try:
                    url = f"http://127.0.0.1:{ctrl_port}/proxies/{tag}/delay?url=http://cp.cloudflare.com/generate_204&timeout={timeout_ms}"
                    resp = requests.get(url, timeout=(timeout_ms / 1000.0) + 1.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if "delay" in data:
                            return (tag, int(data["delay"]))
                except Exception:
                    pass
                return (tag, None)

            workers = min(35, max(5, len(node_map)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(test_single_tag, tag) for tag in node_map]
                for f in as_completed(futures):
                    tag, latency = f.result()
                    node = node_map[tag]
                    if latency is not None:
                        results[node.id] = {
                            "status": "active",
                            "latency_ms": latency
                        }
                    else:
                        results[node.id] = {
                            "status": "failed",
                            "latency_ms": -1
                        }

        except Exception as e:
            logging.error(f"Error testing nodes latency with Mihomo: {e}")
        finally:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            try:
                shutil.rmtree(test_dir, ignore_errors=True)
            except Exception:
                pass

        # 补全未测到的节点
        for n in nodes:
            if n.id not in results:
                results[n.id] = {"status": "failed", "latency_ms": -1}

        return results

    # ==========================================
    # 单节点测速 (真实下行吞吐 + IP/国家探测)
    # ==========================================

    def test_node_speed(
        self,
        node: SubscriptionNode,
        duration_sec: int = 5
    ) -> Dict[str, Any]:
        """使用 Mihomo 创建单节点通道，真实测试下行吞吐速率并探测出口 IP 和国家"""
        res = {
            "status": "failed",
            "latency_ms": None,
            "speed_mbps": None,
            "exit_ip": None,
            "country": None
        }

        if not self._ready:
            self.wait_until_ready(timeout=4.0)

        if not self.bin_path.exists():
            return res

        test_dir = self.data_dir / f"test_spd_{int(time.time()*1000)}"
        test_dir.mkdir(parents=True, exist_ok=True)

        for name in ["Country.mmdb", "ASN.mmdb"]:
            f = self.data_dir / name
            if f.exists():
                self._link_or_copy(f, test_dir / name)

        mixed_port = get_free_port(33100, 34000)
        proxy_cfg = self.build_proxy_dict(node, "target_node")

        config = {
            "mixed-port": mixed_port,
            "mode": "rule",
            "log-level": "warning",
            "dns": {
                "enable": True,
                "nameserver": ["223.5.5.5", "119.29.29.29"],
                "fallback": ["8.8.8.8", "1.1.1.1"]
            },
            "proxies": [proxy_cfg],
            "rules": [
                "MATCH,target_node"
            ]
        }

        cfg_file = test_dir / "config.yaml"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

        proc = None
        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                [str(self.bin_path), "-d", str(test_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            time.sleep(1.2)

            proxy_socks = f"socks5h://127.0.0.1:{mixed_port}"
            proxies = {"http": proxy_socks, "https": proxy_socks}

            # 1. 探测出口 IP 与地理位置 + 探测延迟
            t0 = time.time()
            try:
                ip_resp = requests.get("http://ip-api.com/json", proxies=proxies, timeout=6)
                if ip_resp.status_code == 200:
                    ip_data = ip_resp.json()
                    res["latency_ms"] = int((time.time() - t0) * 1000)
                    res["exit_ip"] = ip_data.get("query")
                    res["country"] = ip_data.get("country")
                    res["status"] = "active"
            except Exception:
                try:
                    cf_resp = requests.get("http://cp.cloudflare.com/generate_204", proxies=proxies, timeout=5)
                    if cf_resp.status_code in (200, 204):
                        res["latency_ms"] = int((time.time() - t0) * 1000)
                        res["status"] = "active"
                except Exception:
                    pass

            # 2. 测速：分块下载 CDN 文件
            speed_targets = [
                "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js",
                "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
                "https://code.jquery.com/jquery-3.7.1.min.js"
            ]

            total_bytes = 0
            start_time = time.time()
            for url in speed_targets:
                if time.time() - start_time >= duration_sec:
                    break
                try:
                    with requests.get(url, proxies=proxies, stream=True, timeout=5) as r:
                        if r.status_code == 200:
                            for chunk in r.iter_content(chunk_size=16384):
                                if chunk:
                                    total_bytes += len(chunk)
                                if time.time() - start_time >= duration_sec:
                                    break
                except Exception:
                    continue

            elapsed = time.time() - start_time
            if total_bytes > 0 and elapsed > 0:
                mbps = round((total_bytes * 8) / (elapsed * 1024 * 1024), 2)
                res["speed_mbps"] = mbps
                res["status"] = "active"

        except Exception as e:
            logging.error(f"Error testing node speed: {e}")
        finally:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            try:
                shutil.rmtree(test_dir, ignore_errors=True)
            except Exception:
                pass

        return res

    # ==========================================
    # Profile 运行时隧道集成
    # ==========================================

    def start_profile_tunnel(self, profile_id: str, node: SubscriptionNode) -> Tuple[str, int]:
        """为指纹环境启动专用协议本地桥接隧道 (SOCKS5/HTTP 混合端口)
        Chromium 无需感知具体复杂协议 (VLESS/VMess/Trojan/SS)，直接连接本地端口
        """
        # 如果已有运行的隧道，先清理
        self.stop_profile_tunnel(profile_id)

        if not self._ready:
            self.wait_until_ready(timeout=4.0)

        tunnel_port = get_free_port(27000, 30000)
        profile_dir = self.data_dir / "profiles" / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        for name in ["Country.mmdb", "ASN.mmdb"]:
            f = self.data_dir / name
            if f.exists():
                self._link_or_copy(f, profile_dir / name)

        proxy_cfg = self.build_proxy_dict(node, "profile_node")
        config = {
            "mixed-port": tunnel_port,
            "mode": "rule",
            "log-level": "warning",
            "dns": {
                "enable": True,
                "nameserver": ["223.5.5.5", "119.29.29.29"],
                "fallback": ["8.8.8.8", "1.1.1.1"]
            },
            "proxies": [proxy_cfg],
            "rules": [
                "MATCH,profile_node"
            ]
        }

        cfg_file = profile_dir / "config.yaml"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [str(self.bin_path), "-d", str(profile_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags
        )

        self._active_tunnels[profile_id] = proc
        self._tunnel_ports[profile_id] = tunnel_port
        time.sleep(0.8)

        logging.info(f"Started Mihomo proxy tunnel for profile {profile_id} on 127.0.0.1:{tunnel_port} [{node.type}]")
        return ("127.0.0.1", tunnel_port)

    def stop_profile_tunnel(self, profile_id: str):
        """停止指纹环境关联的协议隧道"""
        if profile_id in self._active_tunnels:
            proc = self._active_tunnels.pop(profile_id, None)
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=1.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._tunnel_ports.pop(profile_id, None)

        profile_dir = self.data_dir / "profiles" / profile_id
        if profile_dir.exists():
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass
