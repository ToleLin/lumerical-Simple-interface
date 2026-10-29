# LumEasy 一鍵安裝(從原始碼執行用):建立 .venv、安裝套件、建立桌面捷徑。不改系統設定。
# 只想用的人不需要這個:直接下載 Releases 裡的 LumEasy.exe 雙擊即可。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Find-Python {
    foreach ($cand in @(@("py", "-3"), @("python"))) {
        try {
            $exe = $cand[0]
            $args_ = @($cand | Select-Object -Skip 1)
            $v = & $exe @args_ -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) {
                $parts = $v.Trim().Split(".")
                if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10) { return ,$cand }
            }
        } catch {}
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "找不到 Python 3.10 以上版本。" -ForegroundColor Red
    Write-Host "請到 https://www.python.org/downloads/ 安裝(安裝時勾選 Add python.exe to PATH),再重新執行 install.bat。"
    exit 1
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "[1/3] 建立虛擬環境 .venv ..."
if (-not (Test-Path $venvPy)) {
    $a = @($py | Select-Object -Skip 1) + @("-m", "venv", ".venv")
    & $py[0] @a
    if ($LASTEXITCODE -ne 0) { Write-Host "建立虛擬環境失敗" -ForegroundColor Red; exit 1 }
}
Write-Host "[2/3] 安裝套件(第一次約 1-3 分鐘)..."
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { Write-Host "安裝套件失敗,請把上面的訊息截圖回報。" -ForegroundColor Red; exit 1 }
Write-Host "[3/3] 建立桌面捷徑 ..."
if ($env:LUMEASY_NO_SHORTCUT -ne "1") {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "LumEasy.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
    $s.Arguments = "-m lumeasy"
    $s.WorkingDirectory = $root
    $s.IconLocation = Join-Path $root "assets\icon.ico"
    $s.Save()
}
& $venvPy -m lumeasy --selftest | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "自我測試沒有全部通過,詳細結果:$env:TEMP\lumeasy_selftest.txt" -ForegroundColor Yellow
} else {
    Write-Host "自我測試通過。"
}
Write-Host ""
Write-Host "安裝完成!雙擊桌面上的 LumEasy,或執行 run.bat。" -ForegroundColor Green
exit 0
