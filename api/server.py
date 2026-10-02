from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import urllib.request
import json
import time
import tempfile

from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher
from core.proxy_manager import ProxyManager
from core.subscription_manager import SubscriptionManager
from core.fingerprint_generator import FingerprintGenerator
from core.geoip_service import GeoIPService
from core.cookie_manager import CookieManager
from core.models import (
    BrowserProfile, ProfileRunningStatus, ProxyConfig, FingerprintConfig,
    ProxyItem, SubscriptionItem, SubscriptionNode
)

import sys

if hasattr(sys, '_MEIPASS'):
    GUI_DIR = Path(sys._MEIPASS) / "gui"
else:
    GUI_DIR = Path(__file__).resolve().parent.parent / "gui"

if not GUI_DIR.exists():
    GUI_DIR = Path(sys.executable).resolve().parent / "gui"

app = FastAPI(
    title="Phantom Browser Engine API",
    version="1.0.0",
    description="Phantom Browser 控制面 API & GUI 后端"
)

profile_mgr = ProfileManager()
proxy_mgr = ProxyManager()
subscription_mgr = SubscriptionManager()
launcher = BrowserLauncher(profile_mgr, proxy_mgr, subscription_mgr)


class CreateProxyRequest(BaseModel):
    name: str
    type: str = "http"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


class UpdateProxyRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class TestProxyRequest(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = "http"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class CreateProfileRequest(BaseModel):
    name: str
    group: Optional[str] = "Default"
    locale: Optional[str] = "zh-CN"
    notes: Optional[str] = ""
    os_type: Optional[str] = "win10"
    browser_type: Optional[str] = "chrome"
    browser_version: Optional[str] = None
    proxy_id: Optional[str] = None
    sub_node_id: Optional[str] = None
    proxy: Optional[ProxyConfig] = None
    custom_fingerprint: Optional[FingerprintConfig] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    group: Optional[str] = None
    notes: Optional[str] = None
    proxy_id: Optional[str] = None
    sub_node_id: Optional[str] = None
    proxy: Optional[ProxyConfig] = None
    custom_fingerprint: Optional[FingerprintConfig] = None


class StartProfileResponse(BaseModel):
    success: bool
    status: ProfileRunningStatus
    message: str


class OpenUrlRequest(BaseModel):
    url: str


class CloneProfileRequest(BaseModel):
    name: Optional[str] = None
    copy_data: bool = True


class ImportCookiesRequest(BaseModel):
    content: str
    format: Optional[str] = "auto"


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "phantom-browser-engine",
        "active_profiles": len(launcher.running_processes)
    }


@app.get("/api/v1/fingerprint/options")
def get_fingerprint_options():
    """获取所有支持的操作系统及浏览器类型与版本预设选项"""
    return {
        "os_list": FingerprintGenerator.get_supported_os_list(),
        "browser_list": FingerprintGenerator.get_supported_browser_list()
    }


@app.get("/api/v1/fingerprint/random", response_model=FingerprintConfig)
def generate_random_fingerprint(
    locale: str = "zh-CN",
    os_type: str = "win10",
    browser_type: str = "chrome",
    browser_version: Optional[str] = None
):
    """根据指定的操作系统、浏览器及版本，自洽生成逼真的指纹配置"""
    return FingerprintGenerator.generate(
        locale_preference=locale,
        os_platform=os_type,
        browser_type=browser_type,
        browser_version=browser_version
    )


@app.get("/api/v1/geo/countries")
def get_supported_countries():
    """获取系统支持的全量主流国家与语言列表"""
    return GeoIPService.list_supported_countries()


@app.get("/api/v1/profiles", response_model=List[BrowserProfile])
def list_profiles():
    """获取所有配置环境"""
    return profile_mgr.list_profiles()


