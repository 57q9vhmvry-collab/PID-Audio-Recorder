#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef OutputBaseFilename
  #define OutputBaseFilename "PIDAudioRecorder-Setup-" + AppVersion
#endif

[Setup]
AppId={{5EAF1D4D-8ECA-4A53-A97D-6BAA6D8956F6}
AppName=PID Audio Recorder
AppVersion={#AppVersion}
AppPublisher=PID Audio Recorder
DefaultDirName={localappdata}\PIDAudioRecorder
DefaultGroupName=PID Audio Recorder
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PIDAudioRecorder.exe
OutputDir=installer
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\ui.ico
CloseApplications=yes
CloseApplicationsFilter=PIDAudioRecorder.exe
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer_lang\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "dist\PIDAudioRecorder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PID Audio Recorder"; Filename: "{app}\PIDAudioRecorder.exe"
Name: "{autodesktop}\PID Audio Recorder"; Filename: "{app}\PIDAudioRecorder.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PIDAudioRecorder.exe"; Description: "启动 PID Audio Recorder"; Flags: nowait postinstall skipifsilent
