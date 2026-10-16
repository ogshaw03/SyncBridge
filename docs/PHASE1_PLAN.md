# Phase 1 計画: 通信基盤

作成: 2026-10-16 / 状態: **Phase 1 完了**（2026-10-16、Maya 2024 + AE 26.5 で V-P1C 合格、P1-1〜P1-8 を満たす）

| 段階 | 状態 |
|---|---|
| 1-A | ✅ プロトコル、サーバー、セッション、二重起動防止、自動終了、転送の手順、テスト（実機なし）。P1-1、P1-2、P1-8 を満たす |
| 1-B | ✅ 標準ライブラリの WebSocket クライアント、`SyncClient`、サーバーの自動起動、Maya の `service` と最小 UI、AE の代役 `tools/fake_ae.py`。Maya 2024 で V-P1B 合格（7 章）。AE 側は代役なので P1-3〜P1-5 は 1-D で本物の AE と確認する |
| 1-C | ✅ CEP の manifest、パネル（`panel/`）、ExtendScript の窓口（`jsx/syncbridge_cep_host.jsx`）、適用処理の共通化（`SB.applyToLayer`）、日本語の警告。AE 26.5 で V-P1C 合格 |
| 1-D | ✅ V-P1C で確認（Maya と本物の AE で両方向、P1-3〜P1-7）。古い接続が残る問題を修正（同じプロセスの新しい接続が古い接続を置き換える） |

仕様 12 章の Phase 1 は「FastAPI / WebSocket サーバー、Maya Adapter、AE Adapter、接続管理、JSON 送受信、手動転送」。
Phase 0 でファイル経由（CLI）で確認した Maya ⇔ AE の手動転送を、ローカルサーバー経由のボタン操作に置き換えるのが目標。
自動同期（変更検出、リビジョン、競合）は Phase 5 の範囲だが、メッセージ形式はそれに備えておく。

## 1. 完了条件

| # | 条件 |
|---|---|
| P1-1 | サーバーが `127.0.0.1:8765` だけで待ち受け、トークンのない接続を拒否する（テストで確認） |
| P1-2 | 二重起動しない。2 つ目は既存のサーバーを見つけて終了する |
| P1-3 | Maya（2024）と AE（26.5）の両方が接続し、サーバーが両方を一覧できる |
| P1-4 | Maya から「AE へ送る」で、選択中の AE レイヤーに Time Remap が適用される（AE 側で確認・バックアップ・undo・リードバックあり） |
| P1-5 | AE から「Maya へ送る」で、Maya の Scene Time Warp が置き換わる（同上） |
| P1-6 | 転送の結果（誤差レポート、警告、リードバック）が送信元に返り、表示される |
| P1-7 | 片方が未接続・切断・エラーのとき、送信元に分かるエラーが返る（固まらない） |
| P1-8 | Maya / AE なしで、サーバーとプロトコルの単体・結合テストが通る |

## 2. 構成

```
Maya (メインスレッド)                         AE
  syncbridge_maya.service / ui ─WebSocket─┐  after_effects/panel (CEP: HTML/JS, Chromium の WebSocket)
   syncbridge.client.sync_client / ws      │        │ evalScript
   (標準ライブラリだけ、受信は別スレッド →  │     after_effects/jsx/syncbridge_ae_lib.jsxinc（Phase 0 のまま再利用）
    executeDeferred でメインへ)             │
                                          ▼
                     Local Sync Server（別プロセス、src/syncbridge/server）
                       app          : FastAPI、/ws（WebSocket）、/health
                       connections  : 接続中のクライアント（app, pid, 文書名, 能力）
                       transfer     : 転送の手順を実行（相手に export を依頼 → core.transfer で変換 → apply を依頼 → 結果を返す）
                       session      : トークンとポートを %LOCALAPPDATA%/SyncBridge/session.json に書く、二重起動防止
                     syncbridge.core（Phase 0 のまま）
```

### 手動転送の流れ（Maya → AE の例）

1. Maya → サーバー: `transfer.request {direction: "maya2ae", mode, options}`
2. サーバー → Maya: `export.request` → Maya が `maya.timewarp.export`（Phase 0 と同じ内容）を返す
3. サーバー → AE: `export.request` → AE が選択レイヤーの `ae.timeremap.export` を返す（コンプ fps、startTime を得るため）
4. サーバー: `core.transfer.maya_to_ae()` で変換（CLI の maya2ae と同じ処理）
5. サーバー → AE: `apply.request`（`ae.timeremap.apply`）→ AE が確認ダイアログ → バックアップ → 適用 → 読み戻し → `apply.result`
6. サーバー: 読み戻しを検証して、`transfer.result` を Maya に返す

AE → Maya も同じ形で、役割を入れ替える。

## 3. メッセージ

