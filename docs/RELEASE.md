# 配布（リリース）

最終更新: 2026-10-26 / 現在の配布: **0.1.9（先行配布。Phase 1〜3 の一部: タイムワープ、シーン設定と時間の同期、Pixel Mapping・レイヤーマップ・ビューアー）**

## 1. 先行配布 0.1.0 の範囲（D-14）

タイムワープ転送（Maya の Scene Time Warp ⇔ AE のタイムリマップ、手動・両方向）だけを、ターミナルを使わない利用者向けに配布する。
仕様の Phase 6（UI の作り込み、自動起動、アップデーター、GitHub Releases）を待たずに、必要な部分だけ先に作った。

含まない: 設定の同期（Phase 2）、自動同期（Phase 5）、アップデーター（更新は新しい zip で上書きインストール）。

## 2. 利用者の手順（README_SyncBridge.txt と同じ）

1. zip を解凍して `Install.bat` をダブルクリック（管理者権限不要）
2. Maya を起動 → シェルフの「SyncBridge」タブ（0.1.5 から。インストーラーが置く。予備として
   `drag_to_maya_SyncBridge.py` のドラッグ＆ドロップも使える）
3. AE を再起動し「ウィンドウ → エクステンション → SyncBridge」

## 3. インストール先

| もの | 場所 |
|---|---|
| サーバー `SyncServer.exe`（PyInstaller onedir） | `%LOCALAPPDATA%\Programs\SyncBridge\server\` |
| モニター `SyncBridge.exe`（PySide6、PyInstaller onedir、0.1.3 から） | `%LOCALAPPDATA%\Programs\SyncBridge\app\`。スタートメニュー（利用者ごと）に「SyncBridge Monitor」（0.1.5 までは「SyncBridge モニター」。0.1.6 のインストーラーが古い名前の項目を消す） |
| Maya のスクリプト、アイコン、ドラッグ用ファイル | `%LOCALAPPDATA%\Programs\SyncBridge\maya\` |
| AE パネル（署名済み ZXP を展開） | `%APPDATA%\Adobe\CEP\extensions\com.syncbridge.panel\` |
| アンインストーラー、`install.json` | `%LOCALAPPDATA%\Programs\SyncBridge\` |
| セッション、サーバーのログ（利用者のデータ） | `%LOCALAPPDATA%\SyncBridge\` |
| Maya のシェルフ（0.1.5 から） | `<MAYA_APP_DIR またはドキュメント\maya>\<バージョン>[\ja_JP]\prefs\shelves\shelf_SyncBridge.mel` と `prefs\icons\syncbridge_shelf.png`（Maya 2023 以降で一度起動したバージョンすべて。D-17） |
| Maya のシェルフボタン（予備） | ドラッグ＆ドロップしたときの今のシェルフ（再ドラッグで置き換え） |

- サーバーは Maya の Connect で `launcher` が起動する。探す順: 環境変数 `SYNCBRIDGE_SERVER_EXE` → インストール先 → 開発用 `.venv`。
- インストーラーは古いサーバーを止めてから上書きする。ダウンロードの印（Zone.Identifier）を外す。
- AE の拡張機能フォルダに開発用のジャンクションがあれば、**リンクだけ**を消して置き換える（リンク先は消さない。テストで確認済み）。
- アンインストールはプログラムと AE パネルを消し、バックアップとログは残す。Maya のシェルフボタンは利用者が右クリック → 削除。

## 4. ビルド（開発者）

```powershell
.\.venv\Scripts\python -m pip install -r requirements-build.txt     # 初回のみ（PyInstaller）
# 初回のみ: ZXPSignCmd 4.1.3 x64 を packaging\tools\ZXPSignCmd.exe に置く（requirements-build.txt の URL）
.\.venv\Scripts\python packaging\build_release.py                   # テスト → ビルド → 署名 → zip
```

出力: `dist\SyncBridge-<version>\` と `dist\SyncBridge-<version>.zip`（どちらも Git 管理外）。
バージョンは `version.json`、`src/syncbridge/__init__.py`、`pyproject.toml`、`after_effects/CSXS/manifest.xml` の 4 か所を揃える。

### 署名用の証明書

- 初回のビルドで自己署名証明書（10 年）とパスワードを `packaging\local\` に作る。**Git 管理外。消さずに保管する**
  （別の PC でビルドするときはこの 2 ファイルを安全な方法でコピーする。ログにはパスワードを出さない）。
- 署名にはタイムスタンプ（digicert）を付ける。オフラインならタイムスタンプなしで署名する。
- 2024 年 11 月の Adobe の既知の問題（KnownIssue2024: 拡張機能内のシンボリックリンクと UPIA）を避けるため、
  リンクを含めない（ビルドで確認）・Windows で署名・UPIA ではなく自前で展開してインストールする。

### 開発用の状態（zip を作らずにリポジトリのまま試す）

インストールし直さずに、リポジトリのコードをそのまま Maya と AE で使う。準備は PC ごとに 1 回だけ。

1. リポジトリを置き、`.venv` を作る（CLAUDE.md の「新しい PC では」。サーバーとモニターはここから動く）。
2. インストール版が入っていれば、`%LOCALAPPDATA%\Programs\SyncBridge\Uninstall.bat` で外す
   （AE のパネルの置き場が同じ名前のため）。
3. AE: Maya と AE を終了して、開発者が自分で実行する（レジストリの PlayerDebugMode を変えるため）。
   AE のパネルの置き場がリポジトリの `after_effects` へのリンクになる。
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev_env_on.ps1
   ```
