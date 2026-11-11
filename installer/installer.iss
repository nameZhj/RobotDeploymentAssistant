; Inno Setup 6 脚本 - VSISLAB机器人部署助手 中文安装向导
#define MyAppName "VSISLAB机器人部署助手"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "VSISLAB"
#define MyAppExeName "VSISLAB机器人部署助手.exe"
#define MyOutputDir "dist"
#define MyOutputBaseFilename "VSISLAB机器人部署助手_安装向导_v1.0.0"

[Setup]
AppId={{C8E2C44B-3694-4F3A-8A46-4B36D331A47B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SourceDir=..
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\app_icon.ico
DisableProgramGroupPage=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; 在用户安装目录下创建 cache 文件夹与 preview 文件夹，并授予用户读写修改权限
Name: "{app}\cache"; Permissions: users-modify
Name: "{app}\preview"; Permissions: users-modify

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
; 在用户安装目录下的 cache 文件夹中放置初始 robot_fleet.json
Source: "installer\default_fleet.json"; DestDir: "{app}\cache"; DestName: "robot_fleet.json"; Flags: onlyifdoesntexist
; 在用户安装目录下放置 preview 文件夹初始结构
Source: "preview\.gitkeep"; DestDir: "{app}\preview"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\cache\*.log"
Type: files; Name: "{app}\cache\*.tmp"
