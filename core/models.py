from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class ProxyConfig(BaseModel):
    """代理配置"""
    enabled: bool = True
    type: str = Field(default="http", description="http, socks5, https")
    host: str = Field(..., description="代理主机地址")
    port: int = Field(..., description="代理端口")
    username: Optional[str] = None
    password: Optional[str] = None

    def to_chrome_arg(self) -> str:
        """生成 Chrome 代理参数"""
        if not self.enabled:
            return ""
        if self.type.startswith("socks"):
            return f"--proxy-server=socks5://{self.host}:{self.port}"
        elif self.type == "https":
            return f"--proxy-server=https://{self.host}:{self.port}"
        return f"--proxy-server=http://{self.host}:{self.port}"


class ProxyItem(BaseModel):
    """独立代理实体"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="代理名称/别名")
    type: str = Field(default="http", description="http, socks5, https")
    host: str = Field(..., description="代理主机地址")
    port: int = Field(..., description="代理端口")
    username: Optional[str] = None
    password: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # 状态与探测结果缓存
    status: str = "untested"  # "active", "failed", "untested"
    latency_ms: Optional[int] = None
    exit_ip: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    last_tested_at: Optional[str] = None

    def to_proxy_config(self) -> ProxyConfig:
        return ProxyConfig(
            enabled=True,
            type=self.type,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password
        )


class FingerprintConfig(BaseModel):
    """指纹属性配置（自洽性参数）"""
    user_agent: str
    os_name: str = "Windows"
    os_version: str = "10.0"
    platform: str = "Win32"
    browser_name: str = "Chrome"
    browser_version: str = "153"
    screen_width: int = 1920
    screen_height: int = 1080
    screen_avail_width: int = 1920
    screen_avail_height: int = 1040
    device_scale_factor: float = 1.0
    color_depth: int = 24
    hardware_concurrency: int = 8
    device_memory: int = 8
    languages: List[str] = ["zh-CN", "zh", "en-US", "en"]
    timezone: str = "Asia/Shanghai"
    webgl_vendor: str = "Google Inc. (NVIDIA)"
    webgl_renderer: str = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    webrtc_policy: str = "disable_non_proxied_udp"
    # 确定性加噪种子（单个 Profile 恒定，不同 Profile 各异）
    noise_seed: int = Field(default_factory=lambda: hash(uuid.uuid4().hex) % 1000000)
    canvas_noise_enabled: bool = False
    audio_noise_enabled: bool = False

    # 商业级防指纹内核 (Apostate 16 项原生参数细粒度绑定)
    platform_persona: str = Field(default="windows", description="操作系统人格: windows, macos, linux")
    fingerprint_anchor: Optional[str] = Field(default=None, description="硬件真实锚点ID (来自 catalogue.json)")
    webrtc_ip: Optional[str] = Field(default=None, description="显式绑定的出口 IP / 虚拟本地 IP")
    webrtc_udp: str = Field(default="disable", description="WebRTC UDP 策略: allow, block, disable")
    noise_enabled: bool = Field(default=False, description="是否启用全管线物理噪声微扰")
    explain_enabled: bool = Field(default=False, description="启动时是否输出指纹自检报告")
    custom_envelope: Optional[Dict[str, Any]] = Field(default=None, description="高级自定义 --apostate-profile JSON 载荷")


class SubscriptionNode(BaseModel):
    """订阅解析出的独立代理节点"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sub_id: str = Field(..., description="所属订阅 ID")
    name: str = Field(..., description="节点名称")
    type: str = Field(default="http", description="vless, vmess, trojan, ss, hysteria2, tuic, http, socks5")
    host: str = Field(..., description="节点地址")
    port: int = Field(..., description="节点端口")
    username: Optional[str] = None
    password: Optional[str] = None
    raw_config: Optional[Dict[str, Any]] = Field(default=None, description="原始完整内核代理配置")
    
    # 测速与探测结果缓存
    status: str = "untested"  # "active", "failed", "untested"
    latency_ms: Optional[int] = None   # 延迟 (ms)
    speed_mbps: Optional[float] = None # 速度 (Mbps)
    exit_ip: Optional[str] = None
    country: Optional[str] = None
    last_tested_at: Optional[str] = None

    def to_proxy_config(self) -> ProxyConfig:
        return ProxyConfig(
            enabled=True,
            type="socks5" if "sock" in self.type.lower() else self.type,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password
        )


class SubscriptionItem(BaseModel):
    """订阅实体"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="订阅名称")
    url: Optional[str] = Field(default="", description="远程订阅 URL")
    source_text: Optional[str] = Field(default="", description="手动填入的节点文本/Base64/配置")
    node_count: int = 0
    nodes: List[SubscriptionNode] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_updated_at: Optional[str] = None


class BrowserProfile(BaseModel):
    """指纹环境 Profile 实体"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="环境名称")
    group: Optional[str] = "Default"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = ""
    
    # 核心指纹配置
    fingerprint: FingerprintConfig
    
    # 网络代理 (支持独立代理 proxy_id、订阅节点 sub_node_id 与嵌入代理 proxy)
    proxy_id: Optional[str] = None
    sub_node_id: Optional[str] = None
    proxy: Optional[ProxyConfig] = None
    
    # 自定义浏览器内核可执行文件路径（留空则自动检测系统 Chrome/Edge，支持替换为自编译内核）
    custom_browser_path: Optional[str] = None
    custom_args: List[str] = Field(default_factory=list)


class ProfileRunningStatus(BaseModel):
    """正在运行的环境状态"""
    profile_id: str
    name: str
    is_running: bool
    pid: Optional[int] = None
    cdp_port: Optional[int] = None
    ws_endpoint: Optional[str] = None
    http_endpoint: Optional[str] = None
    started_at: Optional[str] = None
