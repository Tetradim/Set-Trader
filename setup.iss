; Sentinel Pulse - Inno Setup Script
; Build: iscc setup.iss
; Requires Inno Setup 6.0+

#define MyAppName "Sentinel Pulse"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Tetradim / SignalForge Lab"
#define MyAppURL "https://github.com/Tetradim/Set-Trader"
#define MyAppExeName "SentinelPulse.exe"
#define MyAppAssocName "Sentinel Pulse Config"
#define MyAppAssocExt ".sentinel"

[Setup]
AppId={{8A3E4B2C-1D5F-6E7A-9B8C-0D1E2F3A4B5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=SentinelPulse-Setup-{#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0.18362
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "launchapp"; Description: "Launch Sentinel Pulse after install"; GroupDescription: "Startup"; Flags: checkedonce

[Files]
Source: "backend\dist\SentinelPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "setup-and-launch.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch-sentinel-pulse.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch-sentinel-pulse.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "start-mongodb.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "start-mongodb.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "start-sentinel.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "backend\.env.example"; DestDir: "{app}"; Flags: ignoreversion; Check: not FileExists(ExpandConstant('{app}\.env'))
Source: "readme.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Launch-Sentinel-Pulse.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\Launch-Sentinel-Pulse.bat"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{commondesktop}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocName}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocName}"; ValueType: string; ValueName: ""; ValueData: "Sentinel Pulse Configuration"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
; Install VC++ Redistributable silently
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Flags: waituntilterminated; OnlyBelowVersion: 6.1

; Launch Sentinel Pulse if task selected
Filename: "{app}\Setup-And-Launch.bat"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec; Tasks: launchapp; WorkingDir: "{app}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: files; Name: "{userdesktop}\Sentinel-Pulse.log"
Type: files; Name: "{userdesktop}\Sentinel-Pulse-Transcript.log"
Type: files; Name: "{userdesktop}\Sentinel-Pulse-MongoDB.log"
Type: files; Name: "{userdesktop}\sentinel_pulse.log"
Type: files; Name: "{userdesktop}\SentinelPulse-Setup*.exe"
Type: files; Name: "{userdesktop}\Sentinel Pulse-Setup*.exe"
Type: files; Name: "{userdesktop}\Sentinel Pulse Setup*.exe"
Type: files; Name: "{commondesktop}\Sentinel-Pulse.log"
Type: files; Name: "{commondesktop}\Sentinel-Pulse-Transcript.log"
Type: files; Name: "{commondesktop}\Sentinel-Pulse-MongoDB.log"
Type: files; Name: "{commondesktop}\sentinel_pulse.log"
Type: files; Name: "{commondesktop}\SentinelPulse-Setup*.exe"
Type: files; Name: "{commondesktop}\Sentinel Pulse-Setup*.exe"
Type: files; Name: "{commondesktop}\Sentinel Pulse Setup*.exe"

[Code]
// Kill Sentinel Pulse processes on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Kill SentinelPulse.exe if running
    Exec('taskkill', '/F /IM SentinelPulse.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    
    // Kill mongod.exe if started by us (running under current user)
    Exec('taskkill', '/F /IM mongod.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// Create necessary directories after installation
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, LogPath, EnvFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataPath := ExpandConstant('{app}\data\db');
    LogPath := ExpandConstant('{app}\logs');
    EnvFile := ExpandConstant('{app}\.env');

    // Create data directory for MongoDB
    if not DirExists(DataPath) then
      CreateDir(DataPath);

    // Create logs directory
    if not DirExists(LogPath) then
      CreateDir(LogPath);

    // Create .env from .env.example if not present
    if not FileExists(EnvFile) then
    begin
      if FileExists(ExpandConstant('{app}\.env.example')) then
        FileCopy(ExpandConstant('{app}\.env.example'), EnvFile, False);
    end;
  end;
end;

// Check for existing installation
function InitializeSetup(): Boolean;
var
  Version: String;
begin
  Result := True;

  if RegQueryStringValue(HKCU, 'Software\{#MyAppPublisher}\{#MyAppName}', 'Version', Version) then
  begin
    if MsgBox('Sentinel Pulse is already installed. Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
