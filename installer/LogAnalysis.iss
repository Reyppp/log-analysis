#define MyAppName "Log Analysis"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-beta.6"
#endif
#define MyNumericVersion "0.1.0.0"
#define MyAppPublisher "Reyppp"
#define MyAppURL "https://github.com/Reyppp/log-analysis"
#define MyAppExeName "Log Analysis.exe"

[Setup]
AppId={{4982086B-FC4C-4A9F-86ED-CBE770A3A2E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=Log-Analysis-Setup-v{#MyAppVersion}-x64
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyNumericVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyNumericVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Local coating log analysis workbench

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\dist\Log Analysis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  RemoveSettings: Boolean;

const
  InstallerSettingsKey = 'Software\Log Analysis\Installer';

function GetDesktopDirectory(): String;
begin
  Result := '';
  if not RegQueryStringValue(HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders',
    'Desktop', Result) or (Result = '') or (Pos('%', Result) > 0) then
    Result := ExpandConstant('{userdesktop}');
end;

function GetDesktopShortcutPath(Param: String): String;
begin
  Result := AddBackslash(GetDesktopDirectory()) + '{#MyAppName}.lnk';
end;

function HasWebView2At(Base: String): Boolean;
var
  Found: TFindRec;
begin
  Result := FindFirst(Base + '\*\msedgewebview2.exe', Found);
  if Result then
    FindClose(Found);
end;

function WebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '')) or
            (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '')) or
            HasWebView2At(ExpandConstant('{pf32}\Microsoft\EdgeWebView\Application')) or
            HasWebView2At(ExpandConstant('{pf64}\Microsoft\EdgeWebView\Application')) or
            HasWebView2At(ExpandConstant('{localappdata}\Microsoft\EdgeWebView\Application'));
end;

function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := WebView2Installed();
  if not Result then
  begin
    if SuppressibleMsgBox('Log Analysis 需要 Microsoft Edge WebView2 Runtime。是否打开微软下载页面？', mbError, MB_YESNO, IDNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ShortcutPath: String;
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('desktopicon') then
  begin
    ShortcutPath := GetDesktopShortcutPath('');
    try
      ForceDirectories(ExtractFileDir(ShortcutPath));
      CreateShellLink(
        ShortcutPath,
        '{#MyAppName}',
        ExpandConstant('{app}\{#MyAppExeName}'),
        '',
        ExpandConstant('{app}'),
        ExpandConstant('{app}\{#MyAppExeName}'),
        0,
        SW_SHOWNORMAL);
      RegWriteStringValue(HKCU, InstallerSettingsKey,
        'DesktopShortcut', ShortcutPath);
    except
      Log('Desktop shortcut creation failed: ' + GetExceptionMessage);
      SuppressibleMsgBox(
        'Log Analysis 已完成安装，但桌面快捷方式创建失败。' + #13#10 +
        '请从开始菜单启动应用。',
        mbInformation, MB_OK, IDOK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ShortcutPath: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveSettings := SuppressibleMsgBox('是否同时删除 Log Analysis 保存的上次炉次路径？', mbConfirmation, MB_YESNO, IDNO) = IDYES;
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKCU, InstallerSettingsKey,
      'DesktopShortcut', ShortcutPath) and FileExists(ShortcutPath) then
      DeleteFile(ShortcutPath);
    RegDeleteValue(HKCU, InstallerSettingsKey, 'DesktopShortcut');
    RegDeleteKeyIfEmpty(HKCU, InstallerSettingsKey);
    RegDeleteKeyIfEmpty(HKCU, 'Software\Log Analysis');
    if RemoveSettings then
      DelTree(ExpandConstant('{localappdata}\Log Analysis'), True, True, True);
  end;
end;
