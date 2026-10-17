# CLAUDE.md — SyncBridge

Maya の Scene Time Warp と After Effects の Time Remap を双方向に転送・同期するツール。
自宅 PC と会社 PC で開発するため、**会話履歴ではなくこのリポジトリのファイルから作業状況を復元する。**

## 作業開始時に読むもの

1. `docs/PROGRESS.md` — 現在のフェーズ、実装済み、未検証、次の作業
2. `docs/PHASE0_RESEARCH.md` — 仮説（H-*）とその検証状態、リスク、検証手順
3. 必要に応じて `docs/SPEC.md`（ルールとデータ形式）、`docs/ARCHITECTURE.md`（構成と設計判断 D-*）、`docs/API.md`

## 構成

| パス | 内容 |
|---|---|
| `src/syncbridge/core/` | Time Mapping Core。純 Python、**標準ライブラリのみ**、Maya/AE を import しない |
| `src/syncbridge/core/jobs.py` | 変換手順（CLI とサーバーで共有、D-13） |
| `src/syncbridge/cli.py` | Phase 0 の変換ハブ（ファイル経由） |
| `src/syncbridge/protocol.py` | Phase 1 のメッセージ（標準ライブラリのみ、Maya からも使う） |
| `src/syncbridge/client/` | サーバーへのクライアント（WebSocket、SyncClient、サーバー起動）。標準ライブラリのみ（Maya 内で動く） |
| `tools/fake_ae.py` | 開発用の AE の代役（AE パネルなしで Maya 側を試す） |
| `src/syncbridge/server/` | Local Sync Server（FastAPI、`.venv` が必要）。`session.py` だけは標準ライブラリのみ |
| `src/syncbridge/hubs.py` | ハブの発見・確認・強制終了、管理 API の呼び出し（標準ライブラリのみ、D-15） |
| `src/syncbridge/monitor/` | モニター（P-B）。`model.py` は Qt なし、`window.py` は PySide6（`requirements-monitor.txt`） |
| `src/syncbridge/updater/` | Phase 6（未実装） |
| `maya_plugin/scripts/syncbridge_maya/` | Maya アダプタ。`maya/` という名前は使わない（D-1） |
| `maya_plugin/plug-ins/` | Maya のプラグイン（Python API 2.0）。`syncbridge_guide.py` = AE の解像度の枠（D-16） |
| `after_effects/` | CEP 拡張機能のルート（`CSXS/manifest.xml`、`panel/`）。`jsx/` は ExtendScript。詳細は `after_effects/README.md` |
| `schemas/` | 交換形式の JSON Schema |
| `tests/unit`, `tests/integration` | DCC 不要のテスト |

## コマンド

```powershell
py -3 -m unittest discover -s tests -t .          # 標準ライブラリだけで動くテスト（サーバーはスキップ）
.\.venv\Scripts\python -m unittest discover -s tests -t .   # サーバーを含む全テスト
.\syncbridge.cmd selftest                          # CLI（参照カーブの往復テスト）
.\syncbridge-server.cmd                            # Local Sync Server を起動
.\syncbridge-monitor.cmd                           # モニターを起動（PySide6 が必要）
.\.venv\Scripts\python packaging\build_release.py  # 配布用 zip を作る（docs/RELEASE.md）
```

- 新しい PC では最初に `.venv` を作る: `py -3.10 -m venv .venv` → `.venv\Scripts\python -m pip install -r requirements-server.txt -r requirements-monitor.txt`
  （PC の Python 本体には入れない、D-11）。
- Qt の画面をスクリーンショットで確認するときは `QT_QPA_PLATFORM=offscreen` と `QT_QPA_FONTDIR=C:/Windows/Fonts`（指定しないと日本語が □ になる）。

- `python` コマンドが Windows ストアの仮のコマンドの PC があるため、`py -3` か `syncbridge.cmd` を使う。pytest は未インストール（unittest で書く）。
- Git Bash から `cmd //c syncbridge.cmd` を呼ぶとカレントフォルダが解決されないことがある。CLI の確認は PowerShell で行う。
- **ファイルの一括編集で、Bash の heredoc や sed に `\n`、` `、`\\` などのエスケープを含めない。**
  この環境ではシェル経由でエスケープが余分に解釈され、生の改行や U+2028 が書き込まれたり `\` が消えたりした（2026-10）。
  Edit ツールを使うか、スクラッチに置いた `.py` ファイル（`chr(92)` など）で編集する。

## コーディング規約

- **Python:** Maya 2023 の Python 3.9 で動くこと。`from __future__ import annotations` を使い、3.10 以降の構文
  （`match`、実行時の `X | Y`）は使わない。core は外部依存なし（numpy も不可）。
- **JSX:** ExtendScript = ES3。`let`/`const`、アロー関数、`forEach`/`map`/`indexOf`、組み込み `JSON` は使わない（`SBJSON` を使う）。
  **ファイルは ASCII のみ**（U+2028 などが正規表現リテラルに入ると構文エラーになる）。テストが Node で構文と ASCII を確認する。
- 変換ロジックは Python に一元化する（D-2）。JSX に Bezier の変換を書かない。
- AE パネル経由の利用者向けメッセージは日本語。JSX はコード付きの `SB.userError` を投げ、日本語の文は
  `after_effects/panel/js/sbclient.js` の `MESSAGES` で作る（after_effects/README.md）。
- 時間は内部ですべて秒、fps は `FrameRate`（有理数）。フレームと秒の変換はアプリとの境界だけで行う。
- コードのコメントと識別子は英語、ドキュメントは日本語。

## 開発ルール（仕様 13 章）

1. Maya/AE に依存する処理と共通ロジックを分ける。変換は単体テストできる純粋関数にする。
2. 元データを確認なしで壊さない: 適用前に確認、JSON バックアップ、1 回で undo できること、リードバック検証（SPEC 5 章）。
3. フレーム番号と時間を混同しない。
4. 転送前後の時間変換の結果を比較できるようにする（`ErrorReport`）。
5. **API の存在を推測して実装しない。未確認の仕様を動作確認済みとして扱わない。**
   実機で確認していない API・挙動は仮説 ID（H-MY-*, H-AE-*）を付けて `PHASE0_RESEARCH.md` に載せ、コードのコメントでも ID を参照する。
   状態の表記: ✅ 検証済 / 📘 文書 / ❓ 仮説。
6. 実装後はテストを実行し、結果を `PROGRESS.md` に記録する。既存のテストを壊さない。
7. 設計を変えたら `ARCHITECTURE.md` の「設計判断」に理由とともに追記する。
8. リアルタイム同期の応答性と、時間変換の精度は別々に評価する。
9. 将来の機能を見据えつつ、初期実装を複雑にしすぎない。

## 禁止事項

- PC 固有のパス、API キー、認証情報、作業シーン（`.mb`, `.aep`）、大きなキャッシュをコミットしない（`.gitignore` 参照）。
  プローブの結果は `probe_results/`（Git 管理外）に置く。
- 更新用の認証情報を EXE に埋め込まない。
- 利用者のシステム設定（レジストリなど）を Claude が変更しない。手順を書いて利用者に任せる。
- 競合時に自動で上書きしない。

## 作業終了時

`docs/PROGRESS.md` を更新する（実装したこと、テスト結果、未解決の問題、次にやること）。