Phase 0 のエンベロープ（`envelope.make()`）をそのまま使い、`kind` を追加する。要求と応答は `reply_to`（要求の `event_id`）で対応づける。

| kind | 向き | 内容 |
|---|---|---|
| `hello` / `welcome` | クライアント → サーバー / 逆 | トークン、app、バージョン、pid、文書名 / 割り当てた client_id |
| `peers` | サーバー → 全員 | 接続中のクライアント一覧（変化のたび） |
| `transfer.request` / `transfer.result` | 送信元 ⇔ サーバー | 方向、モード、許容誤差、範囲 / 誤差レポート、警告、リードバック |
| `export.request` / `export.result` | サーバー ⇔ アプリ | Phase 0 の export と同じデータ |
| `apply.request` / `apply.result` | サーバー ⇔ アプリ | Phase 0 の apply と同じデータ / 適用したか、キャンセルか、リードバック |
| `error` | どちらでも | コード、メッセージ、`reply_to` |

要求にはタイムアウトを設ける（利用者の確認待ちがあるので apply は長め）。

## 4. 実装の順番

| 段階 | 内容 | 実機 |
|---|---|---|
| 1-A | プロトコル（純 Python）、サーバー本体、トークン、二重起動防止、テスト用クライアント | 不要 |
| 1-B | Maya クライアント（標準ライブラリの WebSocket、別スレッド受信 → メインスレッドで実行）、Maya の最小 UI（接続状態、送る／受けるボタン） | Maya |
| 1-C | 最小 CEP パネル（接続状態、送るボタン）、V-AE-3 の確認 | AE（PlayerDebugMode の設定は利用者が行う） |
| 1-D | サーバーでの転送の手順、両方向の手動転送、エラー処理 | Maya + AE |

UI はこの段階では最小限（Phase 6 で作り込む）。

## 5. 決めること・前提

- **D-11（決定）: サーバーは FastAPI + uvicorn**（仕様どおり）。開発用にリポジトリ内の仮想環境 `.venv`（Git 管理外）に入れる。
  配布時は PyInstaller で EXE に含める（Phase 6）。
- **D-12（決定）: Maya のクライアントは標準ライブラリだけで書く。** Maya の Python に外部パッケージを入れずに済むようにするため。
  WebSocket のクライアント側は小さく実装できる（テキストフレーム、ping/pong、close のみ）。
- **AE:** CEP パネルの JavaScript は Chromium 標準の `WebSocket` を使う（ライブラリ不要）。JSX の呼び出しは CEP の `evalScript`。
  未署名の CEP 拡張を開発中に読み込むには PlayerDebugMode のレジストリ設定が必要（**利用者が行う**、手順は 1-C で用意）。
- **未確認の仕様（新しい仮説）:**
  - H-AE-8: CEP パネルから `ws://127.0.0.1:8765` に接続できる（1-C で確認）
  - H-AE-13: AE 26.5 で CEP 拡張がまだ動く（CEP 廃止の時期は要確認）
  - H-AE-14: AE 26.5 の PlayerDebugMode は `HKCU\Software\Adobe\CSXS.<N>` のどれか（N は未確認。11〜13 を設定する）
  - H-AE-15: パネルの JS から `window.__adobe_cep__.evalScript(script, callback)` で ExtendScript を呼べる（CSInterface.js を使わない）
  - H-AE-16: evalScript から呼んだ ExtendScript の `confirm()` が AE のダイアログとして表示される
  - H-AE-17: ExtendScript の `$.getenv("LOCALAPPDATA")` でセッションファイルの場所がわかる
  - H-MY-14: Maya の Python で `socket` / `threading` の別スレッド受信と `executeDeferred` の組み合わせが UI を固めない
    → ✅ Maya 2024（接続中の再生・スクラブに問題なし、利用者の操作で確認）
  - H-MY-15: Maya から起動したサーバー（`.venv` の Python）が、Maya の `PYTHONHOME` / `PYTHONPATH` を外せば正常に動く → ✅ Maya 2024
  - H-MY-16: `executeDeferred` で実行した処理の中で `confirmDialog` を出しても問題ない → ✅ Maya 2024（Apply / Cancel とも）

## 6. 実機での確認手順

### V-P1B: Maya クライアント（Maya 2024、AE は代役）

準備: この PC には `.venv` がある（なければ CLAUDE.md の手順で作る）。Phase 0 の転送テストで使ったシーン（Scene Time Warp あり）を開く。

1. **パネルを開く**（Script Editor、Python）
   ```python
   import sys
   sys.path.insert(0, r"E:/OG_Tools/SyncBridge/maya_plugin/scripts")
   for name in [m for m in list(sys.modules) if m.startswith("syncbridge")]:
       del sys.modules[name]
   import syncbridge_maya.ui as sbui
   sbui.show()
   ```
