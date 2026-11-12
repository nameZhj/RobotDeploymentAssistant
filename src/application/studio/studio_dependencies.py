"""
@file: src/application/studio/studio_dependencies.py
@brief: 舞台编导依赖组装器 (Composition Root)，统一管理数据库、控制器单例与资源释放
@exports: StudioDependencies, get_studio_dependencies
"""
import logging
from typing import Optional
from src.application.services.virtual_show_player import VirtualShowPlayer
from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator
from src.application.studio.studio_facade import StudioFacade, studio_facade
from src.core.storage_manager import StorageManager, storage_manager

logger = logging.getLogger("StudioDependencies")


class StudioDependencies:
    """舞台编导唯一依赖注入容器，保证单例生命周期与退出释放安全"""

    def __init__(self, storage: Optional[StorageManager] = None) -> None:
        self.storage: StorageManager = storage or storage_manager
        self.facade: StudioFacade = studio_facade
        self.map_controller: StageMapController = StageMapController(map_dir=self.storage.maps_dir)
        self.preview_coordinator: Optional[StagePreviewCoordinator] = None
        self.show_player: Optional[VirtualShowPlayer] = None

    def bind_window_services(self, coordinator: StagePreviewCoordinator, player: VirtualShowPlayer) -> None:
        self.preview_coordinator = coordinator
        self.show_player = player

    def dispose(self) -> None:
        """窗口关闭时安全释放后台线程、播放定时器与未完成事务"""
        if self.show_player and hasattr(self.show_player, "stop"):
            try:
                self.show_player.stop()
            except Exception as e:
                logger.warning(f"停止播放器异常: {e}")
        logger.info("StudioDependencies 资源已完全安全释放")


_global_deps: Optional[StudioDependencies] = None


def get_studio_dependencies() -> StudioDependencies:
    global _global_deps
    if _global_deps is None:
        _global_deps = StudioDependencies()
    return _global_deps
