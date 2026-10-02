import re
import socket
import logging
import urllib.request
import json
import time
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from .models import BrowserProfile, FingerprintConfig, ProxyConfig
from .fingerprint_generator import HOST_CHROME_MAJOR, HOST_CHROME_VERSION

logger = logging.getLogger(__name__)

# 全球主要国家/地区的时区、语言和地理坐标知识库
GEO_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "GB": {
        "name": "United Kingdom",
        "cn_name": "英国",
        "timezone": "Europe/London",
        "languages": ["en-GB", "en"],
        "locale": "en-GB",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "accuracy": 100,
    },
    "US": {
        "name": "United States",
        "cn_name": "美国",
        "timezone": "America/New_York",
        "languages": ["en-US", "en"],
        "locale": "en-US",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "accuracy": 100,
    },
    "JP": {
        "name": "Japan",
        "cn_name": "日本",
        "timezone": "Asia/Tokyo",
        "languages": ["ja-JP", "ja", "en-US", "en"],
        "locale": "ja-JP",
        "latitude": 35.6762,
        "longitude": 139.6503,
        "accuracy": 100,
    },
    "HK": {
        "name": "Hong Kong",
        "cn_name": "香港",
        "timezone": "Asia/Hong_Kong",
        "languages": ["zh-HK", "zh", "en-US", "en"],
        "locale": "zh-HK",
        "latitude": 22.3193,
        "longitude": 114.1694,
        "accuracy": 100,
    },
    "TW": {
        "name": "Taiwan",
        "cn_name": "台湾",
        "timezone": "Asia/Taipei",
        "languages": ["zh-TW", "zh", "en-US", "en"],
        "locale": "zh-TW",
        "latitude": 25.0330,
        "longitude": 121.5654,
        "accuracy": 100,
    },
    "SG": {
        "name": "Singapore",
        "cn_name": "新加坡",
        "timezone": "Asia/Singapore",
        "languages": ["en-SG", "zh-SG", "en", "zh"],
        "locale": "en-SG",
        "latitude": 1.3521,
        "longitude": 103.8198,
        "accuracy": 100,
    },
    "KR": {
        "name": "South Korea",
        "cn_name": "韩国",
        "timezone": "Asia/Seoul",
        "languages": ["ko-KR", "ko", "en-US", "en"],
        "locale": "ko-KR",
        "latitude": 37.5665,
        "longitude": 126.9780,
        "accuracy": 100,
    },
    "DE": {
        "name": "Germany",
        "cn_name": "德国",
        "timezone": "Europe/Berlin",
        "languages": ["de-DE", "de", "en-US", "en"],
        "locale": "de-DE",
        "latitude": 52.5200,
        "longitude": 13.4050,
        "accuracy": 100,
    },
    "FR": {
        "name": "France",
        "cn_name": "法国",
        "timezone": "Europe/Paris",
        "languages": ["fr-FR", "fr", "en-US", "en"],
        "locale": "fr-FR",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "accuracy": 100,
    },
    "CA": {
        "name": "Canada",
        "cn_name": "加拿大",
        "timezone": "America/Toronto",
        "languages": ["en-CA", "en-US", "en"],
        "locale": "en-CA",
        "latitude": 43.6532,
        "longitude": -79.3832,
        "accuracy": 100,
    },
    "AU": {
        "name": "Australia",
        "cn_name": "澳大利亚",
        "timezone": "Australia/Sydney",
        "languages": ["en-AU", "en-US", "en"],
        "locale": "en-AU",
        "latitude": -33.8688,
        "longitude": 151.2093,
        "accuracy": 100,
    },
    "NL": {
        "name": "Netherlands",
        "cn_name": "荷兰",
        "timezone": "Europe/Amsterdam",
        "languages": ["nl-NL", "nl", "en-US", "en"],
        "locale": "nl-NL",
        "latitude": 52.3676,
        "longitude": 4.9041,
        "accuracy": 100,
    },
    "MY": {
        "name": "Malaysia",
        "cn_name": "马来西亚",
        "timezone": "Asia/Kuala_Lumpur",
        "languages": ["ms-MY", "en-MY", "en", "zh"],
        "locale": "ms-MY",
        "latitude": 3.1390,
        "longitude": 101.6869,
        "accuracy": 100,
    },
    "TH": {
        "name": "Thailand",
        "cn_name": "泰国",
        "timezone": "Asia/Bangkok",
        "languages": ["th-TH", "th", "en-US", "en"],
        "locale": "th-TH",
        "latitude": 13.7563,
        "longitude": 100.5018,
        "accuracy": 100,
    },
    "VN": {
        "name": "Vietnam",
        "cn_name": "越南",
        "timezone": "Asia/Ho_Chi_Minh",
        "languages": ["vi-VN", "vi", "en-US", "en"],
        "locale": "vi-VN",
        "latitude": 10.8231,
        "longitude": 106.6297,
        "accuracy": 100,
    },
    "IN": {
        "name": "India",
        "cn_name": "印度",
        "timezone": "Asia/Kolkata",
        "languages": ["en-IN", "hi-IN", "en"],
        "locale": "en-IN",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "accuracy": 100,
    },
    "PH": {
        "name": "Philippines",
        "cn_name": "菲律宾",
        "timezone": "Asia/Manila",
        "languages": ["en-PH", "fil-PH", "en"],
        "locale": "en-PH",
        "latitude": 14.5995,
        "longitude": 120.9842,
        "accuracy": 100,
    },
    "RU": {
        "name": "Russia",
        "cn_name": "俄罗斯",
        "timezone": "Europe/Moscow",
        "languages": ["ru-RU", "ru", "en-US", "en"],
        "locale": "ru-RU",
        "latitude": 55.7558,
        "longitude": 37.6173,
        "accuracy": 100,
    },
    "CN": {
        "name": "China",
        "cn_name": "中国大陆",
        "timezone": "Asia/Shanghai",
        "languages": ["zh-CN", "zh", "en-US", "en"],
        "locale": "zh-CN",
        "latitude": 31.2304,
        "longitude": 121.4737,
        "accuracy": 100,
    },
    "ES": {
        "name": "Spain",
        "cn_name": "西班牙",
        "timezone": "Europe/Madrid",
        "languages": ["es-ES", "es", "en-US", "en"],
        "locale": "es-ES",
        "latitude": 40.4168,
        "longitude": -3.7038,
        "accuracy": 100,
    },
    "IT": {
        "name": "Italy",
        "cn_name": "意大利",
        "timezone": "Europe/Rome",
        "languages": ["it-IT", "it", "en-US", "en"],
        "locale": "it-IT",
        "latitude": 41.9028,
        "longitude": 12.4964,
        "accuracy": 100,
    },
    "BR": {
        "name": "Brazil",
        "cn_name": "巴西",
        "timezone": "America/Sao_Paulo",
        "languages": ["pt-BR", "pt", "en-US", "en"],
        "locale": "pt-BR",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "accuracy": 100,
    },
    "MX": {
        "name": "Mexico",
        "cn_name": "墨西哥",
        "timezone": "America/Mexico_City",
        "languages": ["es-MX", "es", "en-US", "en"],
        "locale": "es-MX",
        "latitude": 19.4326,
        "longitude": -99.1332,
        "accuracy": 100,
    },
    "TR": {
        "name": "Turkey",
        "cn_name": "土耳其",
        "timezone": "Europe/Istanbul",
        "languages": ["tr-TR", "tr", "en-US", "en"],
        "locale": "tr-TR",
        "latitude": 41.0082,
        "longitude": 28.9784,
        "accuracy": 100,
    },
    "ID": {
        "name": "Indonesia",
        "cn_name": "印度尼西亚",
        "timezone": "Asia/Jakarta",
        "languages": ["id-ID", "id", "en-US", "en"],
        "locale": "id-ID",
        "latitude": -6.2088,
        "longitude": 106.8456,
        "accuracy": 100,
    },
    "PL": {
        "name": "Poland",
        "cn_name": "波兰",
        "timezone": "Europe/Warsaw",
        "languages": ["pl-PL", "pl", "en-US", "en"],
        "locale": "pl-PL",
        "latitude": 52.2297,
        "longitude": 21.0122,
        "accuracy": 100,
    },
    "SE": {
        "name": "Sweden",
        "cn_name": "瑞典",
        "timezone": "Europe/Stockholm",
        "languages": ["sv-SE", "sv", "en-US", "en"],
        "locale": "sv-SE",
        "latitude": 59.3293,
        "longitude": 18.0686,
        "accuracy": 100,
    },
    "CH": {
        "name": "Switzerland",
        "cn_name": "瑞士",
        "timezone": "Europe/Zurich",
        "languages": ["de-CH", "fr-CH", "en-US", "en"],
        "locale": "de-CH",
        "latitude": 47.3769,
        "longitude": 8.5417,
        "accuracy": 100,
    },
    "AE": {
        "name": "United Arab Emirates",
        "cn_name": "阿联酋",
        "timezone": "Asia/Dubai",
        "languages": ["ar-AE", "en-AE", "en"],
        "locale": "ar-AE",
        "latitude": 25.2048,
        "longitude": 55.2708,
        "accuracy": 100,
    },
    "NZ": {
        "name": "New Zealand",
        "cn_name": "新西兰",
        "timezone": "Pacific/Auckland",
        "languages": ["en-NZ", "en-US", "en"],
        "locale": "en-NZ",
        "latitude": -36.8485,
        "longitude": 174.7633,
        "accuracy": 100,
    },
    "PT": {
        "name": "Portugal",
        "cn_name": "葡萄牙",
        "timezone": "Europe/Lisbon",
        "languages": ["pt-PT", "pt", "en-US", "en"],
        "locale": "pt-PT",
        "latitude": 38.7223,
        "longitude": -9.1393,
        "accuracy": 100,
    },
    "IE": {
        "name": "Ireland",
        "cn_name": "爱尔兰",
        "timezone": "Europe/Dublin",
        "languages": ["en-IE", "en-US", "en"],
        "locale": "en-IE",
        "latitude": 53.3498,
        "longitude": -6.2603,
        "accuracy": 100,
    },
    "AR": {
        "name": "Argentina",
        "cn_name": "阿根廷",
        "timezone": "America/Argentina/Buenos_Aires",
        "languages": ["es-AR", "es", "en-US", "en"],
        "locale": "es-AR",
        "latitude": -34.6037,
        "longitude": -58.3816,
        "accuracy": 100,
    },
    "ZA": {
        "name": "South Africa",
        "cn_name": "南非",
        "timezone": "Africa/Johannesburg",
        "languages": ["en-ZA", "en-US", "en"],
        "locale": "en-ZA",
        "latitude": -26.2041,
        "longitude": 28.0473,
        "accuracy": 100,
    },
}

