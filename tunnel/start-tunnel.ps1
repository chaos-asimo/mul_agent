# 龙虾Claw 外网隧道启动脚本
# 用法：
#   .\start-tunnel.ps1                        # Quick Tunnel（临时地址）
#   .\start-tunnel.ps1 -Port 8888             # 指定本地端口
#   .\start-tunnel.ps1 -Token <tunnel_token>  # 命名隧道（固定地址，需 Cloudflare 账号）
#
# 依赖：
#   cloudflared 已安装到 C:\Users\admin\.cache\cloudflared\cloudflared.exe

param(
    [int]$Port = 8888,
    [string]$Token = ""
)

$Cloudflared = "C:\Users\admin\.cache\cloudflared\cloudflared.exe"
if (-not (Test-Path $Cloudflared)) {
    Write-Host "[ERROR] cloudflared not found at $Cloudflared" -ForegroundColor Red
    Write-Host "Download from: https://github.com/cloudflare/cloudflared/releases/latest" -ForegroundColor Yellow
    exit 1
}

# Kill existing cloudflared
$existing = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[INFO] Stopping existing cloudflared (PID $($existing.Id))..."
    $existing | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# Verify local service is running
try {
    $test = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -UseBasicParsing -TimeoutSec 3
    Write-Host "[OK] Local service running on port $Port (HTTP $($test.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Local service not responding on port ${Port}: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "Starting tunnel anyway (service may start later)..." -ForegroundColor Yellow
}

$logDir = "C:\Users\admin\.cache\cloudflared"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$errLog = "$logDir\tunnel-err.log"
$outLog = "$logDir\tunnel-out.log"
Remove-Item $errLog, $outLog -Force -ErrorAction SilentlyContinue

if ($Token) {
    # Named tunnel (fixed address) — requires Cloudflare account
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host "  Named Tunnel (fixed address)" -ForegroundColor Cyan
    Write-Host "  Token: $($Token.Substring(0,8))..." -ForegroundColor Cyan
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host ""
    $namedArgs = @{
        FilePath               = $Cloudflared
        ArgumentList           = @("tunnel", "--token", $Token)
        RedirectStandardOutput = $outLog
        RedirectStandardError  = $errLog
        WindowStyle            = "Hidden"
    }
    Start-Process @namedArgs
} else {
    # Quick tunnel (temporary address)
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host "  Quick Tunnel (temporary address)" -ForegroundColor Cyan
    Write-Host "  Local:  http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host ""
    # 必须用 127.0.0.1 而不是 localhost：Windows 上 localhost 优先解析为 IPv6 ::1，
    # 而 uvicorn 只监听 IPv4 0.0.0.0，会导致 Cloudflare 返回 530/502。
    $quickArgs = @{
        FilePath               = $Cloudflared
        ArgumentList           = @("tunnel", "--url", "http://127.0.0.1:$Port", "--protocol", "http2", "--no-autoupdate")
        RedirectStandardOutput = $outLog
        RedirectStandardError  = $errLog
        WindowStyle            = "Hidden"
    }
    Start-Process @quickArgs
}

Start-Sleep -Seconds 10

# Extract and display tunnel URL
$url = Select-String -Path $errLog -Pattern "https://[a-zA-Z0-9\-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | ForEach-Object { $_.Matches[0].Value }

$proc = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "[OK] cloudflared running (PID $($proc.Id))" -ForegroundColor Green
    if ($url) {
        Write-Host ""
        Write-Host "  >>> Tunnel URL: $url <<<" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Login page: $url/login" -ForegroundColor White
        Write-Host ""
        Write-Host "  NOTE: Quick tunnel addresses are TEMPORARY." -ForegroundColor Yellow
        Write-Host "  For a FIXED address, register a free Cloudflare account" -ForegroundColor Yellow
        Write-Host "  and use a named tunnel: .\start-tunnel.ps1 -Token <token>" -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] Tunnel starting... check $errLog for URL" -ForegroundColor Yellow
    }
    Write-Host "  Logs: $errLog" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] cloudflared crashed. Check log:" -ForegroundColor Red
    Get-Content $errLog -Tail 10
    exit 1
}
