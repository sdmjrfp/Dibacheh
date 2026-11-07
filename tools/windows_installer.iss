; برنامهٔ نصب ویندوز. بدون نیاز به دسترسی مدیر، برای کاربر فعلی نصب می‌شود.
#define Version GetEnv("DIBACHEH_VERSION")

[Setup]
AppId={{5B7C8F1E-6E0B-4F6B-9C55-D1BAC4E40001}
AppName=Dibacheh
AppVersion={#Version}
AppPublisher=sdmjrfp
DefaultDirName={localappdata}\Programs\Dibacheh
DefaultGroupName=Dibacheh
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\release
OutputBaseFilename=Dibacheh-{#Version}-Windows-Setup
SetupIconFile=..\build\release\icon.ico
UninstallDisplayIcon={app}\Dibacheh.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "..\build\release\dist\Dibacheh\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Dibacheh"; Filename: "{app}\Dibacheh.exe"
Name: "{autodesktop}\Dibacheh"; Filename: "{app}\Dibacheh.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Dibacheh.exe"; Description: "Open Dibacheh"; Flags: nowait postinstall skipifsilent
