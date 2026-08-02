; Raphael — Inno Setup installer script
;
; How to use:
;   1. Build the app first:  python build_app.py
;   2. Open this file in Inno Setup Compiler and press Compile (Ctrl+F9)
;      OR build from command line:  iscc raphael.iss
;
; Output: installer\Raphael_Setup.exe

#define MyAppName "Raphael"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Raphael Contributors"
#define MyAppURL "https://github.com/indala/raphael"
#define MyAppExeName "Raphael.exe"

[Setup]
; Basic metadata
AppId=Raphael
AppName={#MyAppName}
AppVerName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Windows version info
VersionInfoVersion=0.1.0.0
VersionInfoProductName=Raphael
VersionInfoCompany=Raphael Contributors

; Install directory
DefaultDirName={autopf}\Raphael
DefaultGroupName=Raphael
; Remember previous install dir on upgrades
UsePreviousAppDir=yes
UsePreviousGroup=yes
; Auto-close running Raphael during install
CloseApplications=yes
; Only show dir/group pages on fresh install, not upgrades
DisableDirPage=auto
DisableProgramGroupPage=auto

; Output
OutputDir=installer
OutputBaseFilename=Raphael_Setup

; Compression
Compression=lzma2/max
SolidCompression=yes

; Uninstall
UninstallDisplayIcon={app}\Raphael.exe
UninstallDisplayName=Raphael

; Windows version range — Windows 10 (10.0.10240) and later
MinVersion=10.0.10240

; Privileges — requires admin for Program Files install
PrivilegesRequired=admin

; Use the app icon for the installer
SetupIconFile=assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Files to install ───────────────────────────────────────────────────
[Files]
; Main executable
Source: "dist\Raphael\{#MyAppExeName}";  DestDir: "{app}"; Flags: ignoreversion

; All internal files (DLLs, Python runtime, etc.)
Source: "dist\Raphael\_internal\*";       DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; App icon (for shortcuts)
Source: "assets\icon.ico";                DestDir: "{app}"; Flags: ignoreversion
Source: "bin\ffmpeg.exe";                DestDir: "{app}"; Flags: ignoreversion
Source: "bin\avcodec-63.dll";           DestDir: "{app}"; Flags: ignoreversion
Source: "bin\avdevice-63.dll";           DestDir: "{app}"; Flags: ignoreversion
Source: "bin\avfilter-12.dll";           DestDir: "{app}"; Flags: ignoreversion
Source: "bin\avformat-63.dll";           DestDir: "{app}"; Flags: ignoreversion
Source: "bin\avutil-61.dll";             DestDir: "{app}"; Flags: ignoreversion
Source: "bin\swresample-7.dll";          DestDir: "{app}"; Flags: ignoreversion
Source: "bin\swscale-10.dll";            DestDir: "{app}"; Flags: ignoreversion

; ── Start Menu + Desktop shortcuts ─────────────────────────────────────
[Icons]
Name: "{autoprograms}\Raphael";       Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\Raphael (debug)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Parameters: "--dev"
Name: "{autodesktop}\Raphael";         Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"

; ── What to run after install ─────────────────────────────────────────
[Run]
; 1. Install Playwright Chromium browser (checkable, waits to finish)
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-playwright"; Description: "Install Playwright Chromium browser for web automation"; Flags: postinstall runascurrentuser skipifsilent; StatusMsg: "Installing Playwright Chromium browser..."; Check: NotPlaywrightInstalled
; 2. Launch the app (checkbox offered to user)
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Raphael"; Flags: postinstall nowait skipifsilent shellexec

; ── Uninstall cleanup ──────────────────────────────────────────────────
[UninstallDelete]
; Logs are safe to remove — config stays so reinstalling doesn't require re-setup
Type: filesandordirs; Name: "{app}\logs"
; Remove Playwright browser binaries installed to user AppData
Type: filesandordirs; Name: "{userappdata}\.raphael\ms-playwright"

; ── Custom Pascal functions ────────────────────────────────────────────
[Code]

function NotPlaywrightInstalled: Boolean;
var
  SearchPath: string;
  FindRec: TFindRec;
begin
  Result := True;
  SearchPath := GetEnv('APPDATA') + '\.raphael\ms-playwright\chromium-*';
  if FindFirst(SearchPath, FindRec) then
  begin
    FindClose(FindRec);
    Result := False;  // Already installed — skip step
  end;
end;
