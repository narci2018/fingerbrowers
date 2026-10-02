import sys
import os
from pathlib import Path

# 将根目录加入模块搜索路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("Fingerprint-Browser-Engine")
except ImportError:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("Fingerprint-Browser-Engine")

from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher

profile_mgr = ProfileManager()
launcher = BrowserLauncher(profile_mgr)


@mcp.tool()
def list_browser_profiles() -> str:
    """列出所有本地指纹环境及其配置概要与当前运行状态。"""
    profiles = profile_mgr.list_profiles()
    if not profiles:
        return "当前暂无已创建的指纹环境。"
    
    result = []
    for p in profiles:
        status = launcher.get_status(p.id)
        running_desc = f"[RUNNING | Port: {status.cdp_port}]" if status.is_running else "[STOPPED]"
        result.append(
            f"- ID: {p.id}\n"
            f"  名称: {p.name} ({p.group}) {running_desc}\n"
            f"  系统与硬件: {p.fingerprint.os_name} | {p.fingerprint.hardware_concurrency}C/{p.fingerprint.device_memory}GB\n"
            f"  屏幕与语言: {p.fingerprint.screen_width}x{p.fingerprint.screen_height} | {','.join(p.fingerprint.languages)}\n"
            f"  代理: {'启用' if p.proxy and p.proxy.enabled else '无'}"
        )
    return "\n\n".join(result)


@mcp.tool()
def create_browser_profile(name: str, group: str = "AI-Tasks", locale: str = "zh-CN", notes: str = "") -> str:
    """
    创建全新独立的指纹环境。
    :param name: 环境名称（如 'Amazon_Store_1'）
    :param group: 分组名称
    :param locale: 语言与地区（'zh-CN', 'en-US', 'ja-JP' 等）
    :param notes: 备注说明
    """
    profile = profile_mgr.create_profile(name=name, group=group, locale=locale, notes=notes)
    return (
        f"成功创建指纹环境！\n"
        f"Profile ID: {profile.id}\n"
        f"名称: {profile.name}\n"
        f"User-Agent: {profile.fingerprint.user_agent}\n"
        f"加噪种子: {profile.fingerprint.noise_seed}"
    )


@mcp.tool()
def start_browser_profile(profile_id: str, headless: bool = False) -> str:
    """
    启动指定的指纹浏览器环境，返回 CDP WebSocket 连接端点，可直接供 Playwright / Puppeteer 挂载。
    :param profile_id: 指纹环境 ID
    :param headless: 是否使用无头模式
    """
    try:
        status = launcher.start_profile(profile_id, headless=headless)
        return (
            f"浏览器环境已启动！\n"
            f"Profile ID: {status.profile_id}\n"
            f"PID: {status.pid}\n"
            f"CDP 调试端口: {status.cdp_port}\n"
            f"CDP WebSocket 调试地址: {status.ws_endpoint}\n"
            f"HTTP 调试地址: {status.http_endpoint}"
        )
    except Exception as e:
        return f"启动失败: {str(e)}"


@mcp.tool()
def stop_browser_profile(profile_id: str) -> str:
    """
    安全关闭指定的指纹浏览器环境并持久化沙箱数据。
    :param profile_id: 指纹环境 ID
    """
    launcher.stop_profile(profile_id)
    return f"指纹环境 {profile_id} 已安全关闭。"


@mcp.tool()
def get_browser_status(profile_id: str) -> str:
    """
    查询指定指纹环境的运行状态。
    :param profile_id: 指纹环境 ID
    """
    status = launcher.get_status(profile_id)
    if status.is_running:
        return f"环境 [{status.name}] 正在运行中 (PID: {status.pid}, Port: {status.cdp_port})"
    return f"环境 [{status.name}] 当前处于已停止状态。"


if __name__ == "__main__":
    mcp.run()
