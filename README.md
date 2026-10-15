# SyncBridge

Maya の **Scene Time Warp** と After Effects の **Time Remap** を双方向に転送・同期するツール。

- **Editable モード:** キーフレームと補間を保ち、転送先でも編集できる
- **Precision モード:** 時間変換の結果を高い精度（既定 0.1 フレーム以内）で一致させる

> 現在は **Phase 0（技術検証）**。時間変換コアと CLI は動作確認済み、Maya / AE 側のスクリプトは実機検証待ち。
> 状況は [docs/PROGRESS.md](docs/PROGRESS.md) を参照。

## 対応環境

Maya 2023 以降、After Effects 2024 以降、Windows 10 / 11（他 OS も見据えた構成）

## クイックスタート（DCC なし）

```powershell
py -3 -m unittest discover -s tests -t .
.\syncbridge.cmd selftest
```

## Phase 0 の転送手順（ファイル経由）

1. Maya（Script Editor, Python）
   ```python
   import sys; sys.path.insert(0, r"<repo>/maya_plugin/scripts")
   import syncbridge_maya.exchange as sbx
   sbx.export_timewarp()
   ```
2. PC: `.\syncbridge.cmd maya2ae maya.json -o ae_apply.json --origin 1001 --mode editable`
3. AE: `File > Scripts > Run Script File...` → `after_effects/jsx/syncbridge_ae.jsx` → Apply…

逆方向や検証の詳細は [docs/PHASE0_RESEARCH.md](docs/PHASE0_RESEARCH.md) の 6 章。

## ドキュメント

- [docs/SPEC.md](docs/SPEC.md) — 仕様（時間の用語、変換ルール、安全ルール）
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 構成と設計判断
- [docs/PHASE0_RESEARCH.md](docs/PHASE0_RESEARCH.md) — API 制約、仮説、リスク、検証手順、合格条件
- [docs/API.md](docs/API.md) — ファイル形式、CLI、関数
- [docs/PROGRESS.md](docs/PROGRESS.md) — 進捗
- [CLAUDE.md](CLAUDE.md) — Claude Code 向けの開発ルール
