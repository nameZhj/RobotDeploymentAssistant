# @file: src/ui/common/__init__.py
# @brief: Shared UI infrastructure: background task runner keeping blocking robot I/O off the Qt GUI thread.
# @exports: BackgroundTaskRunner, TaskHandle, get_task_runner, run_in_background, wait_for_all_tasks

from src.ui.common.async_task import (
    BackgroundTaskRunner,
    TaskHandle,
    get_task_runner,
    run_in_background,
    wait_for_all_tasks,
)

__all__ = ["BackgroundTaskRunner", "TaskHandle", "get_task_runner", "run_in_background", "wait_for_all_tasks"]
