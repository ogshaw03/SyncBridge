# 配布（リリース）

最終更新: 2026-10-16 / 現在の配布: **0.1.0（先行配布、Phase 1 の機能のみ）**

## 1. 先行配布 0.1.0 の範囲（D-14）

タイムワープ転送（Maya の Scene Time Warp ⇔ AE のタイムリマップ、手動・両方向）だけを、ターミナルを使わない利用者向けに配布する。
仕様の Phase 6（UI の作り込み、自動起動、アップデーター、GitHub Releases）を待たずに、必要な部分だけ先に作った。

含まない: 設定の同期（Phase 2）、自動同期（Phase 5）、アップデーター（更新は新しい zip で上書きインストール）。

## 2. 利用者の手順（README_SyncBridge.txt と同じ）

1. zip を解凍して `Install.bat` をダブルクリック（管理者権限不要）
2. 開いたフォルダの `drag_to_maya_SyncBridge.py` を Maya のビューポートへドラッグ＆ドロップ → シェルフにボタン
3. AE を再起動し「ウィンドウ → エクステンション → SyncBridge」

## 3. インストール先

| もの | 場所 |
|---|---|
| サーバー `SyncServer.exe`（PyInstaller onedir） | `%LOCALAPPDATA%\Programs\SyncBridge\server\` |
| Maya のスクリプト、アイコン、ドラッグ用ファイル | `%LOCALAPPDATA%\Programs\SyncBridge\maya\` |
| AE パネル（署名済み ZXP を展開） | `%APPDATA%\Adobe\CEP\extensions\com.syncbridge.panel\` |
| アンインストーラー、`install.json` | `%LOCALAPPDATA%\Programs\SyncBridge\` |
| セッション、サーバーのログ（利用者のデータ） | `%LOCALAPPDATA%\SyncBridge\` |
| Maya のシェルフボタン | Maya のバージョンごとのシェルフ（ドラッグ時に今のシェルフへ追加。再ドラッグで置き換え） |

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
| 0.1.0 | 2026-10-16 | 先行配布。手動の両方向転送（Editable / Precision）、Maya のシェルフボタン、AE パネル（署名済み）。zip 10.7MB |
