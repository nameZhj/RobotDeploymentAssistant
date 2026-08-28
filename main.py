"""
VSISLAB 机器人助手 (Robot Deployment Assistant)
客户端桌面启动程序
"""
import os
import sys
import time
import socket
import threading
import webbrowser
import logging

# Windows 任务栏专属应用 ID 绑定，确保任务栏独立显示专属机器人图标
if sys.platform == "win32":
    try:
        import ctypes
        app_id = "visislab.robotdeploymentassistant.suite.2.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

from app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger("Launcher")

PORT = 8088
HOST = "127.0.0.1"


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def ensure_port_available(port):
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr and conn.laddr.port == port and conn.status == 'LISTEN':
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


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def run_flask():
    ensure_port_available(PORT)
    logger.info(f"正在启动后台服务: http://{HOST}:{PORT} ...")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def wait_for_server(timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(PORT):
            return True
        time.sleep(0.2)
    return False


def main():
    ensure_port_available(PORT)
    # 1. 启动 Flask 后台服务线程
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if not wait_for_server():
        logger.error("Flask 服务启动超时！")
        sys.exit(1)

    url = f"http://{HOST}:{PORT}"
    logger.info(f"后台服务已就绪: {url}")

    # 2. 尝试通过 pywebview 唤起现代化原生桌面窗口
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
            background_color='#0a0e17'
        )
        webview.start()
    except Exception as e:
        logger.warning(f"无法启动 pywebview 原生窗口 ({e})，正在自动回退至系统默认浏览器...")
        use_webview = False

    # 3. 回退模式：打开浏览器并挂起主进程
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


if __name__ == "__main__":
    main()
