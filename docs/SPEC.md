# SyncBridge 仕様

最終更新: 2026-10-15 / 元仕様: 「Maya × After Effects Sync Tool 開発方針・基本仕様書 v0.1」
（ツール名は **SyncBridge** に決定）

この文書は元仕様のうち、**実装の判断に必要なルールとデータ形式** を確定させたものである。
未確定の項目は「未確定」と明記し、`PHASE0_RESEARCH.md` の仮説 ID を付ける。

## 1. 目的と範囲

Maya の Scene Time Warp と AE の Time Remap を双方向に転送・同期する。

- **Editable モード:** キーフレーム構造と補間を保ち、転送先でも編集できる。
- **Precision モード:** キー構造より、時間変換の結果の一致を優先する。
- 制作設定（FPS、解像度、ピクセルアスペクト比、フレーム範囲、現在フレーム）も同期する（Phase 2）。
- 同期項目ごとに ON／OFF を切り替えられる。

## 2. 時間の用語

| 用語 | 定義 | 単位 |
|---|---|---|
| シーン時間 | Maya のタイムスライダーの時間（ワープ前） | Maya: フレーム |
| ワープ後時間 | Scene Time Warp を通した評価時間 | Maya: フレーム |
| コンプ時間 | AE コンポジションの時間 | 秒 |
| ソース時間 | AE レイヤーのソース（フッテージ／プリコンポジション）の時間。Time Remap の値 | 秒 |
| 入力時間 / 出力時間 | 中立カーブの横軸 / 縦軸 | 秒 |
| フレーム番号 | 時間 × fps。表示用で、内部計算には使わない | フレーム |
| レイヤー開始オフセット | AE `layer.startTime` | 秒 |

規則:

1. 内部の計算はすべて **秒（float）**。fps は **有理数**（`Fraction`）で持つ（24000/1001 など）。
2. フレームと秒の変換はアプリとの境界（codec、adapter）だけで行う。
3. AE の float の fps（例: 23.976023976…）は既知の有理数に丸めて扱う（誤差 1e-4 以内）。
4. 29.97df などのドロップフレームは表示上の区別であり、時間は 30000/1001 fps として扱う。

## 3. 時間変換の仕様

### 3.1 中立カーブ（`TimeCurve`）

入力秒 → 出力秒の関数。キー i は `t, v, in, out, ih, oh` を持つ。

| 区間 i → i+1 | 評価 |
|---|---|
| キー i の out が HOLD、またはキー i+1 の in が HOLD | v_i を保持（t_{i+1} で v_{i+1} にジャンプ） |
| out が LINEAR かつ次の in が LINEAR | 直線 |
| それ以外 | 2D 3 次 Bezier。P1 = P0 + oh_i、P2 = P3 + ih_{i+1}。LINEAR 側は弦の 1/3 |

- ハンドルの時間成分は区間内に収める（関数であることを保つ）。
- 範囲外は `pre_infinity` / `post_infinity`（constant / linear）。AE は constant のみ表現できる。

### 3.2 アプリ形式との対応

**AE（`ae_codec.py`）:** ❓H-AE-3

```
out ハンドル: dx = 影響度/100 × (t_{i+1} − t_i),  dy = 速度 × dx
in  ハンドル: dx = −影響度/100 × (t_i − t_{i−1}), dy = 速度 × dx
影響度は 0.1〜100%。範囲外は丸めて警告する。
```

**Maya（`maya_codec.py`）:** ❓H-MY-4/5/7

```
非 weighted: ハンドル長 = 区間長 / 3、傾き = tan(角度)
weighted:    ハンドル長（フレーム）= weight × cos(角度) × c（c はプローブで確定）
step 接線 → HOLD、stepnext → 未対応（Editable では警告）
出力時は接線タイプ fixed（Maya に再計算させない）。全ハンドルが 1/3 のときは非 weighted で出力する。
```

### 3.3 Maya と AE の時間軸の対応（`MappingContext`）

```
comp_time   = (maya_in_frame  − maya_input_origin_frame)  / maya_fps + ae_comp_time_offset
source_time = (maya_out_frame − maya_output_origin_frame) / maya_fps × source_time_scale + ae_source_time_offset
```

