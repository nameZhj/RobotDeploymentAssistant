# @file: src/core/paths.py
# @brief: Centralized workspace, asset, runtime, and database path resolver preventing root directory pollution.
# @exports: WorkspacePaths, get_paths

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _resolve_repo_root() -> Path:
    """Resolve the project root directory cleanly across source and frozen runs."""
    return Path(__file__).resolve().parents[2]


def _default_workspace_root(repo_root: Path) -> Path:
    """R-4: anchor the writable workspace when frozen so DB/overlay/logs survive process exit."""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "RDA"
        return Path(sys.executable).resolve().parent
    return repo_root


@dataclass(frozen=True)
class WorkspacePaths:
    """Immutable container holding canonical project, asset, and isolated runtime paths."""

    root_dir: Path
    configs_dir: Path
    docs_dir: Path
    workspace_dir: Path
    runtime_dir: Path
    db_path: Path
    pcd_cache_dir: Path
    http_uploads_dir: Path
    logs_dir: Path
    exports_dir: Path
    fragments_dir: Path
    maps_dir: Path
    g1_urdf_dir: Path
    g1_urdf_file: Path
    g1_mesh_dir: Path
    motions_dir: Path
    g1_dance_csv: Path
    preview_dir: Path

    def ensure_runtime_dirs(self) -> None:
        """Create isolated .agent_workspace runtime directories if missing."""
        for directory in (
            self.workspace_dir,
            self.runtime_dir,
            self.pcd_cache_dir,
            self.http_uploads_dir,
            self.logs_dir,
            self.exports_dir,
            self.fragments_dir,
            self.maps_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def build_workspace_paths(root_override: Optional[Path] = None) -> WorkspacePaths:
    """Build WorkspacePaths anchored at the given root or detected repo root."""
    repo_root = _resolve_repo_root()
    root = Path(root_override).resolve() if root_override else _default_workspace_root(repo_root)
    workspace_dir = root / ".agent_workspace"
    runtime_dir = workspace_dir / "runtime"
    asset_root = root if (root / "backend" / "models").exists() else repo_root
    motion_root = root if (root / "assets" / "motions").exists() else repo_root
    g1_urdf_dir = asset_root / "backend" / "models" / "g1_29dof_rubber_hand"
    motions_dir = motion_root / "assets" / "motions"
    return WorkspacePaths(
        root_dir=root,
        configs_dir=root / "configs" if (root / "configs").exists() else repo_root / "configs",
        docs_dir=repo_root / "docs",
        workspace_dir=workspace_dir,
        runtime_dir=runtime_dir,
        db_path=runtime_dir / "stage_studio.db",
        pcd_cache_dir=runtime_dir / "pcd_cache",
        http_uploads_dir=runtime_dir / "http_uploads",
        logs_dir=runtime_dir / "logs",
        exports_dir=runtime_dir / "exports",
        fragments_dir=runtime_dir / "fragments",
        maps_dir=(root / "data" / "maps") if (root != repo_root or (root / "data" / "maps").exists()) else (repo_root / "data" / "maps"),
        g1_urdf_dir=g1_urdf_dir,
        g1_urdf_file=g1_urdf_dir / "g1_29dof_mode_15.urdf",
        g1_mesh_dir=g1_urdf_dir / "meshes",
        motions_dir=motions_dir,
        g1_dance_csv=motions_dir / "G1_dance.csv",
        preview_dir=asset_root / "preview",
    )


_CACHED_PATHS: Optional[WorkspacePaths] = None


def get_paths(reset: bool = False) -> WorkspacePaths:
    """Return the singleton WorkspacePaths instance and ensure runtime folders exist."""
    global _CACHED_PATHS
    if _CACHED_PATHS is None or reset:
        env_root = os.environ.get("RDA_WORKSPACE_ROOT")
        override = Path(env_root) if env_root else None
        _CACHED_PATHS = build_workspace_paths(override)
        _CACHED_PATHS.ensure_runtime_dirs()
        legacy_db = _CACHED_PATHS.runtime_dir / "uniuni_studio.db"
        if not _CACHED_PATHS.db_path.exists() and legacy_db.exists():
            try:
                shutil.copy2(legacy_db, _CACHED_PATHS.db_path)
            except OSError:
                pass
    return _CACHED_PATHS