4. Maya: `tools\dev_maya_shelf.py` をビューポートへドラッグする。今のシェルフに「SB Dev」ボタンができる。

その後の使い方:

- **Maya:** 「SB Dev」を押すたびに、リポジトリの最新のコードを読み直してパネルを開き直す（Maya の再起動は不要）。
  例外は `maya_plugin/plug-ins` のプラグイン（解像度の枠など）で、これを変えたときは Maya を開き直す。
- **AE:** パネルの HTML / JS を変えたら、パネルを閉じて開き直す（ウィンドウ > エクステンション）。
  `jsx` を変えたときは AE を開き直すのが確実。
- **サーバー（ハブ）:** リポジトリから動かすときは、インストール版があっても `.venv` のサーバーを起動する（`client/launcher.py`）。
  すでに動いているハブはそのまま使われるので、サーバー側のコードを変えたら、モニターでハブを止めてから Connect し直す。

### 開発用 PC でインストーラーを試すとき

開発中の設定（AE パネルの開発用リンク、PlayerDebugMode、開発用サーバー）が残っていると、インストール版を正しく確認できない。
切り替えはスクリプトで行う（レジストリを変えるので開発者が自分で実行する。Maya と AE は終了しておく）。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev_env_off.ps1   # 未インストールの利用者と同じ状態へ
# ... dist の zip を解凍して Install.bat → 確認 → %LOCALAPPDATA%\Programs\SyncBridge\Uninstall.bat ...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev_env_on.ps1    # 開発用の状態へ戻す
```

Python と `.venv` はこの PC から消せないので、Python のない PC での動作（H-PKG-2）は別の PC で確認する。
この PC ではタスクマネージャーに `SyncServer.exe` が出ていれば、インストール版のサーバーが動いている。

## 5. 未確認（実機で確認する）

| ID | 内容 | 確認方法 |
|---|---|---|
| H-MY-17 | Maya 2023/2024/2025 で、ビューポートにドロップした `.py` の `onMayaDroppedPythonFile` が呼ばれる | ドラッグしてシェルフにボタンが出るか（出ない場合は `.mel` を使う） |
| H-AE-18 | 自己署名した ZXP を展開したパネルが、PlayerDebugMode なしで AE 26.5 に読み込まれる | PlayerDebugMode を 0 に戻した PC（または未設定の PC）でパネルが開くか |
| H-PKG-1 | PyInstaller で作った `SyncServer.exe` が、ウイルス対策ソフトや SmartScreen に止められない | 利用者の PC で Connect できるか |
| H-PKG-2 | Python の入っていない PC で動く | 別の PC でインストールして転送する |

## 6. リリースの記録

| バージョン | 日付 | 内容 |
|---|---|---|
| 0.1.0 | 2026-10-16 | 先行配布。手動の両方向転送（Editable / Precision）、Maya のシェルフボタン、AE パネル（署名済み）。zip 10.7MB。GitHub Releases（pre-release）、タグ v0.1.0 = a7df2ac |
| 0.1.1 | 2026-10-16 | 素材の長さの事前確認（R-16）、タイムワープの保存・復元・範囲変更、Maya の日本語化。zip 10.7MB、SHA-256 60f1eeed…。タグ v0.1.1 = 7a092e9（0.1.0 と同じ署名用証明書） |
| 0.1.2 | 2026-10-16 | ハブの管理 API（モニター用、P-A）、ハブのログファイル、停止・切断の通知（P-B）。転送の機能は 0.1.1 と同じ。zip 10.7MB、SHA-256 b9f26450…。ビルドした SyncServer.exe で発見・管理 API・停止・ログファイルを確認。タグ v0.1.2 |
| 0.1.3 | 2026-10-16 | SyncBridge モニター（`SyncBridge.exe`、スタートメニュー）。zip 45.1MB（PySide6 を含むため）、SHA-256 1097c9a7…。一時フォルダへのインストール・モニターの起動（ハブの `/admin/events` に接続）・アンインストール（ショートカットも削除）を確認。タグ v0.1.3 |
| 0.1.4 | 2026-10-17 | AE の解像度の枠を Maya のビューに表示（AE から送る、Maya のパネルで大きさを入力）、Maya のプラグイン `syncbridge_guide.py` を追加（D-16）。zip 45.2MB、SHA-256 3e1390ff…。利用者の PC（Maya 2023 + AE 26.5）でインストール版を確認。タグ v0.1.4 |
| 0.1.5 | 2026-10-19 | Install.bat が Maya の専用タブ「SyncBridge」を置く（ドラッグ＆ドロップ不要、D-17）、アンインストールで削除。zip 45.2MB、SHA-256 c57b5130…。利用者の PC（Maya 2023）でインストール版を確認。タグ v0.1.5 |
| 0.1.6 | 2026-10-20 | AE のタイムリマップのキーを Maya のマーカーに（D-18）、ポート 8765 が使われていても空きポートで接続（D-19）、Maya の確認ダイアログがパネルの裏に隠れる問題の修正、新しいアイコン（シェルフ、パネル、Monitor、EXE、スタートメニュー）、SyncBridge Monitor（名前を英語に）のダークテーマ、停止済みのハブの記録の自動の片付け。zip 45.7MB、SHA-256 3a4d3c20…。テスト 252 件と mayapy 2023 / 2024 で確認。**GUI の Maya / AE での確認の一部（マーカーの表示、確認ダイアログ、スタートメニューとタスクバーのアイコン）は未確認のまま、利用者の判断でリリース**。タグ v0.1.6 |
| 0.1.7 | 2026-10-20 | 解像度の枠とキーのマーカーを、ビューの「表示」メニューの専用の項目で出し入れ（ロケーターを隠しても消えない、D-20）。2 つのノードをプラグインのシェイプに変更。zip 45.7MB、SHA-256 153f9d68…。テスト 252 件と mayapy 2023 / 2024 で確認、同じ方法のテスト用プラグインを利用者の Maya 2025 の GUI で確認。**本番のプラグインの GUI での確認は未実施** |
| 0.1.8 | 2026-10-25 | シーン設定の転送とタイムスライダーの同期（D-21, D-22）、Pixel Mapping（AE のレイヤーの動きを Maya の専用カメラへ、D-23〜D-30）、レイヤーマップ、SyncBridge ビューアー（D-32〜D-35）、ヌル・プリコンポの PAN、余白、Origin frame の統一、素材カメラモード（D-36〜D-39）。Maya のプラグイン `syncbridge_layer_stack.py` を追加。zip 45.8MB、SHA-256 5f50720f…。テスト 370 件、mayapy 2023 / 2024、利用者の PC でレイヤーマップ・転送・ビューアー・素材カメラモードを開発用の状態で確認。**インストール版での確認、ヌル・プリコンポの PAN と余白の GUI での確認は未実施** |
| 0.1.9 | 2026-10-26 | レイヤーマップに出す AE のレイヤーを AE の選択で決める・メインのコンポを記録してプリコンポの中のレイヤーを経路ごと扱う（D-40）、ビューアーで一番上のレイヤーを非表示にしても枠が消えない修正。zip 45.8MB、SHA-256 da410562…。テスト 379 件、利用者の PC でAE の選択での追加と PAN 込みの転送を開発用の状態で確認。**インストール版での確認は未実施** |

### 0.1.0 の利用者テストで見つかった問題（次の版で修正）

- インストール版の AE パネルは PlayerDebugMode なしで読み込まれ、Maya と接続できた（H-AE-18 は動作から確認）。
- Maya → AE で、素材より長い時間が必要なタイムワープを送ると、AE の `setValueAtTime` が「値 7.26 は 0 から 2 の範囲外」で失敗した
  （R-16）。書き込みの途中で止まるので、レイヤーが一部だけ変わり得る（取り消し 1 回で戻る）。
  → 送る前にサーバーと AE の両方で素材の長さを確認し、日本語で理由を出すよう修正（未リリース）。
- Scene Time Warp の値の範囲は作成時に決まり、範囲を変えるには作り直しが必要（H-MY-18）。作り直すと調整したワープが消える
  → 利用者の要望で、Maya のパネルに **保存・復元・範囲変更** を追加（未リリース。復元は自動バックアップからも可能、
  範囲変更は時間方向の伸縮で形と値を保つ）。Maya の確認ダイアログとエラーを日本語に。
