# Phase 1 計画: 通信基盤

作成: 2026-10-16 / 状態: **1-A 完了**（2026-10-16）、1-B（Maya クライアント）から未着手

| 段階 | 状態 |
|---|---|
| 1-A | ✅ プロトコル、サーバー、セッション、二重起動防止、自動終了、転送の手順、テスト（実機なし）。P1-1、P1-2、P1-8 を満たす |
| 1-B〜1-D | 未着手 |

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
  syncbridge_maya.client  ──WebSocket──┐     after_effects/cep (HTML/JS, Chromium の WebSocket)
   (標準ライブラリだけの WS クライアント、    │        │ evalScript
    受信は executeDeferred でメインへ)      │     after_effects/jsx/syncbridge_ae_lib.jsxinc（Phase 0 のまま再利用）
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
  - H-MY-14: Maya の Python で `socket` / `threading` の別スレッド受信と `executeDeferred` の組み合わせが UI を固めない（1-B で確認）
