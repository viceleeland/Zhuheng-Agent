param([switch]$Build)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    throw '缺少本机 .env 配置，请按 JIANGQING.md 配置服务。'
}
& docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw '请先启动 Docker Desktop，等待引擎就绪后重试。' }
if ($Build) {
    & docker compose build api worker web
    if ($LASTEXITCODE -ne 0) { throw '镜像构建失败，未继续启动。' }
}
& docker compose up -d --no-build
if ($LASTEXITCODE -ne 0) { throw '主服务启动失败，请检查 docker compose logs。' }
if (Test-Path -LiteralPath 'D:\workspace\rag_tt_1\rag_qa\models\bge-m3') {
    & docker compose -p changwei-local-bge -f compose.local-bge.yml up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw '本地向量服务启动失败。' }
}
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5051/api/system/ready' -TimeoutSec 3
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { throw '服务仍未就绪，请检查 docker compose logs api worker。' }
Write-Host '江擎已就绪：http://127.0.0.1:5174/changwei'
Write-Host '手机和客户端请连接同一 Tailscale 网络；首次访问仍需登录项目账号。'
$ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
if (Test-Path -LiteralPath $ts) { & $ts serve status }