2. **接続:** パネルの **Connect** を押す。サーバーが自動で起動し、「Server: connected (maya-1)」「After Effects: not connected」と出る（H-MY-15）。
3. **固まらないこと（H-MY-14）:** 接続したまま、タイムラインのスクラブや再生をして、Maya の動作が重くならないことを確認する。
4. **AE の代役を起動**（PowerShell、リポジトリのフォルダ）
   ```powershell
   py -3 tools\fake_ae.py --export probe_results\v2_ae_before.json
   ```
   パネルが「After Effects: connected (fake AE: v2_ae_before.json)」に変わり、2 つのボタンが押せるようになる。
5. **Maya → AE:** パネルの **Maya → AE** を押す。パネルのログに「maya2ae applied conversion 0.0000 f readback 0.0000 f」。
   代役のコンソールに受け取った 3 キーが表示される（読み戻しは代役が計算した **模擬** で、本物の AE ではない）。
6. **AE → Maya（H-MY-16）:** 代役のコンソールで `m` + Enter。Maya に確認ダイアログ → **Apply** → パネルのログに
   「ae2maya applied ... readback 0.0000 f」。Scene Time Warp が 2 キー（1→1、49→49）になる。**Ctrl+Z 1 回で元に戻る** ことを確認する。
7. **エラー（P1-7）:** 確認ダイアログで **Cancel** → ログに「cancelled」。代役を `q` で終了 → 「After Effects: not connected」になり、ボタンが押せなくなる。
8. **切断:** パネルの **Disconnect**。Maya を閉じても、10 分接続がなければサーバーは自動で終了する。
   サーバーのログは `%LOCALAPPDATA%\SyncBridge\server.log`。

### V-P1C: AE パネル（AE 26.5）+ Maya 2024（1-C と 1-D を同時に確認）

**準備 A（利用者が行う、初回のみ）: 未署名の拡張機能を読み込めるようにする**

PlayerDebugMode はレジストリの設定（システム設定の変更）なので、ツールではなく利用者が実行する。
AE 26.5 が使う CSXS のバージョンは未確認（H-AE-14）なので、11〜13 を設定する。不要なキーが増えるだけで害はない。

```powershell
foreach ($n in 11, 12, 13) { reg add "HKCU\Software\Adobe\CSXS.$n" /v PlayerDebugMode /t REG_SZ /d 1 /f }
```

元に戻すときは `/d 0` で同じコマンドを実行するか、値を削除する。

