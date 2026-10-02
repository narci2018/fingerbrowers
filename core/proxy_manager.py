import json
import os
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import requests

from .models import ProxyItem, ProxyConfig


class ProxyManager:
    """独立代理配置仓库管理器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.data_dir / "proxies.json"
        self._ensure_storage()

    def _ensure_storage(self):
        if not self.storage_file.exists():
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load_raw(self) -> List[dict]:
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_raw(self, data: List[dict]):
        tmp_file = self.storage_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_file.replace(self.storage_file)

    def list_proxies(self) -> List[ProxyItem]:
        """获取所有已保存的独立代理"""
        raw = self._load_raw()
        return [ProxyItem(**item) for item in raw]

    def get_proxy(self, proxy_id: str) -> Optional[ProxyItem]:
        """获取单个代理详情"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == proxy_id:
                return ProxyItem(**item)
        return None

    def create_proxy(
        self,
        name: str,
        type: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> ProxyItem:
        """创建全新独立代理"""
        item = ProxyItem(
            name=name.strip(),
            type=type.lower().strip(),
            host=host.strip(),
            port=int(port),
            username=username.strip() if username else None,
            password=password.strip() if password else None,
            status="untested",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        raw = self._load_raw()
        raw.append(item.model_dump())
        self._save_raw(raw)
        return item

    def update_proxy(self, proxy_id: str, update_data: Dict[str, Any]) -> Optional[ProxyItem]:
        """修改指定代理配置"""
        raw = self._load_raw()
        updated_item = None
        for i, item in enumerate(raw):
            if item.get("id") == proxy_id:
                # 保留原有 id 和 created_at
                for k, v in update_data.items():
                    if k not in ["id", "created_at"] and v is not None:
                        item[k] = v
                item["updated_at"] = datetime.now().isoformat()
                raw[i] = item
                updated_item = ProxyItem(**item)
                break

        if updated_item:
            self._save_raw(raw)
        return updated_item

    def delete_proxy(self, proxy_id: str) -> bool:
        """删除指定代理"""
        raw = self._load_raw()
        initial_len = len(raw)
        raw = [item for item in raw if item.get("id") != proxy_id]
        if len(raw) < initial_len:
            self._save_raw(raw)
            return True
        return False

    def test_proxy(
        self,
        host: str,
        port: int,
        type: str = "http",
        username: Optional[str] = None,
        password: Optional[str] = None,
        proxy_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        测试 HTTP / SOCKS5 代理连通性、探测出口 IP、国家城市与延迟。
        支持 socks5h:// 远程 DNS 解析，防止本地 DNS 泄露。
        """
        proxy_type = type.lower().strip()
        auth_part = ""
        if username and password:
            auth_part = f"{username}:{password}@"
        elif username:
            auth_part = f"{username}@"

        # 优先使用 socks5h 以支持代理端远程 DNS 解析，https 代理使用 https 协议头
        if "sock" in proxy_type:
            scheme = "socks5h"
        elif proxy_type == "https":
            scheme = "https"
        else:
            scheme = "http"
        proxy_url = f"{scheme}://{auth_part}{host}:{port}"

        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        start_time = time.time()
        result = {
            "success": False,
            "latency_ms": 0,
            "exit_ip": None,
            "country": None,
            "city": None,
            "timezone": None,
            "isp": None,
            "error": None
        }

        try:
            # 优先请求 ip-api.com 获取详尽归属地及对应时区
            resp = requests.get(
                "http://ip-api.com/json",
                proxies=proxies,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            result["latency_ms"] = elapsed_ms

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    result["success"] = True
                    result["exit_ip"] = data.get("query")
                    result["country"] = data.get("country")
                    result["city"] = data.get("city")
                    result["timezone"] = data.get("timezone")
                    result["isp"] = data.get("isp")
                else:
                    # 备选 ipify 查询
                    result["success"] = True
                    result["exit_ip"] = data.get("query", "Connected")
            else:
                result["error"] = f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            # 尝试备用轻量出口探测 api.ipify.org
            try:
                sub_resp = requests.get(
                    "https://api.ipify.org?format=json",
                    proxies=proxies,
                    timeout=5
                )
                elapsed_ms = int((time.time() - start_time) * 1000)
                if sub_resp.status_code == 200:
                    data = sub_resp.json()
                    result["success"] = True
                    result["latency_ms"] = elapsed_ms
                    result["exit_ip"] = data.get("ip")
                    result["country"] = "Global Proxy"
                else:
                    result["error"] = str(e)
            except Exception as e2:
                result["error"] = str(e)

        # 如果传入了 proxy_id，自动回写并持久化测试结果
        if proxy_id:
            now_iso = datetime.now().isoformat()
            if result["success"]:
                self.update_proxy(proxy_id, {
                    "status": "active",
                    "latency_ms": result["latency_ms"],
                    "exit_ip": result["exit_ip"],
                    "country": result["country"],
                    "city": result["city"],
                    "timezone": result["timezone"],
                    "last_tested_at": now_iso
                })
            else:
                self.update_proxy(proxy_id, {
                    "status": "failed",
                    "last_tested_at": now_iso
                })

        return result

    def batch_test_proxies(self, proxy_ids: Optional[List[str]] = None, max_workers: int = 5) -> List[Dict[str, Any]]:
        """并发批量检测多个独立代理"""
        from concurrent.futures import ThreadPoolExecutor
        proxies = self.list_proxies()
        if proxy_ids:
            target_ids = set(proxy_ids)
            proxies = [p for p in proxies if p.id in target_ids]

        def _test_single(item):
            res = self.test_proxy(
                host=item.host,
                port=item.port,
                type=item.type,
                username=item.username,
                password=item.password,
                proxy_id=item.id
            )
            res["proxy_id"] = item.id
            res["proxy_name"] = item.name
            return res

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_test_single, proxies))

        return results

    def batch_import_proxies(self, content: str, default_type: str = "http") -> Dict[str, Any]:
        """
        批量导入代理文本（支持多行文本、常见代理格式及 JSON）
        支持格式：
        1. http://user:pass@host:port 或 socks5://host:port
        2. host:port:user:pass
        3. host:port
        4. JSON 列表
        """
        imported = []
        failed = []
        content = content.strip()
        if not content:
            return {"imported": 0, "failed": 0, "items": []}

        # 尝试 JSON 格式
        if content.startswith("[") and content.endswith("]"):
            try:
                arr = json.loads(content)
                for entry in arr:
                    if isinstance(entry, dict) and "host" in entry and "port" in entry:
                        p = self.create_proxy(
                            name=entry.get("name") or f"Proxy-{entry['host']}:{entry['port']}",
                            type=entry.get("type", default_type),
                            host=str(entry["host"]),
                            port=int(entry["port"]),
                            username=entry.get("username"),
                            password=entry.get("password")
                        )
                        imported.append(p)
                return {"imported": len(imported), "failed": len(failed), "items": imported}
            except Exception:
                pass

        # 按行解析
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        for line in lines:
            try:
                p_type = default_type
                p_host = ""
                p_port = 0
                p_user = None
                p_pass = None

                # 协议头格式: http://user:pass@host:port
                if "://" in line:
                    from urllib.parse import urlsplit
                    sp = urlsplit(line)
                    p_type = sp.scheme or default_type
                    p_host = sp.hostname or ""
                    p_port = sp.port or 80
                    p_user = sp.username
                    p_pass = sp.password
                elif line.count(":") == 3:
                    # host:port:user:pass
                    parts = line.split(":")
                    p_host = parts[0].strip()
                    p_port = int(parts[1].strip())
                    p_user = parts[2].strip()
                    p_pass = parts[3].strip()
                elif line.count(":") == 1:
                    # host:port
                    parts = line.split(":")
                    p_host = parts[0].strip()
                    p_port = int(parts[1].strip())
                else:
                    failed.append({"line": line, "reason": "无法识别的格式"})
                    continue

                if p_host and p_port > 0:
                    name = f"Proxy-{p_host}:{p_port}"
                    item = self.create_proxy(
                        name=name,
                        type=p_type,
                        host=p_host,
                        port=p_port,
                        username=p_user,
                        password=p_pass
                    )
                    imported.append(item)
                else:
                    failed.append({"line": line, "reason": "主机或端口无效"})
            except Exception as ex:
                failed.append({"line": line, "reason": str(ex)})

        return {"imported": len(imported), "failed": len(failed), "items": imported}

    def export_proxies(self, format: str = "text", proxy_ids: Optional[List[str]] = None) -> str:
        """批量导出代理配置（支持 text, json, csv）"""
        proxies = self.list_proxies()
        if proxy_ids:
            target_ids = set(proxy_ids)
            proxies = [p for p in proxies if p.id in target_ids]

        fmt = format.lower().strip()
        if fmt == "json":
            return json.dumps([p.model_dump() for p in proxies], ensure_ascii=False, indent=2)
        elif fmt == "csv":
            import io
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Name", "Type", "Host", "Port", "Username", "Password", "Status", "Latency_MS", "Exit_IP", "Country"])
            for p in proxies:
                writer.writerow([
                    p.name, p.type, p.host, p.port, p.username or "", p.password or "",
                    p.status, p.latency_ms or "", p.exit_ip or "", p.country or ""
                ])
            return output.getvalue()
        else:
            # 默认 text 格式：每行一个 URL
            lines = []
            for p in proxies:
                if p.username and p.password:
                    lines.append(f"{p.type}://{p.username}:{p.password}@{p.host}:{p.port}")
                else:
                    lines.append(f"{p.type}://{p.host}:{p.port}")
            return "\n".join(lines)
