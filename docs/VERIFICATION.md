# 検証の方法（Claude が実機で確かめるとき）

Claude が利用者の PC の Maya・AE・Qt を使って変更を確かめる方法と注意をまとめる。どのセッションでもこの手順で行う。
開発ルール 5（未確認の仕様を確認済みとして扱わない）と 6（結果を `PROGRESS.md` に記録）は、ここでも同じ。

| 確かめたいもの | 方法 | 章 |
|---|---|---|
| 変換・計算（core） | unittest | 1 |
| Maya の中の処理・数値・レンダー | mayapy（画面なし） | 2 |
| ビューポートの描画、ウィンドウ、操作の流れ | Maya の GUI を自動で操作して撮る | 3 |
| 画面の見た目（変更前の相談） | Qt / ブラウザのモック | 4 |
| Maya と AE の通信 | AE の代役（`tools/fake_ae.py`） | 5 |
| AE 本体の挙動 | 今は利用者に依頼（自動化は 6 章の案、未検証） | 6 |

## 0. 守ること

- **利用者の Maya を止めない・触らない。** 起動中の Maya（プロセス）を終了しない。確認用の Maya は別のプロセスとして起動し、
  スクリプトの最後に自分で `cmds.quit(force=True)` する。
- **利用者の設定を変えない。** GUI でも mayapy でも、環境変数 `MAYA_APP_DIR` をスクラッチのフォルダ（例: `maya_app_dir2023`、
  `maya_app_dir2024`）に向ける。利用者の設定・シェルフ・ウィンドウの位置はそのまま。
- **作業シーンを使わない。** シーンは確認スクリプトが `cmds.file(new=True, force=True)` から作る。`.mb` / `.aep` をコミットしない。
- 結果の画像やログはスクラッチに置く（リポジトリに入れない）。見せたい画像は SendUserFile で利用者に送る。
- GUI の確認中は Maya のウィンドウが画面の前面に出る（`WindowStaysOnTopHint`）。利用者が作業中なら、先に一言断る。

## 1. 単体テスト

```powershell
py -3 -m unittest discover -s tests -t .                       # 標準ライブラリだけ（サーバー・Qt はスキップ）
.\.venv\Scripts\python -m unittest discover -s tests -t .      # サーバー・Qt（offscreen）を含む全部
```

- Qt の部品（`layer_stack_view.py` など Maya を import しないもの）は、`.venv` の PySide6 と `QT_QPA_PLATFORM=offscreen` で
  テストできる（`tests/integration/test_layer_stack_view.py`）。
- JSX は Node で構文と ASCII だけかを確かめる（`tests/integration/test_cli_and_jsx.py`）。
- 結果は件数だけ見るとき: `... 2>&1 | Select-String -Pattern "^Ran |^OK|^FAILED"`

## 2. mayapy（画面なしの Maya）

`tools/maya_*_check.py` と `tools/pixel_mapping/maya_*_check.py` が例。形はどれも同じ:

1. `maya.standalone.initialize()`、`sys.path` に `src` と `maya_plugin/scripts` を足す
2. シーンを一から作り、SyncBridge の処理を呼ぶ
3. Maya が評価した値（`getAttr`、`getAttr -time`）やレンダーを、core の計算や期待値と比べる
4. 項目ごとに `OK` / `NG`、最後に `RESULT PASS` / `RESULT FAIL` を出す

```powershell
$s = '<スクラッチ>'
$env:MAYA_APP_DIR = "$s\maya_app_dir2024"
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' tools\maya_viewer_steady_check.py "$s\out"
```

- Maya 2023 と 2024 の両方で流す（Python 3.9 と 3.10）。
- 単精度の属性（Film Translate など）は 4e-8 ほどの誤差が出る。許容は 1e-6 程度にする。
- レンダーの比較は Hardware 2.0（`tools/pixel_mapping/maya_render_check.py`、`src/syncbridge/pixelcheck/` で PNG を読む）。
- mayapy では Viewport 2.0 がないので、**レンダーオーバーライド（ビューアー）と HUD は確かめられない** → 3 章。
- mayapy で `QMessageBox` を出すと落ちる。Qt を使うなら `QApplication` を `maya.standalone.initialize` より先に作る。

## 3. Maya の GUI を自動で操作して撮る

ビューアーの描画、ボタンを押したときの流れ、undo などは、GUI の Maya で確かめる。

### 手順

