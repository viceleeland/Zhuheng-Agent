#ifndef BuildDir
  #define BuildDir "..\..\work\windows-build\app"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\work\windows-build\installer"
#endif
[Setup]
AppId={{A9D5B48A-72A7-4C1C-86EA-66AAB63012B5}
AppName=江擎
AppVersion=1.0.2
AppPublisher=江擎
DefaultDirName={localappdata}\Programs\ChangweiAgent
DefaultGroupName=江擎
UsePreviousGroup=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Jiangqing-Windows-x64-Setup-1.0.2
SetupIconFile=..\branding\jiangqing.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ChangweiAgent.exe
AppMutex=Local\JiangqingDesktopRunning
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

[Code]
function ProbeFile(FileName: String; DesiredAccess, ShareMode, SecurityAttributes, CreationDisposition, FlagsAndAttributes, TemplateFile: LongWord): LongWord;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseProbe(Handle: LongWord): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Files: TArrayOfString;
  I: Integer;
  Handle: LongWord;
  FileName: String;
begin
  Result := '';
  Files := ['ChangweiAgent.exe', 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll'];
  for I := 0 to GetArrayLength(Files) - 1 do begin
    FileName := ExpandConstant('{app}\') + Files[I];
    if FileExists(FileName) then begin
      { Request WRITE and DELETE access only; OPEN_EXISTING and no delete-on-close flag.
        This does not modify/delete the file. Deny installation on any failure,
        including legacy clients without AppMutex or insufficient file rights. }
      Handle := ProbeFile(FileName, $40010000, 7, 0, 3, 0, 0);
      if Handle = $FFFFFFFF then begin
        Log('Pre-install replacement probe blocked: ' + FileName);
        Result := '无法更新 ' + Files[I] + '。请先保存草稿并关闭所有江擎窗口，再点击重试；若仍失败，请检查安装目录的写入权限。安装尚未替换文件。';
        Exit;
      end;
      CloseProbe(Handle);
    end;
  end;
end;
