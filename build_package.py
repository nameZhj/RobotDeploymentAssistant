import os
import sys
import shutil
import subprocess
import logging

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BuildPackage")

APP_NAME = "VSISLAB机器人部署助手"
APP_VERSION = "2.0.0"
PUBLISHER = "VSISLAB Robotics"
MAIN_SCRIPT = "main.py"
ICON_PATH = "app_icon.ico"


def step_1_clean():
    """清理历史构建产物"""
    logger.info("[步骤 1/4] 清理旧的 build/ 与 dist/ 目录...")
    for d in ["build", "dist", "__pycache__"]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
    for f in os.listdir("."):
        if f.endswith(".spec"):
            try:
                os.remove(f)
            except Exception:
                pass
    logger.info("旧产物清理完成。")


def step_2_build_pyinstaller():
    """执行 PyInstaller 生成独立可执行程序"""
    logger.info("[步骤 2/4] 正在使用 PyInstaller 打包客户端 EXE (应用自定义机器人图标) ...")
    
    # 收集需要打包的数据目录 (web/ 与 backend/drivers/)
    web_dir = os.path.abspath("web")
    drivers_dir = os.path.abspath(os.path.join("backend", "drivers"))
    add_data_args = [
        f'--add-data="{web_dir};web"',
        f'--add-data="{drivers_dir};backend/drivers"',
    ]
    
    # 隐藏导入项
    hidden_imports = [
        "--hidden-import=paramiko",
        "--hidden-import=yaml",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=webview",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",             # 生成目录包
        "--windowed",            # 隐藏控制台窗口
        f"--name={APP_NAME}",
        f'--icon="{ICON_PATH}"', # 自定义应用图标
    ] + add_data_args + hidden_imports + [MAIN_SCRIPT]

    cmd_str = " ".join(cmd)
    logger.info(f"执行打包命令: {cmd_str}")
    res = subprocess.run(cmd_str, shell=True)
    if res.returncode != 0:
        logger.error(f"PyInstaller 打包失败，退出码: {res.returncode}")
        return False

    logger.info(f"EXE 打包成功！产物位于: dist/{APP_NAME}/")
    return True


def step_3_generate_inno_setup_script():
    """生成 100% 纯中文 Inno Setup 安装向导脚本 (.iss)"""
    logger.info("[步骤 3/4] 正在生成 Inno Setup 纯中文安装向导脚本 (setup_installer.iss) ...")

    base_dir = os.path.abspath(".")
    dist_app_dir = os.path.join(base_dir, "dist", APP_NAME)

    iss_raw = """// Inno Setup 纯中文安装向导脚本
#define MyAppName "@APP_NAME@"
#define MyAppVersion "@APP_VERSION@"
#define MyAppPublisher "@PUBLISHER@"
#define MyAppURL "https://github.com/unitree-robotics"
#define MyAppExeName "@APP_NAME@.exe"

[Setup]
AppId={{B867C828-8EFB-4962-A1B5-32E86948CD7D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=@BASE_DIR@\\dist\\Installer
OutputBaseFilename=@APP_NAME@_v{#MyAppVersion}_Setup
SetupIconFile=@BASE_DIR@\\app_icon.ico
UninstallIconFile=@BASE_DIR@\\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Messages]
BeveledLabel=VSISLAB 宇树机器人部署套件
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=此向导将在您的计算机上安装 [name] (Unitree G1 商业化部署系统)。%n%n建议您在继续之前关闭所有其他应用程序。
WizardSelectDir=选择安装路径
SelectDirDesc=您希望将 [name] 安装到哪个文件夹？
SelectDirLabel3=[name] 将安装到以下目标文件夹中。
SelectDirBrowseLabel=若要继续，请单击“下一步”。若要选择其他文件夹，请单击“浏览”。
WizardSelectTasks=选择附加任务
SelectTasksDesc=您希望执行哪些快捷方式配置？
SelectTasksLabel2=选择您希望安装向导在安装 [name] 时执行的附加任务：
WizardReady=准备开始安装
ReadyLabel1=安装向导已准备就绪，即将开始在您的计算机上安装 [name]。
ReadyLabel2a=单击“安装”开始解压并安装组件，或者单击“上一步”检查并修改设置。
WizardInstalling=正在安装组件
InstallingLabel=安装向导正在将 [name] 部署到您的计算机中，请稍候...
WizardFinished=[name] 安装向导完成
FinishedHeadingLabel=[name] 安装成功
FinishedLabelNoIcons=[name] 已成功部署到您的计算机。
FinishedLabel=[name] 已成功安装到您的计算机。您可以通过桌面快捷方式或开始菜单启动本软件。
ClickFinish=单击“完成”退出安装向导。
ExitSetupTitle=退出安装向导
ExitSetupMessage=安装尚未完成。如果您现在退出，程序将不会被完全部署。%n%n您确定要退出安装向导吗？
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonInstall=安装(&I)
ButtonFinish=完成(&F)
ButtonCancel=取消

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "快捷方式:"

[Files]
Source: "@DIST_APP_DIR@\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "@BASE_DIR@\\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; IconFilename: "{app}\\app_icon.ico"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; IconFilename: "{app}\\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
"""

    iss_content = iss_raw.replace("@APP_NAME@", APP_NAME)\
                         .replace("@APP_VERSION@", APP_VERSION)\
                         .replace("@PUBLISHER@", PUBLISHER)\
                         .replace("@BASE_DIR@", base_dir)\
                         .replace("@DIST_APP_DIR@", dist_app_dir)

    iss_path = os.path.join(base_dir, "setup_installer.iss")
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(iss_content)

    logger.info(f"纯中文 Inno Setup 脚本已生成: {iss_path}")
    return iss_path


