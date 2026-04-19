#define MyAppName "Sentinel Pulse"
#define MyAppVersion "1.0.0-beta"
#define MyAppPublisher "Tetradim"
#define MyAppExeName "SentinelPulse.exe"
#define MyAppURL "https://github.com/Tetradim/Set-Trader"

[Setup]
AppId={{A1B2C3D4-E5F6-4789-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=SentinelPulse-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: desktopicon; Description: "Create desktop shortcut for the program"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: uninstallicon; Description: "Create desktop shortcut for Uninstall"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "backend\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "backend\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Add any other files/folders you need

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{commondesktop}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: uninstallicon; IconFilename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
