# -*- coding: utf-8 -*-
"""
PhantomBrowser 全平台底层自洽 Envelope 构建器 (Unified Profile Envelope Builder)
严格对齐 Apostate C++ 内核 profile.schema.json 契约规范，
为 Windows、macOS、Linux 生成 100% 完整的原生硬件与操作系统载荷。
"""

import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from .font_packs import get_font_profile

# 常用系统预设系统语音 (SpeechSynthesis Voices)
SYSTEM_SPEECH_VOICES: Dict[str, List[Dict[str, Any]]] = {
    "macos": [
        {"name": "Samantha", "lang": "en-US", "default": True, "local_service": True},
        {"name": "Alex", "lang": "en-US", "default": False, "local_service": True},
        {"name": "Victoria", "lang": "en-US", "default": False, "local_service": True},
        {"name": "Tingting", "lang": "zh-CN", "default": False, "local_service": True},
        {"name": "Meijia", "lang": "zh-TW", "default": False, "local_service": True},
        {"name": "Sinji", "lang": "zh-HK", "default": False, "local_service": True},
    ],
    "windows": [
        {"name": "Microsoft David - English (United States)", "lang": "en-US", "default": True, "local_service": True},
        {"name": "Microsoft Zira - English (United States)", "lang": "en-US", "default": False, "local_service": True},
        {"name": "Microsoft Mark - English (United States)", "lang": "en-US", "default": False, "local_service": True},
        {"name": "Microsoft Huihui - Chinese (Simplified, PRC)", "lang": "zh-CN", "default": False, "local_service": True},
        {"name": "Microsoft Yaoyao - Chinese (Simplified, PRC)", "lang": "zh-CN", "default": False, "local_service": True},
        {"name": "Microsoft Kangkang - Chinese (Simplified, PRC)", "lang": "zh-CN", "default": False, "local_service": True},
    ],
    "linux": [
        {"name": "English (America)", "lang": "en-US", "default": True, "local_service": True},
        {"name": "Chinese (China)", "lang": "zh-CN", "default": False, "local_service": True},
    ]
}


def build_unified_envelope(
    platform_persona: str,
    user_agent: str,
    cpu_cores: int,
    memory_gb: int,
    gpu_vendor: str,
    gpu_renderer: str,
    screen_width: int,
    screen_height: int,
    screen_avail_width: int,
    screen_avail_height: int,
    device_pixel_ratio: float = 1.0,
    os_version: str = "10.0.0",
    languages: Optional[List[str]] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    构建符合 Apostate 规范的统一 profile envelope 字典
    """
    persona = (platform_persona or "windows").lower()
    if "mac" in persona:
        os_key = "macos"
        platform_name = "macOS"
        nav_platform = "MacIntel"
        arch = "arm"
        bitness = "64"
        audio_buffer = 256  # CoreAudio default buffer
    elif "linux" in persona:
        os_key = "linux"
        platform_name = "Linux"
        nav_platform = "Linux x86_64"
        arch = "x86"
        bitness = "64"
        audio_buffer = 512
    else:
        os_key = "windows"
        platform_name = "Windows"
        nav_platform = "Win32"
        arch = "x86"
        bitness = "64"
        audio_buffer = 480  # Windows WASAPI shared mode default

    # 1. 基础硬件与平台描述
    envelope: Dict[str, Any] = {
        "platform": {
            "name": platform_name,
            "navigator_platform": nav_platform,
            "version": os_version or ("14.5.0" if os_key == "macos" else "10.0.0"),
            "architecture": arch,
            "bitness": bitness,
            "model": "",
            "mobile": False
        },
        "browser": {
            "user_agent": user_agent
        },
        "cpu": {
            "logical_cores": max(2, min(int(cpu_cores or 8), 64))
        },
        "memory": {
            "total_bytes": max(2, int(memory_gb or 8)) * 1024 * 1024 * 1024
        },
        "gpu": {
            "unmasked_vendor": gpu_vendor or ("Google Inc. (Apple)" if os_key == "macos" else "Google Inc. (NVIDIA)"),
            "unmasked_renderer": gpu_renderer or ("ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)" if os_key == "macos" else "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)")
        },
        "screen": {
            "width": int(screen_width or 1920),
            "height": int(screen_height or 1080),
            "avail_width": int(screen_avail_width or screen_width or 1920),
            "avail_height": int(screen_avail_height or (screen_height - 40 if screen_height else 1040)),
            "device_pixel_ratio": float(device_pixel_ratio or (2.0 if os_key == "macos" else 1.0)),
            "color_depth": 24
        },
        # 2. 操作系统全量字体白名单与通用族映射
        "fonts": get_font_profile(os_key),
        # 3. 真实系统合成语音列表
        "speech": {
            "voices": SYSTEM_SPEECH_VOICES.get(os_key, SYSTEM_SPEECH_VOICES["windows"])
        },
        # 4. 音频输出硬件缓冲
        "audio": {
            "hardware_buffer_frames": audio_buffer
        },
        # 5. 网络信息指示 (NetInfo API)
        "network": {
            "effective_type": "4g",
            "http_rtt_ms": 50,
            "downlink_mbps": 10.0,
            "save_data": False
        },
        # 6. 电池状态指示 (桌面/高电量笔记本)
        "battery": {
            "present": True,
            "charging": True,
            "level": 1.0,
            "charging_time_seconds": 0,
            "discharging_time_seconds": 0
        }
    }

    return envelope


def encode_envelope_payload(envelope: Dict[str, Any]) -> str:
    """将 envelope 编码为 Apostate 接收的 base64 字符串"""
    raw_json = json.dumps(envelope, ensure_ascii=True, separators=(',', ':'))
    return base64.b64encode(raw_json.encode('utf-8')).decode('ascii')
