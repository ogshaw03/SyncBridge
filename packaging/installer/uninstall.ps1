# SyncBridge uninstaller (per user). Run through Uninstall.bat in the install folder.
#
# Removes the program folder, the After Effects panel, the Start menu shortcut and the Maya
# shelf tabs written by the installer (0.1.5 and later). Keeps user data: the backups made
# before each transfer and the server log. A button added by dragging drag_to_maya_SyncBridge.py
# onto a shelf cannot be removed from outside Maya; the message says how.
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
    # Maya saves the shelves it has loaded when it quits, which would write the SyncBridge tab again.
    while (-not $Quiet -and (Get-Process -Name maya -ErrorAction SilentlyContinue)) {
        if (-not (Ask "Maya が起動中です。Maya を終了してから「OK」を押してください（「キャンセル」で中止）。")) { exit 0 }
    }

    Get-Process -Name SyncServer, SyncBridge -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallRoot, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force

    # Start menu shortcut of the monitor (0.1.3 and later record it in install.json).
    $record = Join-Path $InstallRoot 'install.json'
    if (Test-Path $record) {
        $info = Get-Content $record -Raw | ConvertFrom-Json
        $shortcut = $info.shortcut
        if ($shortcut -and $shortcut.EndsWith('.lnk') -and (Test-Path $shortcut)) { Remove-Item -Force $shortcut }
        # Maya shelf tabs and icons (0.1.5 and later): only files with our names.
        foreach ($file in @($info.maya_files)) {
            if (-not $file) { continue }
            $name = Split-Path -Leaf $file
            if (($name -eq 'shelf_SyncBridge.mel' -or $name -eq 'syncbridge_shelf.png') -and (Test-Path $file)) {
                Remove-Item -Force $file
            }
        }
    }

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
        "Maya のシェルフの「SyncBridge」タブも消しました。`n" +
        "ドラッグ＆ドロップで追加した SyncBridge ボタンがある場合は、ボタンを右クリック →「削除」で消してください（Maya のバージョンごと）。`n" +
        "転送前のバックアップ（ドキュメント\maya\SyncBridge など）は残しています。")
    exit 0
}
catch {
    Show-Message ("SyncBridge のアンインストールに失敗しました。`n`n" + $_.Exception.Message) 'Error'
    exit 1
}
