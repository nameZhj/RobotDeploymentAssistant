from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import serial.tools.list_ports

from src.core.config_loader import config_loader
from src.core.logger import get_logger

logger = get_logger("Ch341Installer")


class Ch341Installer:
    """
    Detects and installs the host serial driver (CH341 / CH340).
    """

    def __init__(self) -> None:
        self._root = Path(__file__).resolve().parent.parent.parent.parent
        self._driver_filenames = ["CH341SER.EXE", "CH340 CH341驱动.exe"]

    def find_installer_path(self) -> Optional[Path]:
        search_dirs = [
            self._root / "backend" / "drivers",
            self._root / "assets" / "drivers",
            self._root,
        ]
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            for fname in self._driver_filenames:
                p = sdir / fname
                if p.is_file():
                    return p
        return None

    def detect_driver_ports(self) -> List[Dict[str, str]]:
        matches = []
        for port in serial.tools.list_ports.comports():
            desc = (port.description or "").lower()
            hwid = (port.hwid or "").lower()
            if "ch340" in desc or "ch341" in desc or "1a86:7523" in hwid or "1a86:5523" in hwid:
                matches.append({
                    "port": port.device,
                    "description": port.description,
                    "hwid": port.hwid,
                })
        return matches

    def run_installer(self) -> Dict[str, Any]:
        exe_path = self.find_installer_path()
        if not exe_path:
            return {"success": False, "msg": "Installer executable not found"}
        try:
            cmd = f'"{exe_path}" /S'
            subprocess.Popen(cmd, shell=True)
            return {"success": True, "msg": "Driver installation launched"}
        except Exception as e:
            logger.error(f"Failed to launch driver installer: {e}")
            return {"success": False, "msg": str(e)}


ch341_installer = Ch341Installer()
