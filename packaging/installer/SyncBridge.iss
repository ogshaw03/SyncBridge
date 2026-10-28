; SyncBridge setup (Inno Setup 6): SyncBridge-Setup-<version>.exe, per user, no administrator rights.
; Built by packaging/build_release.py, which saves a copy with a BOM (Japanese text) and runs
;   ISCC /DAppVersion=0.1.15 /DPayload=<release>\payload /DIcon=<ico> /DOutputDir=<dist>
;        /DOutputName=SyncBridge-Setup-0.1.15 SyncBridge.iss
;
; The payload (the same as the zip's) is unpacked to a temporary folder and installed by its install.ps1
; with -Setup: the same steps as Install.bat (program files, AE panel, Start menu, Maya shelf tabs),
; tested on users' PCs. Its message is shown on the last page. The uninstaller (registered in
; "Apps", in <app>\uninstall) runs uninstall.ps1 -Setup.
;
; Automated tests (tests/integration/test_installer.py): /SBTest=1 makes no "Apps" entry (no registry),
; /DIR=, /CepRoot=, /ProgramsDir= and /MayaAppDir= point everything at temporary folders.

#ifndef AppVersion
  #error AppVersion is required
#endif

[Setup]
AppId={{37BA4B31-BD87-4A70-AE30-F53FA9756084}
AppName=SyncBridge
AppVersion={#AppVersion}
AppVerName=SyncBridge {#AppVersion}
AppPublisher=SyncBridge
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\SyncBridge
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\app\syncbridge.ico
UninstallDisplayName=SyncBridge
UninstallFilesDir={app}\uninstall
CreateUninstallRegKey=not IsTest
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
CloseApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Files]
; to {tmp}: removed with it when the setup ends; install.ps1 copies what is installed
Source: "{#Payload}\*"; DestDir: "{tmp}\payload"; Flags: recursesubdirs createallsubdirs ignoreversion

[Code]
var
  InstallMessage: String;
  UninstallMessage: String;

function IsTest: Boolean;
begin
  Result := ExpandConstant('{param:SBTest|0}') = '1';
end;

function Quote(S: String): String;
begin
  Result := '"' + S + '"';
end;

{ -Name "value" when the setup was started with /Name=value (the automated tests' folders) }
function PassOn(Name: String): String;
var
  Value: String;
begin
  Result := '';
  Value := ExpandConstant('{param:' + Name + '|}');
  if Value <> '' then
    Result := ' -' + Name + ' ' + Quote(Value);
end;

{ Run a payload script with -Setup; returns its exit code and the message it wrote. }
function RunScript(Script, Args, MessageFile: String; var Message: String): Integer;
var
  Code, I: Integer;
  Lines: TArrayOfString;
begin
  DeleteFile(MessageFile);
  if not Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File ' + Quote(Script) +
              ' -Setup -MessageFile ' + Quote(MessageFile) + Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Code := -1;
  Message := '';
  if LoadStringsFromFile(MessageFile, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      if I > 0 then
        Message := Message + #13#10;
      Message := Message + Lines[I];
    end;
  DeleteFile(MessageFile);
  Result := Code;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Code := RunScript(ExpandConstant('{tmp}\payload\install.ps1'),
                      ' -InstallRoot ' + Quote(ExpandConstant('{app}')) +
                      PassOn('CepRoot') + PassOn('ProgramsDir') + PassOn('MayaAppDir'),
                      ExpandConstant('{tmp}\install_message.txt'), InstallMessage);
    if Code <> 0 then
    begin
      if InstallMessage = '' then
        InstallMessage := 'SyncBridge のインストールに失敗しました（PowerShell の終了コード ' + IntToStr(Code) + '）。';
      SuppressibleMsgBox(InstallMessage, mbCriticalError, MB_OK, IDOK);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (InstallMessage <> '') then
  begin
    WizardForm.FinishedLabel.Caption := InstallMessage;
    WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
  end;
end;

function MayaRunning: Boolean;
var
  Code: Integer;
begin
  Result := Exec('powershell.exe', '-NoProfile -Command "if (Get-Process -Name maya -ErrorAction SilentlyContinue) { exit 2 }"',
                 '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 2);
end;

{ Maya saves the shelves it has loaded when it quits, which would write the SyncBridge tab again. }
function InitializeUninstall: Boolean;
begin
  Result := True;
  if UninstallSilent then
    Exit;
  while MayaRunning do
    if MsgBox('Maya が起動中です。Maya を終了してから「OK」を押してください（「キャンセル」で中止）。',
              mbConfirmation, MB_OKCANCEL) <> IDOK then
    begin
      Result := False;
      Exit;
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RunScript(ExpandConstant('{app}\uninstall.ps1'), ' -InstallRoot ' + Quote(ExpandConstant('{app}')),
              AddBackslash(GetTempDir) + 'syncbridge_uninstall_message.txt', UninstallMessage)
  else if (CurUninstallStep = usPostUninstall) and (UninstallMessage <> '') then
    SuppressibleMsgBox(UninstallMessage, mbInformation, MB_OK, IDOK);
end;
