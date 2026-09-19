#ifndef BuildDir
  #define BuildDir "..\..\work\windows-build\app"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\work\windows-build\installer"
#endif
[Setup]
AppId={{A9D5B48A-72A7-4C1C-86EA-66AAB63012B5}
AppName=江擎
AppVersion=1.0.1
AppPublisher=江擎
DefaultDirName={localappdata}\Programs\ChangweiAgent
DefaultGroupName=江擎
UsePreviousGroup=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Jiangqing-Windows-x64-Setup-1.0.1
SetupIconFile=..\branding\jiangqing.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ChangweiAgent.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
[Files]
Source: "{#BuildDir}\ChangweiAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\ChangweiAgent.exe.config"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\Microsoft.Web.WebView2.Core.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\Microsoft.Web.WebView2.WinForms.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\WebView2-LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\WebView2-NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\江擎"; Filename: "{app}\ChangweiAgent.exe"; Comment: "水利工程智能协作"
Name: "{group}\卸载江擎"; Filename: "{uninstallexe}"
Name: "{userdesktop}\江擎"; Filename: "{app}\ChangweiAgent.exe"; Comment: "水利工程智能协作"
[InstallDelete]
Type: files; Name: "{userdesktop}\长委工程智能工作台.lnk"
Type: files; Name: "{userprograms}\长委工程智能工作台\长委工程智能工作台.lnk"
Type: files; Name: "{userprograms}\长委工程智能工作台\卸载长委工程智能工作台.lnk"
Type: dirifempty; Name: "{userprograms}\长委工程智能工作台"
[Run]
Filename: "{app}\ChangweiAgent.exe"; Description: "打开江擎"; Flags: nowait postinstall skipifsilent
