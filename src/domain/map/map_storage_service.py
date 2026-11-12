"""
@file: src/domain/map/map_storage_service.py
@brief: 安全托管地图文件存储服务，处理路径遍历防护、SHA-256 计算、Staging 暂存与原子替换
@exports: MapStorageService, map_storage_service
"""
import hashlib
import os
import shutil
from typing import Optional, Tuple


class MapStorageService:
    """提供本地 PCD 地图资源安全托管存储管理，防御路径穿越与提供原子写入"""

    def __init__(self, base_dir: str = "data/maps") -> None:
        self.base_dir = os.path.abspath(base_dir)
        self.staging_dir = os.path.join(self.base_dir, ".staging")
        self.cache_dir = os.path.join(self.base_dir, ".cache")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.staging_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    def resolve_safe_path(self, relative_or_absolute: str) -> str:
        """解析并校验托管文件路径，严格禁止 ../ 路径越界逃逸"""
        if not relative_or_absolute or not relative_or_absolute.strip():
            raise ValueError("地图文件路径不能为空")

        clean_path = relative_or_absolute.strip().replace("\\", "/")
        if not os.path.isabs(clean_path):
            abs_target = os.path.abspath(os.path.join(self.base_dir, clean_path))
        else:
            abs_target = os.path.abspath(clean_path)

        # 检查是否逃逸出 base_dir
        common = os.path.commonpath([self.base_dir, abs_target])
        if common != self.base_dir:
            raise PermissionError(f"检测到路径遍历非法访问: '{relative_or_absolute}'")

        return abs_target

    def compute_sha256(self, file_path: str) -> str:
        """计算指定文件的 SHA-256 哈希散列值"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: '{file_path}'")

        hasher = hashlib.sha256()
        with open(file_path, "rb") as fp:
            while chunk := fp.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def create_staging_file(self, prefix: str = "import") -> str:
        """在 .staging 目录中创建安全的暂存文件路径"""
        import time
        staging_filename = f"{prefix}_{int(time.time() * 1000)}.tmp"
        return os.path.join(self.staging_dir, staging_filename)

    def atomic_commit(self, staging_path: str, target_relative_name: str) -> Tuple[str, str]:
        """将 staging 暂存文件原子替换到最终目标路径，返回 (绝对路径, 相对路径)"""
        if not os.path.exists(staging_path):
            raise FileNotFoundError(f"暂存文件缺失: {staging_path}")

        target_path = self.resolve_safe_path(target_relative_name)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # 执行 fsync 保证物理刷盘
        try:
            with open(staging_path, "rb+") as f:
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass

        os.replace(staging_path, target_path)
        rel_uri = os.path.relpath(target_path, self.base_dir).replace("\\", "/")
        return target_path, rel_uri

    def clean_staging(self, staging_path: str) -> None:
        """安全清理未提交的暂存文件"""
        if os.path.exists(staging_path):
            try:
                os.remove(staging_path)
            except OSError:
                pass

    def check_file_status(self, file_uri: str) -> str:
        """核验物理文件存在性与就绪状态，缺失时返回 MISSING"""
        try:
            abs_path = self.resolve_safe_path(file_uri)
            if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
                return "MISSING"
            if os.path.getsize(abs_path) == 0:
                return "FAILED"
            return "READY"
        except (ValueError, PermissionError):
            return "FAILED"

    def delete_physical_file(self, file_uri: str) -> bool:
        """安全物理删除托管地图文件及其衍生缓存"""
        try:
            abs_path = self.resolve_safe_path(file_uri)
            if os.path.exists(abs_path):
                os.remove(abs_path)
            stem = os.path.splitext(os.path.basename(abs_path))[0]
            # 清理匹配缓存
            for f in os.listdir(self.cache_dir):
                if f.startswith(stem):
                    try:
                        os.remove(os.path.join(self.cache_dir, f))
                    except OSError:
                        pass
            return True
        except Exception:
            return False


map_storage_service = MapStorageService()
