# SyncBridge installer (per user, no administrator rights). Run through Install.bat.
#
#   server : <InstallRoot>\server\SyncServer.exe
#   Maya   : <InstallRoot>\maya  (the user drags drag_to_maya_SyncBridge.py onto a Maya viewport)
#   AE     : <CepRoot>\com.syncbridge.panel   (extracted from the signed ZXP)
#
# -Quiet skips dialogs and Explorer (automated tests). The release build saves this file
# as UTF-8 with BOM so Windows PowerShell 5.1 reads the Japanese messages correctly.
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\SyncBridge'),
    [string]$CepRoot = (Join-Path $env:APPDATA 'Adobe\CEP\extensions'),
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$payload = Split-Path -Parent $MyInvocation.MyCommand.Path
$extensionId = 'com.syncbridge.panel'

function Show-Message([string]$text, [string]$icon = 'Information') {
    if ($Quiet) { Write-Output $text; return }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($text, 'SyncBridge', 'OK', $icon)
}

try {
    $version = (Get-Content (Join-Path $payload 'version.json') -Raw | ConvertFrom-Json).version

    # 1. Stop a running SyncBridge server of an earlier install (its files are replaced).
    Get-Process -Name SyncServer -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallRoot, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force
    Start-Sleep -Milliseconds 500

    # 2. Program files.
    New-Item -ItemType Directory -Force $InstallRoot | Out-Null
    foreach ($part in 'server', 'maya') {
        $target = Join-Path $InstallRoot $part
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        Copy-Item -Recurse (Join-Path $payload $part) $target
    }
    foreach ($file in 'version.json', 'uninstall.ps1', 'Uninstall.bat', 'README_SyncBridge.txt') {
        $source = Join-Path $payload $file
        if (Test-Path $source) { Copy-Item -Force $source (Join-Path $InstallRoot $file) }
    }
    # Files from a downloaded zip carry the "downloaded from the internet" mark; remove it.
    Get-ChildItem -Recurse -File $InstallRoot | Unblock-File

    # 3. After Effects panel (signed ZXP = zip). A development link (junction) is removed as a
    #    link only; its target folder is never deleted.
    New-Item -ItemType Directory -Force $CepRoot | Out-Null
    $extension = Join-Path $CepRoot $extensionId
    if (Test-Path $extension) {
        $item = Get-Item $extension -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { $item.Delete() }
        else { Remove-Item -Recurse -Force $extension }
    }
    $zip = Join-Path $env:TEMP ('syncbridge_panel_' + [Guid]::NewGuid().ToString('N') + '.zip')
    Copy-Item (Join-Path $payload "ae\$extensionId.zxp") $zip
    Expand-Archive -Path $zip -DestinationPath $extension
    Remove-Item $zip
    Get-ChildItem -Recurse -File $extension | Unblock-File

    # 4. Install record (read by the uninstaller).
    @{ version = $version; installed = (Get-Date).ToString('s'); install_root = $InstallRoot;
       extension = $extension } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $InstallRoot 'install.json')

    $running = @()
    if (Get-Process -Name AfterFX -ErrorAction SilentlyContinue) { $running += 'After Effects' }
    if (Get-Process -Name maya -ErrorAction SilentlyContinue) { $running += 'Maya' }
    $restart = ''
    if ($running.Count -gt 0) {
        $restart = "`n`n※ " + ($running -join ' と ') + ' が起動中です。After Effects は再起動するとパネルが使えるようになります。'
    }
    $dragFile = Join-Path $InstallRoot 'maya\drag_to_maya_SyncBridge.py'
    Show-Message ("SyncBridge $version をインストールしました。`n`n" +
        "次の 2 つを行ってください:`n" +
        "1. Maya: このあと開くフォルダの「drag_to_maya_SyncBridge.py」を Maya のビューポートにドラッグ＆ドロップ" +
        "（シェルフに SyncBridge ボタンが追加されます。Maya のバージョンごとに 1 回）`n" +
        "2. After Effects: 「ウィンドウ」→「エクステンション」→「SyncBridge」でパネルを開く" + $restart)
    if (-not $Quiet) { Start-Process explorer.exe "/select,`"$dragFile`"" }
    exit 0
}
catch {
    Show-Message ("SyncBridge のインストールに失敗しました。`n`n" + $_.Exception.Message) 'Error'
    exit 1
}
