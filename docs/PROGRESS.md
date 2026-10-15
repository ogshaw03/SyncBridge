# 進捗

## 現在の状態

- **フェーズ:** Phase 0（技術検証）— DCC 不要の部分は完了、**Maya / AE の実機検証が未実施**
- **最終更新:** 2026-10-15

## 実装済み

| 機能 | 場所 | 状態 |
|---|---|---|
| 有理数 fps、Maya 時間単位、フレーム ⇔ 秒 | `core/timebase.py` | ✅ テスト済 |
| 中立カーブ（LINEAR/BEZIER/HOLD、外挿、アフィン変換、JSON） | `core/curve.py` | ✅ テスト済 |
| AE Time Remap 形式 ⇔ 中立カーブ | `core/ae_codec.py` | ✅ テスト済（式自体は ❓H-AE-3） |
| Maya animCurveTT 形式 ⇔ 中立カーブ | `core/maya_codec.py` | ✅ テスト済（式自体は ❓H-MY-4/5/7） |
| Maya ⇔ AE の時間軸の対応 | `core/mapping.py` | ✅ テスト済 |
| Precision モード（適応的な区分線形、サブフレームでの検証） | `core/sampler.py` | ✅ テスト済 |
| 誤差計測とレポート | `core/validation.py` | ✅ テスト済 |
| 変換パイプライン（Editable/Precision、両方向、3 種類の誤差レポート） | `core/transfer.py` | ✅ テスト済 |
| 交換エンベロープ、JSON Schema | `core/envelope.py`, `schemas/` | ✅ テスト済 |
| CLI（maya2ae, ae2maya, readback, probe-vectors, verify-ae-probe, selftest） | `cli.py` | ✅ テスト済 |
| Maya アダプタ（検索、読み書き、export/apply、バックアップ、リードバック） | `maya_plugin/.../` | ⚠ 未実行（ダミーの maya モジュールで import のみ確認） |
| Maya プローブ | `maya_plugin/.../probe.py` | ⚠ 未実行 |
| AE スクリプト（Export/Apply、バックアップ、undo） | `after_effects/jsx/syncbridge_ae.jsx` | ⚠ 未実行（Node で構文のみ確認） |
| AE プローブ | `after_effects/jsx/probe_ae.jsx` | ⚠ 未実行（Node で構文のみ確認） |
| ES3 用 JSON | `after_effects/jsx/syncbridge_json.jsxinc` | ✅ Node で Python の json と往復確認 |
| CI（Windows/Ubuntu × Python 3.9/3.11） | `.github/workflows/tests.yml` | ⚠ 未実行（push 後に確認） |

## テスト結果

### 2026-10-15（Windows 11, Python 3.10.6, Node v24.16.0）

- `py -3.10 -m unittest discover -s tests -t .` → **52 件 OK**
- `python -m syncbridge.cli selftest`（24fps、許容 0.1 フレーム）→ **全件 PASS**
  - Editable: 8 カーブ × 両方向で誤差 0.00000 フレーム
  - Precision: 最大誤差 0.0495 フレーム（`nonmonotonic_bezier`）。`asymmetric_ease` はサブフレームのキーを補助的に使用
- 途中で見つけて直した不具合:
  - `syncbridge_json.jsxinc` の正規表現リテラルに生の U+2028/U+2029 が入っていた（AE でも構文エラーになるはずだった）。
    → エスケープ表記に修正し、JSX が ASCII のみであることをテストで確認するようにした。
  - Precision でフレーム位置のキーだけでは許容誤差に届かない区間があった → サブフレームの補助キーと内部マージン（50%）を追加。

## 未解決の問題・未確認事項

- Maya の仮説 H-MY-1〜8、AE の仮説 H-AE-1〜8 はすべて未判定（`PHASE0_RESEARCH.md` 4 章）。
- weighted 接線の単位（H-MY-5）が未確定 → `anim_curve.DEFAULT_WEIGHT_SCALE` は仮の値。
- Scene Time Warp を自動で作成する方法が未確認（D-7）。
- Python 3.9 での実行は CI で確認する（このPCには 3.10 しかない）。
- 社内のセキュリティ規程（会社 PC での clone/push）の確認（R-13）。

## 次にやること

1. **[実機・利用者]** V-MY-1: Maya プローブを実行し、結果を `PHASE0_RESEARCH.md` に記録する。
2. **[実機・利用者]** V-AE-1: AE プローブを実行し、`verify-ae-probe` で判定する。
3. プローブの結果に応じて `DEFAULT_WEIGHT_SCALE` やコーデックを修正し、仮説の状態を更新する。
4. **[実機・利用者]** V-MY-2 / V-AE-2: エンドツーエンドの転送とリードバック、V-MY-3: レンダー比較。
5. GitHub に push して CI（Python 3.9 を含む）を確認する。
6. Phase 1 の準備: V-AE-3（CEP → localhost の WebSocket）、サーバーの最小実装。
