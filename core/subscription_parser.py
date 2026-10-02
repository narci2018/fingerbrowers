import base64
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .models import SubscriptionNode


def _query_dict(query: str) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(query, keep_blank_values=True).items()}


def _b64_decode_safe(s: str) -> str:
    s = s.strip()
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        try:
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        except Exception:
            return ""


def parse_vless_uri(uri: str, sub_id: str) -> Optional[SubscriptionNode]:
    """解析 vless:// 链接"""
    m = re.match(r"^vless://([^@#]+)@(\[[^\]]+\]|[^:@/]+):(\d+)(?:[/?]([^#]*))?(?:#(.*))?$", uri.strip())
    if not m:
        return None
    user, host, port, query, name = m.groups()
    params = _query_dict(query or "")
    node_name = urllib.parse.unquote(name.strip()) if name else f"VLESS-{host}:{port}"
    port_int = int(port)

    raw_cfg = {
        "name": node_name,
        "type": "vless",
        "server": host,
        "port": port_int,
        "uuid": user,
        "udp": True
    }

    if params.get("flow"):
        raw_cfg["flow"] = params["flow"]

    sec = params.get("security", "").lower()
    if sec == "reality":
        raw_cfg["tls"] = True
        raw_cfg["reality-opts"] = {"public-key": params.get("pbk", "")}
        if params.get("sid"):
            raw_cfg["reality-opts"]["short-id"] = params["sid"]
        raw_cfg["servername"] = params.get("sni", host)
        if params.get("fp"):
            raw_cfg["client-fingerprint"] = params["fp"]
    elif sec in ("tls", "xtls"):
        raw_cfg["tls"] = True
        raw_cfg["servername"] = params.get("sni", host)
        raw_cfg["skip-cert-verify"] = params.get("allowInsecure", "0") in ("1", "true")
        if params.get("fp"):
            raw_cfg["client-fingerprint"] = params["fp"]

    net = params.get("type", "tcp").lower()
    if net == "ws":
        raw_cfg["network"] = "ws"
        raw_cfg["ws-opts"] = {
            "path": urllib.parse.unquote(params.get("path", "/")),
            "headers": {"Host": params.get("host", host)}
        }
    elif net in ("grpc", "gun"):
        raw_cfg["network"] = "grpc"
        raw_cfg["grpc-opts"] = {"grpc-service-name": urllib.parse.unquote(params.get("serviceName", ""))}
    elif net in ("h2", "http"):
        raw_cfg["network"] = "h2"
        raw_cfg["h2-opts"] = {
            "host": [params.get("host", host)],
            "path": urllib.parse.unquote(params.get("path", "/"))
        }

    return SubscriptionNode(
        sub_id=sub_id,
        name=node_name,
        type="vless",
        host=host,
        port=port_int,
        raw_config=raw_cfg,
        status="untested"
    )


def parse_vmess_uri(uri: str, sub_id: str) -> Optional[SubscriptionNode]:
    """解析 vmess:// 链接"""
    raw_b64 = uri[8:].strip()
    decoded = _b64_decode_safe(raw_b64)
    if not decoded:
        return None
    try:
        data = json.loads(decoded)
    except Exception:
        return None

    server = str(data.get("add", "")).strip()
    port = int(data.get("port", 0) or 0)
    if not server or port <= 0:
        return None

    node_name = str(data.get("ps", f"VMess-{server}:{port}")).strip()
    raw_cfg = {
        "name": node_name,
        "type": "vmess",
        "server": server,
        "port": port,
        "uuid": str(data.get("id", "")).strip(),
        "alterId": int(data.get("aid", 0) or 0),
        "cipher": "auto",
        "udp": True
    }

    if str(data.get("tls", "")).lower() in ("tls", "1", "true"):
        raw_cfg["tls"] = True
        raw_cfg["servername"] = str(data.get("sni") or data.get("host") or server).strip()
        raw_cfg["skip-cert-verify"] = str(data.get("verify_cert", "false")).lower() in ("true", "1")

    net = str(data.get("net", "tcp")).lower()
    if net == "ws":
        raw_cfg["network"] = "ws"
        raw_cfg["ws-opts"] = {
            "path": str(data.get("path", "/")),
            "headers": {"Host": str(data.get("host", server))}
        }
    elif net in ("grpc", "gun"):
        raw_cfg["network"] = "grpc"
        raw_cfg["grpc-opts"] = {"grpc-service-name": str(data.get("path", ""))}

    return SubscriptionNode(
        sub_id=sub_id,
        name=node_name,
        type="vmess",
        host=server,
        port=port,
        raw_config=raw_cfg,
        status="untested"
    )


