# Windows PowerShell Demo Launcher
# Crop Safety Guide & AI Crop Failure Intelligence Platform

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "  Crop Safety Guide & AI Crop Failure Intelligence Platform" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

# Test if port is in use and auto-fallback
$portCheck = Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue
if ($portCheck) {
    Write-Host "[!] Port $BackendPort is already in use. Switching Backend to port 8001..." -ForegroundColor Yellow
    $BackendPort = 8001
}

Write-Host "`n[1/3] Environment Pre-Flight Check..." -ForegroundColor Cyan
if (-not (Get-Command "py" -ErrorAction SilentlyContinue) -and -not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[-] Python is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
    Write-Host "[-] Node.js/npm is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

Write-Host "    Python and Node.js detected." -ForegroundColor DarkGreen

Write-Host "`n[2/3] Starting FastAPI Backend on port $BackendPort..." -ForegroundColor Cyan
$backendEnv = @{
    "PORT" = "$BackendPort"
    "PYTHONPATH" = "$projectRoot"
}
$backendProcess = Start-Process -FilePath "py" -ArgumentList "-3.13", "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host "`n[3/3] Starting Next.js Unified Frontend (Farmer + Expert) on port $FrontendPort..." -ForegroundColor Cyan
$frontendProcess = Start-Process -FilePath "npm" -ArgumentList "--prefix", "apps/farmer", "run", "dev", "--", "-p", "$FrontendPort" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 3

Write-Host "`n=====================================================================" -ForegroundColor Green
Write-Host "  PLATFORM READY FOR DEMONSTRATION" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "  * Unified App URL:     http://localhost:$FrontendPort/login" -ForegroundColor White
Write-Host "  * Unified Dashboard:   http://localhost:$FrontendPort/dashboard" -ForegroundColor White
Write-Host "  * Backend API Health:  http://127.0.0.1:$BackendPort/health" -ForegroundColor White
Write-Host "  * Backend API Docs:    http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
Write-Host "---------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "  Credentials (Farmer):  farmer@example.com / demo123" -ForegroundColor DarkCyan
Write-Host "  Credentials (Expert):  expert@example.com / demo123 (Activates Workbench)" -ForegroundColor DarkCyan
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "Press Ctrl+C or close the spawned windows to stop the servers." -ForegroundColor Gray
