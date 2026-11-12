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
SetupIconFile={#Root}\noise_filter\assets\icon.ico
InfoBeforeFile={#Root}\packaging\windows\VB-CABLE-NOTICE.txt

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
; Inno Setup has no official Indonesian translation, so key lines are bilingual.
InstallCable=Install VB-CABLE virtual microphone / Pasang mic virtual VB-CABLE
CableInstalling=Installing VB-CABLE... / Memasang VB-CABLE...

[Tasks]
Name: "vbcable"; Description: "{cm:InstallCable}"; Check: not CableInstalled
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Root}\dist\NoiseFilter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\packaging\windows\VB-CABLE-NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\build\vbcable\*"; DestDir: "{tmp}\vbcable"; Flags: ignoreversion recursesubdirs deleteafterinstall; Tasks: vbcable

[Icons]
Name: "{group}\Noise Filter"; Filename: "{app}\NoiseFilter.exe"
Name: "{group}\{cm:UninstallProgram,Noise Filter}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Noise Filter"; Filename: "{app}\NoiseFilter.exe"; Tasks: desktopicon

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

function NeedRestart: Boolean;
begin
  Result := CableJustInstalled;
end;

