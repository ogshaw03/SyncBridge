# SyncBridge

Maya の **Scene Time Warp** と After Effects の **Time Remap** を、ボタン 1 つで双方向に転送するツール。

- **Editable モード:** キーフレームと補間を保ち、転送先でも編集できる
- **Precision モード:** 時間変換の結果を高い精度（既定 0.1 フレーム以内）で一致させる

> 現在の配布は **0.1.6（先行配布）**。Phase 1（Maya ⇔ AE のパネルとローカルサーバーによる手動転送）まで完了。
> 状況は [docs/PROGRESS.md](docs/PROGRESS.md)、配布の記録は [docs/RELEASE.md](docs/RELEASE.md)。

## できること（0.1.5）

| 機能 | 内容 |
|---|---|
| タイムワープの転送 | Maya の Scene Time Warp ⇔ AE のレイヤーのタイムリマップ（両方向、手動）。適用前の確認、バックアップ、取り消し 1 回、読み戻しの検証 |
| タイムワープの保存・復元・範囲変更 | Maya のパネルで、Scene Time Warp を名前を付けて保存、自動バックアップからの復元、形を保ったままの伸縮 |
| 解像度の枠 | AE のコンポの大きさ（または Maya のパネルで入れた大きさ）の枠を、Maya のカメラのビューに表示。レンダーには写らない |
| キーのマーカー | AE のタイムリマップのキーのタイミングを、Maya のタイムスライダーのブックマークとビューの表示に。シーンに保存され、AE がなくても表示される（0.1.6） |
| SyncBridge Monitor | 動作中のサーバー、接続中のアプリ、転送の履歴、ログの確認。サーバーの停止・強制終了、アプリの切断 |
| かんたん導入 | `Install.bat` だけで、サーバー、モニター、AE のパネル、Maya のシェルフの「SyncBridge」タブまで入る（管理者権限不要） |

## 対応環境

- Windows 10 / 11
- Maya 2023 以降（動作確認は Maya 2023、2024、2025）
- After Effects 2024 以降（動作確認は After Effects 2026 / 26.5）

## 使う人向け

1. [Releases](https://github.com/ogshaw03/SyncBridge/releases) から **SyncBridge-&lt;バージョン&gt;.zip** をダウンロードして「すべて展開」
   （「Source code」は開発用のファイルで、インストールには使えない）
2. `Install.bat` をダブルクリック
3. Maya を起動してシェルフの「SyncBridge」タブのボタンを押す。After Effects は「ウィンドウ」→「エクステンション」→「SyncBridge」

使い方、困ったとき、アンインストールの詳しい説明は、zip に入っている `README_SyncBridge.txt`
（元のファイル: [packaging/installer/README_SyncBridge.txt](packaging/installer/README_SyncBridge.txt)）。

## 開発する人向け

新しい PC では、最初にリポジトリの中に `.venv` を作る（PC の Python 本体には入れない、D-11）。

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-server.txt -r requirements-monitor.txt
```

| コマンド | 内容 |
|---|---|
| `.\.venv\Scripts\python -m unittest discover -s tests -t .` | すべてのテスト（サーバー、モニター、インストーラーを含む） |
| `py -3 -m unittest discover -s tests -t .` | 標準ライブラリだけで動くテスト（サーバーとモニターはスキップ） |
| `.\syncbridge.cmd selftest` | CLI（参照カーブの往復テスト） |
| `.\syncbridge-server.cmd` | ローカルサーバー（ハブ）を起動 |
| `.\syncbridge-monitor.cmd` | モニターを起動 |
| `.\.venv\Scripts\python packaging\build_release.py` | 配布用の zip を作る（`requirements-build.txt` と ZXPSignCmd が必要。[docs/RELEASE.md](docs/RELEASE.md)） |

- 開発のルール（Python 3.9 互換、JSX は ES3 で ASCII のみ、未確認の API は仮説 ID を付ける、など）は [CLAUDE.md](CLAUDE.md)。
- 開発用の PC でインストーラーを試すときの切り替えは `tools\dev_env_off.ps1` / `tools\dev_env_on.ps1`（[docs/RELEASE.md](docs/RELEASE.md) の 4 章）。
- Maya の解像度の枠を GUI の Maya で調べるときは `tools/maya_guide_diagnose.py`（ファイルの先頭に使い方）。

## フォルダ構成

| パス | 内容 |
|---|---|
| `src/syncbridge/core/` | 時間変換のコア（純 Python、標準ライブラリのみ。Maya / AE を import しない） |
| `src/syncbridge/server/` | ローカルサーバー（ハブ、FastAPI）。管理 API、転送の履歴、ログ |
| `src/syncbridge/client/` | サーバーへのクライアント（Maya の中でも動く、標準ライブラリのみ） |
| `src/syncbridge/monitor/`, `src/syncbridge/hubs.py` | モニター（PySide6）、ハブの発見と強制終了 |
| `maya_plugin/` | Maya 側（`scripts/syncbridge_maya` のパネルとアダプタ、`plug-ins/` の解像度の枠のプラグイン） |
| `after_effects/` | AE の CEP 拡張機能（[after_effects/README.md](after_effects/README.md)） |
| `packaging/` | 配布物のビルドとインストーラー |
| `tests/` | テスト（Maya / AE は不要） |

## ドキュメント

- [docs/SPEC.md](docs/SPEC.md) — 仕様（時間の用語、変換ルール、安全ルール）
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 構成と設計判断（D-1〜D-20）
- [docs/PLATFORM_DESIGN.md](docs/PLATFORM_DESIGN.md) — ハブ・ランチャー・モニター・アップデーターの設計
- [docs/PHASE0_RESEARCH.md](docs/PHASE0_RESEARCH.md) — API の制約、仮説と検証状態、リスク、検証手順
- [docs/PHASE1_PLAN.md](docs/PHASE1_PLAN.md) — Phase 1（通信基盤）の計画と確認
- [docs/API.md](docs/API.md) — ファイル形式、プロトコル、CLI、関数
- [docs/RELEASE.md](docs/RELEASE.md) — 配布の仕組み、ビルド、リリースの記録（リリースノートは [docs/release_notes/](docs/release_notes/)）
- [docs/PROGRESS.md](docs/PROGRESS.md) — 進捗、テスト結果、未解決の問題、次にやること
- [CLAUDE.md](CLAUDE.md) — Claude Code 向けの開発ルール
