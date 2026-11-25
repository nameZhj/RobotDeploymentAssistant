# @file: src/ui/mapping/pcd_remote_sync.py
# @brief: Blocking Wi-Fi HTTP PCD helpers (remote map listing, download, push, local import into the map library) designed for background tasks.
# @exports: list_remote_pcds, download_remote_pcd, push_pcd_to_robot, import_pcd_entity

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Dict, List, Tuple

from src.core.paths import get_paths
from src.domain.map_entities import PcdMapEntity
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import PcdPointCloud, load_pcd
from src.protocol.robot_http_client import RobotHttpClient, RobotHttpResponse


def list_remote_pcds(client: RobotHttpClient, robot_ip: str) -> Tuple[RobotHttpResponse, List[Dict[str, Any]]]:
    """Discover onboard .pcd maps over Wi-Fi HTTP; returns the raw response and the parsed map list."""
    res = client.list_remote_maps(robot_ip)
    maps = list((res.data.get("maps") or [])) if res.ok else []
    return res, maps


def download_remote_pcd(client: RobotHttpClient, robot_ip: str, remote_path: str) -> Tuple[RobotHttpResponse, Path]:
    """Download one onboard .pcd into the workspace maps directory."""
    dst = get_paths().maps_dir / Path(remote_path).name
    res = client.download_slam_pcd(robot_ip, dst, remote_path=remote_path)
    return res, dst


def push_pcd_to_robot(client: RobotHttpClient, robot_ip: str, pcd_path: Path, restart_localization: bool) -> RobotHttpResponse:
    """Push a local .pcd to the robot (large binary upload; always run off the GUI thread)."""
    return client.upload_slam_pcd(robot_ip, pcd_path, restart_localization=bool(restart_localization))


def import_pcd_entity(state, src: Path) -> Tuple[PcdMapEntity, PcdPointCloud]:
    """Copy a local .pcd into the maps dir, parse it, generate the occupancy grid and persist the entity (no widgets)."""
    dst = get_paths().maps_dir / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    state.map_repo.unmark_deleted_map_path(str(dst))
    cloud = load_pcd(dst, max_points=100000)
    png = get_paths().pcd_cache_dir / f"{dst.stem}_grid.png"
    grid = generate_occupancy_grid_png(cloud, png)
    ent = PcdMapEntity(
        name=dst.stem,
        file_path=str(dst),
        file_size=dst.stat().st_size,
        point_count=cloud.header.points,
        grid_png_path=grid.png_path,
        resolution=grid.resolution,
        origin_x=grid.origin_x,
        origin_y=grid.origin_y,
    )
    saved = state.map_repo.upsert_map(ent)
    return saved, cloud