def parse_trojan_uri(uri: str, sub_id: str) -> Optional[SubscriptionNode]:
    """解析 trojan:// 链接"""
    m = re.match(r"^trojan://([^@#]+)@(\[[^\]]+\]|[^:@/]+):(\d+)(?:[/?]([^#]*))?(?:#(.*))?$", uri.strip())
    if not m:
        return None
    password, host, port, query, name = m.groups()
    params = _query_dict(query or "")
    node_name = urllib.parse.unquote(name.strip()) if name else f"Trojan-{host}:{port}"
    port_int = int(port)

    raw_cfg = {
        "name": node_name,
        "type": "trojan",
        "server": host,
        "port": port_int,
        "password": urllib.parse.unquote(password),
        "sni": params.get("sni", params.get("peer", host)),
        "skip-cert-verify": params.get("allowInsecure", "0") in ("1", "true"),
        "udp": True
    }

    net = params.get("type", "tcp").lower()
    if net == "ws":
        raw_cfg["network"] = "ws"
        raw_cfg["ws-opts"] = {
            "path": urllib.parse.unquote(params.get("path", "/")),
            "headers": {"Host": params.get("host", host)}
        }
    elif net in ("grpc", "gun"):
        raw_cfg["network"] = "grpc"
        raw_cfg["grpc-opts"] = {"grpc-service-name": urllib.parse.unquote(params.get("serviceName", ""))}

    return SubscriptionNode(
        sub_id=sub_id,
        name=node_name,
        type="trojan",
        host=host,
        port=port_int,
        raw_config=raw_cfg,
        status="untested"
    )


def parse_ss_uri(uri: str, sub_id: str) -> Optional[SubscriptionNode]:
    """解析 ss:// 链接 (SIP002 与标准 Base64)"""
    raw_ss = uri[5:].strip()
    name = ""
    if "#" in raw_ss:
        raw_ss, name = raw_ss.split("#", 1)
        name = urllib.parse.unquote(name.strip())

    host, port, cipher, password = None, None, None, None
    if "@" in raw_ss:
        user_info, host_port = raw_ss.split("@", 1)
        # 解码 user_info (cipher:password)
        decoded_user = _b64_decode_safe(user_info)
        if ":" in decoded_user:
            cipher, password = decoded_user.split(":", 1)
        elif ":" in user_info:
            cipher, password = user_info.split(":", 1)
        if ":" in host_port:
            hp_parts = host_port.split(":")
            host = hp_parts[0]
            port = int(hp_parts[1].split("/")[0])
    else:
        # 全串 Base64
        decoded = _b64_decode_safe(raw_ss)
        if "@" in decoded and ":" in decoded:
            user_info, host_port = decoded.split("@", 1)
            if ":" in user_info:
                cipher, password = user_info.split(":", 1)
            hp_parts = host_port.split(":")
            host = hp_parts[0]
            port = int(hp_parts[1].split("/")[0])

    if host and port and cipher:
        node_name = name or f"SS-{host}:{port}"
        raw_cfg = {
            "name": node_name,
            "type": "ss",
            "server": host,
            "port": port,
            "cipher": cipher,
            "password": password or "",
            "udp": True
        }
        return SubscriptionNode(
            sub_id=sub_id,
            name=node_name,
            type="ss",
            host=host,
            port=port,
            raw_config=raw_cfg,
            status="untested"
        )
    return None


def parse_hy2_uri(uri: str, sub_id: str) -> Optional[SubscriptionNode]:
    """解析 hysteria2:// 或 hy2:// 链接"""
    clean_uri = uri.replace("hy2://", "hysteria2://")
    m = re.match(r"^hysteria2://([^@#]+)@(\[[^\]]+\]|[^:@/]+):(\d+)(?:[/?]([^#]*))?(?:#(.*))?$", clean_uri.strip())
    if not m:
        return None
    auth, host, port, query, name = m.groups()
    params = _query_dict(query or "")
    node_name = urllib.parse.unquote(name.strip()) if name else f"HY2-{host}:{port}"
    port_int = int(port)

    raw_cfg = {
        "name": node_name,
        "type": "hysteria2",
        "server": host,
        "port": port_int,
        "password": urllib.parse.unquote(auth),
        "sni": params.get("sni", host),
        "skip-cert-verify": params.get("insecure", "0") in ("1", "true"),
        "udp": True
    }

    return SubscriptionNode(
        sub_id=sub_id,
        name=node_name,
        type="hysteria2",
        host=host,
        port=port_int,
        raw_config=raw_cfg,
        status="untested"
    )


def parse_clash_yaml(text: str, sub_id: str) -> List[SubscriptionNode]:
    """解析 Clash YAML 配置中的 proxies 列表"""
    nodes: List[SubscriptionNode] = []
    if "proxies:" not in text:
        return nodes

    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and "proxies" in data and isinstance(data["proxies"], list):
            for item in data["proxies"]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "Node")).strip()
                p_type = str(item.get("type", "http")).lower()
                server = str(item.get("server", "")).strip()
                port = int(item.get("port", 0))

                if not server or port <= 0:
                    continue

                user = str(item.get("username", "")) if item.get("username") else None
                pwd = str(item.get("password", "")) if item.get("password") else None

                # 完整保留 Clash 内核配置
                raw_cfg = copy_item = dict(item)

                nodes.append(SubscriptionNode(
                    sub_id=sub_id,
                    name=name,
                    type=p_type,
                    host=server,
                    port=port,
                    username=user,
                    password=pwd,
                    raw_config=raw_cfg,
                    status="untested"
                ))
    except Exception:
        pass
    return nodes


