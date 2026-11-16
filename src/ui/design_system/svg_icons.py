# @file: src/ui/design_system/svg_icons.py
# @brief: Crisp DPI-aware vector SVG icon factory eliminating blurry text/emoji icons across toolbars.
# @exports: SVG_PATHS, render_svg_icon, get_icon_pixmap

from __future__ import annotations

from typing import Dict
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.ui.design_system.tokens import C_TEXT_1

SVG_PATHS: Dict[str, str] = {
    "play": '<polygon points="6,4 20,12 6,20" fill="currentColor"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor"/>',
    "replay": '<path d="M4 12a8 8 0 1 0 2.3-5.6L4 8.5M4 4v4.5h4.5" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/>',
    "plus": '<path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "save": '<path d="M5 4h11l3 3v13H5V4zm3 0v5h7V4M8 20v-6h8v6" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "import": '<path d="M12 4v11m0 0l-4-4m4 4l4-4M4 17v3h16v-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "export": '<path d="M12 15V4m0 0L8 8m4-4l4 4M4 17v3h16v-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "upload": '<path d="M12 16V6m0 0l-4 4m4-4l4 4M4 18h16" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "sort": '<path d="M4 7h12M4 12h8M4 17h5M17 6v12m0 0l-3-3m3 3l3-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "copy": '<rect x="8" y="8" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M5 15V5h10" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "edit": '<path d="M4 17l11-11 3 3L7 20H4v-3z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "select_all": '<rect x="4" y="4" width="16" height="16" rx="2" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3 2" fill="none"/><path d="M8 12l3 3 5-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
    "range_export": '<path d="M6 5v14M18 5v14M9 12h6m0 0l-2-2m2 2l-2 2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "eye_off": '<path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M6.5 6.5C4.2 8.2 2.8 10.6 2.2 12c1.6 3.5 5.4 6 9.8 6 1.7 0 3.3-.4 4.7-1.1" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "music": '<path d="M9 18V6l10-2v12" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="18" r="2.5" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="17" cy="16" r="2.5" stroke="currentColor" stroke-width="1.8" fill="none"/>',
    "code": '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13 6l-2 12" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14-5M4 4v5h5M4 13a8 8 0 0 0 14 5M20 20v-5h-5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "pin": '<path d="M12 21s-6-5.5-6-10a6 6 0 1 1 12 0c0 4.5-6 10-6 10z" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="11" r="2" fill="currentColor"/>',
    "map": '<path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2V6zm6-2v14m6-12v14" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
    "fullscreen": '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "wifi": '<path d="M4 10a12 12 0 0 1 16 0M7.5 13.5a7 7 0 0 1 9 0M11 17h2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "radar": '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 12l6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "robots": '<rect x="5" y="7" width="14" height="11" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 3v4M9 12h.01M15 12h.01M9 15h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "check": '<path d="M5 12l4.5 4.5L19 7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "sparkle": '<path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
    "cursor": '<path d="M5 3l12 9-5 1.5L9.5 19 5 3z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "cut": '<circle cx="6.5" cy="17.5" r="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="17.5" cy="17.5" r="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M8.5 15.5L18 5M15.5 15.5L6 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "undo": '<path d="M9 14L4 9l5-5M4 9h10a5 5 0 0 1 0 10h-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "redo": '<path d="M15 14l5-5-5-5M20 9H10a5 5 0 0 0 0 10h3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "layers": '<path d="M12 3l9 4.5-9 4.5-9-4.5L12 3zm-9 9l9 4.5 9-4.5M3 16.5L12 21l9-4.5" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
    "zoom_in": '<circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M16 16l4 4M11 8v6M8 11h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "zoom_out": '<circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M16 16l4 4M8 11h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "sliders": '<path d="M4 7h16M4 17h16M9 4v6M15 14v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "home": '<path d="M4 11l8-7 8 7v9h-5v-6H9v6H4v-9z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "folder": '<path d="M3 6h6l2 2h10v11H3V6z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "target": '<circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "bookmark": '<path d="M6 4h12v16l-6-4-6 4V4z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "file": '<path d="M6 3h8l4 4v14H6V3zm8 0v4h4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1" stroke="currentColor" stroke-width="1.7" fill="none"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1" stroke="currentColor" stroke-width="1.7" fill="none"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1" stroke="currentColor" stroke-width="1.7" fill="none"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1" stroke="currentColor" stroke-width="1.7" fill="none"/>',
}


def get_icon_pixmap(name: str, color: str = C_TEXT_1, size: int = 16) -> QPixmap:
    """Rasterize named vector SVG glyph cleanly at high precision."""
    body = SVG_PATHS.get(name, SVG_PATHS["code"]).replace("currentColor", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    pm.setDevicePixelRatio(2.0)
    return pm


def render_svg_icon(name: str, color: str = C_TEXT_1, size: int = 16) -> QIcon:
    """Create a QIcon backed by the crisp vector SVG glyph."""
    return QIcon(get_icon_pixmap(name, color=color, size=size))