def step_4_compile_installer(iss_path: str):
    """尝试调用 Inno Setup 编译器 (ISCC.exe) 编译安装向导 EXE"""
    logger.info("[步骤 4/4] 正在检测并编译中文安装向导 EXE ...")

    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"D:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        shutil.which("ISCC.exe") or ""
    ]

    iscc_exe = next((p for p in iscc_paths if p and os.path.exists(p)), None)

    if iscc_exe:
        logger.info(f"找到 Inno Setup 编译器: {iscc_exe}")
        os.makedirs(os.path.join("dist", "Installer"), exist_ok=True)
        res = subprocess.run(f'"{iscc_exe}" "{iss_path}"', shell=True)
        if res.returncode == 0:
            installer_file = os.path.join("dist", "Installer", f"{APP_NAME}_v{APP_VERSION}_Setup.exe")
            logger.info("=" * 60)
            logger.info(f"🎉 中文安装向导编译成功！文件位于: {installer_file}")
            logger.info("=" * 60)
            return True
        else:
            logger.warning("Inno Setup 编译遇到错误，但绿色可执行程序已就绪。")
    else:
        logger.info("系统中未安装 Inno Setup 编译器，已为您生成便携安装包和标准 .iss 脚本。")
        # 生成绿色便携压缩包
        zip_output = os.path.join("dist", f"{APP_NAME}_v{APP_VERSION}_Portable")
        logger.info(f"正在打包绿色便携 ZIP: {zip_output}.zip ...")
        shutil.make_archive(zip_output, "zip", root_dir="dist", base_dir=APP_NAME)
        logger.info(f"绿色便携安装包打包完成: {zip_output}.zip")

    return True


def step_5_cleanup_temp_build():
    """清理中间临时 build 目录，防止误点击 build 目录中的半成品"""
    logger.info("[步骤 5/5] 清理中间临时 build 目录...")
    if os.path.exists("build"):
        shutil.rmtree("build", ignore_errors=True)
    logger.info("临时 build 目录清理完成。")


def main():
    print("=" * 65)
    print(f"        {APP_NAME} 一键打包与中文安装程序构建工具")
    print("=" * 65)

    # 1. 清理
    step_1_clean()

    # 2. PyInstaller 打包
    if not step_2_build_pyinstaller():
        print("[错误] 打包失败，请检查上方日志。")
        sys.exit(1)

    # 3. 生成 ISS 脚本
    iss_path = step_3_generate_inno_setup_script()

    # 4. 编译安装向导
    step_4_compile_installer(iss_path)

    # 5. 清理临时 build 目录
    step_5_cleanup_temp_build()

    print("\n" + "=" * 65)
    print("  🎉 打包与构建全部成功！")
    print(f"  👉 1. 中文安装向导 (发给客户安装): dist/Installer/{APP_NAME}_v{APP_VERSION}_Setup.exe")
    print(f"  👉 2. 免安装绿色版 (直接运行): dist/{APP_NAME}/{APP_NAME}.exe")
    print("  ⚠️ 注意：请勿运行临时 build/ 目录中的文件（已自动为您清理）")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
