# 停止外网隧道
$proc = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($proc) {
    $proc | Stop-Process -Force
    Write-Host "[OK] cloudflared stopped (was PID $($proc.Id))" -ForegroundColor Green
} else {
    Write-Host "[INFO] cloudflared is not running" -ForegroundColor Yellow
}
