# 進捗

## 現在の状態

- **フェーズ:** Phase 0（技術検証）— DCC 不要の部分は完了、**実機検証中**
  （AE 26.5・Maya 2024 とも、プローブの合格条件 P0-3/P0-4 を満たした。エンドツーエンド転送とレンダー比較は未実施）
- **最終更新:** 2026-10-16

## 実装済み

| 機能 | 場所 | 状態 |
|---|---|---|
| 有理数 fps、Maya 時間単位、フレーム ⇔ 秒 | `core/timebase.py` | ✅ テスト済 |
| 中立カーブ（LINEAR/BEZIER/HOLD、外挿、アフィン変換、JSON） | `core/curve.py` | ✅ テスト済 |
| AE Time Remap 形式 ⇔ 中立カーブ | `core/ae_codec.py` | ✅ AE 26.5 の実データで誤差 0（H-AE-3/6/12） |
| Maya animCurveTT 形式 ⇔ 中立カーブ | `core/maya_codec.py` | ✅ Maya 2024 で誤差 0（H-MY-4/5/7）。Linear 外挿の傾き（H-MY-11）は未判定 |
| Maya ⇔ AE の時間軸の対応 | `core/mapping.py` | ✅ テスト済 |
| Precision モード（適応的な区分線形、サブフレームでの検証） | `core/sampler.py` | ✅ テスト済 |
| 誤差計測とレポート | `core/validation.py` | ✅ テスト済 |
| 変換パイプライン（Editable/Precision、両方向、3 種類の誤差レポート） | `core/transfer.py` | ✅ テスト済 |
| 交換エンベロープ、JSON Schema | `core/envelope.py`, `schemas/` | ✅ テスト済 |
| CLI（maya2ae, ae2maya, readback, probe-vectors, verify-ae-probe, selftest） | `cli.py` | ✅ テスト済 |
| Maya アダプタ（検索、読み書き、export/apply、バックアップ、リードバック） | `maya_plugin/.../` | ⚠ Maya 2024 で読み書きとも確認（プローブ経由）。`export_timewarp` / `apply_timewarp` は未実行。ダミー cmds で回帰テスト |
| Maya プローブ | `maya_plugin/.../probe.py` | ✅ Maya 2024 で 2 回実行（PHASE0_RESEARCH.md 8 章 #5）。範囲外のサンプルとサンプル値の保存を追加済み |
| AE スクリプト（Export/Apply、バックアップ、undo） | `after_effects/jsx/syncbridge_ae.jsx` | ⚠ AE 26.5 で Export は成功。Apply は未実行 |
| AE プローブ | `after_effects/jsx/probe_ae.jsx` | ✅ AE 26.5 で 2 回実行、2 回目は 13 ベクトル全て誤差 0 |
| AE の実データによる回帰テスト | `tests/fixtures/ae26.5_probe_run2.json`, `tests/unit/test_ae_real_data.py` | ✅ |
| ES3 用 JSON | `after_effects/jsx/syncbridge_json.jsxinc` | ✅ Node で Python の json と往復確認 |
| CI（Windows/Ubuntu × Python 3.9/3.11） | `.github/workflows/tests.yml` | ⚠ 未実行（push 後に確認） |

## テスト結果

### 2026-10-16（Windows 11, Python 3.10.6）

- Maya 2024 プローブ #1: Scene Time Warp = `timewarp.apply` → `time1.timewarpIn_Raw`（H-MY-1 ✅）、`enableTimewarp` あり。
  `setInfinity -q` が `None` を返して読み取りが全て停止 → `query_infinity()` でノード属性にフォールバックするよう修正。
- `py -3.10 -m unittest discover -s tests -t .` → **57 件 OK**（ダミー cmds による Maya アダプタのテスト 5 件を追加）
- Maya 2024 プローブ #2（PHASE0_RESEARCH.md 8 章 #5）: 全項目が完走。シーンのカーブを誤差 0 で再現、
  非 weighted 8 カーブは誤差 0、weighted 3 カーブは "w (frames)" のみ誤差 0（H-MY-5 確定）。
  シーンの Scene Time Warp は前後 Linear 外挿だった → H-MY-11 と R-20 を追加。`DEFAULT_WEIGHT_SCALE` を変更（**65 件 OK**）。
- R-20 対応: 転送に評価範囲を追加（ARCHITECTURE.md D-10、SPEC.md 3.5）。Precision は範囲外の Linear 外挿をキーに焼き込み、
  Editable は警告して不合格。CLI に `--range` / `--no-range`、既定は Maya の再生範囲と AE のコンプ範囲（**73 件 OK**）。
