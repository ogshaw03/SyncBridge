# Restore the development setup of this repository (after tools\dev_env_off.ps1 or a release test).
# Run it yourself (it changes the registry):
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev_env_on.ps1
#
#   1. PlayerDebugMode = 1 for CSXS.11-13 (unsigned development panel)
#   2. link %APPDATA%\Adobe\CEP\extensions\com.syncbridge.panel -> <this repository>\after_effects
# An installed release must be uninstalled first (its panel uses the same folder name).
$ErrorActionPreference = 'Stop'
$repoAe = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) 'after_effects'

$ext = Join-Path $env:APPDATA 'Adobe\CEP\extensions\com.syncbridge.panel'
if (Test-Path $ext) {
    $item = Get-Item $ext -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Write-Host "インストール版の AE パネルがあります。先に %LOCALAPPDATA%\Programs\SyncBridge\Uninstall.bat でアンインストールしてください。"
        exit 1
    }
    $item.Delete()
}

foreach ($n in 11, 12, 13) {
    reg add "HKCU\Software\Adobe\CSXS.$n" /v PlayerDebugMode /t REG_SZ /d 1 /f | Out-Null
    Write-Host ("設定: CSXS.$n の PlayerDebugMode = 1")
}

New-Item -ItemType Directory -Force (Split-Path -Parent $ext) | Out-Null
New-Item -ItemType Junction -Path $ext -Target $repoAe | Out-Null
Write-Host ("作成: AE パネルの開発用リンク -> " + $repoAe)
Write-Host ""
Write-Host "完了: 開発用の状態です。Maya では PHASE1_PLAN.md のスクリプトでパネルを開いてください。"
