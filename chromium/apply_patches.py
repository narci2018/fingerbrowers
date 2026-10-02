#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PhantomBrowser 路线 B: 源码级补丁一键应用工具 (chromium/apply_patches.py)
-------------------------------------------------------------------
功能：
1. 读取 chromium/patches/series 补丁序列清单；
2. 针对指定 Chromium 源码树 (默认 ./src 或传入路径) 执行逐项检查与应用；
3. 输出每个补丁的应用状态（OK / Skip / Conflict），并生成诊断日志。
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# 确保 UTF-8 控制台输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMIUM_DIR = BASE_DIR / "chromium"
PATCHES_DIR = CHROMIUM_DIR / "patches"
SERIES_FILE = PATCHES_DIR / "series"


def main():
    parser = argparse.ArgumentParser(description="PhantomBrowser Chromium 源码级补丁批量应用工具")
    parser.add_argument("--src", type=str, default=str(BASE_DIR / "src"), help="Chromium 源码 checkout 根目录 (包含 .git 的 src 目录)")
    parser.add_argument("--dry-run", action="store_true", help="仅执行应用前模拟检查 (git apply --check)，不修改实际文件")
    parser.add_argument("--reverse", action="store_true", help="反向撤销已应用的全部补丁")
    args = parser.parse_args()

    src_dir = Path(args.src).resolve()
    print("=" * 65)
    print(" [PhantomBrowser 路线 B] Chromium 源码级 C++ 补丁应用管线")
    print("=" * 65)
    print(f"[*] 源码目标路径: {src_dir}")
    print(f"[*] 补丁存放目录: {PATCHES_DIR}")

    if not SERIES_FILE.exists():
        print(f"[ERROR] 未找到补丁清单文件: {SERIES_FILE}")
        sys.exit(1)

    if not src_dir.exists():
        print(f"[提示] 指定的源码目录不存在: {src_dir}")
        print("  若需进行本地完整内核编译，请先使用 depot_tools 执行：")
        print("  fetch --no-history chromium")
        print("  然后再运行本工具进行补丁自动化植入。")
        sys.exit(0)

    # 读取 series
    patches = [line.strip() for line in SERIES_FILE.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    print(f"[*] 正在读取补丁清单，共需处理 {len(patches)} 项核心补丁...")

    if args.reverse:
        patches = list(reversed(patches))

    success_cnt = 0
    fail_cnt = 0

    for i, p_name in enumerate(patches, 1):
        p_path = PATCHES_DIR / p_name
        if not p_path.exists():
            print(f"  [{i}/{len(patches)}] [MISSING] {p_name}")
            fail_cnt += 1
            continue

        cmd = ["git", "apply", "--whitespace=nowarn"]
        if args.dry_run:
            cmd.append("--check")
        if args.reverse:
            cmd.append("-R")
        cmd.append(str(p_path))

        res = subprocess.run(cmd, cwd=str(src_dir), capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  [{i}/{len(patches)}] [OK] {p_name}")
            success_cnt += 1
        else:
            print(f"  [{i}/{len(patches)}] [FAILED] {p_name} - {res.stderr.strip()[:120]}")
            fail_cnt += 1

    print("\n" + "=" * 65)
    print(f" [处理完毕] 成功: {success_cnt} | 失败: {fail_cnt}")
    print("=" * 65)


if __name__ == "__main__":
    main()
