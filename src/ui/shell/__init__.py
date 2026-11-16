# @file: src/ui/shell/__init__.py
# @brief: Exports UniUni shell navigation titlebar, statusbar, shortcut manager, and main shell window.
# @exports: PAGE_DEFS, UTitlebar, UStatusBar, ShortcutManager, UniUniAppShell

from src.ui.shell.app_shell_window import UniUniAppShell
from src.ui.shell.shortcut_manager import ShortcutManager
from src.ui.shell.u_statusbar import UStatusBar
from src.ui.shell.u_titlebar import PAGE_DEFS, UTitlebar

__all__ = ["PAGE_DEFS", "UTitlebar", "UStatusBar", "ShortcutManager", "UniUniAppShell"]
