; Inno Setup script: one offline setup.exe with the frozen app and VB-CABLE.
; Build: iscc /DAppVersion=0.2.0 packaging\windows\installer.iss
;   expects dist\NoiseFilter\ (PyInstaller output) and build\vbcable\ (extracted VBCABLE_Driver_Pack)

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#define Root "..\.."

[Setup]
AppId={{6F0B7C1E-2B7A-4E8B-9C55-4C1F2E1A9D31}
AppName=Noise Filter
AppVersion={#AppVersion}
AppPublisher=SkillsHUB Electronics
DefaultDirName={autopf}\Noise Filter
DefaultGroupName=Noise Filter
OutputDir={#Root}\dist
OutputBaseFilename=NoiseFilter-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\NoiseFilter.exe
CloseApplications=force
ChangesEnvironment=yes
SetupIconFile={#Root}\noise_filter\assets\icon.ico
InfoBeforeFile={#Root}\packaging\windows\VB-CABLE-NOTICE.txt

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
; Inno Setup has no official Indonesian translation, so key lines are bilingual.
InstallCable=Install VB-CABLE virtual microphone / Pasang mic virtual VB-CABLE
CableInstalling=Installing VB-CABLE... / Memasang VB-CABLE...
AddToPath=Add the nfctl command (control by command line / AI) to PATH / Tambahkan perintah nfctl ke PATH

[Tasks]
Name: "vbcable"; Description: "{cm:InstallCable}"; Check: not CableInstalled
Name: "addtopath"; Description: "{cm:AddToPath}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Root}\dist\NoiseFilter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\packaging\windows\VB-CABLE-NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\build\vbcable\*"; DestDir: "{tmp}\vbcable"; Flags: ignoreversion recursesubdirs deleteafterinstall; Tasks: vbcable

[Icons]
Name: "{group}\Noise Filter"; Filename: "{app}\NoiseFilter.exe"
Name: "{group}\{cm:UninstallProgram,Noise Filter}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Noise Filter"; Filename: "{app}\NoiseFilter.exe"; Tasks: desktopicon

[Registry]
; The app writes this value itself ("Start with Windows" setting); remove it on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "NoiseFilter"; \
  ValueType: none; Flags: uninsdeletevalue dontcreatekey

; nfctl.exe (command-line / AI control) is reachable from any terminal
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueName: "Path"; \
  ValueType: expandsz; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{tmp}\vbcable\VBCABLE_Setup_x64.exe"; Parameters: "-i -h"; StatusMsg: "{cm:CableInstalling}"; \
  Flags: waituntilterminated; Tasks: vbcable; AfterInstall: AfterCable
Filename: "{app}\NoiseFilter.exe"; Description: "{cm:LaunchProgram,Noise Filter}"; Flags: nowait postinstall skipifsilent

[Code]
var CableJustInstalled: Boolean;

function CableInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64_win10.sys')) or
            FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64_win7.sys')) or
            FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64arm_win10.sys'));
end;

procedure AfterCable;
var Code: Integer;
begin
  if not CableInstalled then
    { silent install did not take: show the VB-Audio setup window instead }
    Exec(ExpandConstant('{tmp}\vbcable\VBCABLE_Setup_x64.exe'), '', '', SW_SHOW, ewWaitUntilTerminated, Code);
  CableJustInstalled := CableInstalled;
end;

const EnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function NeedsAddPath(Dir: string): Boolean;
var Paths: string;
begin
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Paths) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

procedure RemovePath(Dir: string);
var Paths: string; P: Integer;
begin
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Paths) then exit;
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then exit;
  { P is the position of the separator in front of Dir in ';' + Paths + ';' }
  if P = 1 then
    Delete(Paths, 1, Length(Dir) + 1)
  else
    Delete(Paths, P - 1, Length(Dir) + 1);
  RegWriteExpandStringValue(HKLM, EnvKey, 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath(ExpandConstant('{app}'));
end;

function NeedRestart: Boolean;
begin
  Result := CableJustInstalled;
end;

