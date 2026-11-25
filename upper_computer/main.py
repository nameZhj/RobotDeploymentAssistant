"""
@file: main.py
@brief: 机器人助手主程序（支持原生部署控制台与舞台编导控制台交互唤起）
@exports: main, launch_studio_window
"""
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple
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
from werkzeug.serving import make_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# R-2：恢复 werkzeug 错误级日志（app.py 导入期整体禁用了该 logger），绑定失败等关键错误必须可见
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("werkzeug").disabled = False

logger = logging.getLogger("Launcher")

PORT = 8088
HOST = "127.0.0.1"

# R-2：Flask 线程以 Event 回传绑定成败；绑定失败原因由主线程读取并给用户可见错误
_flask_ready = threading.Event()
_flask_bind_error: List[str] = []


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
            request_show = Signal(object, object, object, str)

        self._app = app_inst
        self._bridge = _LauncherBridge()

        def _handle_show(s_mgr: Any, d_upd: Any, s_chan: Any, initial_page: str = "choreography") -> None:
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
                        initial_page=initial_page,
                    )
                elif hasattr(self._window, "switch_page"):
                    # R-1：窗口复用路径须在 switch_page/show 前重挂事件总线 dispatcher 并重启遥测回调
                    # 监听，否则 closeEvent 的 clear/stop 之后工作线程 publish 会退化为工作线程直发 UI。
                    rearm = getattr(self._window, "rearm_event_flow", None)
                    if callable(rearm):
                        rearm()
                    self._window.switch_page(initial_page)
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
        from src.ui.theme.studio_dark_theme import apply_studio_theme
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        apply_studio_theme(self._app)
        self._init_bridge(self._app)
        self._app.exec()

    def show_studio(
        self,
        s_mgr: Any = None,
        d_upd: Any = None,
        s_chan: Any = None,
        initial_page: str = "choreography",
    ) -> Tuple[bool, str]:
        try:
            self.ensure_qt_running()
            if self._bridge is not None:
                # 跨线程信号会由 Qt 事件循环自动排队处理；切勿在 Flask 线程里调用 processEvents()
                # （QApplication 事件循环只能在创建它的线程中驱动，否则会导致随机崩溃）。
                self._bridge.request_show.emit(s_mgr, d_upd, s_chan, initial_page)
                return True, "🎬 舞台编导控制台正在唤起"
            return False, "Qt 事件循环初始化超时"
        except Exception as e:
            logger.error(f"唤起舞台编导异常: {e}", exc_info=True)
            return False, str(e)


_studio_manager = StudioWindowManager()


def launch_studio_window(initial_page: str = "choreography") -> Tuple[bool, str]:
    """供 Flask 接口调用的全局窗口唤起方法，注入全局 serial_manager, dance_updater, ssh_manager"""
    return _studio_manager.show_studio(
        s_mgr=serial_manager,
        d_upd=dance_updater,
        s_chan=ssh_manager,
        initial_page=initial_page,
    )


def _looks_like_app_process(p: Any) -> bool:
    """R-3：以 exe/命令行白名单确认占用进程是否为本应用实例（打包 exe 或本仓 main.py/app.py）。"""
    try:
        if getattr(sys, "frozen", False):
            return Path(p.exe()).name.lower() == Path(sys.executable).name.lower()
        own_dir = Path(__file__).resolve().parent
        for arg in p.cmdline():
            arg_path = Path(str(arg))
            if arg_path.name.lower() not in ("main.py", "app.py"):
                continue
            base = arg_path if arg_path.is_absolute() else Path(p.cwd()) / arg_path
            if base.resolve().parent == own_dir:
                return True
        return False
    except Exception as ex:
        logger.warning(f"读取进程 {getattr(p, 'pid', '?')} 身份信息失败，按非本应用处理: {ex}")
        return False


