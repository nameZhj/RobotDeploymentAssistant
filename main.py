"""
@file: main.py
@brief: 机器人助手主程序（支持原生部署控制台与舞台编导控制台交互唤起）
@exports: main, launch_studio_window
"""
import logging
import os
import socket
import sys
import threading
import time
from typing import Any, Optional, Tuple
import webbrowser

# Windows 任务栏专属应用 ID 绑定
if sys.platform == "win32":
    try:
        import ctypes
        app_id = "visislab.robotdeploymentassistant.suite.2.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

from app import app
from backend.dance_updater import dance_updater
from backend.serial_manager import serial_manager
from backend.ssh_client import ssh_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger("Launcher")

PORT = 8088
HOST = "127.0.0.1"


class StudioWindowManager:
    """管理 Qt 事件循环线程与 MainStudioWindow 生命周期"""

    def __init__(self) -> None:
        self._app: Optional[Any] = None
        self._window: Optional[Any] = None
        self._bridge: Optional[Any] = None
        self._lock = threading.Lock()
        self._ready_event = threading.Event()

    def ensure_qt_running(self) -> None:
        with self._lock:
            if self._bridge is not None:
                return
            from PySide6.QtWidgets import QApplication
            app_inst = QApplication.instance()
            if app_inst is not None and threading.current_thread() is threading.main_thread():
                self._init_bridge(app_inst)
                return
            qt_thread = threading.Thread(
                target=self._run_qt_event_loop,
                daemon=True,
                name="QtStudioThread",
            )
            qt_thread.start()
            self._ready_event.wait(timeout=5.0)

    def _init_bridge(self, app_inst: Any) -> None:
        from PySide6.QtCore import QObject, Signal
        from src.ui.windows.main_studio_window import MainStudioWindow

        app_inst.setQuitOnLastWindowClosed(False)

        class _LauncherBridge(QObject):
            request_show = Signal(object, object, object)

        self._app = app_inst
        self._bridge = _LauncherBridge()

        def _handle_show(s_mgr: Any, d_upd: Any, s_chan: Any) -> None:
            try:
                is_alive = False
                if self._window is not None:
                    try:
                        _ = self._window.isVisible()
                        is_alive = True
                    except (RuntimeError, AttributeError):
                        is_alive = False
                        self._window = None

                if not is_alive:
                    self._window = MainStudioWindow(
                        serial_manager=s_mgr,
                        dance_updater=d_upd,
                        ssh_channel=s_chan,
                    )
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    self._window.show()
                    self._window.raise_()
                    self._window.activateWindow()
                logger.info("🎬 舞台编导控制台已就绪并展示")
            except Exception as ex:
                logger.error(f"实例化 MainStudioWindow 失败: {ex}", exc_info=True)

        self._bridge.request_show.connect(_handle_show)
        self._ready_event.set()

    def _run_qt_event_loop(self) -> None:
        from PySide6.QtWidgets import QApplication
        from src.ui.theme.uniuni_inspired_theme import apply_uniuni_theme
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        apply_uniuni_theme(self._app)
        self._init_bridge(self._app)
        self._app.exec()

    def show_studio(self, s_mgr: Any = None, d_upd: Any = None, s_chan: Any = None) -> Tuple[bool, str]:
        try:
            self.ensure_qt_running()
            if self._bridge is not None:
                self._bridge.request_show.emit(s_mgr, d_upd, s_chan)
                from PySide6.QtWidgets import QApplication
                app_inst = QApplication.instance()
                if app_inst is not None:
                    app_inst.processEvents()
                return True, "🎬 舞台编导控制台已唤起"
            return False, "Qt 事件循环初始化超时"
        except Exception as e:
            logger.error(f"唤起舞台编导异常: {e}", exc_info=True)
            return False, str(e)


_studio_manager = StudioWindowManager()


def launch_studio_window() -> Tuple[bool, str]:
    """供 Flask 接口调用的全局窗口唤起方法，注入全局 serial_manager, dance_updater, ssh_channel"""
    ssh_chan = getattr(ssh_manager, "client", ssh_manager)
    return _studio_manager.show_studio(
        s_mgr=serial_manager,
        d_upd=dance_updater,
        s_chan=ssh_chan,
    )


def ensure_port_available(port: int) -> None:
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                if conn.pid and conn.pid != os.getpid():
                    logger.info(f"检测到端口 {port} 被旧进程 (PID {conn.pid}) 占用，正在自动释放...")
                    try:
                        p = psutil.Process(conn.pid)
                        p.terminate()
                        p.wait(timeout=2)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Port check notice: {e}")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def run_flask() -> None:
    ensure_port_available(PORT)
    logger.info(f"正在启动后台服务: http://{HOST}:{PORT} ...")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def wait_for_server(timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(PORT):
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    if "--studio" in sys.argv:
        from PySide6.QtWidgets import QApplication
        from src.ui.theme.fusion_dark_theme import apply_fusion_dark_theme
        from src.ui.windows.main_studio_window import MainStudioWindow
        app_qt = QApplication.instance() or QApplication(sys.argv)
        apply_fusion_dark_theme(app_qt)
        ssh_chan = getattr(ssh_manager, "client", ssh_manager)
        win = MainStudioWindow(serial_manager=serial_manager, dance_updater=dance_updater, ssh_channel=ssh_chan)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            win.show()
        return app_qt.exec() if os.environ.get("QT_QPA_PLATFORM") != "offscreen" else 0

    ensure_port_available(PORT)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if not wait_for_server():
        logger.error("Flask 服务启动超时！")
        return 1

    url = f"http://{HOST}:{PORT}"
    logger.info(f"后台服务已就绪: {url}")

    use_webview = True
    try:
        import webview
        logger.info("正在唤起 pywebview 原生客户端窗口...")
        window = webview.create_window(
            title="VSISLAB 机器人助手 - Unitree G1 Commercial Suite",
            url=url,
            width=1320,
            height=860,
            min_size=(1050, 720),
            background_color="#0a0e17",
        )
        webview.start()
    except Exception as e:
        logger.warning(f"无法启动 pywebview 原生窗口 ({e})，正在自动回退至系统默认浏览器...")
        use_webview = False

    if not use_webview:
        webbrowser.open(url)
        print("\n" + "=" * 60)
        print(f"  VSISLAB 机器人助手已在浏览器中启动: {url}")
        print("  按 Ctrl+C 退出程序")
        print("=" * 60 + "\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("程序已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
