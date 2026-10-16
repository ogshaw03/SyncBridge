# SyncBridge uninstaller (per user). Run through Uninstall.bat in the install folder.
#
# Removes the program folder and the After Effects panel. Keeps user data: the
# backups made before each transfer and the server log.
# The Maya shelf button cannot be removed from outside Maya; the message says how.
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\SyncBridge'),
    [string]$CepRoot = (Join-Path $env:APPDATA 'Adobe\CEP\extensions'),
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$extensionId = 'com.syncbridge.panel'

function Show-Message([string]$text, [string]$icon = 'Information') {
    if ($Quiet) { Write-Output $text; return }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($text, 'SyncBridge', 'OK', $icon)
}

function Ask([string]$text) {
    if ($Quiet) { return $true }
    Add-Type -AssemblyName System.Windows.Forms
    return [System.Windows.Forms.MessageBox]::Show($text, 'SyncBridge', 'OKCancel', 'Question') -eq 'OK'
}

try {
    if (-not (Ask 'SyncBridge をアンインストールしますか？')) { exit 0 }

    Get-Process -Name SyncServer -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallRoot, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force

    # After Effects panel: only our own folder (its manifest names our extension).
    $extension = Join-Path $CepRoot $extensionId
    if (Test-Path $extension) {
        $item = Get-Item $extension -Force
        $manifest = Join-Path $extension 'CSXS\manifest.xml'
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { $item.Delete() }
        elseif ((Test-Path $manifest) -and (Select-String -Quiet -SimpleMatch $extensionId $manifest)) {
            Remove-Item -Recurse -Force $extension
        }
    }

    # Program folder. This script and Uninstall.bat live in it, so remove it after they exit.
    if (Test-Path (Join-Path $InstallRoot 'install.json')) {
        if ($Quiet) { Remove-Item -Recurse -Force $InstallRoot }
        else {
            Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c timeout /t 3 /nobreak >nul & rmdir /s /q `"$InstallRoot`""
        }
    }

    Show-Message ("SyncBridge をアンインストールしました。`n`n" +
        "Maya のシェルフの SyncBridge ボタンは、ボタンを右クリック →「削除」で消してください（Maya のバージョンごと）。`n" +
        "転送前のバックアップ（ドキュメント\maya\SyncBridge など）は残しています。")
    exit 0
}
catch {
    Show-Message ("SyncBridge のアンインストールに失敗しました。`n`n" + $_.Exception.Message) 'Error'
    exit 1
}
