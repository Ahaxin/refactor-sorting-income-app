; Inno Setup Script for Salary Planner
; Generates a Windows installer for the PyInstaller bundle.
;
; Prerequisites:
;   1. Build the PyInstaller bundle first:  python -m PyInstaller SalaryPlanner.spec
;   2. Install Inno Setup from: https://jrsoftware.org/isinfo.php
;   3. Run this script with the Inno Setup Compiler (ISCC.exe)

#define MyAppName "Monthly Salary Planner"
#define MyAppNameCN "月度工资计划器"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Salary Planner"
#define MyAppURL ""
#define MyAppExeName "SalaryPlanner.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{A8F3C9E1-2B4D-4F6A-8C3E-1D5B7F9A0E2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SalaryPlanner
; "ArchitecturesAllowed=x64" specifies that Setup cannot run on
; anything but x64.
ArchitecturesAllowed=x64
; "ArchitecturesInstallIn64BitMode=x64" requests that the install
; be done in "64-bit mode" on x64, meaning it should use the
; native 64-bit Program Files directory and the 64-bit view of the
; registry.
ArchitecturesInstallIn64BitMode=x64
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Remove the following line to run in administrative install mode.
; PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=SalaryPlanner-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Show language selection
ShowLanguageDialog=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The PyInstaller bundle — copy everything from dist/SalaryPlanner/
Source: "dist\SalaryPlanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Note: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppNameCN}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppNameCN}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
