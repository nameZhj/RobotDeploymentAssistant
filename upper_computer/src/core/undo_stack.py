# @file: src/core/undo_stack.py
# @brief: Bounded multi-level Undo/Redo command stack for trajectory editing, timeline manipulation, and formation updates.
# @exports: UndoCommand, CallableUndoCommand, StudioUndoStack

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional


class UndoCommand(ABC):
    """Abstract reversible editor action."""

    def __init__(self, description: str) -> None:
        self.description = description

    @abstractmethod
    def redo(self) -> None:
        """Execute or re-apply the edit."""

    @abstractmethod
    def undo(self) -> None:
        """Revert the edit back to prior state."""


class CallableUndoCommand(UndoCommand):
    """Functional wrapper for simple reversible closures."""

    def __init__(
        self,
        description: str,
        redo_fn: Callable[[], None],
        undo_fn: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._redo_fn = redo_fn
        self._undo_fn = undo_fn

    def redo(self) -> None:
        self._redo_fn()

    def undo(self) -> None:
        self._undo_fn()


class StudioUndoStack:
    """Maintains bounded undo and redo histories with observer hooks."""

    MAX_HISTORY = 100

    def __init__(self, max_history: int = MAX_HISTORY) -> None:
        self._max_history = max(1, max_history)
        self._undo_list: List[UndoCommand] = []
        self._redo_list: List[UndoCommand] = []
        self._listeners: List[Callable[[], None]] = []

    def add_change_listener(self, fn: Callable[[], None]) -> None:
        """Subscribe to stack state changes (can_undo/can_redo)."""
        if fn not in self._listeners:
            self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            fn()

    def push(self, command: UndoCommand, execute_redo: bool = True) -> None:
        """Push a command, optionally execute redo immediately, and clear redo history."""
        if execute_redo:
            command.redo()
        self._undo_list.append(command)
        if len(self._undo_list) > self._max_history:
            self._undo_list.pop(0)
        self._redo_list.clear()
        self._notify()

    def undo(self) -> Optional[str]:
        """Undo the most recent command and return its description."""
        if not self._undo_list:
            return None
        cmd = self._undo_list.pop()
        cmd.undo()
        self._redo_list.append(cmd)
        self._notify()
        return cmd.description

    def redo(self) -> Optional[str]:
        """Redo the most recently undone command and return its description."""
        if not self._redo_list:
            return None
        cmd = self._redo_list.pop()
        cmd.redo()
        self._undo_list.append(cmd)
        self._notify()
        return cmd.description

    def can_undo(self) -> bool:
        return len(self._undo_list) > 0

    def can_redo(self) -> bool:
        return len(self._redo_list) > 0

    def clear(self) -> None:
        self._undo_list.clear()
        self._redo_list.clear()
        self._notify()
