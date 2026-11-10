#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
AppId={{1C0BDA83-85B7-4DB3-967B-8EB94B9F76F3}
AppName=TaskStack
AppVersion={#AppVersion}
AppPublisher=TaskStack
DefaultDirName={localappdata}\Programs\TaskStack
DefaultGroupName=TaskStack
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\..\release-build\setup
OutputBaseFilename=TaskStack-Setup-{#AppVersion}-win-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\TaskStack.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\..\release-build\dist\TaskStack.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TaskStack"; Filename: "{app}\TaskStack.exe"
Name: "{autodesktop}\TaskStack"; Filename: "{app}\TaskStack.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\TaskStack.exe"; Description: "{cm:LaunchProgram,TaskStack}"; Flags: postinstall nowait skipifsilent