# 文本关键词匹配国家简称
KEYWORD_TO_COUNTRY: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?:香港|HK|Hong\s*Kong)", re.I), "HK"),
    (re.compile(r"(?:台湾|台灣|TW|Taiwan)", re.I), "TW"),
    (re.compile(r"(?:日本|JP|Japan|Tokyo|Osaka)", re.I), "JP"),
    (re.compile(r"(?:英国|英國|GB|UK|United\s*Kingdom|London)", re.I), "GB"),
    (re.compile(r"(?:美国|美國|US|USA|United\s*States|America|New\s*York|Los\s*Angeles)", re.I), "US"),
    (re.compile(r"(?:新加坡|SG|Singapore)", re.I), "SG"),
    (re.compile(r"(?:韩国|韓國|KR|Korea|Seoul)", re.I), "KR"),
    (re.compile(r"(?:德国|德國|DE|Germany|Berlin|Frankfurt)", re.I), "DE"),
    (re.compile(r"(?:法国|法國|FR|France|Paris)", re.I), "FR"),
    (re.compile(r"(?:加拿大|CA|Canada|Toronto|Vancouver)", re.I), "CA"),
    (re.compile(r"(?:澳大利亚|澳洲|AU|Australia|Sydney|Melbourne)", re.I), "AU"),
    (re.compile(r"(?:荷兰|荷蘭|NL|Netherlands|Amsterdam)", re.I), "NL"),
    (re.compile(r"(?:西班牙|ES|Spain|Madrid)", re.I), "ES"),
    (re.compile(r"(?:意大利|IT|Italy|Rome|Milan)", re.I), "IT"),
    (re.compile(r"(?:巴西|BR|Brazil|Sao\s*Paulo)", re.I), "BR"),
    (re.compile(r"(?:墨西哥|MX|Mexico)", re.I), "MX"),
    (re.compile(r"(?:土耳其|TR|Turkey|Istanbul)", re.I), "TR"),
    (re.compile(r"(?:印尼|印度尼西亚|ID|Indonesia|Jakarta)", re.I), "ID"),
    (re.compile(r"(?:波兰|PL|Poland|Warsaw)", re.I), "PL"),
    (re.compile(r"(?:瑞典|SE|Sweden|Stockholm)", re.I), "SE"),
    (re.compile(r"(?:瑞士|CH|Switzerland|Zurich)", re.I), "CH"),
    (re.compile(r"(?:阿联酋|迪拜|AE|Dubai|Abu\s*Dhabi)", re.I), "AE"),
    (re.compile(r"(?:新西兰|NZ|New\s*Zealand|Auckland)", re.I), "NZ"),
    (re.compile(r"(?:葡萄牙|PT|Portugal|Lisbon)", re.I), "PT"),
    (re.compile(r"(?:爱尔兰|IE|Ireland|Dublin)", re.I), "IE"),
    (re.compile(r"(?:阿根廷|AR|Argentina|Buenos\s*Aires)", re.I), "AR"),
    (re.compile(r"(?:南非|ZA|South\s*Africa|Johannesburg)", re.I), "ZA"),
    (re.compile(r"(?:马来西亚|MY|Malaysia)", re.I), "MY"),
    (re.compile(r"(?:泰国|泰國|TH|Thailand|Bangkok)", re.I), "TH"),
    (re.compile(r"(?:越南|VN|Vietnam)", re.I), "VN"),
    (re.compile(r"(?:印度|IN|India|Mumbai)", re.I), "IN"),
    (re.compile(r"(?:菲律宾|PH|Philippines|Manila)", re.I), "PH"),
    (re.compile(r"(?:俄罗斯|俄羅斯|RU|Russia|Moscow)", re.I), "RU"),
    (re.compile(r"(?:中国|CN|China|Shanghai|Beijing)", re.I), "CN"),
]


