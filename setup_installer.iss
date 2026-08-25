// Inno Setup 纯中文安装向导脚本
#define MyAppName "VSISLAB机器人部署助手"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "VSISLAB Robotics"
#define MyAppURL "https://github.com/unitree-robotics"
#define MyAppExeName "VSISLAB机器人部署助手.exe"

[Setup]
AppId={{B867C828-8EFB-4962-A1B5-32E86948CD7D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=E:\code\python\RobotDeploymentAssistant\dist\Installer
OutputBaseFilename=VSISLAB机器人部署助手_v{#MyAppVersion}_Setup
SetupIconFile=E:\code\python\RobotDeploymentAssistant\app_icon.ico
UninstallIconFile=E:\code\python\RobotDeploymentAssistant\app_icon.ico
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
Source: "E:\code\python\RobotDeploymentAssistant\dist\VSISLAB机器人部署助手\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\code\python\RobotDeploymentAssistant\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
