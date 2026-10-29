# 打包成單一 dist\LumEasy.exe(會先安裝、跑單元測試,打包後跑自我測試)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    & (Join-Path $PSScriptRoot "install.ps1")
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
& $venvPy -m pip install -q "pyinstaller>=6.10" pytest
Write-Host "單元測試 ..."
& $venvPy -m pytest -q tests
if ($LASTEXITCODE -ne 0) { Write-Host "單元測試失敗" -ForegroundColor Red; exit 1 }
Write-Host "打包中(約 3-5 分鐘)..."
& $venvPy -m PyInstaller LumEasy.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Host "打包失敗" -ForegroundColor Red; exit 1 }
$p = Start-Process -FilePath (Join-Path $root "dist\LumEasy.exe") -ArgumentList "--selftest" -Wait -PassThru
Get-Content (Join-Path $env:TEMP "lumeasy_selftest.txt") -Encoding UTF8
if ($p.ExitCode -ne 0) { Write-Host "打包後的自我測試失敗" -ForegroundColor Red; exit 1 }
Write-Host ""
Write-Host "完成:dist\LumEasy.exe" -ForegroundColor Green
exit 0
