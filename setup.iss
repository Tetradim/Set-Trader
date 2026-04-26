; Sentinel Pulse - Inno Setup Script
; Build: iscc setup.iss
; Requires Inno Setup 6.0+

#define MyAppName "Sentinel Pulse"
#define MyAppVersion "1.0.0-beta"
#define MyAppPublisher "Tetradim / SignalForge Lab"
#define MyAppURL "https://github.com/Tetradim/Set-Trader"
#define MyAppExeName "SentinelPulse.exe"
#define MyAppAssocName "Sentinel Pulse Config"
#define MyAppAssocExt ".sentinel"

[Setup]
; Unique app ID - Generate new via Inno Setup > Tools > Generate GUID
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
; License - add LICENSE.txt to project root
; LicenseFile=LICENSE.txt
OutputDir=dist
OutputBaseFilename=SentinelPulse-Setup-{#MyAppVersion}
; SetupIconFile=SentinelPulse.ico  ; Place SentinelPulse.ico in project root
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Minimum Windows version (Win 10 1903+)
MinVersion=10.0.18362

; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Architecture
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
telemetryOptIn=Enable anonymous usage telemetry to help improve Sentinel Pulse

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1
Name: "autostart"; Description: "Start Sentinel Pulse on Windows login"; GroupDescription: "Startup Options"
Name: "firewall"; Description: "Add Windows Firewall exception for local web server"; GroupDescription: "Network"
Name: "telemetry"; Description: "Send anonymous usage statistics"; GroupDescription: "Privacy"; Flags: unchecked
Name: "mongodb"; Description: "Install portable MongoDB server"; GroupDescription: "Database"; Flags: unchecked

[Files]
; Main executable
Source: "backend\dist\SentinelPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: isreadme
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

; Sample configuration
Source: "backend\.env.example"; DestDir: "{app}"; Flags: ignoreversion; DestName: ".env.example"

; VC++ Redistributable (silent install)
Source: "backend\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
; Main app (launches batch which starts MongoDB then exe)
Name: "{group}\{#MyAppName}"; Filename: "{app}\Start Sentinel Pulse.bat"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\Start Sentinel Pulse.bat"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\Start Sentinel Pulse.bat"; WorkingDir: "{app}"; Tasks: autostart

[Registry]
; File association for .sentinel config files
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocName}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocName}"; ValueType: string; ValueName: ""; ValueData: "Sentinel Pulse Configuration"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocName}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Store install info
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Run]
; Install VC++ Redistributable silently
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Flags: waituntilterminated
; Launch after install
Filename: "{app}\Start Sentinel Pulse.bat"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent shellexec; WorkingDir: "{app}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Create necessary directories after installation
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, LogPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataPath := ExpandConstant('{app}\data\db');
    LogPath := ExpandConstant('{app}\logs');

    // Create data directory for MongoDB
    if not DirExists(DataPath) then
      CreateDir(DataPath);

    // Create logs directory
    if not DirExists(LogPath) then
      CreateDir(LogPath);
  end;
end;

// Add Windows Firewall exception if requested
procedure CurPageChanged(CurPageID: Integer);
var
  ResultCode: Integer;
begin
  if CurPageID = wpFinished then
  begin
    if IsTaskSelected('firewall') then
    begin
      Exec('netsh', 'advfirewall firewall add rule name="Sentinel Pulse Web Server" dir=in action=allow program="{app}\{#MyAppExeName}" enable=yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

// Clean up firewall on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="Sentinel Pulse Web Server"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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
