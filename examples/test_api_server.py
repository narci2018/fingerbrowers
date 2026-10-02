import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from api.server import app, profile_mgr

client = TestClient(app)

def test_api_workflow():
    print("=== 开始自动化测试 REST API 控制面服务 ===")
    
    # 1. Health check
    resp = client.get("/health")
    assert resp.status_code == 200
    print("[1/5] Health Check OK:", resp.json())

    # 2. 创建 Profile
    create_payload = {
        "name": "API-Test-Profile",
        "group": "Automated",
        "locale": "zh-CN",
        "notes": "Testing through REST API"
    }
    resp = client.post("/api/v1/profiles", json=create_payload)
    assert resp.status_code == 200
    profile_data = resp.json()
    profile_id = profile_data["id"]
    print(f"[2/5] Profile 创建成功: ID={profile_id}, Name={profile_data['name']}")
    print(f"      UA: {profile_data['fingerprint']['user_agent']}")
    print(f"      Screen: {profile_data['fingerprint']['screen_width']}x{profile_data['fingerprint']['screen_height']}")

    # 3. 列表查询
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    all_profiles = resp.json()
    assert any(p["id"] == profile_id for p in all_profiles)
    print(f"[3/5] 列表查询成功，当前环境总数: {len(all_profiles)}")

    # 4. 启动与状态查询（headless 模式）
    print("[4/5] 启动环境...")
    resp = client.post(f"/api/v1/profiles/{profile_id}/start?headless=true")
    assert resp.status_code == 200
    start_info = resp.json()
    print(f"      启动响应: PID={start_info['status']['pid']}, CDP={start_info['status']['cdp_port']}")
    assert start_info["status"]["is_running"] is True

    # 检查状态接口
    resp = client.get(f"/api/v1/profiles/{profile_id}/status")
    assert resp.status_code == 200
    assert resp.json()["is_running"] is True

    # 关闭环境
    resp = client.post(f"/api/v1/profiles/{profile_id}/stop")
    assert resp.status_code == 200
    print("      环境已安全关闭。")

    # 5. 删除环境与清理沙箱
    resp = client.delete(f"/api/v1/profiles/{profile_id}?delete_data=true")
    assert resp.status_code == 200
    print(f"[5/5] 环境清理成功: {resp.json()['message']}")

    print("\n[SUCCESS] REST API 控制面全套流程自动化验证 100% 通过！")


if __name__ == "__main__":
    test_api_workflow()
