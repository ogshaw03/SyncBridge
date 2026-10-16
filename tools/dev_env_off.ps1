# Put this PC into the state of a user who has never installed SyncBridge (to test the release).
# Undo with tools\dev_env_on.ps1. Run it yourself (it changes the registry):
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev_env_off.ps1
#
# What it does:
#   1. stops SyncBridge servers (development python and SyncServer.exe)
#   2. removes the development link %APPDATA%\Adobe\CEP\extensions\com.syncbridge.panel (link only)
#   3. removes the PlayerDebugMode values of CSXS.11-13 (only that value; the keys stay)
#   4. deletes session.json and server.log in %LOCALAPPDATA%\SyncBridge
# It keeps the transfer backups (they do not affect an install) and never touches an installed
# release (use its Uninstall.bat for that).
$ErrorActionPreference = 'Stop'

$busy = @(Get-Process -Name maya, AfterFX -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name -Unique)
if ($busy.Count -gt 0) {
    Write-Host ("Maya / After Effects が起動中です（" + ($busy -join ', ') + "）。終了してから、もう一度実行してください。")
    exit 1
}

# 1. servers
$servers = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -and $_.CommandLine -like '*syncbridge.server*') -or $_.Name -eq 'SyncServer.exe' }
foreach ($p in $servers) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host ("停止: " + $p.Name + " (pid " + $p.ProcessId + ")")
}

# 2. development link of the AE panel
$ext = Join-Path $env:APPDATA 'Adobe\CEP\extensions\com.syncbridge.panel'
if (Test-Path $ext) {
    $item = Get-Item $ext -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        $item.Delete()
        Write-Host ("削除: AE パネルの開発用リンク（リンク先 " + $item.Target + " は残っています）")
    } else {
        Write-Host "注意: AE パネルはインストール版です。先に %LOCALAPPDATA%\Programs\SyncBridge\Uninstall.bat でアンインストールしてください。"
    }
}

# 3. PlayerDebugMode
foreach ($n in 11, 12, 13) {
    $key = "HKCU:\Software\Adobe\CSXS.$n"
    if ((Test-Path $key) -and ((Get-Item $key).GetValue('PlayerDebugMode') -ne $null)) {
        Remove-ItemProperty -Path $key -Name PlayerDebugMode
        Write-Host ("削除: CSXS.$n の PlayerDebugMode")
    }
}

# 4. session and log of the development server
foreach ($f in 'session.json', 'server.log') {
    $path = Join-Path $env:LOCALAPPDATA "SyncBridge\$f"
    if (Test-Path $path) { Remove-Item -Force $path; Write-Host ("削除: " + $path) }
}

Write-Host ""
Write-Host "完了: SyncBridge を一度も入れていない状態です（転送前のバックアップは残しています）。"
Write-Host "開発用の状態に戻すときは tools\dev_env_on.ps1 を実行してください。"
