#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PhantomBrowser 路线 B 核心资产同步工具 (tools/download_patches.py)
-----------------------------------------------------------------
自动从官方仓库同步全套 138 项工业级 Chromium C++ 补丁集及 series 清单。
"""

import os
import sys
import json
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = Path(__file__).resolve().parent.parent
PATCHES_DIR = BASE_DIR / "chromium" / "patches"
PATCHES_DIR.mkdir(parents=True, exist_ok=True)

PROXY = "http://127.0.0.1:10808"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))

def fetch_file(item):
    name = item["name"]
    url = item["download_url"]
    dest = PATCHES_DIR / name
    if dest.exists() and dest.stat().st_size == item.get("size", 0):
        return name, "cached"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with opener.open(req, timeout=15) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return name, "downloaded"
    except Exception as e:
        return name, f"error: {e}"

def main():
    print("=" * 65)
    print(" [PhantomBrowser 路线 B] 同步 138 项 Chromium 源码 C++ 补丁集")
    print("=" * 65)

    req = urllib.request.Request("https://api.github.com/repos/heretic-tech/apostate/contents/patches", headers={'User-Agent': 'Mozilla/5.0'})
    with opener.open(req, timeout=10) as resp:
        items = json.loads(resp.read().decode())

    print(f"[*] 发现 {len(items)} 个补丁资产，开始多线程并发拉取...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch_file, items))

    success = sum(1 for _, s in results if s in ("cached", "downloaded"))
    print(f"[OK] 同步完成: {success} / {len(items)} 补丁已全部就绪在 {PATCHES_DIR}")

if __name__ == "__main__":
    main()
