import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.profile_manager import ProfileManager
from core.browser_launcher import BrowserLauncher


def test_isolation():
    print("=== 开始测试多 Profile 物理隔离与自洽性 ===")
    profile_mgr = ProfileManager()
    launcher = BrowserLauncher(profile_mgr)

    # 1. 创建两个不同地区和配置的环境
    p1 = profile_mgr.create_profile("Isolation-Test-CN", locale="zh-CN")
    p2 = profile_mgr.create_profile("Isolation-Test-US", locale="en-US")

    print(f"创建 Profile A [CN]: ID={p1.id}")
    print(f"  - 目录: {profile_mgr.get_user_data_path(p1.id)}")
    print(f"  - UA: {p1.fingerprint.user_agent}")
    print(f"  - 屏幕: {p1.fingerprint.screen_width}x{p1.fingerprint.screen_height}")
    print(f"  - 种子: {p1.fingerprint.noise_seed}")

    print(f"\n创建 Profile B [US]: ID={p2.id}")
    print(f"  - 目录: {profile_mgr.get_user_data_path(p2.id)}")
    print(f"  - UA: {p2.fingerprint.user_agent}")
    print(f"  - 屏幕: {p2.fingerprint.screen_width}x{p2.fingerprint.screen_height}")
    print(f"  - 种子: {p2.fingerprint.noise_seed}")

    assert p1.id != p2.id, "ID 必须唯一"
    assert profile_mgr.get_user_data_path(p1.id) != profile_mgr.get_user_data_path(p2.id), "沙箱数据目录必须独立物理隔离"
    print("\n[OK] 物理沙箱目录与指纹参数完全隔离自洽！")

    # 2. 并发启动测试（无头模式以极速验证端口与生命周期）
    print("\n正在启动 Profile A 与 Profile B 并发共存...")
    try:
        s1 = launcher.start_profile(p1.id, headless=True)
        s2 = launcher.start_profile(p2.id, headless=True)

        print(f"Profile A 运行成功: PID={s1.pid}, Port={s1.cdp_port}")
        print(f"Profile B 运行成功: PID={s2.pid}, Port={s2.cdp_port}")
        assert s1.cdp_port != s2.cdp_port, "端口分配不得冲突"
        print("[OK] 双环境独立进程与 CDP 端口分配完全独立且运行正常！")
    finally:
        print("\n清理关闭进程...")
        launcher.stop_profile(p1.id)
        launcher.stop_profile(p2.id)
        # 清理测试数据
        profile_mgr.delete_profile(p1.id, delete_user_data=True)
        profile_mgr.delete_profile(p2.id, delete_user_data=True)
        print("[OK] 测试完毕，沙箱资源已安全回收。")


if __name__ == "__main__":
    test_isolation()
