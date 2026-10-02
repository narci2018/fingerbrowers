import json
import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from .models import BrowserProfile, FingerprintConfig
from .fingerprint_generator import FingerprintGenerator

import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
BROWSER_DATA_DIR = DATA_DIR / "browser_data"


class ProfileManager:
    """负责 Profile 的持久化、检索、存储沙箱隔离"""

    def __init__(self):
        self._ensure_storage()

    def _ensure_storage(self):
        """确保存储路径与基础文件存在"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not PROFILES_FILE.exists():
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load_raw(self) -> List[dict]:
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_raw(self, data: List[dict]):
        tmp_file = PROFILES_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_file.replace(PROFILES_FILE)

    def list_profiles(self) -> List[BrowserProfile]:
        raw_list = self._load_raw()
        return [BrowserProfile(**item) for item in raw_list]

    def get_profile(self, profile_id: str) -> Optional[BrowserProfile]:
        for item in self._load_raw():
            if item.get("id") == profile_id:
                return BrowserProfile(**item)
        return None

    def create_profile(
        self,
        name: str,
        group: str = "Default",
        locale: str = "zh-CN",
        custom_args: Optional[List[str]] = None,
        notes: str = "",
        os_platform: Optional[str] = "win10",
        browser_type: Optional[str] = "chrome",
        browser_version: Optional[str] = None,
        custom_fingerprint: Optional[FingerprintConfig] = None
    ) -> BrowserProfile:
        """创建全新指纹环境（自动生成自洽指纹并分配沙箱目录）"""
        fp = custom_fingerprint or FingerprintGenerator.generate(
            locale_preference=locale,
            os_platform=os_platform,
            browser_type=browser_type,
            browser_version=browser_version
        )
        profile = BrowserProfile(
            name=name,
            group=group,
            notes=notes,
            fingerprint=fp,
            custom_args=custom_args or []
        )
        
        # 创建独立的沙箱目录
        profile_data_path = BROWSER_DATA_DIR / profile.id
        profile_data_path.mkdir(parents=True, exist_ok=True)

        raw = self._load_raw()
        raw.append(profile.model_dump())
        self._save_raw(raw)
        return profile

    def update_profile(self, profile: BrowserProfile) -> bool:
        raw = self._load_raw()
        for idx, item in enumerate(raw):
            if item.get("id") == profile.id:
                raw[idx] = profile.model_dump()
                self._save_raw(raw)
                return True
        return False

    def delete_profile(self, profile_id: str, delete_user_data: bool = True) -> bool:
        raw = self._load_raw()
        new_raw = [item for item in raw if item.get("id") != profile_id]
        if len(new_raw) != len(raw):
            self._save_raw(new_raw)
            if delete_user_data:
                user_dir = BROWSER_DATA_DIR / profile_id
                if user_dir.exists():
                    shutil.rmtree(user_dir, ignore_errors=True)
            return True
        return False

    def get_user_data_path(self, profile_id: str) -> Path:
        """获取 Profile 独占的独立数据目录"""
        p = BROWSER_DATA_DIR / profile_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def clone_profile(self, profile_id: str, new_name: Optional[str] = None, copy_data: bool = True) -> BrowserProfile:
        """克隆指纹环境，重新生成唯一种子并深度复制沙箱目录"""
        src = self.get_profile(profile_id)
        if not src:
            raise ValueError(f"Profile {profile_id} not found")

        import uuid
        from datetime import datetime

        new_id = str(uuid.uuid4())
        name = new_name.strip() if new_name else f"{src.name} (副本)"
        
        # 深度复制数据字典并分配新 ID 与独有 Noise Seed
        p_dict = src.model_dump()
        p_dict["id"] = new_id
        p_dict["name"] = name
        p_dict["created_at"] = datetime.now().isoformat()
        p_dict["updated_at"] = datetime.now().isoformat()
        p_dict["fingerprint"]["noise_seed"] = hash(uuid.uuid4().hex) % 1000000

        cloned_profile = BrowserProfile(**p_dict)
        new_data_path = BROWSER_DATA_DIR / new_id
        new_data_path.mkdir(parents=True, exist_ok=True)

        if copy_data:
            src_data_path = BROWSER_DATA_DIR / profile_id
            if src_data_path.exists():
                # 排除锁定文件与高耗存储缓存
                def ignore_filter(src_dir, names):
                    ignored = set()
                    for n in names:
                        lower_n = n.lower()
                        if lower_n in ("cache", "code cache", "gpucache", "dawncache", "lockfile") or lower_n.startswith("singleton"):
                            ignored.add(n)
                    return ignored

                shutil.copytree(src_data_path, new_data_path, dirs_exist_ok=True, ignore=ignore_filter)

        raw = self._load_raw()
        raw.append(cloned_profile.model_dump())
        self._save_raw(raw)
        return cloned_profile

    def export_profile_archive(self, profile_id: str, output_zip: Optional[Path] = None) -> Path:
        """导出 Profile 独立便携式归档包 (.zip)，包含完整指纹元数据、Cookie 与浏览器状态"""
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        import zipfile
        from .cookie_manager import CookieManager

        export_dir = DATA_DIR / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        if not output_zip:
            safe_name = "".join(c for c in profile.name if c.isalnum() or c in ("-", "_", " ")).strip() or "profile"
            output_zip = export_dir / f"{safe_name}_{profile_id[:8]}.zip"

        src_data_path = BROWSER_DATA_DIR / profile_id
        cookies = CookieManager.load_offline_cookies(src_data_path)
        pending = CookieManager.get_pending_cookies(src_data_path)
        all_cookies = cookies + pending

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 写入环境配置
            zf.writestr("profile.json", json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))
            
            # 2. 写入 Cookie
            zf.writestr("cookies.json", json.dumps(all_cookies, ensure_ascii=False, indent=2))
            
            # 3. 写入核心沙箱文件 (Default/Preferences, Bookmarks, Local Storage 等)
            if src_data_path.exists():
                for root, dirs, files in os.walk(src_data_path):
                    # 忽略巨大的缓存目录
                    dirs[:] = [d for d in dirs if d.lower() not in ("cache", "code cache", "gpucache", "dawncache")]
                    for f in files:
                        lower_f = f.lower()
                        if lower_f in ("lockfile",) or lower_f.startswith("singleton"):
                            continue
                        full_f = Path(root) / f
                        rel_path = full_f.relative_to(src_data_path)
                        try:
                            zf.write(full_f, arcname=f"data/{rel_path.as_posix()}")
                        except Exception:
                            pass

        return output_zip

    def import_profile_archive(self, zip_path: Path, new_name: Optional[str] = None) -> BrowserProfile:
        """从 .zip 归档包中恢复环境及沙箱数据，并重新赋予新沙箱 ID"""
        import zipfile
        import uuid
        from datetime import datetime
        from .cookie_manager import CookieManager

        if not zip_path.exists():
            raise FileNotFoundError(f"Archive file not found: {zip_path}")

        new_id = str(uuid.uuid4())
        dest_data_path = BROWSER_DATA_DIR / new_id
        dest_data_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            if "profile.json" not in namelist:
                raise ValueError("无效的环境归档包: 缺少 profile.json")

            profile_data = json.loads(zf.read("profile.json").decode("utf-8"))
            profile_data["id"] = new_id
            if new_name:
                profile_data["name"] = new_name.strip()
            else:
                profile_data["name"] = f"{profile_data.get('name', 'Imported')} (导入)"
            profile_data["created_at"] = datetime.now().isoformat()
            profile_data["updated_at"] = datetime.now().isoformat()

            # 解压沙箱数据
            for member in namelist:
                if member.startswith("data/") and not member.endswith("/"):
                    rel_sub = member[len("data/"):]
                    target_file = dest_data_path / rel_sub
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as sf, open(target_file, "wb") as df:
                        df.write(sf.read())

            # 恢复 Cookie 到待注入队列
            if "cookies.json" in namelist:
                try:
                    cookies = json.loads(zf.read("cookies.json").decode("utf-8"))
                    if cookies:
                        CookieManager.save_pending_cookies(dest_data_path, cookies, merge=True)
                except Exception:
                    pass

        imported_profile = BrowserProfile(**profile_data)
        raw = self._load_raw()
        raw.append(imported_profile.model_dump())
        self._save_raw(raw)
        return imported_profile

    def clean_profile_cache(self, profile_id: str) -> int:
        """安全清理指定 Profile 的非关键缓存目录 (Cache, Code Cache, DawnGraphiteCache, GPUCache)
        保留 Cookies, Local Storage, IndexedDB, History 等用户凭据数据。
        返回释放的磁盘字节数。
        """
        user_data = self.get_user_data_path(profile_id)
        if not user_data.exists():
            return 0

        cache_dirs = [
            user_data / "Default" / "Cache",
            user_data / "Default" / "Code Cache",
            user_data / "Default" / "DawnGraphiteCache",
            user_data / "Default" / "DawnWebGPUCache",
            user_data / "Default" / "GPUCache",
            user_data / "ShaderCache",
            user_data / "GrShaderCache",
        ]

        freed = 0
        for cd in cache_dirs:
            if cd.exists():
                try:
                    for root, dirs, files in os.walk(cd):
                        for f in files:
                            try:
                                fp = Path(root) / f
                                freed += fp.stat().st_size
                            except Exception:
                                pass
                    shutil.rmtree(cd, ignore_errors=True)
                except Exception:
                    pass
        return freed
