import sys
import time
import subprocess

# 确保 Windows 命令行支持 UTF-8 打印
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    ENDC = '\033[0m'

def log_info(msg: str):
    print(f"{Colors.CYAN}[INFO] {time.strftime('%H:%M:%S')} - {msg}{Colors.ENDC}")

def log_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS] {time.strftime('%H:%M:%S')} - {msg}{Colors.ENDC}")

def main():
    log_info("正在启动桌面客户端并挂载实时日志监控...")
    subprocess.Popen([sys.executable, "main.py"])
    log_success("客户端已启动，正在监控日志...")

if __name__ == "__main__":
    main()