- AE 26.5 で AE プローブ 2 回目（PHASE0_RESEARCH.md 8 章 #4）: 13 ベクトル中 12 が誤差 0。
  `ae_mixed_linear_bezier` は 2.85 フレームずれ → AE は片側 LINEAR を「弦の 1/6」で評価すると判明（H-AE-6 は偽）。
  コーデックを修正して 13 ベクトル全て誤差 0。実データを fixture にして回帰テストを追加（**63 件 OK**）。
- AE 26.5 で AE プローブ 1 回目（PHASE0_RESEARCH.md 8 章 #3）: Bezier 系の 4 ベクトルは誤差 0。LINEAR/HOLD 系は
  キーが BEZIER に変わって FAIL（H-AE-11）→ `applyKeys` の設定順を修正、ベクトル 3 種と差分の列を追加（テスト 59 件 OK）。
- AE 26.5 で `syncbridge_ae.jsx` の Export に成功（PHASE0_RESEARCH.md 8 章 #2）。AE の評価値とコーデックが誤差 0 で一致。
  **AE の 29.97 は 2997/100**（H-AE-9）→ `FrameRate.from_ae()` を追加（テスト 58 件 OK）。
  平面レイヤーでは「Time Remap を使えない」と案内、保存・読み込みのダイアログは `probe_results/` で開くように変更。
- AE で初めてスクリプトを起動: `#include` を含めて読み込みは成功。`syncbridge_ae.jsx` は
  レイヤー未選択の前提チェックで停止（正常動作だが「Error … (line 81)」と表示されて紛らわしかった）。
  `probe_ae.jsx` は `ae_probe_vectors.json` が未作成のため先に進めなかった。対応:
  - 操作で解決できるエラーは案内として表示（`SB.userError` / `SB.alertError`）、ファイル書き込みの許可設定も案内
  - `probe_ae.jsx` が `<repo>/probe_results/ae_probe_vectors.json` を自動で探し、無ければ作り方を表示
  - CLI の起動用 `syncbridge.cmd` を追加（この PC の `python` は Store の仮コマンドのため）。手順書のコマンドを統一

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

- Maya（2024）: H-MY-1〜7, 9 は確認。H-MY-5 は 24fps でのみ確認。H-MY-8（レンダー）、H-MY-10（自動作成）、
  H-MY-11（Linear 外挿の傾き）は未判定。Maya 2023 では未実施。
- UI で作った Scene Time Warp は Linear 外挿（R-20）→ Precision で評価範囲まで焼き込むよう対応済み。
  ただし焼き込む外挿の傾きは H-MY-11 が未判定のため、Maya の範囲外の値と一致するかは未確認。
- AE（26.5）: H-AE-1/3/4/5/7/11/12 は確認、H-AE-6 は偽（1/6 に修正）、H-AE-2 は一部、H-AE-9/10 は 1 コンプで確認。
  H-AE-8（CEP の通信）は未判定。AE 2024/2025 では未実施。片側 LINEAR の 1/6 モデルは 1 ベクトルのみで決定。
- AE の Apply（`syncbridge_ae.jsx`）とリードバックは未実行（V-MY-2）。
- AE で読んだ片側 LINEAR のキーを Maya に送ると、ハンドルが 1/3 でないため weighted 接線になる（H-MY-5 は確認済み、エンドツーエンドは未確認）。
- Maya の「29.97fps」単位が 30000/1001 なのか 29.97 なのかは未確認（AE とずれる可能性、R-14）。
- Scene Time Warp の自動作成: コマンドは `sceneTimeWarp "add"` と判明、実行時の挙動は未確認（H-MY-10, D-7）。
- Python 3.9 での実行は CI で確認する（このPCには 3.10 しかない）。
- 社内のセキュリティ規程（会社 PC での clone/push）の確認（R-13）。

## 次にやること

1. **[実機・利用者]** Maya プローブ 3 回目: H-MY-11（Linear 外挿）の判定と、書き込みテストのサンプルを回帰テストのデータにする。
   可能なら 30fps のシーンでも実行して H-MY-5 を確認し、Maya 2023 でも実行する。
2. **[実機・利用者]** V-MY-2 / V-AE-2: エンドツーエンドの転送とリードバック（Maya の export/apply、AE の Apply を初めて使う）。
   Linear 外挿のシーンは `--mode precision` で送る。
3. **[実機・利用者]** V-MY-3: レンダー比較（H-MY-8）。
4. GitHub に push して CI（Python 3.9 を含む）を確認する。
5. Phase 1 の準備: V-AE-3（CEP → localhost の WebSocket）、サーバーの最小実装。
