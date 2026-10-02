import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

def run_cmd(cmd: str, cwd: Path = BASE_DIR):
    full_cmd = f'call "{VCVARS}" >nul && {cmd}'
    res = subprocess.run(full_cmd, shell=True, cwd=str(cwd))
    if res.returncode != 0:
        print(f"[ERROR] Command failed with code {res.returncode}: {cmd}")
        sys.exit(res.returncode)

def main():
    print("=" * 60)
    print(" [PhantomBrowser] 一键构建与商业级发布流水线")
    print("=" * 60)

    # 1. 编译 native hook version.dll
    print("\n[1/3] 编译 Native C++ 核心 Hook 引擎 (version.dll)...")
    hook_dir = BASE_DIR / "native_hook"
    run_cmd("cl.exe /O2 /LD /MT /utf-8 /std:c++17 version_hook.cpp /Fe:version.dll /link /DEF:version.def user32.lib kernel32.lib", cwd=hook_dir)
    
    # 部署到便携 Chromium 备用内核目录 (注意：Apostate 是源码级商业内核自带原生补丁，不可放入未签名的 version.dll，否则会触发 Windows RendererCodeIntegrity 沙箱签名校验崩溃)
    runtime_hook = BASE_DIR / "runtime" / "chrome-win" / "version.dll"
    if runtime_hook.parent.exists():
        shutil.copy2(hook_dir / "version.dll", runtime_hook)
        print(f"[OK] version.dll 已部署至备用内核: {runtime_hook}")

    # 2. 编译启动器 PhantomBrowser.exe
    print("\n[2/3] 编译根目录原生静默启动器 (PhantomBrowser.exe)...")
    run_cmd("cl.exe /O2 /MT /utf-8 launcher.c /Fe:PhantomBrowser.exe /link user32.lib shell32.lib", cwd=BASE_DIR)
    for obj in BASE_DIR.glob("*.obj"):
        try:
            obj.unlink()
        except Exception:
            pass
    print("[OK] PhantomBrowser.exe 原生启动器编译完成！")

    # 3. 使用 PyInstaller 打包 dist/PhantomBrowser 独立免安装分发包
    print("\n[3/4] 编译打包 dist/PhantomBrowser/PhantomBrowser.exe 分发包...")
    spec_path = BASE_DIR / "PhantomBrowser.spec"
    if spec_path.exists():
        py_res = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "PhantomBrowser.spec"], cwd=str(BASE_DIR))
        if py_res.returncode == 0:
            print("[OK] dist/PhantomBrowser 独立分发包打包成功！")
            
            # 为 dist 目录创建 runtime 目录联接 (Junction)，实现防关联内核零开销即时可用
            dist_runtime = BASE_DIR / "dist" / "PhantomBrowser" / "runtime"
            src_runtime = BASE_DIR / "runtime"
            if src_runtime.exists() and not dist_runtime.exists():
                subprocess.run(f'cmd /c mklink /J "{dist_runtime}" "{src_runtime}"', shell=True)
                print(f"[OK] 已为 dist 分发包建立 runtime 内核联接: {dist_runtime}")
            
            # 同步初始环境预设与数据配置至 dist/PhantomBrowser/data
            dist_data = BASE_DIR / "dist" / "PhantomBrowser" / "data"
            dist_data.mkdir(parents=True, exist_ok=True)
            for f_name in ["profiles.json", "proxies.json", "subscriptions.json"]:
                src_f = BASE_DIR / "data" / f_name
                dst_f = dist_data / f_name
                if src_f.exists() and not dst_f.exists():
                    shutil.copy2(src_f, dst_f)
                    print(f"[OK] 已同步初始预设数据至分发目录: {dst_f}")
        else:
            print(f"[WARN] PyInstaller 打包退出码: {py_res.returncode}")

    # 4. 清理 build/ 缓存
    print("\n[4/4] 清理临时构建缓存...")
    build_dir = BASE_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
        print("[OK] 已清除 build 缓存目录，防止误运行报错。")

    print("\n" + "=" * 60)
    print(" [完成] 构建流水线全部执行完毕！")
    print(" 根目录启动器: PhantomBrowser.exe (轻量快捷启动)")
    print(" 独立分发目录: dist/PhantomBrowser/PhantomBrowser.exe (完整打包)")
    print(" 批处理入口  : 启动GUI.bat")
    print(" 定制便携内核: runtime/chrome-win/chrome.exe")
    print("=" * 60)

if __name__ == "__main__":
    main()
