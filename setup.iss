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
SetupIconFile=SentinelPulse.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/extra
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

[Files]
; Main executable
Source: "backend\dist\SentinelPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: isreadme
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

; Sample configuration
Source: "backend\.env.example"; DestDir: "{app}"; Flags: ignoreversion; DestName: ".env.example"

; Optional portable MongoDB (user choice)
Source: "mongod.exe"; DestDir: "{app}\mongodb"; Flags: ignoreversion; Check: ShouldInstallMongo

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

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
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Check if user wants MongoDB bundled
function ShouldInstallMongo(): Boolean;
begin
  Result := False;
  if FileExists(ExpandConstant('{src}\mongod.exe')) then
  begin
    if MsgBox('Do you want to install a portable MongoDB server with Sentinel Pulse?' + #13#10 + #13#10 +
              'If you already have MongoDB installed or plan to use MongoDB Atlas, choose No.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      Result := True;
    end;
  end;
end;

// Create necessary directories after installation
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, MongoPath, LogPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataPath := ExpandConstant('{app}\data');
    LogPath := ExpandConstant('{app}\logs');

    // Create data directory for state/MongoDB
    if not DirExists(DataPath) then
      CreateDir(DataPath);

    // Create logs directory
    if not DirExists(LogPath) then
      CreateDir(LogPath);

    // Create MongoDB directory if installing portable
    if ShouldInstallMongo then
    begin
      MongoPath := ExpandConstant('{app}\mongodb');
      if not DirExists(MongoPath) then
        CreateDir(MongoPath);
    end;
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
      // Add inbound rule for the app
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