class GeoIPService:
    """GeoIP 与代理自洽分析服务"""

    @staticmethod
    def infer_country_from_text(text: str) -> Optional[str]:
        """从节点名称、代理别名或城市描述中提取国家代码 (如 'GB', 'US', 'HK')"""
        if not text:
            return None
        for pattern, code in KEYWORD_TO_COUNTRY:
            if pattern.search(text):
                return code
        return None

    @classmethod
    def get_geo_defaults(cls, country_or_locale: str) -> Dict[str, Any]:
        """获取指定国家或语言区域的自洽时区、语言列表及参考经纬度（支持 'US', 'GB', 'zh-CN', 'ja-JP' 等）"""
        if not country_or_locale:
            return GEO_KNOWLEDGE_BASE["US"]
        
        # 1. 尝试直接通过国家代码匹配 (如 'GB', 'US', 'JP')
        code = country_or_locale.upper().strip()
        if code in GEO_KNOWLEDGE_BASE:
            return GEO_KNOWLEDGE_BASE[code]

        # 2. 如果包含连字符或下划线 (如 'zh-CN', 'en-US', 'ja_JP')
        if "-" in code or "_" in code:
            parts = code.replace("_", "-").split("-")
            sub_code = parts[-1].upper()
            if sub_code in GEO_KNOWLEDGE_BASE:
                return GEO_KNOWLEDGE_BASE[sub_code]

        # 3. 遍历匹配 locale
        for c_code, info in GEO_KNOWLEDGE_BASE.items():
            if info.get("locale", "").lower() == country_or_locale.lower():
                return info

        # 4. 尝试关键词提取
        inferred = cls.infer_country_from_text(country_or_locale)
        if inferred and inferred in GEO_KNOWLEDGE_BASE:
            return GEO_KNOWLEDGE_BASE[inferred]

        return GEO_KNOWLEDGE_BASE["US"]

    @classmethod
    def list_supported_countries(cls) -> List[Dict[str, Any]]:
        """获取全部已支持的主流国家与语言列表（按常见使用热度排序）"""
        priority_order = [
            "CN", "US", "GB", "JP", "HK", "TW", "SG", "KR", "DE", "FR",
            "CA", "AU", "NL", "ES", "IT", "RU", "BR", "IN", "MY", "TH",
            "VN", "PH", "ID", "TR", "AE", "CH", "SE", "PL", "NZ", "MX",
            "PT", "IE", "AR", "ZA"
        ]
        results = []
        for code in priority_order:
            if code in GEO_KNOWLEDGE_BASE:
                info = GEO_KNOWLEDGE_BASE[code]
                results.append({
                    "country_code": code,
                    "locale": info["locale"],
                    "cn_name": info["cn_name"],
                    "en_name": info["name"],
                    "timezone": info["timezone"],
                    "languages": info["languages"],
                    "display_name": f"{info['cn_name']} ({info['locale']}, {info['timezone']})"
                })
        return results

    @staticmethod
    def probe_proxy_live_geo(proxy_config: ProxyConfig) -> Optional[Dict[str, Any]]:
        """通过指定代理实时探测出口真实 IP 及地理时区信息"""
        import requests
        try:
            scheme = "socks5h" if "sock" in proxy_config.type.lower() else ("https" if proxy_config.type == "https" else "http")
            auth = f"{proxy_config.username}:{proxy_config.password}@" if proxy_config.username else ""
            p_url = f"{scheme}://{auth}{proxy_config.host}:{proxy_config.port}"
            proxies = {"http": p_url, "https": p_url}
            
            resp = requests.get(
                "http://ip-api.com/json",
                proxies=proxies,
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return {
                        "exit_ip": data.get("query"),
                        "country_code": data.get("countryCode"),
                        "country": data.get("country"),
                        "city": data.get("city"),
                        "timezone": data.get("timezone"),
                        "latitude": data.get("lat"),
                        "longitude": data.get("lon"),
                        "isp": data.get("isp"),
                    }
        except Exception as e:
            logger.debug(f"Direct proxy live geo probe failed: {e}")
        return None

    @classmethod
    def resolve_profile_target_geo(
        cls,
        profile: BrowserProfile,
        proxy_manager: Any,
        subscription_manager: Any
    ) -> Dict[str, Any]:
        """
        全量推导 Profile 所绑定的代理的地理归属：
        1. 尝试从绑定的节点或代理缓存中获取国家/时区
        2. 若缓存无，则通过名称模式匹配国家代码
        3. 若命中已知国家，返回对应的权威时区和语言设定
        """
        country_code = None
        source_desc = "未绑定代理"
        cached_tz = None
        cached_city = None
        exit_ip = None

        # 1. 订阅节点
        if profile.sub_node_id and subscription_manager:
            for sub in subscription_manager.list_subscriptions():
                for n in sub.nodes:
                    if n.id == profile.sub_node_id:
                        source_desc = f"订阅节点: {n.name}"
                        exit_ip = n.exit_ip
                        cached_city = getattr(n, "city", None)
                        cached_tz = getattr(n, "timezone", None)
                        if n.country:
                            country_code = cls.infer_country_from_text(n.country)
                        if not country_code:
                            country_code = cls.infer_country_from_text(n.name)
                        break
                if country_code:
                    break

        # 2. 独立代理
        if not country_code and profile.proxy_id and proxy_manager:
            p = proxy_manager.get_proxy(profile.proxy_id)
            if p:
                source_desc = f"独立代理: {p.name}"
                exit_ip = p.exit_ip
                cached_city = p.city
                cached_tz = p.timezone
                if p.country:
                    country_code = cls.infer_country_from_text(p.country)
                if not country_code:
                    country_code = cls.infer_country_from_text(p.name)

        # 3. 嵌入式代理
        if not country_code and profile.proxy and profile.proxy.enabled:
            source_desc = f"嵌入代理: {profile.proxy.host}:{profile.proxy.port}"
            # 尝试通过 IP 反查
            country_code = cls.infer_country_from_text(profile.proxy.host)

        if not country_code:
            country_code = "CN" if "zh" in (profile.fingerprint.languages[0] if profile.fingerprint.languages else "") else "US"

        defaults = cls.get_geo_defaults(country_code)

        target_tz = cached_tz if cached_tz else defaults["timezone"]
        return {
            "country_code": country_code,
            "country_name": defaults["name"],
            "country_cn_name": defaults["cn_name"],
            "timezone": target_tz,
            "languages": defaults["languages"],
            "locale": defaults["locale"],
            "latitude": defaults["latitude"],
            "longitude": defaults["longitude"],
            "accuracy": defaults["accuracy"],
            "exit_ip": exit_ip,
            "city": cached_city,
            "source_desc": source_desc,
        }

    @classmethod
    def auto_align_profile(
        cls,
        profile: BrowserProfile,
        proxy_manager: Any,
        subscription_manager: Any
    ) -> Dict[str, Any]:
        """
        一键自洽对齐：将 Profile 的指纹（时区、语言、WebRTC、内核参数）深度适配当前绑定的代理
        """
        geo_info = cls.resolve_profile_target_geo(profile, proxy_manager, subscription_manager)

        changes = []
        old_tz = profile.fingerprint.timezone
        new_tz = geo_info["timezone"]
        if old_tz != new_tz:
            profile.fingerprint.timezone = new_tz
            changes.append(f"时区: {old_tz} ➔ {new_tz}")

        old_langs = profile.fingerprint.languages
        new_langs = geo_info["languages"]
        if old_langs != new_langs:
            profile.fingerprint.languages = new_langs
            changes.append(f"语言: {','.join(old_langs)} ➔ {','.join(new_langs)}")

        # 确保 WebRTC 策略处于最安全模式
        if profile.fingerprint.webrtc_policy != "disable_non_proxied_udp":
            profile.fingerprint.webrtc_policy = "disable_non_proxied_udp"
            changes.append("WebRTC策略 ➔ disable_non_proxied_udp")

        # 确保 Canvas 与 Audio 处于原生纯净模式
        if profile.fingerprint.canvas_noise_enabled:
            profile.fingerprint.canvas_noise_enabled = False
            changes.append("Canvas加噪 ➔ 关闭 (恢复原生自洽)")
        if profile.fingerprint.audio_noise_enabled:
            profile.fingerprint.audio_noise_enabled = False
            changes.append("Audio加噪 ➔ 关闭 (恢复原生自洽)")

        # 确保 User-Agent 与宿主 Chrome 主版本对齐（仅当指纹类型为 Chrome 且未指定特定系统/浏览器时）
        b_name = getattr(profile.fingerprint, "browser_name", "Chrome") or "Chrome"
        current_ua = profile.fingerprint.user_agent
        if b_name.lower() == "chrome" and f"Chrome/{HOST_CHROME_MAJOR}" not in current_ua and "Firefox" not in current_ua and "Safari" not in current_ua:
            new_ua = re.sub(r"Chrome/\d+", f"Chrome/{HOST_CHROME_MAJOR}", current_ua)
            profile.fingerprint.user_agent = new_ua
            changes.append(f"User-Agent 内核版本 ➔ Chrome/{HOST_CHROME_MAJOR}")

        return {
            "success": True,
            "profile_id": profile.id,
            "profile_name": profile.name,
            "aligned_country": f"{geo_info['country_cn_name']} ({geo_info['country_code']})",
            "source_desc": geo_info["source_desc"],
            "changes": changes,
            "aligned_fingerprint": profile.fingerprint.model_dump(),
        }

    @classmethod
    def audit_profile_health(
        cls,
        profile: BrowserProfile,
        proxy_manager: Any,
        subscription_manager: Any
    ) -> Dict[str, Any]:
        """
        全面深度自洽体检：检查时区、语言、UA、WebRTC、硬件等各项参数是否存在矛盾与红线
        满分 100 分。
        """
        score = 100
        items = []
        geo = cls.resolve_profile_target_geo(profile, proxy_manager, subscription_manager)
        fp = profile.fingerprint

        # 1. 代理与时区交叉自洽性检测 (致命项)
        expected_tz = geo["timezone"]
        current_tz = fp.timezone
        # 提取洲际/地区前缀
        expected_region = expected_tz.split("/")[0] if "/" in expected_tz else ""
        current_region = current_tz.split("/")[0] if "/" in current_tz else ""

        if current_tz == expected_tz:
            items.append({
                "category": "网络与时区自洽",
                "title": "时区与代理国家匹配",
                "status": "pass",
                "message": f"当前时区 ({current_tz}) 与代理归属 ({geo['country_cn_name']}) 完美匹配",
                "detail": f"代理出口: {geo['source_desc']}"
            })
        elif expected_region and expected_region == current_region:
            score -= 10
            items.append({
                "category": "网络与时区自洽",
                "title": "时区处于同一大区但有偏差",
                "status": "warning",
                "message": f"当前时区为 {current_tz}，建议与代理精准匹配为 {expected_tz}",
                "detail": f"建议时区: {expected_tz}"
            })
        else:
            score -= 30
            items.append({
                "category": "网络与时区自洽",
                "title": "时区跨洲严重冲突 (高危红线)",
                "status": "danger",
                "message": f"代理出口为 {geo['country_cn_name']}，但浏览器时区为 {current_tz}，将直接导致 Cloudflare/WAF 拦截",
                "detail": f"建议立刻对齐为: {expected_tz}"
            })

        # 2. 语言 (Accept-Language / navigator.languages) 检测
        primary_lang = fp.languages[0] if fp.languages else ""
        expected_primary = geo["languages"][0] if geo["languages"] else ""
        if primary_lang.split("-")[0] == expected_primary.split("-")[0]:
            items.append({
                "category": "网络与语言自洽",
                "title": "主语言与代理属地匹配",
                "status": "pass",
                "message": f"浏览器主语言 ({primary_lang}) 与代理属地一致",
                "detail": f"语言列表: {', '.join(fp.languages)}"
            })
        else:
            score -= 15
            items.append({
                "category": "网络与语言自洽",
                "title": "主语言与代理属地存在偏离",
                "status": "warning",
                "message": f"代理出口为 {geo['country_cn_name']}，但浏览器主语言为 {primary_lang}，容易引起站点风控警惕",
                "detail": f"推荐语言首选: {expected_primary}"
            })

        # 3. User-Agent 与宿主 Chrome/V8 内核版本检测
        b_name = getattr(fp, "browser_name", "Chrome") or "Chrome"
        os_name = getattr(fp, "os_name", "Windows") or "Windows"
        ua_match = re.search(r"Chrome/(\d+)", fp.user_agent)
        ua_major = ua_match.group(1) if ua_match else "0"

        if b_name.lower() in ["firefox", "safari"]:
            items.append({
                "category": "环境与仿真属性",
                "title": f"模拟 {b_name} 浏览器特征",
                "status": "pass",
                "message": f"当前配置为模拟 {b_name} 浏览器 ({os_name})，CDP 已适配对应客户端协议与标头",
                "detail": f"UA: {fp.user_agent[:45]}..."
            })
        elif b_name.lower() == "edge":
            items.append({
                "category": "环境与仿真属性",
                "title": "Microsoft Edge 内核特征",
                "status": "pass",
                "message": f"已配置 Edge 专属品牌签名与 Client Hints (Edg/{ua_major})",
                "detail": f"底层 Chromium 内核版本: {ua_major}"
            })
        elif ua_major == HOST_CHROME_MAJOR:
            items.append({
                "category": "内核与 V8 一致性",
                "title": "UA 主版本与底层宿主对齐",
                "status": "pass",
                "message": f"Chrome/{ua_major} 与宿主二进制 Chrome/{HOST_CHROME_MAJOR} 保持 100% 同步",
                "detail": "V8 内部字节码与特征探测完全自洽"
            })
        else:
            score -= 10
            items.append({
                "category": "内核与 V8 一致性",
                "title": "自定义内核版本 (跨版本仿真)",
                "status": "warning",
                "message": f"声明 UA 为 Chrome/{ua_major}，宿主底层为 Chrome/{HOST_CHROME_MAJOR}。已通过 CDP Client Hints 实现全链路参数映射",
                "detail": f"当前版本: Chrome/{ua_major} | 宿主: Chrome/{HOST_CHROME_MAJOR}"
            })

        # 4. WebRTC 泄露策略检测
        if fp.webrtc_policy == "disable_non_proxied_udp":
            items.append({
                "category": "协议安全",
                "title": "WebRTC UDP 防泄漏已开启",
                "status": "pass",
                "message": "已配置 disable_non_proxied_udp，阻止本地局域网与物理真实公网 IP 旁路泄露",
                "detail": "WebRTC IP Handling Policy 生效中"
            })
        else:
            score -= 15
            items.append({
                "category": "协议安全",
                "title": "WebRTC 存在公网 IP 泄露风险",
                "status": "danger",
                "message": f"当前 WebRTC 策略为 {fp.webrtc_policy}，网页可通过 STUN 获取您的物理真实 IP",
                "detail": "建议切换为 disable_non_proxied_udp"
            })

        # 5. 指纹伪造洁净度检测 (Canvas / Audio)
        if not fp.canvas_noise_enabled and not fp.audio_noise_enabled:
            items.append({
                "category": "指纹纯净度",
                "title": "原生硬件自洽 (无粗暴加噪痕迹)",
                "status": "pass",
                "message": "采用原生物理 GPU/Audio 特征，零 JS 原型链污染，杜绝被指纹探针识别为篡改环境",
                "detail": f"GPU: {fp.webgl_renderer.split('(')[1].split(',')[0] if '(' in fp.webgl_renderer else 'Standard'}"
            })
        else:
            score -= 10
            items.append({
                "category": "指纹纯净度",
                "title": "开启了粗暴加噪 (可能被高级探针识别)",
                "status": "warning",
                "message": "检测到开启了 Canvas 或 Audio 噪声扰动，部分严苛风控站点可能判定 Canvas 被篡改",
                "detail": "建议关闭强加噪，保持原生纯净"
            })

        # 6. 视口与屏幕几何自洽性检测
        if fp.screen_avail_height <= fp.screen_height and fp.screen_avail_width <= fp.screen_width:
            items.append({
                "category": "设备参数自洽",
                "title": "屏幕工作区几何逻辑正常",
                "status": "pass",
                "message": f"分辨率 {fp.screen_width}x{fp.screen_height}，工作区 {fp.screen_avail_width}x{fp.screen_avail_height} 符合物理桌面规范",
                "detail": "AvailScreen 尺寸低于总分辨率，符合 Windows 任务栏形态"
            })
        else:
            score -= 10
            items.append({
                "category": "设备参数自洽",
                "title": "工作区尺寸超越物理屏幕",
                "status": "warning",
                "message": "availHeight 或 availWidth 大于物理分辨率，不合常理",
                "detail": "请修正屏幕尺寸"
            })

        score = max(0, min(100, score))
        if score >= 90:
            level = "excellent"
            level_text = "极佳 (自洽度 90%+)"
            level_color = "#10B981"
        elif score >= 75:
            level = "good"
            level_text = "良好 (自洽度 75%+)"
            level_color = "#38BDF8"
        elif score >= 60:
            level = "warning"
            level_text = "有风险 (自洽度 60%+)"
            level_color = "#F59E0B"
        else:
            level = "danger"
            level_text = "高危 (严重冲突)"
            level_color = "#EF4444"

        return {
            "profile_id": profile.id,
            "profile_name": profile.name,
            "score": score,
            "level": level,
            "level_text": level_text,
            "level_color": level_color,
            "target_geo": geo,
            "items": items,
            "can_auto_fix": score < 100,
        }
