param(
    [string]$SdkDirectory = (Join-Path $PSScriptRoot '..\..\work\windows-build\webview2-sdk'),
    [string]$InnoCompiler = (Join-Path $PSScriptRoot '..\..\work\windows-build\inno\ISCC.exe'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\..\work\windows-build\installer')
)
$ErrorActionPreference = 'Stop'
$appDirectory = Join-Path $PSScriptRoot '..\..\work\windows-build\app'
New-Item -ItemType Directory -Path $appDirectory,$OutputDirectory -Force | Out-Null
$core = Join-Path $SdkDirectory 'lib\net462\Microsoft.Web.WebView2.Core.dll'
$forms = Join-Path $SdkDirectory 'lib\net462\Microsoft.Web.WebView2.WinForms.dll'
$loader = Join-Path $SdkDirectory 'runtimes\win-x64\native\WebView2Loader.dll'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$brandIcon = Join-Path $PSScriptRoot '..\branding\jiangqing.ico'
foreach ($required in @($core,$forms,$loader,$compiler,$InnoCompiler,$brandIcon)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Build dependency missing: $required" }
}
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$appDirectory\ChangweiAgent.exe" "/win32icon:$brandIcon" "/win32manifest:$PSScriptRoot\app.manifest" "/reference:$core" "/reference:$forms" /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll "$PSScriptRoot\Program.cs"
if ($LASTEXITCODE -ne 0) { throw 'C# build failed' }
Copy-Item -LiteralPath $core,$forms,$loader -Destination $appDirectory -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ChangweiAgent.exe.config') -Destination $appDirectory -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $appDirectory 'README.txt') -Force
Copy-Item -LiteralPath (Join-Path $SdkDirectory 'LICENSE.txt') -Destination (Join-Path $appDirectory 'WebView2-LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $SdkDirectory 'NOTICE.txt') -Destination (Join-Path $appDirectory 'WebView2-NOTICE.txt') -Force
& $InnoCompiler "/DBuildDir=$([IO.Path]::GetFullPath($appDirectory))" "/DOutputDir=$([IO.Path]::GetFullPath($OutputDirectory))" (Join-Path $PSScriptRoot 'setup.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
Get-ChildItem -LiteralPath $OutputDirectory -Filter '*.exe' | Get-FileHash -Algorithm SHA256