1. `tools/maya_gui_check_template.py` をスクラッチに写し、SETUP（シーンの作り方）と STEPS（1 手ずつの操作と撮影）を書く。
   - 1 手 = 1 つの関数（ボタンを押す、フレームを変える、`grab("名前")`、`log(...)`）。間は 1.5 秒（Maya が描き、Qt が動く）。
   - ボタンは利用者と同じ経路で押す（例: `tree.itemWidget(item, SOLO).click()`）。内部の関数を直接呼ぶと、配線の誤りを見逃す。
   - 判定に使う値（状態、ステータスの文、プラグインに渡したデータ）は `log` に書く。
2. スクリプトを読む `.mel` を ASCII で作り、Maya を起動して終わるまで待つ:

```powershell
$s = '<スクラッチ>'; $out = "$s\gui_xxx2024"
New-Item -ItemType Directory -Force $out | Out-Null
$py = ($s -replace '\\','/') + '/gui_xxx_check.py'
Set-Content -Encoding ascii "$s\gui_xxx.mel" ("python(""exec(open(r'" + $py + "', encoding='utf-8').read())"");")
$env:MAYA_APP_DIR = "$s\maya_app_dir2024"; $env:SB_GUI_OUT = $out; $env:SB_REPO = 'E:\OG_Tools\SyncBridge'
$p = Start-Process -FilePath 'C:\Program Files\Autodesk\Maya2024\bin\maya.exe' -ArgumentList '-script', "$s\gui_xxx.mel" -PassThru
$p.WaitForExit(300000) | Out-Null
Get-Content "$out\log.txt" -Encoding utf8
Select-String -Path "$out\script_editor.txt" -Pattern "SyncBridge"      # プラグインの警告など
```

3. 撮った PNG を Read で見る。細かいところは `.venv` の PySide6 で切り出して拡大する:

```powershell
.\.venv\Scripts\python -c "from PySide6 import QtGui, QtWidgets; import sys; app=QtWidgets.QApplication([]); im=QtGui.QImage(sys.argv[1]); im.copy(1100,80,160,120).scaled(640,480).save(sys.argv[2])" in.png zoom.png
```

4. 2023 と 2024 の両方で撮る（出力のフォルダを分ける）。

### よくあるつまずき

- **答え合わせになる物をシーンに置く。** 例（D-49）: 素材カメラの枠にぴったり合う板ポリを置き、描いた範囲の線が板ポリの縁に
  重なるかを見る。Maya が実際に描いたものと、SyncBridge の計算を比べられる。
- **ログは UTF-8。** PowerShell の `Get-Content` に `-Encoding utf8` を付けないと文字化けする。
- **`script_editor.txt` も必ず見る。** プラグインの描画の例外は `displayWarning` だけで、画面は前の状態のまま残ることがある
  （D-49: `None not in (MDagPath, ...)` が例外になり、単独表示の描き直しごと止まっていた）。
- スクラッチの出力フォルダの中身は消せないことがある（保護される）。撮り直しは新しいフォルダに出す。
- HUD（`MUIDrawManager.text2d`）の文字は ASCII にしておく。`kDashed` の線は細かい点になって見えにくい。
- `maya_plugin/plug-ins` のプラグインは、新しい Maya のプロセスで読み込まれるので、毎回最新になる。
- **描画エンジンでも試す。** 新しい設定の Maya は OpenGL。ビューの表示やクリックの確認は `MAYA_VP2_DEVICE_OVERRIDE=VirtualDeviceDx11` でも行う
  （H-MY-48: DirectX 11 だけで起きる問題を、OpenGL の確認では見つけられなかった）。
- **「Untrusted Plugin Loading - Security Warning」で止まる。** 新しい `MAYA_APP_DIR` で `syncbridge_layer_stack.py` を読むと出る。
  QTimer で `QApplication.activeModalWidget()` を見て `accept()` すると進む。**確認用の Maya（別の `MAYA_APP_DIR`）で、このリポジトリのプラグインに限る。**
- **利用者の設定で起きる問題は、設定のコピーで調べる。** `Documents\maya\<版>\prefs` だけをスクラッチの `MAYA_APP_DIR\<版>\prefs` へコピーする。
  `Documents\maya\scripts`（`userSetup.py` や他のツール）は持ち込まない。
- **利用者の Maya で調べるときは `tools/viewer_click_probe.py`。** ビューアーで 6 回クリックすると、状態とクリックの行き先を
  `probe_results/viewer_click_probe.txt` に書く。シーンは変更しない。
- **実際のマウスで試す。** `QCursor.setPos` と `user32.mouse_event` で動かす。`WindowFromPoint` の窓が自分のプロセスのものか確かめてからクリックする。

## 4. 画面のモック（見た目を変える前に利用者に見せる）