def parse_all_subscription_nodes(text: str, sub_id: str) -> List[SubscriptionNode]:
    """全协议通用解析入口 (Clash YAML / Base64 / URI 协议行 / 普通文本行)"""
    nodes: List[SubscriptionNode] = []
    if not text or not text.strip():
        return nodes

    clean_text = text.strip()

    # 1. 尝试 Clash YAML 格式 (优先完整识别)
    if "proxies:" in clean_text or ("proxy-groups:" in clean_text and "rules:" in clean_text):
        nodes = parse_clash_yaml(clean_text, sub_id)
        if nodes:
            return nodes
        # 如果明确是 Clash 配置文件，但 proxies 为空或无节点，绝不能把配置项 (如 mixed-port: 7890) 误当代理节点
        if "mixed-port:" in clean_text or "port:" in clean_text or "proxies:" in clean_text:
            return []

    # 2. 尝试 Base64 解码
    decoded = _b64_decode_safe(clean_text)
    if decoded and any(k in decoded for k in ["vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "http://", "socks5://", "\n"]):
        clean_text = decoded
        if "proxies:" in clean_text:
            nodes = parse_clash_yaml(clean_text, sub_id)
            if nodes:
                return nodes
            if "mixed-port:" in clean_text or "port:" in clean_text:
                return []

    # 3. 按行解析多协议 URI
    lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    yaml_config_keys = {
        "mixed-port", "port", "socks-port", "redir-port", "allow-lan",
        "external-controller", "secret", "mode", "log-level", "dns",
        "proxies", "rules", "proxy-groups", "bind-address"
    }
    for idx, line in enumerate(lines):
        try:
            if line.startswith("vless://"):
                n = parse_vless_uri(line, sub_id)
                if n:
                    nodes.append(n)
                continue

            if line.startswith("vmess://"):
                n = parse_vmess_uri(line, sub_id)
                if n:
                    nodes.append(n)
                continue

            if line.startswith("trojan://"):
                n = parse_trojan_uri(line, sub_id)
                if n:
                    nodes.append(n)
                continue

            if line.startswith("ss://"):
                n = parse_ss_uri(line, sub_id)
                if n:
                    nodes.append(n)
                continue

            if line.startswith(("hysteria2://", "hy2://")):
                n = parse_hy2_uri(line, sub_id)
                if n:
                    nodes.append(n)
                continue

            # HTTP / SOCKS5 完整 URI
            if line.startswith(("http://", "https://", "socks5://", "socks5h://")):
                parsed = urllib.parse.urlparse(line)
                proto = "socks5" if "sock" in parsed.scheme.lower() else "http"
                host = parsed.hostname
                port = parsed.port
                user = urllib.parse.unquote(parsed.username) if parsed.username else None
                pwd = urllib.parse.unquote(parsed.password) if parsed.password else None
                name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"{proto.upper()}-{host}:{port}"
                if host and port:
                    nodes.append(SubscriptionNode(
                        sub_id=sub_id,
                        name=name,
                        type=proto,
                        host=host,
                        port=port,
                        username=user,
                        password=pwd,
                        raw_config={"name": name, "type": proto, "server": host, "port": port},
                        status="untested"
                    ))
                continue

            # 兼容普通单行代理 host:port[:user:pass] (严格校验非 yaml 配置项且 host 合法)
            if ":" in line and not line.startswith("//"):
                frag = f"Node-{idx+1}"
                if "#" in line:
                    line, frag = line.split("#", 1)
                    frag = urllib.parse.unquote(frag.strip())
                parts = [p.strip() for p in line.split(":")]
                if len(parts) >= 2:
                    host = parts[0]
                    # 避免把 yaml 配置指令当成 host
                    if host.lower() in yaml_config_keys or host.startswith(("-", "http", "socks")):
                        continue
                    # host 必须形如合法 IP 地址、包含 '.' 的域名、或 localhost
                    if "." not in host and host.lower() != "localhost":
                        continue
                    try:
                        port = int(parts[1])
                        if not (1 <= port <= 65535):
                            continue
                    except ValueError:
                        continue

                    user = parts[2].strip() if len(parts) >= 3 else None
                    pwd = parts[3].strip() if len(parts) >= 4 else None
                    nodes.append(SubscriptionNode(
                        sub_id=sub_id,
                        name=frag,
                        type="http",
                        host=host,
                        port=port,
                        username=user,
                        password=pwd,
                        raw_config={"name": frag, "type": "http", "server": host, "port": port},
                        status="untested"
                    ))
        except Exception:
            continue

    return nodes
