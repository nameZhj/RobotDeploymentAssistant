# @file: src/core/__init__.py
# @brief: Core infrastructure exports for paths, settings, logging, event bus, and undo stack.
# @exports: WorkspacePaths, get_paths, StudioSettings, get_settings, StudioEvent, StudioEventBus, get_event_bus, StudioUndoStack

from src.core.event_bus import StudioEvent, StudioEventBus, get_event_bus
from src.core.logger import configure_studio_logging, get_studio_logger
from src.core.paths import WorkspacePaths, get_paths
from src.core.settings import StudioSettings, get_settings, save_settings
from src.core.undo_stack import CallableUndoCommand, StudioUndoStack, UndoCommand

__all__ = [
    "WorkspacePaths",
    "get_paths",
    "StudioSettings",
    "get_settings",
    "save_settings",
    "configure_studio_logging",
    "get_studio_logger",
    "StudioEvent",
    "StudioEventBus",
    "get_event_bus",
    "UndoCommand",
    "CallableUndoCommand",
    "StudioUndoStack",
]
