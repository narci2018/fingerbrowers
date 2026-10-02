import copy
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .mihomo_service import MihomoService
from .models import ProxyConfig, SubscriptionItem, SubscriptionNode
from .subscription_parser import parse_all_subscription_nodes


class SubscriptionManager:
    """订阅管理与节点测速/测延迟核心控制器 (全面支持 VLESS, VMess, Trojan, SS, Hysteria2, HTTP, SOCKS5)"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.data_dir / "subscriptions.json"
        self._ensure_storage()

        # 初始化 Mihomo 全协议代理内核服务
        self.mihomo_service = MihomoService(base_dir=str(self.data_dir.parent))

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

    # ==========================
    # 订阅解析引擎 (全协议支持)
    # ==========================

    def parse_nodes_from_text(self, text: str, sub_id: str) -> List[SubscriptionNode]:
        """从订阅文本解析出节点列表 (Clash YAML / Base64 / URI 协议)"""
        return parse_all_subscription_nodes(text, sub_id)

    def fetch_nodes_from_url(self, url: str, sub_id: str) -> List[SubscriptionNode]:
        """从远程订阅链接拉取并解析全协议节点"""
        clean_url = url.strip()
        # 1. 优先使用 ClashMeta 标识，指示服务端下发 VLESS / Reality / Hysteria2 等 Meta 扩展协议配置
        meta_headers = {
            "User-Agent": "ClashMeta; Mihomo; clash.meta; ClashX Meta",
            "Accept": "*/*"
        }
        try:
            resp = requests.get(clean_url, headers=meta_headers, timeout=20)
            resp.encoding = "utf-8"
            nodes = self.parse_nodes_from_text(resp.text, sub_id)
            if nodes:
                return nodes
        except Exception as e:
            logging.warning(f"ClashMeta UA fetch failed for {clean_url}: {e}")

        # 2. 备用回退：部分机场对 ClashMeta 屏蔽，仅向 v2rayN / Shadowrocket 下发 Base64/URI 协议
        fallback_headers = {
            "User-Agent": "v2rayN/6.23; Shadowrocket/2.2.0",
            "Accept": "*/*"
        }
        try:
            resp = requests.get(clean_url, headers=fallback_headers, timeout=20)
            resp.encoding = "utf-8"
            nodes = self.parse_nodes_from_text(resp.text, sub_id)
            if nodes:
                return nodes
        except Exception as e:
            logging.warning(f"Fallback UA fetch failed for {clean_url}: {e}")

        return []

    # ==========================
    # 订阅 CRUD
    # ==========================

    def list_subscriptions(self) -> List[SubscriptionItem]:
        """获取所有订阅列表"""
        raw = self._load_raw()
        return [SubscriptionItem(**item) for item in raw]

    def get_subscription(self, sub_id: str) -> Optional[SubscriptionItem]:
        """获取单个订阅完整详情（包含节点）"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                return SubscriptionItem(**item)
        return None

    def create_subscription(
        self,
        name: str,
        url: Optional[str] = "",
        source_text: Optional[str] = "",
        fetch_now: bool = True
    ) -> SubscriptionItem:
        """创建全新订阅并可选择立即拉取解析节点"""
        sub = SubscriptionItem(
            name=name.strip(),
            url=url.strip() if url else "",
            source_text=source_text.strip() if source_text else "",
            node_count=0,
            nodes=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        nodes = []
        if fetch_now:
            if sub.url:
                try:
                    nodes = self.fetch_nodes_from_url(sub.url, sub.id)
                except Exception as e:
                    logging.warning(f"Failed to fetch subscription URL: {e}")
            if not nodes and sub.source_text:
                nodes = self.parse_nodes_from_text(sub.source_text, sub.id)

        sub.nodes = nodes
        sub.node_count = len(nodes)
        if nodes:
            sub.last_updated_at = datetime.now().isoformat()

        raw = self._load_raw()
        raw.append(sub.dict())
        self._save_raw(raw)
        return sub

    def update_subscription(
        self,
        sub_id: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        source_text: Optional[str] = None
    ) -> Optional[SubscriptionItem]:
        """更新订阅基础信息"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                if name is not None:
                    item["name"] = name.strip()
                if url is not None:
                    item["url"] = url.strip()
                if source_text is not None:
                    item["source_text"] = source_text.strip()
                item["updated_at"] = datetime.now().isoformat()
                self._save_raw(raw)
                return SubscriptionItem(**item)
        return None

    def refresh_subscription(self, sub_id: str) -> Optional[SubscriptionItem]:
        """重新从远程 URL 或源文本拉取并刷新节点列表"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                url = item.get("url", "")
                text = item.get("source_text", "")
                new_nodes = []
                if url:
                    try:
                        new_nodes = self.fetch_nodes_from_url(url, sub_id)
                    except Exception as e:
                        logging.warning(f"Failed to refresh subscription from url: {e}")
                if not new_nodes and text:
                    new_nodes = self.parse_nodes_from_text(text, sub_id)

                if new_nodes:
                    # 保留已有节点的测速探测缓存
                    old_cache = {
                        f"{n.get('host')}:{n.get('port')}": n
                        for n in item.get("nodes", [])
                    }
                    merged_nodes = []
                    for n in new_nodes:
                        key = f"{n.host}:{n.port}"
                        if key in old_cache:
                            old = old_cache[key]
                            n.status = old.get("status", "untested")
                            n.latency_ms = old.get("latency_ms")
                            n.speed_mbps = old.get("speed_mbps")
                            n.exit_ip = old.get("exit_ip")
                            n.country = old.get("country")
                            n.last_tested_at = old.get("last_tested_at")
                        merged_nodes.append(n.dict())

                    item["nodes"] = merged_nodes
                    item["node_count"] = len(merged_nodes)
                    item["last_updated_at"] = datetime.now().isoformat()
                    item["updated_at"] = datetime.now().isoformat()
                    self._save_raw(raw)
                return SubscriptionItem(**item)
        return None

    def delete_subscription(self, sub_id: str) -> bool:
        """删除订阅及其所有节点"""
        raw = self._load_raw()
        init_len = len(raw)
        raw = [item for item in raw if item.get("id") != sub_id]
        if len(raw) < init_len:
            self._save_raw(raw)
            return True
        return False

    # ==========================
    # 节点单独 CRUD
    # ==========================

    def add_node(self, sub_id: str, node: SubscriptionNode) -> Optional[SubscriptionNode]:
        """向指定订阅手动添加单个节点"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                nodes = item.get("nodes", [])
                node.sub_id = sub_id
                nodes.append(node.dict())
                item["nodes"] = nodes
                item["node_count"] = len(nodes)
                item["updated_at"] = datetime.now().isoformat()
                self._save_raw(raw)
                return node
        return None

    def update_node(self, sub_id: str, node_id: str, updates: Dict[str, Any]) -> Optional[SubscriptionNode]:
        """更新单个节点信息或测速/延迟状态"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                for n in item.get("nodes", []):
                    if n.get("id") == node_id:
                        for k, v in updates.items():
                            if v is not None:
                                n[k] = v
                        item["updated_at"] = datetime.now().isoformat()
                        self._save_raw(raw)
                        return SubscriptionNode(**n)
        return None

    def delete_node(self, sub_id: str, node_id: str) -> bool:
        """从指定订阅中删除单个节点"""
        raw = self._load_raw()
        for item in raw:
            if item.get("id") == sub_id:
                nodes = item.get("nodes", [])
                init_len = len(nodes)
                nodes = [n for n in nodes if n.get("id") != node_id]
                if len(nodes) < init_len:
                    item["nodes"] = nodes
                    item["node_count"] = len(nodes)
                    item["updated_at"] = datetime.now().isoformat()
                    self._save_raw(raw)
                    return True
        return False

    def get_node(self, node_id: str) -> Optional[Tuple[SubscriptionItem, SubscriptionNode]]:
        """跨所有订阅查找单个节点及所属订阅"""
        raw = self._load_raw()
        for item in raw:
            for n in item.get("nodes", []):
                if n.get("id") == node_id:
                    return SubscriptionItem(**item), SubscriptionNode(**n)
        return None

    def list_all_nodes(self) -> List[Dict[str, Any]]:
        """获取所有订阅下的所有节点扁平列表（附带订阅名称，用于环境创建选择框）"""
        result = []
        raw = self._load_raw()
        for sub in raw:
            sub_name = sub.get("name", "未命名订阅")
            sub_id = sub.get("id")
            for n in sub.get("nodes", []):
                item = dict(n)
                item["sub_name"] = sub_name
                item["sub_id"] = sub_id
                result.append(item)
        return result

    # ==========================
    # 测延迟 & 测速度引擎 (Mihomo 全协议驱动)
    # ==========================

    def test_node_latency(self, sub_id: str, node_id: str) -> Dict[str, Any]:
        """测试指定节点的连通性与真实往返延迟 (RTT ms)"""
        res = self.get_node(node_id)
        if not res:
            return {"success": False, "error": "Node not found"}
        _, node = res

        probe_res = self.mihomo_service.test_nodes_latency([node], timeout_ms=3000)
        node_res = probe_res.get(node_id, {"status": "failed", "latency_ms": None})

        now_iso = datetime.now().isoformat()
        if node_res.get("status") == "active":
            lat = node_res.get("latency_ms")
            self.update_node(sub_id, node_id, {
                "status": "active",
                "latency_ms": lat,
                "last_tested_at": now_iso
            })
            return {
                "success": True,
                "latency_ms": lat,
                "status": "active"
            }
        else:
            self.update_node(sub_id, node_id, {
                "status": "failed",
                "latency_ms": -1,
                "last_tested_at": now_iso
            })
            return {
                "success": False,
                "latency_ms": -1,
                "status": "failed"
            }

    def test_all_latencies(self, sub_id: str) -> List[Dict[str, Any]]:
        """批量测试指定订阅下所有节点的延迟 (Mihomo 极速并发引擎)"""
        sub = self.get_subscription(sub_id)
        if not sub or not sub.nodes:
            return []

        # 调用 MihomoService 一次性载入所有节点并发测试
        results_map = self.mihomo_service.test_nodes_latency(sub.nodes, timeout_ms=3000)

        # 批量写回存储
        raw = self._load_raw()
        results = []
        now_iso = datetime.now().isoformat()

        for item in raw:
            if item.get("id") == sub_id:
                for n in item.get("nodes", []):
                    nid = n.get("id")
                    if nid in results_map:
                        probe = results_map[nid]
                        lat = probe.get("latency_ms") if probe["status"] == "active" else -1
                        n["status"] = probe["status"]
                        n["latency_ms"] = lat
                        n["last_tested_at"] = now_iso
                        results.append({
                            "node_id": nid,
                            "node_name": n.get("name"),
                            "success": probe["status"] == "active",
                            "latency_ms": lat
                        })
                item["updated_at"] = now_iso
                self._save_raw(raw)
                break

        return results

    def test_node_speed(self, sub_id: str, node_id: str) -> Dict[str, Any]:
        """测试指定节点的真实带宽吞吐速率 (Mbps / MB/s) 并探测出口 IP 和国家"""
        res = self.get_node(node_id)
        if not res:
            return {"success": False, "error": "Node not found"}
        _, node = res

        speed_res = self.mihomo_service.test_node_speed(node, duration_sec=5)
        now_iso = datetime.now().isoformat()

        if speed_res.get("status") == "active":
            updates = {
                "status": "active",
                "last_tested_at": now_iso
            }
            if speed_res.get("speed_mbps") is not None:
                updates["speed_mbps"] = speed_res["speed_mbps"]
            if speed_res.get("latency_ms") is not None:
                updates["latency_ms"] = speed_res["latency_ms"]
            if speed_res.get("exit_ip"):
                updates["exit_ip"] = speed_res["exit_ip"]
            if speed_res.get("country"):
                updates["country"] = speed_res["country"]

            self.update_node(sub_id, node_id, updates)
            return {
                "success": True,
                "speed_mbps": speed_res.get("speed_mbps", 0.0),
                "latency_ms": speed_res.get("latency_ms"),
                "exit_ip": speed_res.get("exit_ip"),
                "country": speed_res.get("country")
            }
        else:
            self.update_node(sub_id, node_id, {
                "status": "failed",
                "last_tested_at": now_iso
            })
            return {
                "success": False,
                "error": "Node speed test failed or timed out"
            }

    def test_all_speeds(self, sub_id: str) -> List[Dict[str, Any]]:
        """并发测试指定订阅下所有节点的下载速度"""
        sub = self.get_subscription(sub_id)
        if not sub or not sub.nodes:
            return []

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_node = {
                executor.submit(self.test_node_speed, sub_id, n.id): n
                for n in sub.nodes
            }
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    res = future.result()
                    res["node_id"] = node.id
                    res["node_name"] = node.name
                    results.append(res)
                except Exception as e:
                    results.append({
                        "node_id": node.id,
                        "node_name": node.name,
                        "success": False,
                        "error": str(e)
                    })

        return results

    # ==========================
    # Profile 运行时协议代理桥接
    # ==========================

    def get_profile_proxy(self, sub_node_id: str, profile_id: str) -> Optional[ProxyConfig]:
        """获取指定指纹环境绑定的代理配置 (如果是 VPN 复杂协议，自动启动 Mihomo 本地专用混合桥接端口)"""
        node_res = self.get_node(sub_node_id)
        if not node_res:
            return None
        _, node = node_res

        # 如果是标准无需转换的 cleartext http/socks5/https
        if node.type in ("http", "socks5", "https") and not node.raw_config:
            return node.to_proxy_config()

        # 针对 VLESS, VMess, Trojan, SS, Hysteria2 等协议，使用 Mihomo 启动本地专属隧道
        host, port = self.mihomo_service.start_profile_tunnel(profile_id, node)
        return ProxyConfig(
            enabled=True,
            type="socks5",
            host=host,
            port=port
        )

    def release_profile_proxy(self, profile_id: str):
        """释放指纹环境占用的协议隧道资源"""
        self.mihomo_service.stop_profile_tunnel(profile_id)
