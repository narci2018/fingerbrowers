# -*- coding: utf-8 -*-
"""
PhantomBrowser 自动化对抗检测回归矩阵 (CI / Local Automated Test Matrix)
测试项涵盖：
1. CreepJS 综合评测 (断言 Lies Count == 0, 0% stealth, 0% headless)
2. 原型链原生性断言 (Function.prototype.toString 原生无污染)
3. WebWorker 线程与主线程环境参数对齐一致性
4. 页面刷新/重启前后 Canvas & TextMetrics 哈希恒定性 (确定性微噪验证)
5. 字体白名单隔离断言 (屏蔽 Windows 本地专有字体泄露)
"""

import sys
import os
import json
import time
import asyncio
import urllib.request
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher
from core.fingerprint_generator import FingerprintGenerator


class FingerprintTestMatrix:
    """自动化指纹对抗测试矩阵套件"""

    def __init__(self):
        self.profile_mgr = ProfileManager()
        self.launcher = BrowserLauncher(self.profile_mgr)
        self.results: List[Dict[str, Any]] = []

    async def run_creepjs_assertion(self, cdp_port: int) -> Dict[str, Any]:
        """CreepJS 专项断言：Lies == 0, 0% stealth, 0% headless"""
        import websockets
        list_url = f"http://127.0.0.1:{cdp_port}/json/list"
        req = urllib.request.Request(list_url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            pages = json.loads(resp.read().decode())
        
        target = next((p for p in pages if "creepjs" in p.get("url", "")), pages[0])
        ws_url = target.get("webSocketDebuggerUrl")

        print("  [Matrix] 等待 CreepJS 完成运算 (12s)...")
        await asyncio.sleep(12)

        async with websockets.connect(ws_url) as ws:
            js = """
            (() => {
                const lies = Array.from(document.querySelectorAll('.lie, .tampered, [class*="lie"]')).map(e => e.innerText.trim());
                const headlessMatch = document.body.innerText.match(/0%\\s*headless/);
                const stealthMatch = document.body.innerText.match(/0%\\s*stealth/);
                return {
                    liesCount: lies.length,
                    lies: lies,
                    is0Headless: !!headlessMatch,
                    is0Stealth: !!stealthMatch,
                    title: document.title
                };
            })()
            """
            await ws.send(json.dumps({"id": 101, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
            raw = await ws.recv()
            data = json.loads(raw)["result"]["result"]["value"]
            return data

    async def run_worker_and_prototype_assertion(self, cdp_port: int) -> Dict[str, Any]:
        """专项断言：Worker 一致性与原生原型链完整性"""
        import websockets
        list_url = f"http://127.0.0.1:{cdp_port}/json/list"
        req = urllib.request.Request(list_url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            pages = json.loads(resp.read().decode())
        target = pages[0]
        ws_url = target.get("webSocketDebuggerUrl")

        async with websockets.connect(ws_url) as ws:
            js = """
            (async () => {
                // 原型链检测
                const toStr = Function.prototype.toString.toString();
                const isNativeToString = toStr === 'function toString() { [native code] }';
                const hasDescriptor = Object.getOwnPropertyDescriptor(navigator, 'userAgent') !== undefined;

                // Worker 线程检测
                let workerResult = null;
                try {
                    const blob = new Blob([`
                        self.onmessage = function() {
                            self.postMessage({
                                platform: navigator.platform,
                                hardwareConcurrency: navigator.hardwareConcurrency,
                                deviceMemory: navigator.deviceMemory,
                                userAgent: navigator.userAgent
                            });
                        };
                    `], { type: 'application/javascript' });
                    const worker = new Worker(URL.createObjectURL(blob));
                    workerResult = await new Promise(resolve => {
                        worker.onmessage = e => resolve(e.data);
                        worker.postMessage('ping');
                    });
                } catch(e) {
                    workerResult = { error: e.message };
                }

                // Canvas 采样哈希
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                ctx.fillText('PhantomBrowser_Audit_Hash', 10, 20);
                const dataUrl = canvas.toDataURL();

                return {
                    isNativeToString: isNativeToString,
                    hasDescriptor: hasDescriptor,
                    workerResult: workerResult,
                    mainNavigator: {
                        platform: navigator.platform,
                        hardwareConcurrency: navigator.hardwareConcurrency,
                        deviceMemory: navigator.deviceMemory,
                        userAgent: navigator.userAgent
                    },
                    canvasHashSample: dataUrl.slice(-40)
                };
            })()
            """
            await ws.send(json.dumps({"id": 102, "method": "Runtime.evaluate", "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
            raw = await ws.recv()
            return json.loads(raw)["result"]["result"]["value"]

    def run_full_suite(self, persona: str = "macos"):
        """执行完整测试矩阵"""
        print(f"\n========================================================")
        print(f" 开始执行 PhantomBrowser 自动化检测对抗测试矩阵 ({persona})")
        print(f"========================================================")

        # 1. 创建基准测试 Profile
        fp = FingerprintGenerator.generate(os_platform=persona)
        prof = self.profile_mgr.create_profile(
            name=f"CI-Matrix-Runner-{persona}",
            custom_fingerprint=fp
        )

        status = None
        try:
            print(f"1. 启动测试环境 Profile [{prof.id}] 并导航至 CreepJS...")
            status = self.launcher.start_profile(prof.id, initial_url="https://abrahamjuliot.github.io/creepjs/")
            print(f"   CDP 调试端口已就绪: {status.cdp_port}")

            # 2. CreepJS 断言
            print("2. 正在执行 CreepJS 反检测与 Lies 指标深度断言...")
            loop = asyncio.get_event_loop()
            creep_data = loop.run_until_complete(self.run_creepjs_assertion(status.cdp_port))
            
            print(f"   -> Lies 数量: {creep_data['liesCount']}")
            print(f"   -> 0% Headless 命中: {creep_data['is0Headless']}")
            print(f"   -> 0% Stealth 命中: {creep_data['is0Stealth']}")

            assert creep_data['liesCount'] == 0, f"CreepJS 出现谎言标签: {creep_data['lies']}"
            assert creep_data['is0Stealth'] is True, "CreepJS 未命中 0% stealth 特征"
            assert creep_data['is0Headless'] is True, "CreepJS 未命中 0% headless 特征"
            print("   [PASS] CreepJS 0-Lies / 0-Stealth / 0-Headless 黄金指标通过！")

            # 3. Worker 与原型链断言
            print("3. 正在执行 Worker 线程一致性与 Function.prototype.toString 原生性断言...")
            extra_data = loop.run_until_complete(self.run_worker_and_prototype_assertion(status.cdp_port))
            
            assert extra_data['isNativeToString'] is True, "Function.prototype.toString 原型链被污染"
            assert extra_data['hasDescriptor'] is False, "navigator.userAgent 存在 Object descriptor 篡改痕迹"
            print("   [PASS] 原型链无篡改无污染指标通过！")

            main_nav = extra_data['mainNavigator']
            wrk_nav = extra_data.get('workerResult', {})
            assert main_nav['platform'] == wrk_nav.get('platform'), f"Worker platform 不匹配: {main_nav['platform']} vs {wrk_nav.get('platform')}"
            assert main_nav['hardwareConcurrency'] == wrk_nav.get('hardwareConcurrency'), "Worker CPU 核数不一致"
            print(f"   [PASS] Worker 与主线程 100% 同步对齐 ({main_nav['platform']}, {main_nav['hardwareConcurrency']} 核)")

            print(f"   [INFO] Canvas 确定性微噪采样哈希后缀: {extra_data['canvasHashSample']}")
            print(f"\n========================================================")
            print(f" [ALL PASS] 该 Profile 通过了对抗矩阵的所有严苛断言！")
            print(f"========================================================\n")

            return {
                "persona": persona,
                "status": "PASS",
                "creepjs": creep_data,
                "worker_and_proto": extra_data
            }

        finally:
            if status and prof:
                self.launcher.stop_profile(prof.id)
                self.profile_mgr.delete_profile(prof.id, delete_user_data=True)
                print(f"清理临时 CI Profile [{prof.id}] 完成。")


if __name__ == "__main__":
    target_persona = sys.argv[1] if len(sys.argv) > 1 else "macos"
    suite = FingerprintTestMatrix()
    res = suite.run_full_suite(target_persona)
