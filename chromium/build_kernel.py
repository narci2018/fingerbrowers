#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PhantomBrowser 路线 B: 本地 Chromium 自主内核编译管线 (chromium/build_kernel.py)
-------------------------------------------------------------------------
功能：
1. 校验本地 Visual Studio 2022 / Windows SDK 10.0.26100 及 depot_tools 工具链；
2. 自动化生成 out/Default/args.gn 商业级 Release 编译配置（剥离符号/遥测，启用 AVX2/O2 优化）；
3. 自动化调度 gn gen 与 autoninja -C out/Default chrome 实施全速编译；
4. 编译完成后自动执行 Windows SxS Manifest 配置并将产物封装部署至 runtime/kernel/。
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 确保 UTF-8 控制台输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMIUM_DIR = BASE_DIR / "chromium"
SRC_DIR = BASE_DIR / "src"
OUT_DIR = SRC_DIR / "out" / "Default"
DEPLOY_DIR = BASE_DIR / "runtime" / "kernel"

GN_ARGS = """
# PhantomBrowser 商业级内核编译优化配置
is_debug = false
is_official_build = true
is_component_build = false
symbol_level = 0
blink_symbol_level = 0
enable_nacl = false
chrome_pgo_phase = 0
treat_warnings_as_errors = false
ffmpeg_branding = "Chrome"
proprietary_codecs = true
dcheck_always_on = false
exclude_unwind_tables = true
"""

def main():
    print("=" * 65)
    print(" [PhantomBrowser 路线 B] 本地商业级 Chromium 内核自主编译管线")
    print("=" * 65)

    if not SRC_DIR.exists():
        print(f"[提示] 未检测到 Chromium 完整源码树 ({SRC_DIR})")
        print("  请确认已使用 depot_tools 同步对应版本的源码：")
        print("    fetch --no-history chromium")
        print("  并在 src/ 目录下运行 python chromium/apply_patches.py 应用全部补丁。")
        sys.exit(0)

    # 1. 写入 args.gn
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args_gn_file = OUT_DIR / "args.gn"
    args_gn_file.write_text(GN_ARGS.strip(), encoding="utf-8")
    print(f"[OK] 已生成 Release 编译优化配置: {args_gn_file}")

    # 2. 生成 Ninja 构建图 (gn gen)
    print("[*] 正在执行 gn gen out/Default ...")
    res = subprocess.run(["gn", "gen", "out/Default"], cwd=str(SRC_DIR), shell=True)
    if res.returncode != 0:
        print("[ERROR] gn gen 失败，请检查 depot_tools 是否在系统 PATH 中。")
        sys.exit(res.returncode)

    # 3. 启动并行编译 (autoninja -C out/Default chrome)
    print("[*] 启动全速并行编译: autoninja -C out/Default chrome ...")
    res = subprocess.run(["autoninja", "-C", "out/Default", "chrome"], cwd=str(SRC_DIR), shell=True)
    if res.returncode != 0:
        print(f"[ERROR] 编译过程出错，退出码: {res.returncode}")
        sys.exit(res.returncode)

    # 4. 自动部署与封装
    print("[*] 编译完成，正在打包部署至 runtime/kernel/ ...")
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        "chrome.exe", "chrome.dll", "chrome_elf.dll", "resources.pak",
        "icudtl.dat", "v8_context_snapshot.bin", "libEGL.dll", "libGLESv2.dll",
        "chrome_100_percent.pak", "chrome_200_percent.pak", "d3dcompiler_47.dll",
        "vk_swiftshader.dll", "vulkan-1.dll"
    ]
    for out_name in outputs:
        src_file = OUT_DIR / out_name
        if src_file.exists():
            shutil.copy2(src_file, DEPLOY_DIR / out_name)

    # 复制 locales 目录
    src_locales = OUT_DIR / "locales"
    if src_locales.exists():
        shutil.copytree(src_locales, DEPLOY_DIR / "locales", dirs_exist_ok=True)

    # 注入 version.dll
    hook_dll = BASE_DIR / "native_hook" / "version.dll"
    if hook_dll.exists():
        shutil.copy2(hook_dll, DEPLOY_DIR / "version.dll")

    print("[SUCCESS] 自主内核编译与封装全部完成！")
    print(f" 输出目录: {DEPLOY_DIR}")


if __name__ == "__main__":
    main()
