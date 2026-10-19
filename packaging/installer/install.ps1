# SyncBridge installer (per user, no administrator rights). Run through Install.bat.
#
#   server : <InstallRoot>\server\SyncServer.exe
#   monitor: <InstallRoot>\app\SyncBridge.exe, Start menu "SyncBridge モニター" (per user)
#   Maya   : <InstallRoot>\maya, and a "SyncBridge" shelf tab for every Maya 2023+ that has
#            been started once: <MayaAppDir>\<version>[\ja_JP]\prefs\shelves\shelf_SyncBridge.mel
#            and prefs\icons\syncbridge_shelf.png (D-17). drag_to_maya_SyncBridge.py stays as
#            the fallback for a Maya that has never been started.
#   AE     : <CepRoot>\com.syncbridge.panel   (extracted from the signed ZXP)
#
# -Quiet skips dialogs and Explorer (automated tests). The release build saves this file
# as UTF-8 with BOM so Windows PowerShell 5.1 reads the Japanese messages correctly.
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\SyncBridge'),
    [string]$CepRoot = (Join-Path $env:APPDATA 'Adobe\CEP\extensions'),
    [string]$ProgramsDir = [Environment]::GetFolderPath('Programs'),
    # Maya's user folder: MAYA_APP_DIR when set, else <Documents>\maya (also when Documents
    # was moved, e.g. to OneDrive).
    [string]$MayaAppDir = $(if ($env:MAYA_APP_DIR) { $env:MAYA_APP_DIR }
                            else { Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'maya' }),
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$payload = Split-Path -Parent $MyInvocation.MyCommand.Path
$extensionId = 'com.syncbridge.panel'
$minimumMaya = 2023

# The shelf file is ASCII only (Maya reads it in the system code page). The scripts folder is
# found from LOCALAPPDATA when the button is pressed, so a non-ASCII user name does no harm.
$shelfTemplate = @'
global proc shelf_SyncBridge () {
    shelfButton
        -enableCommandRepeat 1
        -enable 1
        -width 35
        -height 35
        -manage 1
        -visible 1
        -annotation "SyncBridge: Maya - After Effects"
        -label "SyncBridge"
        -image "syncbridge_shelf.png"
        -image1 "syncbridge_shelf.png"
        -style "iconOnly"
        -docTag "SyncBridge"
        -command "{COMMAND}"
        -sourceType "python"
        -commandRepeatable 1
        -flat 1
    ;
}
'@

function Get-MayaPrefDirs([string]$root) {
    # prefs folders of Maya 2023+ versions started at least once (English and Japanese UI).
    $dirs = @()
    if (-not (Test-Path $root)) { return $dirs }
    foreach ($dir in Get-ChildItem -Directory $root) {
        if ($dir.Name -notmatch '^(\d{4})(-x64)?$' -or [int]$Matches[1] -lt $minimumMaya) { continue }
        foreach ($base in @($dir.FullName, (Join-Path $dir.FullName 'ja_JP'))) {
            $prefs = Join-Path $base 'prefs'
            if (Test-Path $prefs) { $dirs += $prefs }
        }
    }
    return $dirs
}

function Get-ShelfCommand {
    $default = Join-Path $env:LOCALAPPDATA 'Programs\SyncBridge'
    if ($InstallRoot -eq $default) {
        $path = "os.path.join(os.environ['LOCALAPPDATA'], 'Programs', 'SyncBridge', 'maya', 'scripts')"
    } else {
        $path = "r'" + ((Join-Path $InstallRoot 'maya\scripts') -replace '\\', '/') + "'"
    }
    return "import os, sys; p = $path; sys.path.insert(0, p) if p not in sys.path else None; " +
           "import syncbridge_maya.ui; syncbridge_maya.ui.show()"
}

function Show-Message([string]$text, [string]$icon = 'Information') {
    if ($Quiet) { Write-Output $text; return }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($text, 'SyncBridge', 'OK', $icon)
}

