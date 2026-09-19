# 仅提取检查函数，在独立进程用响应桩复现就绪误报，不启动或修改服务。
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot 'start-public-gateway.ps1'
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Gateway script could not be parsed.' }
$definition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Confirm-GatewayReady' }, $true)
if (-not $definition) { throw 'Readiness function not found.' }
. ([scriptblock]::Create($definition.Extent.Text))
function Invoke-WebRequest {
    param($Uri, $TimeoutSec)
    if ($Uri -eq 'http://127.0.0.1:5184/') {
        return [pscustomobject]@{ StatusCode = 200; Content = $script:Case.Page }
    }
    if ($Uri -eq 'http://127.0.0.1:5184/api/system/health') {
        return [pscustomobject]@{ StatusCode = 200; Content = $script:Case.Health }
    }
    throw "Unexpected URL: $Uri"
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    if ($Uri -ne 'http://127.0.0.1:5051/api/system/ready') { throw 'Readiness must use the private backend URL.' }
    if ($script:Case.ReadyFails) { throw 'Backend dependency unavailable: 503' }
    return $script:Case.Ready
}
function Start-Sleep { param($Milliseconds) }
$cases = @(
    @{ Name = 'healthy'; Page = '<script src="/assets/main.js"></script>'; Health = '{"status":"ok"}'; Ready = @{status='ready'; degraded=$false}; Expected = $true },
    @{ Name = 'dependency unavailable despite health 200'; ReadyFails = $true; Expected = $false },
    @{ Name = 'HTML fallback at health URL'; Health = '<html>login</html>'; Expected = $false },
    @{ Name = 'non-ok health JSON'; Health = '{"status":"error"}'; Expected = $false },
    @{ Name = 'Vite mixed with production assets'; Page = '<script src="/assets/main.js"></script><script src="/@vite/client"></script>'; Expected = $false },
    @{ Name = 'backend not ready without degraded flag'; Ready = @{status='not_ready'; degraded=$false}; Expected = $false },
    @{ Name = 'degraded backend'; Ready = @{status='ready'; degraded=$true}; Expected = $false },
    @{ Name = 'missing readiness fields'; Ready = @{}; Expected = $false }
)
foreach ($fixture in $cases) {
    $script:Case = @{ Page = '<script src="/assets/main.js"></script>'; Health = '{"status":"ok"}'; Ready = @{status='ready'; degraded=$false}; ReadyFails = $false }
    foreach ($key in $fixture.Keys) { $script:Case[$key] = $fixture[$key] }
    $accepted = $false
    try { Confirm-GatewayReady; $accepted = $true } catch { }
    if ($accepted -ne $fixture.Expected) { throw "Unexpected readiness result: $($fixture.Name)" }
    Write-Output "PASS: $($fixture.Name)"
}
