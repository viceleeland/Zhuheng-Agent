param([switch]$RefreshStatic, [switch]$Windows)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$static = Join-Path $repo 'work\web-release'
function Confirm-GatewayReady {
    $failure = 'Gateway did not respond.'
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        try {
            $page = Invoke-WebRequest -Uri 'http://127.0.0.1:5184/' -TimeoutSec 3
            $health = Invoke-WebRequest -Uri 'http://127.0.0.1:5184/api/system/health' -TimeoutSec 3
            $healthBody = $health.Content | ConvertFrom-Json
            # 就绪检查只走本机后端，公网入口继续隐藏依赖状态。
            $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:5051/api/system/ready' -TimeoutSec 3
            if ($page.StatusCode -eq 200 -and $page.Content -match '/assets/' -and $page.Content -notmatch '/@vite/client|/src/main' -and $health.StatusCode -eq 200 -and $healthBody.status -eq 'ok' -and $ready.status -eq 'ready' -and $ready.degraded -eq $false) {
                return
            }
            $failure = 'Production assets, gateway API health, or internal backend readiness did not pass.'
        } catch {
            $failure = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Gateway startup verification failed: $failure"
}
if ($RefreshStatic -or -not (Test-Path -LiteralPath (Join-Path $static 'index.html'))) {
    New-Item -ItemType Directory -Path $static -Force | Out-Null
    & docker cp 'changwei-web-dev:/app/dist/.' $static
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy built web distribution; build web production assets first.' }
}
$index = Get-Content -LiteralPath (Join-Path $static 'index.html') -Raw
if ($index -match '/@vite/client|/src/main') { throw 'Refusing to serve a Vite development entry.' }
if ($Windows) {
    $prefix = (Join-Path $repo 'work\nginx-windows\nginx-1.30.5').Replace('\','/') + '/'
    $exe = $prefix + 'nginx.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Download/extract official https://nginx.org/download/nginx-1.30.5.zip into work/nginx-windows first.' }
    $config = Get-Content -LiteralPath (Join-Path $repo 'docker\gateway\nginx.conf') -Raw
    $config = $config.Replace('worker_processes auto;', 'worker_processes 1;').Replace('pid /tmp/nginx.pid;', 'pid logs/nginx.pid;').Replace('/etc/nginx/mime.types', $prefix + 'conf/mime.types').Replace('/dev/stdout', 'logs/access.log').Replace('/dev/stderr', 'logs/error.log').Replace('  resolver 127.0.0.11 valid=10s ipv6=off;', '').Replace('listen 8080;', 'listen 127.0.0.1:5184;').Replace('/usr/share/nginx/html', $static.Replace('\','/')).Replace('http://changwei-api-dev:5050', 'http://127.0.0.1:5051')
    $configFile = (Join-Path $repo 'work\nginx-windows\gateway.conf').Replace('\','/')
    Set-Content -LiteralPath $configFile -Value $config -Encoding utf8
    & $exe -p $prefix -c $configFile -t
    if ($LASTEXITCODE -ne 0) { throw 'Windows gateway configuration invalid.' }
    $pidFile = Join-Path $prefix 'logs\nginx.pid'
    if ((Test-Path -LiteralPath $pidFile) -and (Get-Process -Id ([int](Get-Content -LiteralPath $pidFile)) -ErrorAction SilentlyContinue)) {
        & $exe -p $prefix -c $configFile -s reload
        if ($LASTEXITCODE -ne 0) { throw 'Gateway reload failed.' }
    } else {
        Start-Process -FilePath $exe -ArgumentList @('-p', $prefix, '-c', $configFile) -WorkingDirectory $prefix -WindowStyle Hidden
    }
    Confirm-GatewayReady
    Write-Host 'Project-local Windows gateway ready at http://127.0.0.1:5184/changwei; public tunnel remains separate.'
    return
}
$compose = Join-Path $repo 'compose.public.yml'
& docker compose -p jiangqing-public -f $compose run --rm --no-deps gateway nginx -t
if ($LASTEXITCODE -ne 0) { throw 'Gateway configuration validation failed.' }
& docker compose -p jiangqing-public -f $compose up -d gateway
if ($LASTEXITCODE -ne 0) { throw 'Gateway startup failed.' }
Confirm-GatewayReady
Write-Host 'Static gateway ready at http://127.0.0.1:5184/changwei. Public publishing is a separate step.'
