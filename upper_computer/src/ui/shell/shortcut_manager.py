# @file: src/ui/shell/shortcut_manager.py
# @brief: Global UniUni shell keyboard shortcut registrar (Space, Ctrl+S, Ctrl+Z/Y, 1..6 page switch).
# @exports: ShortcutManager

from __future__ import annotations

from typing import Callable, Dict
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


class ShortcutManager:
    """Binds consistent desktop keyboard accelerators to a UniUni shell window."""

    def __init__(self, parent_window: QWidget) -> None:
        self._parent = parent_window
        self._shortcuts: Dict[str, QShortcut] = {}

    def register(self, key_seq: str, callback: Callable[[], None]) -> QShortcut:
        sc = QShortcut(QKeySequence(key_seq), self._parent)
        sc.activated.connect(callback)
        self._shortcuts[key_seq] = sc
        return sc