def ensure_port_available(port: int) -> bool:
    """释放被本应用旧实例占用的端口；身份确认失败或释放失败时返回 False，由调用方中止启动并告警。"""
    try:
        import psutil
    except ImportError as ex:
        logger.warning(f"psutil 不可用({ex})，跳过端口 {port} 占用清理，直接尝试绑定（占用时将以绑定失败上报）")
        return True
    victim: Optional[int] = None
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                if conn.pid and conn.pid != os.getpid():
                    victim = conn.pid
                    break
    except Exception as ex:
        logger.warning(f"端口 {port} 占用检测失败，直接尝试绑定（占用时将以绑定失败上报）: {ex}")
        return True
    if victim is None:
        return True
    try:
        proc = psutil.Process(victim)
    except psutil.NoSuchProcess:
        return True
    if not _looks_like_app_process(proc):
        logger.error(f"端口 {port} 被无法确认为本应用的进程 (PID {victim}) 占用，为避免误杀不自动终止，启动中止")
        return False
    logger.info(f"检测到端口 {port} 被本应用旧进程 (PID {victim}) 占用，正在自动释放...")
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception as ex:
        logger.error(f"释放端口 {port} 失败 (PID {victim})：{ex}，请手动结束该进程后重试")
        return False
    return True


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def run_flask() -> None:
    if not ensure_port_available(PORT):
        _flask_bind_error.append(f"端口 {PORT} 被占用且未自动释放（非本应用进程或释放失败）")
        _flask_ready.set()
        return
    logger.info(f"正在启动后台服务: http://{HOST}:{PORT} ...")
    try:
        # R-2：make_server 显式绑定，绑定成败立即可知（app.run 的绑定异常只会在线程内消亡，无上报通道）
        server = make_server(HOST, PORT, app, threaded=True)
    except OSError as ex:
        _flask_bind_error.append(f"Flask 服务绑定 {HOST}:{PORT} 失败: {ex}")
        _flask_ready.set()
        logger.error(_flask_bind_error[-1])
        return
    _flask_ready.set()
    try:
        server.serve_forever()
    except Exception as ex:
        logger.error(f"Flask 服务异常退出: {ex}", exc_info=True)


def _self_identify(timeout: float = 4.0) -> bool:
    """R-2：请求本服务自标识端点 /api/status（绕过系统代理），确认 8088 上应答的是本应用。"""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{HOST}:{PORT}/api/status", timeout=timeout) as resp:
            data = json.loads(resp.read(4096).decode("utf-8", errors="replace"))
    except Exception:
        return False
    return isinstance(data, dict) and "connected" in data and "transport" in data


def wait_for_server(timeout: float = 10.0) -> bool:
    """等待本进程 Flask 完成绑定并通过自标识端点应答；绑定已确定失败时立即返回 False。"""
    start = time.time()
    while time.time() - start < timeout:
        if _flask_bind_error:
            return False
        if _flask_ready.is_set() and is_port_in_use(PORT) and _self_identify():
            return True
        time.sleep(0.2)
    return False


def _notify_startup_failure(detail: str) -> None:
    """R-2/R-3：--windowed 构建无控制台，启动失败必须以弹窗形式给用户可见错误。"""
    logger.error(f"后台服务启动失败: {detail}")
    if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f"后台服务启动失败，程序即将退出。\n\n{detail}", "VSISLAB 机器人助手", 0x10,
        )
    except Exception as ex:
        logger.warning(f"无法弹出错误对话框: {ex}")


def main() -> int:
    if "--studio" in sys.argv:
        from PySide6.QtWidgets import QApplication
        from src.ui.theme.fusion_dark_theme import apply_fusion_dark_theme
        from src.ui.windows.main_studio_window import MainStudioWindow
        app_qt = QApplication.instance() or QApplication(sys.argv)
        apply_fusion_dark_theme(app_qt)
        win = MainStudioWindow(serial_manager=serial_manager, dance_updater=dance_updater, ssh_channel=ssh_manager)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            win.show()
        return app_qt.exec() if os.environ.get("QT_QPA_PLATFORM") != "offscreen" else 0

    # R-3：移除 main() 处与 run_flask() 重复的 ensure_port_available 调用，收敛 check-then-bind TOCTOU
    _flask_ready.clear()
    _flask_bind_error.clear()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if not wait_for_server():
        detail = _flask_bind_error[0] if _flask_bind_error else "后台服务绑定超时（端口可能被占用）"
        _notify_startup_failure(detail)
        return 1

    url = f"http://{HOST}:{PORT}"
    logger.info(f"后台服务已就绪: {url}")

    use_webview = True
    try:
        import webview
        logger.info("正在唤起 pywebview 原生客户端窗口...")
        window = webview.create_window(
            title="VSISLAB 机器人助手 - G1 商业化部署系统",
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
