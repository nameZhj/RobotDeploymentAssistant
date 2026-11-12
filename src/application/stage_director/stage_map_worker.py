"""
@file: src/application/stage_director/stage_map_worker.py
@brief: PCD 点云异步解析、栅格化与文件导入 QThread 后台工作器
@exports: StageMapImportWorker, StageMapLoadWorker
"""
from typing import Any, Dict, Optional
from PySide6.QtCore import QObject, Signal
from src.application.stage_director.stage_map_controller import StageMapController
from src.domain.map.stage_map_asset import StageMapAsset


class StageMapImportWorker(QObject):
    """用于在后台线程中执行 PCD 文件导入、解析校验与数据库持久化"""

    finished = Signal(object)  # StageMapAsset
    failed = Signal(str)
    progress = Signal(str)
    progress_step = Signal(str, str)  # (phase, message)
    duplicate_detected = Signal(str, str)  # (existing_map_id, existing_name)

    def __init__(
        self,
        controller: StageMapController,
        src_path: str,
        custom_name: Optional[str] = None,
        allow_duplicate: bool = False,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.src_path = src_path
        self.custom_name = custom_name
        self.allow_duplicate = allow_duplicate
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            self.progress_step.emit("header", "正在校验 PCD 头部与格式规范...")
            if self._is_cancelled:
                return
            self.progress_step.emit("hash", "计算文件散列与防重校验...")
            if self._is_cancelled:
                return
            self.progress_step.emit("parse", "解析三维空间点云并生成占据栅格...")
            asset = self.controller.import_pcd_file(
                self.src_path,
                self.custom_name,
                allow_duplicate=self.allow_duplicate,
            )
            if self._is_cancelled:
                return
            self.progress_step.emit("persist", "持久化元数据至 Canonical 数据库...")
            self.finished.emit(asset)
        except Exception as e:
            if not self._is_cancelled:
                from src.domain.map.stage_map_asset import DuplicateMapError
                if isinstance(e, DuplicateMapError):
                    self.duplicate_detected.emit(e.existing_map_id, e.existing_name)
                else:
                    self.failed.emit(str(e))


class StageMapLoadWorker(QObject):
    """用于在后台线程中读取点云数据并计算 2D 占据栅格图像"""

    finished = Signal(object, dict, dict)  # (QImage, info, meta)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, controller: StageMapController, map_id: str) -> None:
        super().__init__()
        self.controller = controller
        self.map_id = map_id
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            self.progress.emit("正在解析点云并构建 2D 占据栅格...")
            if self._is_cancelled:
                return
            img, info, meta = self.controller.load_map_to_stage(self.map_id)
            if self._is_cancelled:
                return
            self.finished.emit(img, info, meta)
        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(str(e))
