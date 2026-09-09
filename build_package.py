import os
import sys
import stat
import shutil
import logging
import PyInstaller.__main__

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BuildPackage")

APP_NAME = "VSISLAB机器人部署助手"
MAIN_SCRIPT = "main.py"
PNG_ICON_PATH = os.path.join("web", "assets", "app_icon.png")
ICON_PATH = "app_icon.ico"


def force_remove_readonly(func, path, exc_info=None):
    """清除 Windows 只读文件属性并重试删除"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def kill_running_instances():
    """清理正在运行的同名旧程序进程，防止 EXE 文件锁死导致构建失败"""
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name']):
            try:
                name = p.info.get('name') or ''
                if APP_NAME.lower() in name.lower() or 'main.py' in ' '.join(p.cmdline() if p.cmdline() else []):
                    if p.pid != os.getpid():
                        logger.info(f"检测到正在运行的旧实例 (PID {p.pid})，正在终止...")
                        p.kill()
            except Exception:
                pass
    except Exception:
        pass


def step_0_prepare_icons():
    """从 web/assets/app_icon.png 生成包含全套高低分辨率的 Windows ICO 图标"""
    logger.info("[1/3] 正在从 web/assets/app_icon.png 生成多分辨率 Windows 应用图标...")
    if not os.path.exists(PNG_ICON_PATH):
        logger.warning(f"未找到图标源文件: {PNG_ICON_PATH}，将跳过图标转换")
        return

    try:
        from PIL import Image
        img = Image.open(PNG_ICON_PATH).convert("RGBA")
        icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ICON_PATH, format="ICO", sizes=icon_sizes)
        img.save(os.path.join("web", "favicon.ico"), format="ICO", sizes=icon_sizes)
        logger.info(f"应用图标已就绪: {ICON_PATH} 及 web/favicon.ico")
    except Exception as e:
        logger.warning(f"生成 ICO 图标出现警告: {e}")


def step_1_clean():
    """清理历史构建产物"""
    logger.info("[2/3] 清理旧的构建产物与临时文件...")
    kill_running_instances()
    for d in ["build", "dist", "__pycache__", "temp_uploads"]:
        if os.path.exists(d):
            shutil.rmtree(d, onexc=force_remove_readonly)
    for f in os.listdir("."):
        if f.endswith(".spec") or f == "setup_installer.iss":
            try:
                force_remove_readonly(os.remove, f)
            except Exception:
                pass
    logger.info("旧产物清理完成。")


def step_2_build_standalone_exe():
    """使用 PyInstaller 生成唯一的单文件独立可执行程序 (Onefile EXE)"""
    logger.info(f"[3/3] 正在构建唯一的正式版单文件程序: {APP_NAME}.exe (完整打包驱动与Web界面) ...")
    
    web_dir = os.path.abspath("web")
    drivers_dir = os.path.abspath(os.path.join("backend", "drivers"))
    icon_abs = os.path.abspath(ICON_PATH)
    
    add_data_args = [
        f'--add-data={web_dir}{os.pathsep}web',
        f'--add-data={drivers_dir}{os.pathsep}backend/drivers',
    ]
    if os.path.exists(icon_abs):
        add_data_args.append(f'--add-data={icon_abs}{os.pathsep}.')
    
    hidden_imports = [
        "--hidden-import=paramiko",
        "--hidden-import=yaml",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=jinja2",
        "--hidden-import=webview",
        "--hidden-import=serial",
        "--hidden-import=serial.tools",
        "--hidden-import=serial.tools.list_ports",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=requests",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.filedialog",
    ]

    excludes = [
        "--exclude-module=PyQt5",
        "--exclude-module=PyQt6",
        "--exclude-module=PySide2",
        "--exclude-module=PySide6",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=torch",
        "--exclude-module=torchvision",
    ]

    pyinstaller_args = [
        "--noconfirm",
        "--clean",
        "--onefile",             # 仅生成单个纯独立 EXE 文件
        "--windowed",            # 隐藏黑框控制台窗口
        f"--name={APP_NAME}",
    ]
    
    if os.path.exists(ICON_PATH):
        pyinstaller_args.append(f'--icon={ICON_PATH}')
        
    pyinstaller_args = pyinstaller_args + add_data_args + hidden_imports + excludes + [MAIN_SCRIPT]

    logger.info("正在调用 PyInstaller 编译单文件 EXE ...")
    try:
        PyInstaller.__main__.run(pyinstaller_args)
    except SystemExit as e:
        if e.code != 0:
            logger.error(f"PyInstaller 打包退出码: {e.code}")
            return False
    except Exception as e:
        logger.error(f"PyInstaller 打包发生异常: {e}")
        return False

    # 清理临时 build 目录与 spec 文件，确保工作区整洁
    if os.path.exists("build"):
        shutil.rmtree("build", onexc=force_remove_readonly)
    for f in os.listdir("."):
        if f.endswith(".spec"):
            try:
                force_remove_readonly(os.remove, f)
            except Exception:
                pass

    target_exe = os.path.join("dist", f"{APP_NAME}.exe")
    if not os.path.exists(target_exe):
        logger.error(f"未找到生成的 EXE 文件: {target_exe}")
        return False

    exe_size_mb = round(os.path.getsize(target_exe) / (1024 * 1024), 2)
    logger.info(f"单文件 EXE 构建完成！文件位于: {target_exe} (体积: {exe_size_mb} MB)")
    return True


def main():
    print("=" * 65)
    print(f"        {APP_NAME} 正式版单文件 EXE 构建工具")
    print("=" * 65)

    step_0_prepare_icons()
    step_1_clean()
    if not step_2_build_standalone_exe():
        print("[错误] 构建失败，请检查上方日志。")
        sys.exit(1)

    target_exe = os.path.join("dist", f"{APP_NAME}.exe")
    print("\n" + "=" * 65)
    print("  🎉 正式版构建完成！已仅生成单个独立可执行程序：")
    print(f"  👉 {target_exe}")
    print("  💡 双击该 EXE 即可直接运行，内置全部驱动与业务组件。")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