**準備 B（利用者が行う、初回のみ）: 拡張機能フォルダにリポジトリへのリンクを作る**

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\Adobe\CEP\extensions" | Out-Null
New-Item -ItemType Junction -Path "$env:APPDATA\Adobe\CEP\extensions\com.syncbridge.panel" -Target "E:\OG_Tools\SyncBridge\after_effects"
```

ジャンクションなので、リポジトリを更新すればパネルも更新される（AE の再起動かパネルの開き直しが必要）。
削除するときはジャンクションだけを消す: `(Get-Item "$env:APPDATA\Adobe\CEP\extensions\com.syncbridge.panel").Delete()`
（`Remove-Item -Recurse` はリンク先のリポジトリまで消すおそれがあるので使わない）。

**手順**

1. AE を再起動し、「ウィンドウ → エクステンション（または Extensions (Legacy)）→ SyncBridge」でパネルを開く（H-AE-13、H-AE-14）。
   パネルが出ない・真っ白な場合は、その状態を報告する。
2. Maya で V-P1B と同じくパネルを開いて **Connect**（サーバーが起動する）。
3. AE のパネルで **Connect**。「Server: connected (ae-N)」「Maya: connected (...)」になる（H-AE-8、H-AE-15、H-AE-17）。
4. AE で Phase 0 の `SB_test` コンプを開き、`SB_src` レイヤーを選ぶ。パネルに「SB_test / SB_src」と出て、2 つのボタンが押せる。
5. **Maya → AE（Maya のパネルから）:** Maya のパネルの **Maya → AE** → AE に確認ダイアログ（H-AE-16）→ OK →
   AE のパネルに「applied N keys」、Maya のパネルに「maya2ae applied ... readback 0.0000 f」（**本物の AE の読み戻し**）。
   AE で「編集 → 取り消し」1 回で戻ることを確認する。
6. **AE → Maya（AE のパネルから）:** AE のパネルの **AE → Maya** → Maya に確認ダイアログ → Apply →
   AE のパネルに「ae2maya applied ... readback 0.0000 f」、Maya のパネルに「AE → Maya applied ...」。Maya で Ctrl+Z 1 回で戻ることを確認する。
7. **エラー（P1-7）:**
   - AE でレイヤーの選択を外して Maya → AE → Maya のパネルに「Select exactly one layer ...」が返る
   - どちらかの確認ダイアログで Cancel → 両方のパネルに cancelled
   - Maya のパネルで Disconnect → AE のパネルに「Maya disconnected」、ボタンが押せなくなる

## 7. 実機での確認記録

### 2026-10-16 V-P1B — Maya 2024 + AE の代役（`tools/fake_ae.py`、データは `v2_ae_before.json`）

| 項目 | 結果 |
|---|---|
| Connect でサーバーを自動起動して接続（H-MY-15） | ✅ `maya-1` として接続 |
| 接続中の再生・スクラブ（H-MY-14） | ✅ 問題なし |
| Maya → AE | ✅ conversion 0.0000 f。代役が 3 キーを受信（読み戻しは代役の模擬） |
| AE → Maya（代役から要求、H-MY-16） | ✅ 確認ダイアログ → 2 キー適用、バックアップ作成、Maya 自身の読み戻し誤差 0（193 点）、サーバーの読み戻し誤差 0 |
| 取り消し | ✅ `SyncBridge apply time warp` が Undo 1 回で戻る |
| キャンセル | ✅ Maya に「apply cancelled」、代役に `cancelled` |
| 切断 | ✅ 「disconnected by this client」 |

見つかった使い勝手の問題と対応:
- AE 側から送られたとき、パネルのログに適用の結果が出なかった（「server request: apply.request」だけ）
  → `service` が適用後に `applied` イベントを出し、パネルに「applied N keys, readback PASS」「cancelled」「failed」を表示
- AE の接続・切断がログに残らなかった → パネルに「After Effects connected / disconnected」を表示
（この 2 点の修正は Maya では未確認。テストはダミーの maya で確認）

### 2026-10-16 V-P1C 途中経過 — AE 26.5 + Maya 2024

- パネルが AE に読み込まれ、サーバーに接続し、`export.request` に対して AE の中で JSX が実行された
  → PlayerDebugMode の設定が有効（H-AE-14: CSXS.11〜13 のいずれか）、H-AE-8、H-AE-13、H-AE-15、H-AE-17 は動作から確認
- Maya → AE が「Time Remap is not enabled on layer "SB_src"」で失敗した。適用先として書き出すときも Phase 0 の書き出し関数が
  Time Remap の無効なレイヤーを拒否していたため（設計の誤り。適用時には Time Remap を自動で有効にする）
  → パネルからの書き出しは Time Remap が無効でも受け付ける（keys は空）。AE → Maya でキーがない場合は
  「the AE layer ... has no Time Remap to send」と返す。テストを追加（139 件 OK）
- 次: 修正版で手順 5 から再開
- 利用者の要望: レイヤー未選択などの警告を日本語にする（Maya に届いた警告が英語で、Phase 0 用の説明も混ざっていた）
  → JSX の `SB.userError(message, code, params)` にコードを付け、日本語の文はパネルの `sbclient.js`（`MESSAGES`）で組み立てる。
  JSX は ASCII のみの規則を維持（英語の文は Phase 0 のスクリプト用に残す）。サーバーの前置きは `ae-4:` から `After Effects:` に変更。
  パネル上部のレイヤー表示も日本語にした。テスト 140 件 OK。AE 26.5 で日本語の警告が表示されることを利用者が確認
- 手順 5（Maya → AE）・6（AE → Maya）: ✅ 利用者が確認（本物の AE で両方向、確認ダイアログ、取り消し 1 回で復元）
- 手順 7: Maya のパネルで Disconnect した後も、AE から Maya へ送れてしまった。
  サーバーのログでは maya-1・maya-3 が切断されずに残り、AE → Maya は残っていた maya-3 に届いていた。
  原因: 手順のスクリプトは syncbridge のモジュールを捨てて読み込み直すため、古いモジュールの接続が残る。Disconnect は新しい接続だけを切る
  → (1) サーバー: 同じプロセス（pid）・同じアプリから新しい接続が来たら、古い接続に `replaced` を送って閉じる（close 4409）
  → (2) Maya: 接続を `__main__` にも記録し、`service` の読み込み時と Connect 時に前回の接続を切断する
  テストを追加（142 件 OK）。サーバーを再起動して再確認: ✅ Disconnect 後は AE から送れない（利用者が確認）
- **結論: V-P1C 合格。** Maya 2024 と AE 26.5 で、両方向の手動転送、確認ダイアログ、取り消し、日本語の警告、
  未接続・切断時の扱いを確認。1-C と 1-D を完了
- 対象の決め方（利用者の質問への回答として明記）: AE でアクティブなコンポの、選択中の 1 レイヤー（フッテージかプリコン）。
  名前の指定はない（手順書の SB_test / SB_src はテスト用の名前）。対応づけを記憶して選択を不要にする方式は将来の拡張