try {
    $version = (Get-Content (Join-Path $payload 'version.json') -Raw | ConvertFrom-Json).version

    # 1. Stop a running SyncBridge server and monitor of an earlier install (their files are replaced).
    Get-Process -Name SyncServer, SyncBridge -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallRoot, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force
    Start-Sleep -Milliseconds 500

    # 2. Program files.
    New-Item -ItemType Directory -Force $InstallRoot | Out-Null
    foreach ($part in 'server', 'app', 'maya') {
        $target = Join-Path $InstallRoot $part
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        if (Test-Path (Join-Path $payload $part)) { Copy-Item -Recurse (Join-Path $payload $part) $target }
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

    # 4. Start menu shortcut of the monitor (the user's own Start menu, no administrator rights).
    $shortcut = $null
    $monitorExe = Join-Path $InstallRoot 'app\SyncBridge.exe'
    if (Test-Path $monitorExe) {
        New-Item -ItemType Directory -Force $ProgramsDir | Out-Null
        $shortcut = Join-Path $ProgramsDir 'SyncBridge モニター.lnk'
        $link = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut)
        $link.TargetPath = $monitorExe
        $link.WorkingDirectory = Split-Path -Parent $monitorExe
        $link.Description = 'SyncBridge のサーバー、接続中のアプリ、転送の履歴、ログを確認する'
        $link.Save()
    }

    # 5. Maya shelf tab "SyncBridge" for every Maya 2023+ started at least once (D-17).
    $mayaFiles = @()
    $mayaVersions = @()
    $shelfText = $shelfTemplate.Replace('{COMMAND}', (Get-ShelfCommand))
    $icon = Join-Path $InstallRoot 'maya\icons\syncbridge_shelf.png'
    foreach ($prefs in Get-MayaPrefDirs $MayaAppDir) {
        $shelves = Join-Path $prefs 'shelves'
        $icons = Join-Path $prefs 'icons'
        New-Item -ItemType Directory -Force $shelves, $icons | Out-Null
        $shelfFile = Join-Path $shelves 'shelf_SyncBridge.mel'
        [IO.File]::WriteAllText($shelfFile, $shelfText, [Text.Encoding]::ASCII)
        $mayaFiles += $shelfFile
        if (Test-Path $icon) {
            $iconFile = Join-Path $icons 'syncbridge_shelf.png'
            Copy-Item -Force $icon $iconFile
            $mayaFiles += $iconFile
        }
        $parent = Split-Path -Parent $prefs             # <version> or <version>\ja_JP
        if ((Split-Path -Leaf $parent) -eq 'ja_JP') {
            $mayaVersions += (Split-Path -Leaf (Split-Path -Parent $parent)) + ' 日本語版'
        } else {
            $mayaVersions += Split-Path -Leaf $parent
        }
    }

    # 6. Install record (read by the uninstaller).
    @{ version = $version; installed = (Get-Date).ToString('s'); install_root = $InstallRoot;
       extension = $extension; shortcut = $shortcut; maya_files = [string[]]$mayaFiles } | ConvertTo-Json |
        Set-Content -Encoding UTF8 (Join-Path $InstallRoot 'install.json')

    $running = @()
    if (Get-Process -Name AfterFX -ErrorAction SilentlyContinue) { $running += 'After Effects' }
    if (Get-Process -Name maya -ErrorAction SilentlyContinue) { $running += 'Maya' }
    $restart = ''
    if ($running.Count -gt 0) {
        $restart = "`n`n※ " + ($running -join ' と ') + ' が起動中です。再起動すると使えるようになります。'
    }
    $dragFile = Join-Path $InstallRoot 'maya\drag_to_maya_SyncBridge.py'
    if ($mayaVersions.Count -gt 0) {
        $mayaStep = "1. Maya（" + ($mayaVersions -join '、') + "）: Maya を起動すると、シェルフに「SyncBridge」タブが出ます。" +
            "ボタンを押すとパネルが開きます`n" +
            "   （ほかのバージョンの Maya は、一度起動してからもう一度 Install.bat を実行してください）"
    } else {
        $mayaStep = "1. Maya: Maya 2023 以降の設定フォルダが見つかりませんでした。Maya を一度起動して終了してから、" +
            "もう一度 Install.bat を実行してください。`n" +
            "   または、このあと開くフォルダの「drag_to_maya_SyncBridge.py」を Maya のビューポートにドラッグ＆ドロップしてください"
    }
    Show-Message ("SyncBridge $version をインストールしました。`n`n" +
        $mayaStep + "`n" +
        "2. After Effects: 「ウィンドウ」→「エクステンション」→「SyncBridge」でパネルを開く`n`n" +
        "サーバーの状態や転送の履歴は、スタートメニューの「SyncBridge モニター」で確認できます。" + $restart)
    if (-not $Quiet -and $mayaVersions.Count -eq 0) { Start-Process explorer.exe "/select,`"$dragFile`"" }
    exit 0
}
catch {
    Show-Message ("SyncBridge のインストールに失敗しました。`n`n" + $_.Exception.Message) 'Error'
    exit 1
}
