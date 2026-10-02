# -*- coding: utf-8 -*-
"""
PhantomBrowser 字体管理与审计工具 (Font Helper)
提供字体审计、系统专属字体包检测以及跨平台字体环境部署。
"""

import os
import sys
import winreg
from pathlib import Path
from typing import List, Dict, Tuple, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.font_packs import MAC_FONT_ALLOWLIST, WIN_FONT_ALLOWLIST, LINUX_FONT_ALLOWLIST


def get_installed_windows_fonts() -> set:
    """获取 Windows 宿主机当前已注册的所有字体家族名称"""
    fonts = set()
    # 1. 检查 HKLM 字体
    for root, path in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
    ]:
        try:
            with winreg.OpenKey(root, path) as k:
                num_values = winreg.QueryInfoKey(k)[1]
                for i in range(num_values):
                    name, _, _ = winreg.EnumValue(k, i)
                    # 剥离 " (TrueType)", " (OpenType)" 等后缀
                    clean_name = name.split(" (")[0].strip()
                    fonts.add(clean_name.lower())
        except Exception:
            pass
    return fonts


def audit_font_environment(target_os: str = "macos") -> Dict[str, Any]:
    """审计当前宿主机与目标模拟系统的字体匹配情况"""
    installed = get_installed_windows_fonts()
    target = target_os.lower()
    
    if "mac" in target:
        expected = MAC_FONT_ALLOWLIST
    elif "linux" in target:
        expected = LINUX_FONT_ALLOWLIST
    else:
        expected = WIN_FONT_ALLOWLIST

    matched = []
    missing = []
    for f in expected:
        if f.lower() in installed:
            matched.append(f)
        else:
            missing.append(f)

    return {
        "target_os": target_os,
        "expected_count": len(expected),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "matched_sample": matched[:10],
        "missing_sample": missing[:10]
    }


def install_font_files_to_user_profile(font_files: List[str]) -> Tuple[int, List[str]]:
    """无需管理员权限，将字体文件安装至当前用户的本地字体库并写入注册表"""
    dest_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    os.makedirs(dest_dir, exist_ok=True)
    
    installed_count = 0
    errors = []

    reg_key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows NT\CurrentVersion\Fonts",
        0,
        winreg.KEY_SET_VALUE
    )

    for src in font_files:
        p = Path(src)
        if not p.is_file() or p.suffix.lower() not in (".ttf", ".ttc", ".otf"):
            continue
        try:
            target_path = os.path.join(dest_dir, p.name)
            # 复制文件
            with open(src, "rb") as rf, open(target_path, "wb") as wf:
                wf.write(rf.read())
            
            # 注册表注册
            font_title = p.stem.replace("-", " ") + " (TrueType)"
            winreg.SetValueEx(reg_key, font_title, 0, winreg.REG_SZ, target_path)
            installed_count += 1
        except Exception as e:
            errors.append(f"{p.name}: {e}")

    try:
        winreg.CloseKey(reg_key)
    except Exception:
        pass

    return installed_count, errors


if __name__ == "__main__":
    print("=== 宿主机当前字体环境审计 (模拟 macOS) ===")
    res = audit_font_environment("macos")
    print(f"目标系统: {res['target_os']}")
    print(f"标准字体总数: {res['expected_count']}, 当前命中: {res['matched_count']}, 缺失: {res['missing_count']}")
    print(f"已安装 Mac 字体示例: {res['matched_sample']}")
    print(f"缺失 Mac 字体示例: {res['missing_sample']}")
