; Ultron — the Windows installer.
;
; Two rules shape this file.
;
; 1. No administrator. Ultron installs into the user's own folder and never writes
;    to Program Files or the registry outside the user's hive. A personal assistant
;    that needs an administrator password to exist is a personal assistant most
;    people cannot install.
;
; 2. Never throw away the owner's data. Uninstalling removes the program and its
;    Python environment, and keeps the key file, the memory store and the logs,
;    then says where they are. Deleting somebody's keys because they uninstalled
;    is the kind of tidy that costs them an afternoon.
;
; Build it with: powershell -File packaging\build_installer.ps1

#define AppName "Ultron"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8E1C0A54-6F2B-4B7E-9C11-2A6F3B7D9E40}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Ultron
DefaultDirName={localappdata}\Programs\Ultron
DefaultGroupName=Ultron
DisableProgramGroupPage=yes
; Per-user install. "lowest" is Inno's way of saying "this needs no administrator".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\build\installer
OutputBaseFilename=UltronSetup-{#AppVersion}
SetupIconFile=..\config\jarvis.ico
UninstallDisplayIcon={app}\config\jarvis.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; The app is Python; the launcher builds its own environment on first run.
DisableDirPage=no
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put Ultron on the desktop"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
; The staging folder is assembled by build_installer.ps1 from packaging/payload.txt,
; so what ships is a list somebody can read rather than a wildcard nobody checks.
Source: "stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ultron"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\run.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\config\jarvis.ico"; Comment: "Start Ultron"
Name: "{group}\Uninstall Ultron"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Ultron"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\run.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\config\jarvis.ico"; Comment: "Start Ultron"; Tasks: desktopicon

[Run]
; First run is where the setup screen appears and asks for a provider and a key.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\run.ps1"""; WorkingDir: "{app}"; Description: "Start Ultron now"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Only things the app generates that nobody would want back. The key file, the
; memory store and the logs are NOT here, on purpose.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function PythonPresent(): Boolean;
var
  ResultCode: Integer;
begin
  { "py -3" is the Windows launcher, and it is the one thing every Python
    installer since 3.5 has provided. Ultron needs Python to build its own
    environment on first run, so this is checked before anything is copied — a
    missing interpreter found during install is an instruction, and found on the
    first launch it is a mystery. }
  Result := FileExists(ExpandConstant('{sys}\py.exe')) or
            Exec(ExpandConstant('{cmd}'), '/c where py', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not PythonPresent() then
  begin
    if MsgBox('Ultron needs Python 3.11, 3.12 or 3.13, and this PC does not have it yet.' + #13#10 + #13#10 +
              'Install it from python.org (tick "Add python.exe to PATH"), then run this installer again.' + #13#10 + #13#10 +
              'Continue installing anyway? Ultron will explain the same thing when it starts.',
              mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{app}');
    MsgBox('Ultron has been removed from this PC.' + #13#10 + #13#10 +
           'Your own files were kept, on purpose:' + #13#10 +
           '  ' + Data + '\config\api_keys.json' + #13#10 +
           '  ' + Data + '\memory\' + #13#10 + #13#10 +
           'Those hold your API keys and what Ultron remembers about you. ' +
           'Delete that folder yourself if you want them gone too.',
           mbInformation, MB_OK);
  end;
end;