| パラメータ | 意味 | CLI の既定値 |
|---|---|---|
| `maya_input_origin_frame` | コンプ時間 `ae_comp_time_offset` に対応する Maya シーンのフレーム | `--origin`（既定 0） |
| `maya_output_origin_frame` | ソース時間 `ae_source_time_offset` に対応するワープ後の Maya フレーム（通常はレンダー開始フレーム） | `--origin`（既定 0） |
| `ae_comp_time_offset` | 上記に対応するコンプ時間（秒） | AE のエクスポートがあれば layer.startTime、なければ 0 |
| `ae_source_time_offset` | 上記に対応するソース時間（秒） | 0 |
| `source_time_scale` | Maya のワープ後 1 秒あたりの AE ソース秒（フッテージのフレームレート解釈が違うとき） | 1 |

前提（Phase 0）: AE のソースは Maya で **ワープを無効にして** レンダリングした素材。stretch = 100%。プリコンポジションのネストは 1 段。

### 3.4 Editable モード

1. 転送元のキーを中立カーブにデコードする。
2. `MappingContext` で写像する（アフィン変換なので厳密）。
3. 転送先の形式にエンコードし、表現できない部分（影響度の範囲、linear infinity、vertical tangent、stepnext）は警告に記録する。
4. 出力キーを再デコードし、転送元と比較する（`conversion`）。

### 3.5 Precision モード

1. 3.4 の 1〜2 と同じ。
2. HOLD 区間でカーブを分け、連続した区間ごとに適応的な区分線形で当てはめる（`sampler.py`）。
   - キー候補: 既定はフレーム位置（`key_subdivision=1`）
   - 誤差確認: キー候補の間を 8 分割したサブフレーム点（点と点の間の補間誤差も確認する）
   - 許容誤差を超える区間は、最も誤差の大きい点に近い候補で分割する
   - フレーム位置の候補で収まらない箇所だけ、サブフレームのキーを使う
3. 出力は LINEAR／HOLD キーのみ。全範囲で再検証する。

### 3.6 許容誤差

- 既定: **出力時間の誤差 0.1 フレーム以下**（転送先の fps で計測）。利用者が変更できる（CLI `--tol`）。
- 誤差レポート: 最大、平均、RMS、最大誤差の時刻、許容誤差を超えたサンプル（最大 50 件）。
- 環境による精度の限界: Precision でフレーム位置のキーだけでは届かない区間を `unreachable` として報告する。

## 4. 双方向転送と同期

- Phase 0: 手動（ファイル経由）。Maya → AE、AE → Maya。
- Phase 5: 片方向の自動同期 → 双方向の自動同期。
- 自動同期で必須: イベント ID、送信元 ID、リビジョン番号、差分検出、重複イベントの無視、同期ループの防止、
  競合検出（自動上書きしない、利用者が選ぶ）、更新前のバックアップ、デバウンス。
- 現在フレームの同期と、キーフレーム変更の同期は別の機能として扱う。

## 5. 安全に関するルール

1. 適用の前に必ず確認ダイアログを出す（何を、いくつのキーで、どのモードで置き換えるか）。
2. 適用の前に現在の状態を JSON でバックアップする。
   - Maya: `<userAppDir>/SyncBridge/backups/timewarp_<日時>.json`
   - AE: `Folder.userData/SyncBridge/backups/timeremap_<日時>.json`
3. 適用は 1 回の undo（Maya の undo チャンク、AE の undo グループ）で戻せるようにする。
4. 新しいキーを先に置いてから古いキーを消す（カーブやプロパティが空になる瞬間を作らない）。
5. 適用後にリードバック検証を行い、結果を表示する。
6. 表現できない情報は黙って捨てず、警告に記録する。

## 6. その他の同期項目（Phase 2）

| 項目 | Maya | AE |
|---|---|---|
| FPS | `currentUnit -time` | `comp.frameRate` |
| 解像度 | `defaultResolution.width/height` | `comp.width/height` |
| ピクセルアスペクト比 | `defaultResolution.pixelAspect` | `comp.pixelAspect` |
| 再生範囲 | `playbackOptions -min/-max` | Work Area（`workAreaStart`, `workAreaDuration`） |
| アニメーション範囲 | `playbackOptions -ast/-aet` | コンプの範囲（`displayStartTime`, `duration`） |
| レンダー範囲 | `defaultRenderGlobals.startFrame/endFrame` | （対応先は Phase 2 で決める） |
| 現在フレーム | `currentTime` | `comp.time` |

Phase 0 では Maya 側の読み取りだけを実装し、export に含めている（`scene_settings.py`）。
