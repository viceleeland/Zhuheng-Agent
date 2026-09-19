param(
    [string]$SdkRoot,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $SdkRoot) { $SdkRoot = Join-Path $repoRoot 'work/android-sdk' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repoRoot 'outputs/android' }
$buildRoot = Join-Path $repoRoot 'work/android-build'
$tools = Join-Path $SdkRoot 'build-tools/android-14'
$androidJar = Join-Path $SdkRoot 'platform/android-34/android.jar'
foreach ($required in @((Join-Path $tools 'aapt2.exe'), (Join-Path $tools 'lib/d8.jar'), $androidJar)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required official SDK component missing: $required" }
}
$javaCommand = (Get-Command java.exe -ErrorAction Stop).Source
$javaSettings = & $javaCommand -XshowSettings:properties -version 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the active Java runtime' }
$javaHomeMatch = $javaSettings | Select-String '^\s*java.home = (.+)$'
if (-not $javaHomeMatch) { throw 'Cannot resolve the active JDK home' }
$taskJavaHome = $javaHomeMatch.Matches[0].Groups[1].Value.Trim()
$javaBin = Join-Path $taskJavaHome 'bin'
$javac = Join-Path $javaBin 'javac.exe'
$java = Join-Path $javaBin 'java.exe'
$jar = Join-Path $javaBin 'jar.exe'
New-Item -ItemType Directory -Force -Path $buildRoot,$OutputDirectory,(Join-Path $buildRoot 'generated'),(Join-Path $buildRoot 'classes'),(Join-Path $buildRoot 'dex'),(Join-Path $buildRoot 'test') | Out-Null
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program" }
}
Invoke-Checked $javac @('-encoding','UTF-8','-d',(Join-Path $buildRoot 'test'),(Join-Path $PSScriptRoot 'src/org/changwei/mobile/ServerPolicy.java'),(Join-Path $PSScriptRoot 'test/ServerPolicyTest.java'))
Invoke-Checked $java @('-cp',(Join-Path $buildRoot 'test'),'ServerPolicyTest')
Invoke-Checked (Get-Command node.exe -ErrorAction Stop).Source @('--test',(Join-Path $PSScriptRoot 'test/download-bridge.test.cjs'))
Invoke-Checked (Join-Path $tools 'aapt2.exe') @('compile','--dir',(Join-Path $PSScriptRoot 'res'),'-o',(Join-Path $buildRoot 'resources.zip'))
Invoke-Checked (Join-Path $tools 'aapt2.exe') @('link','-o',(Join-Path $buildRoot 'unsigned.apk'),'-I',$androidJar,'--manifest',(Join-Path $PSScriptRoot 'AndroidManifest.xml'),'--java',(Join-Path $buildRoot 'generated'),'-A',(Join-Path $PSScriptRoot 'assets'),(Join-Path $buildRoot 'resources.zip'))
$sources = @((Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Filter '*.java' -Recurse).FullName) + @((Get-ChildItem -LiteralPath (Join-Path $buildRoot 'generated') -Filter '*.java' -Recurse).FullName)
Invoke-Checked $javac (@('-encoding','UTF-8','--release','8','-classpath',$androidJar,'-d',(Join-Path $buildRoot 'classes')) + $sources)
$classes = @((Get-ChildItem -LiteralPath (Join-Path $buildRoot 'classes') -Filter '*.class' -Recurse).FullName)
Invoke-Checked $java (@('-cp',(Join-Path $tools 'lib/d8.jar'),'com.android.tools.r8.D8','--lib',$androidJar,'--min-api','26','--output',(Join-Path $buildRoot 'dex')) + $classes)
Invoke-Checked $jar @('uf',(Join-Path $buildRoot 'unsigned.apk'),'-C',(Join-Path $buildRoot 'dex'),'classes.dex')
Invoke-Checked (Join-Path $tools 'zipalign.exe') @('-f','-p','4',(Join-Path $buildRoot 'unsigned.apk'),(Join-Path $buildRoot 'aligned.apk'))
$keystore = Join-Path $buildRoot 'changwei-local-test.jks'
if (-not (Test-Path -LiteralPath $keystore)) {
    throw 'The existing local test signing key is missing. Restore it to preserve upgrade compatibility.'
}
$apk = Join-Path $OutputDirectory 'jiangqing-android-0.1.1-local-test.apk'
Invoke-Checked $java @('-jar',(Join-Path $tools 'lib/apksigner.jar'),'sign','--ks',$keystore,'--ks-key-alias','changwei-local-test','--ks-pass','pass:android','--key-pass','pass:android','--v4-signing-enabled','false','--out',$apk,(Join-Path $buildRoot 'aligned.apk'))
$signature = & $java -jar (Join-Path $tools 'lib/apksigner.jar') verify --verbose --print-certs $apk
if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed' }
$expectedSigner = '09c0d335dd72a30c659edcb76499839f58a0b14fc52c789a79aa72140d5a26fc'
if (-not (($signature -join "`n").Contains("Signer #1 certificate SHA-256 digest: $expectedSigner"))) {
    throw 'Signing identity differs from version 0.1.0; this APK cannot be shipped as an in-place upgrade.'
}
$signature | Set-Content -LiteralPath (Join-Path $OutputDirectory 'apk-signature.txt') -Encoding utf8
Invoke-Checked (Join-Path $tools 'zipalign.exe') @('-c','-p','4',$apk)
$metadata = & (Join-Path $tools 'aapt2.exe') dump badging $apk
if ($LASTEXITCODE -ne 0) { throw 'APK manifest verification failed' }
$manifestText = $metadata -join "`n"
foreach ($expected in @("package: name='org.changwei.mobile'", "versionCode='2'", "versionName='0.1.1'", "application-label:'江擎'", "sdkVersion:'26'", "targetSdkVersion:'34'", "launchable-activity: name='org.changwei.mobile.MainActivity'")) {
    if (-not $manifestText.Contains($expected)) { throw "APK manifest assertion failed: $expected" }
}
if ($manifestText.Contains('application-debuggable')) { throw 'WebView client must not be debuggable' }
$permissions = @($metadata | Where-Object { $_ -match '^uses-permission:' })
if ($permissions.Count -ne 3 -or -not ($permissions -match "name='android.permission.INTERNET'") -or -not ($permissions -match "name='android.permission.RECORD_AUDIO'") -or -not ($permissions -match "name='android.permission.MODIFY_AUDIO_SETTINGS'")) {
    throw 'APK permission boundary changed; review the manifest'
}
$metadata | Set-Content -LiteralPath (Join-Path $OutputDirectory 'apk-manifest.txt') -Encoding utf8
$archive = [System.IO.Compression.ZipFile]::OpenRead($apk)
try {
    foreach ($entryName in @('AndroidManifest.xml','classes.dex','resources.arsc','assets/download-bridge.js','res/mipmap-anydpi-v26/ic_launcher.xml','res/drawable/ic_launcher_foreground.xml','res/drawable/ic_launcher_background.xml')) {
        if (-not $archive.GetEntry($entryName)) { throw "Required APK entry is missing: $entryName" }
    }
    $resources = $archive.GetEntry('resources.arsc')
    if ($resources.Length -ne $resources.CompressedLength) { throw 'Android resources.arsc must remain uncompressed' }
    if ($archive.Entries.FullName | Where-Object { $_ -match '\.(jks|keystore)$|(^|/)\.env$' }) { throw 'Private build material must not enter the APK' }
} finally { $archive.Dispose() }
$iconTree = & (Join-Path $tools 'aapt2.exe') dump xmltree $apk --file 'res/mipmap-anydpi-v26/ic_launcher.xml'
if ($LASTEXITCODE -ne 0 -or -not (($iconTree -join "`n").Contains('E: adaptive-icon'))) { throw 'Adaptive launcher icon verification failed' }
$iconTree | Set-Content -LiteralPath (Join-Path $OutputDirectory 'apk-icon.txt') -Encoding utf8
$hash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{
    apk = (Split-Path $apk -Leaf)
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $apk).Length
    package = 'org.changwei.mobile'
    label = '江擎'
    versionName = '0.1.1'
    versionCode = 2
    upgradeSignerMatchesVersion010 = $true
    signerSha256 = $expectedSigner
    minAndroid = '8.0 (API 26)'
    targetSdk = 34
    signing = 'Local test key only; not a production release signing identity'
    signatureVerified = $true
    zipAlignmentVerified = $true
    apkStructureVerified = $true
    adaptiveIconVerified = $true
    javaBoundaryTests = 'passed'
    javascriptBridgeTests = 'passed'
    deviceInstallVerified = $false
    cloudAsrVerified = $false
    builtAt = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'build-validation.json') -Encoding utf8
Write-Output "Built and verified: $apk"
Write-Output "SHA-256: $hash"