@app.post("/api/v1/profiles", response_model=BrowserProfile)
def create_profile(req: CreateProfileRequest):
    """创建全新指纹环境"""
    if req.custom_fingerprint:
        import uuid
        from datetime import datetime
        profile = BrowserProfile(
            id=str(uuid.uuid4()),
            name=req.name,
            group=req.group or "Default",
            notes=req.notes or "",
            fingerprint=req.custom_fingerprint,
            proxy_id=req.proxy_id,
            sub_node_id=req.sub_node_id,
            proxy=req.proxy,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        user_path = profile_mgr.get_user_data_path(profile.id)
        user_path.mkdir(parents=True, exist_ok=True)
        raw = profile_mgr._load_raw()
        raw.append(profile.model_dump())
        profile_mgr._save_raw(raw)
    else:
        profile = profile_mgr.create_profile(
            name=req.name,
            group=req.group,
            locale=req.locale,
            notes=req.notes,
            os_platform=req.os_type or "win10",
            browser_type=req.browser_type or "chrome",
            browser_version=req.browser_version
        )
        if req.proxy_id:
            profile.proxy_id = req.proxy_id
        if req.sub_node_id:
            profile.sub_node_id = req.sub_node_id
        if req.proxy:
            profile.proxy = req.proxy
        profile_mgr.update_profile(profile)
    return profile


# ================= 独立代理管理 API =================

@app.get("/api/v1/proxies", response_model=List[ProxyItem])
def list_proxies():
    """获取所有独立代理配置"""
    return proxy_mgr.list_proxies()


@app.post("/api/v1/proxies", response_model=ProxyItem)
def create_proxy(req: CreateProxyRequest):
    """创建独立代理"""
    return proxy_mgr.create_proxy(
        name=req.name,
        type=req.type,
        host=req.host,
        port=req.port,
        username=req.username,
        password=req.password
    )


@app.get("/api/v1/proxies/{proxy_id}", response_model=ProxyItem)
def get_proxy(proxy_id: str):
    """获取单个代理详情"""
    p = proxy_mgr.get_proxy(proxy_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return p


@app.put("/api/v1/proxies/{proxy_id}", response_model=ProxyItem)
def update_proxy(proxy_id: str, req: UpdateProxyRequest):
    """修改独立代理配置"""
    updated = proxy_mgr.update_proxy(proxy_id, req.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return updated


@app.delete("/api/v1/proxies/{proxy_id}")
def delete_proxy(proxy_id: str):
    """删除独立代理"""
    ok = proxy_mgr.delete_proxy(proxy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return {"success": True, "message": f"Proxy {proxy_id} deleted."}


@app.post("/api/v1/proxies/test")
def test_proxy_connection(req: TestProxyRequest):
    """测试代理连通性（可根据已存 ID 测试，或直接根据填写的参数测试）"""
    if req.id:
        p = proxy_mgr.get_proxy(req.id)
        if not p:
            raise HTTPException(status_code=404, detail="Proxy not found")
        res = proxy_mgr.test_proxy(
            host=p.host,
            port=p.port,
            type=p.type,
            username=p.username,
            password=p.password,
            proxy_id=p.id
        )
    else:
        if not req.host or not req.port:
            raise HTTPException(status_code=400, detail="Host and port are required for direct testing")
        res = proxy_mgr.test_proxy(
            host=req.host,
            port=req.port,
            type=req.type or "http",
            username=req.username,
            password=req.password
        )
    return res


class BatchImportProxyRequest(BaseModel):
    content: str
    default_type: Optional[str] = "http"


class BatchTestProxyRequest(BaseModel):
    proxy_ids: Optional[List[str]] = None


@app.post("/api/v1/proxies/batch-import")
def batch_import_proxies(req: BatchImportProxyRequest):
    """批量导入代理配置"""
    return proxy_mgr.batch_import_proxies(req.content, req.default_type or "http")


@app.get("/api/v1/proxies/export")
def export_proxies_endpoint(format: str = Query("text", description="text, json, csv")):
    """批量导出代理配置"""
    content = proxy_mgr.export_proxies(format=format)
    media_type = "text/plain"
    if format == "json":
        media_type = "application/json"
    elif format == "csv":
        media_type = "text/csv"
    return PlainTextResponse(content, media_type=media_type)


@app.post("/api/v1/proxies/batch-test")
def batch_test_proxies_endpoint(req: BatchTestProxyRequest):
    """并发批量检测代理连通性与测速"""
    results = proxy_mgr.batch_test_proxies(proxy_ids=req.proxy_ids)
    return {"total": len(results), "results": results}


# ================= 订阅管理配置 API =================

class CreateSubscriptionRequest(BaseModel):
    name: str
    url: Optional[str] = ""
    source_text: Optional[str] = ""
    fetch_now: bool = True


class UpdateSubscriptionRequest(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_text: Optional[str] = None


class CreateNodeRequest(BaseModel):
    name: str
    type: str = "http"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


class UpdateNodeRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


@app.get("/api/v1/subscriptions", response_model=List[SubscriptionItem])
def list_subscriptions():
    """获取所有订阅列表"""
    return subscription_mgr.list_subscriptions()


@app.post("/api/v1/subscriptions", response_model=SubscriptionItem)
def create_subscription(req: CreateSubscriptionRequest):
    """创建全新订阅并可自动拉取解析节点"""
    return subscription_mgr.create_subscription(
        name=req.name,
        url=req.url,
        source_text=req.source_text,
        fetch_now=req.fetch_now
    )


@app.get("/api/v1/subscriptions/{sub_id}", response_model=SubscriptionItem)
def get_subscription(sub_id: str):
    """获取指定订阅详情及节点"""
    sub = subscription_mgr.get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@app.put("/api/v1/subscriptions/{sub_id}", response_model=SubscriptionItem)
def update_subscription(sub_id: str, req: UpdateSubscriptionRequest):
    """更新订阅基础信息"""
    sub = subscription_mgr.update_subscription(sub_id, req.model_dump(exclude_unset=True))
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@app.delete("/api/v1/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    """删除指定订阅"""
    ok = subscription_mgr.delete_subscription(sub_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"success": True, "message": f"Subscription {sub_id} deleted"}


@app.post("/api/v1/subscriptions/{sub_id}/refresh", response_model=SubscriptionItem)
def refresh_subscription(sub_id: str):
    """刷新并重新拉取订阅中的节点"""
    sub = subscription_mgr.refresh_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@app.post("/api/v1/subscriptions/{sub_id}/nodes")
def add_subscription_node(sub_id: str, req: CreateNodeRequest):
    """向订阅手动添加单个节点"""
    sub = subscription_mgr.get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    node = SubscriptionNode(
        sub_id=sub_id,
        name=req.name,
        type=req.type,
        host=req.host,
        port=req.port,
        username=req.username,
        password=req.password
    )
    subscription_mgr.add_node(sub_id, node)
    return {"success": True, "node": node.model_dump()}


@app.put("/api/v1/subscriptions/{sub_id}/nodes/{node_id}")
def update_subscription_node(sub_id: str, node_id: str, req: UpdateNodeRequest):
    """编辑订阅中的单个节点"""
    ok = subscription_mgr.update_node(sub_id, node_id, req.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="Node or Subscription not found")
    return {"success": True, "message": "Node updated successfully"}


@app.delete("/api/v1/subscriptions/{sub_id}/nodes/{node_id}")
def delete_subscription_node(sub_id: str, node_id: str):
    """删除订阅中的单个节点"""
    ok = subscription_mgr.delete_node(sub_id, node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node or Subscription not found")
    return {"success": True, "message": "Node deleted successfully"}


@app.post("/api/v1/subscriptions/{sub_id}/nodes/{node_id}/test_latency")
def test_node_latency(sub_id: str, node_id: str):
    """测延迟：测试单个节点的连通性与往返延迟"""
    res = subscription_mgr.test_node_latency(sub_id, node_id)
    return res


@app.post("/api/v1/subscriptions/{sub_id}/nodes/{node_id}/test_speed")
def test_node_speed(sub_id: str, node_id: str):
    """测速度：测试单个节点的真实吞吐带宽速率 (Mbps)"""
    res = subscription_mgr.test_node_speed(sub_id, node_id)
    return res


@app.post("/api/v1/subscriptions/{sub_id}/test_all_latencies")
def test_all_node_latencies(sub_id: str):
    """批量一键测延迟：多线程并发测试当前订阅下所有节点"""
    results = subscription_mgr.test_all_latencies(sub_id)
    return {"success": True, "results": results}


@app.post("/api/v1/subscriptions/{sub_id}/test_all_speeds")
def test_all_node_speeds(sub_id: str):
    """批量一键测速度：多线程并发测试当前订阅下所有节点速率"""
    results = subscription_mgr.test_all_speeds(sub_id)
    return {"success": True, "results": results}


@app.get("/api/v1/subscription_nodes/all")
def list_all_subscription_nodes():
    """获取全量订阅节点扁平列表（供环境创建时下拉选择）"""
    return subscription_mgr.list_all_nodes()


@app.get("/api/v1/profiles/{profile_id}", response_model=BrowserProfile)
def get_profile(profile_id: str):
    """获取指定指纹环境详情"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p


@app.put("/api/v1/profiles/{profile_id}", response_model=BrowserProfile)
def update_profile(profile_id: str, req: UpdateProfileRequest):
    """修改现有指纹环境配置（名称、分组、备注、代理及指纹）"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    if req.name is not None:
        p.name = req.name.strip()
    if req.group is not None:
        p.group = req.group.strip()
    if req.notes is not None:
        p.notes = req.notes.strip()

    # 代理绑定变更（传空字符串代表取消绑定）
    if req.proxy_id is not None:
        p.proxy_id = req.proxy_id if req.proxy_id else None
    if req.sub_node_id is not None:
        p.sub_node_id = req.sub_node_id if req.sub_node_id else None
    if req.proxy is not None:
        p.proxy = req.proxy

    # 自定义指纹变更
    if req.custom_fingerprint is not None:
        p.fingerprint = req.custom_fingerprint

    from datetime import datetime
    p.updated_at = datetime.now().isoformat()
    profile_mgr.update_profile(p)
    return p


@app.delete("/api/v1/profiles/{profile_id}")
def delete_profile(profile_id: str, delete_data: bool = Query(True)):
    """删除环境并可选择清理沙箱目录"""
    launcher.stop_profile(profile_id)
    success = profile_mgr.delete_profile(profile_id, delete_user_data=delete_data)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True, "message": f"Profile {profile_id} deleted."}


@app.post("/api/v1/profiles/{profile_id}/clean_cache")
def clean_profile_cache(profile_id: str):
    """安全清理环境缓存（Cache, Code Cache, GPUCache），保留登录凭据与 Cookie"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    freed_bytes = profile_mgr.clean_profile_cache(profile_id)
    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    return {
        "success": True,
        "message": f"缓存清理成功，已释放 {freed_mb} MB 磁盘空间",
        "freed_bytes": freed_bytes,
        "freed_mb": freed_mb
    }


@app.post("/api/v1/profiles/{profile_id}/start", response_model=StartProfileResponse)
def start_profile(profile_id: str, headless: bool = Query(False), initial_url: Optional[str] = Query(None)):
    """启动指定环境并返回 CDP WebSocket 地址"""
    try:
        status = launcher.start_profile(profile_id, headless=headless, initial_url=initial_url)
        return StartProfileResponse(
            success=True,
            status=status,
            message="Browser profile launched successfully."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/profiles/{profile_id}/open_url")
def open_url_in_profile(profile_id: str, req: OpenUrlRequest):
    """在指定的 Profile 浏览器中直接打开某个网址"""
    status = launcher.get_status(profile_id)
    if not status.is_running:
        status = launcher.start_profile(profile_id, headless=False, initial_url=req.url)
        return {"success": True, "message": "Browser profile launched with URL", "status": status}

    # 如果已经在运行，通过 CDP /json/new 新开标签页并激活到前台
    try:
        new_url = f"http://127.0.0.1:{status.cdp_port}/json/new?{req.url}"
        http_req = urllib.request.Request(new_url, method="PUT")
        with urllib.request.urlopen(http_req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            target_id = data.get("id")
            if target_id:
                try:
                    act_url = f"http://127.0.0.1:{status.cdp_port}/json/activate/{target_id}"
                    urllib.request.urlopen(urllib.request.Request(act_url, method="PUT"), timeout=1)
                except Exception:
                    pass
            return {"success": True, "page": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/v1/profiles/{profile_id}/stop")
def stop_profile(profile_id: str):
    """停止环境"""
    launcher.stop_profile(profile_id)
    return {"success": True, "message": f"Profile {profile_id} stopped."}


@app.post("/api/v1/profiles_action/stop_all")
def stop_all_profiles():
    """紧急全部停止"""
    launcher.stop_all()
    return {"success": True, "message": "All running profiles stopped."}


@app.get("/api/v1/profiles/{profile_id}/status", response_model=ProfileRunningStatus)
def get_profile_status(profile_id: str):
    """查询环境运行状态及端口"""
    return launcher.get_status(profile_id)


# ================= 阶段一 & 阶段二：自洽性、Cookie 与生命周期 API =================

@app.post("/api/v1/profiles/{profile_id}/auto_align_geo")
def auto_align_profile_geo(profile_id: str):
    """一键与绑定的代理/订阅节点深度自洽对齐（时区、语言、WebRTC、内核参数）"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    res = GeoIPService.auto_align_profile(p, proxy_mgr, subscription_mgr)
    profile_mgr.update_profile(p)
    return res


@app.get("/api/v1/profiles/{profile_id}/health")
def audit_profile_health(profile_id: str):
    """环境跨层深度自洽体检：检查 IP 属地、时区、语言、UA、硬件及协议一致性，输出 100 分制评分"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    return GeoIPService.audit_profile_health(p, proxy_mgr, subscription_mgr)


@app.get("/api/v1/profiles/{profile_id}/fingerprint-report")
async def get_profile_fingerprint_report(profile_id: str):
    """获取 Profile 指纹自检报告：若已启动执行运行时 CDP 探针审计，未启动执行静态自洽性校验"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    from core.fingerprint_auditor import FingerprintAuditor
    status = launcher.get_status(profile_id)
    if status.is_running and status.cdp_port:
        return await FingerprintAuditor.audit_runtime_via_cdp(status.cdp_port, p)
    else:
        return FingerprintAuditor.audit_static_consistency(p)


@app.post("/api/v1/profiles/{profile_id}/clone", response_model=BrowserProfile)
def clone_profile(profile_id: str, req: Optional[CloneProfileRequest] = None):
    """克隆环境配置并深度复制沙箱隔离数据"""
    try:
        new_name = req.name if req else None
        copy_data = req.copy_data if req else True
        cloned = profile_mgr.clone_profile(profile_id, new_name=new_name, copy_data=copy_data)
        return cloned
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/profiles/{profile_id}/export")
def export_profile_archive(profile_id: str):
    """导出环境独立便携式归档包 (.zip)，包含完整指纹、Cookie 与沙箱数据"""
    try:
        zip_path = profile_mgr.export_profile_archive(profile_id)
        return FileResponse(
            str(zip_path),
            filename=zip_path.name,
            media_type="application/zip"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/profiles/import", response_model=BrowserProfile)
async def import_profile_archive(file: UploadFile = File(...)):
    """从本地上传的 .zip 归档包中导入环境与沙箱数据"""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip archives are supported")
    temp_zip = Path(tempfile.gettempdir()) / f"import_{int(time.time()*1000)}.zip"
    try:
        with open(temp_zip, "wb") as f:
            f.write(await file.read())
        imported = profile_mgr.import_profile_archive(temp_zip)
        return imported
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass


@app.get("/api/v1/profiles/{profile_id}/cookies")
async def get_profile_cookies(profile_id: str, format: str = Query("json")):
    """获取指定环境的 Cookie（运行中通过 CDP 实时抓取，离线时从本地 SQLite 数据库解密提取）"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    st = launcher.get_status(profile_id)
    cookies = []
    if st.is_running and st.ws_endpoint:
        try:
            cookies = await CookieManager.get_live_cookies_via_cdp(st.ws_endpoint)
        except Exception:
            cookies = []
    
    if not cookies:
        u_path = profile_mgr.get_user_data_path(profile_id)
        offline_c = CookieManager.load_offline_cookies(u_path)
        pending_c = CookieManager.get_pending_cookies(u_path)
        # 合并去重
        cmap = {(c.get("name"), c.get("domain"), c.get("path")): c for c in (offline_c + pending_c)}
        cookies = list(cmap.values())

    netscape_text = CookieManager.export_netscape(cookies)
    if format == "netscape":
        return PlainTextResponse(netscape_text)
    return {
        "success": True,
        "count": len(cookies),
        "cookies": cookies,
        "netscape": netscape_text
    }


@app.post("/api/v1/profiles/{profile_id}/cookies")
async def import_profile_cookies(profile_id: str, req: ImportCookiesRequest):
    """导入 Cookie（支持标准 JSON 数组或 Netscape 文本，运行中实时通过 CDP 注入，离线时加入下次启动自动装载队列）"""
    p = profile_mgr.get_profile(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        parsed = CookieManager.parse_any(req.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cookie 解析失败: {e}")

    if not parsed:
        raise HTTPException(status_code=400, detail="未解析出有效 Cookie 条目")

    st = launcher.get_status(profile_id)
    live_injected = False
    if st.is_running and st.ws_endpoint:
        live_injected = await CookieManager.set_live_cookies_via_cdp(st.ws_endpoint, parsed)

    # 无论在线与否，同时保存至待注入队列以备下次启动复用
    u_path = profile_mgr.get_user_data_path(profile_id)
    CookieManager.save_pending_cookies(u_path, parsed, merge=True)

    return {
        "success": True,
        "count": len(parsed),
        "live_injected": live_injected,
        "message": f"成功导入 {len(parsed)} 条 Cookie" + (" 并实时注入活跃浏览器" if live_injected else " (将在启动时自动装载)")
    }


@app.get("/api/v1/system/status")
def get_system_status():
    """查询系统核心网络引擎与 GeoIP 资产库就绪状态"""
    mihomo = subscription_mgr.mihomo_service
    return {
        "ready": mihomo.is_ready(),
        "message": mihomo.status_message,
        "active_profiles": len(launcher.running_processes),
        "engine_version": "Mihomo Meta 1.18+"
    }


# 挂载前端 GUI 静态资源
if GUI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(GUI_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(GUI_DIR / "index.html"))