CLAUDE.md の決まり: UI の見た目を変えるときは、モックを撮って利用者に見せてから進める。

- **Maya のウィンドウ・ダイアログ:** `.venv` の PySide6 で、Maya のパネルに近い暗い配色の `QPalette` と `Yu Gothic UI` を使って
  組み、`widget.grab().save(...)`。Maya を import しない部品（`layer_stack_view.py` など）はそのまま使える。
  環境変数は `QT_QPA_PLATFORM=offscreen` と `QT_QPA_FONTDIR=C:/Windows/Fonts`（ないと日本語が □ になる）。
- **Maya の実物に近い見た目が要るとき:** mayapy で（`QApplication` を先に作る）。ダイアログは落ちるので `.venv` で。
- **AE のパネル:** `.claude/launch.json` の `ae-panel-mock`（ポート 8790、`after_effects/` を配る）をブラウザのプレビューで開き、
  幅 320 にして撮る。
- **モニター:** `.venv` の PySide6 で。

## 5. AE の代役

- `tools/fake_ae.py`: AE のふりをしてハブに接続する（`--export` に AE の書き出しファイルを渡す）。Maya 側の通信と適用を、
  AE なしで確かめられる。AE には何もしない。
- サーバーと CEP の通信は Node のテスト（`tests/integration/cep_driver.js`）でも確かめている。
- **代役で確かめたことは、AE 本体での確認ではない。** AE の挙動の仮説（H-AE-*）は ❓ のまま残す。

## 6. AE 本体（今は利用者に依頼。自動化は未検証の案）

今は、AE のパネル・JSX の変更は利用者に試してもらい、結果を受けて `PHASE0_RESEARCH.md` の H-AE-* を更新している。
自動で確かめる方法として、次の案がある。**どれもこのプロジェクトではまだ試していない**（試したらここと PHASE0_RESEARCH.md に記録する）。

| 案 | 内容 | できそうなこと |
|---|---|---|
| `AfterFX.exe -r <file.jsx>` | Adobe のスクリプトガイドにある起動の仕方。起動中の AE があればそこで JSX を実行するはず | テスト用のプロジェクトを作り、`SBCep.*` を呼んで結果をファイルに書く |
| CEP のリモートデバッグ | 拡張機能のフォルダに `.debug` を置くと、パネルが Chrome の開発者ツールのポートを開く | 本物の AE の中でパネルのボタンを押し、ログを読む |
| `aerender.exe` | コマンドラインのレンダー | レンダー結果の比較（P0-6） |

試した記録:
- **2026-11-11、CEP のリモートデバッグ（`tools/ae_hot_reload_check.py`、D-56）:** 開発用のリンクを一時的に本物のフォルダ（`.debug` 入り）に
  置き換え、AE 2027 を起動したが、4 分たってもパネル（CEPHtmlEngine）が立ち上がらず、ポート 8099 に届かなかった。
  その前に、確認のために起動した AE をプロセスごと終了しており、次の起動で復旧のダイアログが出て止まっていた可能性がある（画面を見る許可がなく未確認）。
  道具はリンクを必ず元に戻す。**次に試すときは、AE の画面を見られる状態で（または利用者に起動時のダイアログを閉じてもらって）行う。**
- この PC の AE は 2027 だけ（`Adobe After Effects 2026` のフォルダに実行ファイルがない）。
- リポジトリの `after_effects` フォルダは、AE がいなくても名前を変えられない（別のプロセスが掴んでいる）。フォルダを掴んでいるかの調べ方には使えない。

注意（AE は Maya と違う）:
- 起動中の AE は 1 つで、`-r` はそこで実行される。**利用者の作業中のプロジェクトに当たりうる**ので、AE を閉じているとき、
  または新しいプロジェクトでだけ行う。利用者に確かめてから。
- 設定フォルダを分けて別の AE を起動する方法は分かっていない。
- `.debug` は開発用の状態（`tools/dev_env_on.ps1`）だけに置き、配布物に入れない。

## 7. 記録

- 結果は `PROGRESS.md` の「テスト結果」に書く: 何で確かめたか（テスト件数、mayapy 2023 / 2024、GUI 2023 / 2024）、途中で見つけて直したこと、
  **未確認のもの**（AE 本体、利用者の作業シーンなど）。
- 実機で確かめた API・挙動は `PHASE0_RESEARCH.md` の仮説の状態を更新する（✅ / 📘 / ❓）。
- 確認用のスクリプトで残す価値のあるもの（mayapy の自動判定）は `tools/` に置き、GUI の一回きりのものはスクラッチに置く。
