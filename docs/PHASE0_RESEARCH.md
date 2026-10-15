# Phase 0 技術検証レポート

最終更新: 2026-10-15 / 対象: Maya 2023+, After Effects 2024+, Windows 10/11

> **重要:** この文書の「仮説（H-*）」は、Maya・AE の実機ではまだ一度も確認していない。
> 公式ドキュメントや一般的な知識を根拠にした作業仮説であり、**動作確認済みとして扱ってはいけない**。
> 各仮説は下記のプローブ（V-*）を実機で実行して判定し、結果をこの文書と `PROGRESS.md` に記録する。

検証状態の表記:

| 表記 | 意味 |
|---|---|
| ✅ 検証済 | このリポジトリのテストまたは実機プローブで確認した |
| 📘 文書 | 公式ドキュメントに記載がある（このプロジェクトの実機では未実行） |
| ❓ 仮説 | 推測。プローブで判定が必要 |

---

## 1. 実現可能性の結論

**実現可能と判断する。** 根拠と条件は次のとおり。

1. **時間変換コアは検証済み（✅）。** Maya・AE の双方に依存しない純 Python 実装で、8 種類の
   参照カーブ（通常再生、スロー、速度ランプ、非対称イーズ、フリーズ、ジャンプ、逆再生、非単調）について、
   Editable／Precision の両モードと両方向で誤差 0.1 フレーム以下を確認した（`selftest`、単体テスト 52 件）。
2. **Precision モードは未検証の接線の数式に依存しない。** 出力を LINEAR／HOLD キーだけで構成するため
   （設計判断 D-4）、Maya と AE の Bezier の解釈が仮説と違っても精度は保証される。
   残るリスクは時間単位とオフセット（H-MY-3, H-AE-1/2）だけで、これはプローブで機械的に判定できる。
3. **Editable モードは、接線の変換式（H-MY-4/5, H-AE-3/6）の実機確認が前提。** 外れていた場合でも、
   読み取り時の自己キャリブレーション（D-6）と適用後のリードバック検証（D-5）で必ず検出し、利用者に通知する。
4. **最大の不確定要素は Maya Scene Time Warp の内部構造（H-MY-1/2）とレンダリングへの適用（H-MY-8）。**
   コードは名前を決め打ちせず、`time1` への接続を探索する方式にしている。

---

## 2. 時間モデルの差異（優先検証項目）

| 観点 | Maya Scene Time Warp | AE Time Remap |
|---|---|---|
| 適用範囲 | シーン全体（全アニメーションの評価時間） | レイヤー単位 |
| 入力軸 | シーン時間（タイムスライダー） | コンポジション時間 |
| 出力軸 | ワープ後の評価時間 | レイヤーのソース時間 |
| 単位 | フレーム（現在の時間単位）。内部は tick（❓H-MY-3） | 秒（❓H-AE-2） |
| カーブ | animCurveTT。Hermite／weighted Bezier、多数の接線タイプ | 時間的イーズ（速度・影響度）、LINEAR／BEZIER／HOLD、auto-bezier／continuous |
| 範囲外 | pre/post infinity（constant, linear, cycle…） | 最初／最後のキー値を保持 |
| オフセット要素 | なし（シーン時間そのもの） | layer.startTime、stretch、プリコンポジション、ソースのフレームレート解釈 |
| 逆再生・非単調 | 可能 | 可能 |
| 評価値の取得 | `keyframe -q -eval` / `getAttr -time`（📘） | `Property.valueAtTime(t, false)`（📘） |

### 「同じ対象を参照しているか」

両者の時間変換が同じ結果になるのは、次の対応が成り立つときだけである。

- AE レイヤーのソース = Maya で **ワープを無効にして** レンダリングしたフレーム列
- ソース時間 0 秒 = Maya のあるフレーム（例: レンダー開始 1001）
- コンプ時間のある時点 = Maya シーンのあるフレーム

この対応は `MappingContext`（`src/syncbridge/core/mapping.py`）で明示的に持つ。

```
comp_time   = (maya_in_frame  - maya_input_origin_frame)  / maya_fps + ae_comp_time_offset
source_time = (maya_out_frame - maya_output_origin_frame) / maya_fps * source_time_scale + ae_source_time_offset
```

**二重適用に注意（R-5）:** Maya でワープを有効にしたままレンダリングした素材に、AE で同じ Time Remap を
かけると、ワープが 2 回かかる。UI と手順書で明示する必要がある。

---

## 3. API 制約の整理

### 3.1 Maya

| 項目 | 内容 | 状態 |
|---|---|---|
| Python | 2023 = 3.9 系、2024 = 3.10 系、2025 = 3.11 系 | 📘 |
| Qt バインディング | 2023/2024 = PySide2、2025 = PySide6 | 📘 → Qt.py などの互換層を推奨（R-6） |
| スレッド | maya.cmds／OpenMaya はメインスレッド専用。別スレッドからは `maya.utils.executeDeferred` / `executeInMainThreadWithResult` | 📘 |
| 外部ライブラリ | numpy は同梱が保証されない → コアは標準ライブラリのみ | 方針 |
| 変更検出 | `scriptJob`、`OpenMaya.MMessage`（例: `MDGMessage`, `MNodeMessage`） | 📘（Phase 5） |
| animCurve 評価 | `keyframe -q -eval -time t` | 📘 |
| 接線 | `keyTangent` の inAngle/outAngle/inWeight/outWeight、`-weightedTangents`、タイプ fixed/linear/step/spline… | 📘 |

### 3.2 After Effects

| 項目 | 内容 | 状態 |
|---|---|---|
| ExtendScript | ES3 相当。`JSON`・`Array.prototype.forEach/map/indexOf` が使えない | 📘 → 独自の `SBJSON` を同梱（Node で動作確認済 ✅） |
| スレッド | ExtendScript は単一スレッドでブロッキング | 📘 |
| 通信 | ExtendScript から直接 WebSocket は使わない。CEP（Chromium + Node.js）側で通信し、`CSInterface.evalScript()` で JSX を呼ぶ | 📘（仕様 3.B） |
| Time Remap | `layer.timeRemapEnabled`, `layer.canSetTimeRemapEnabled`, `property("ADBE Time Remapping")` | 📘 |
| キー操作 | `setValueAtTime`, `keyTime`, `keyValue`, `removeKey`, `nearestKeyIndex`, `setInterpolationTypeAtKey`, `setTemporalEaseAtKey`, `KeyframeEase(speed, influence)` | 📘 |
| 変更通知 | キーフレーム変更のイベント API はない → ポーリング＋ハッシュ差分（Phase 5） | 📘 |
| 拡張方式 | CEP は将来 UXP へ移行の見込み → 通信層と JSX 操作層を分離 | 方針（R-7） |
| CEP の開発時読み込み | 未署名拡張には PlayerDebugMode のレジストリ設定が必要 | 📘（利用者が設定） |

---

## 4. 仮説一覧（実機で判定する）

### Maya

| ID | 仮説 | 判定方法 | 状態 |
|---|---|---|---|
| H-MY-1 | UI で作った Scene Time Warp は、`time1` の名前に "timewarp" を含む入力属性へ接続された animCurveTT である | probe: `time_node.connections`, `animCurveTT_nodes` | ❓ |
| H-MY-2 | `time1.enableTimewarp` で有効／無効が切り替わり、`time1.outTime` がワープ後の時間を出す | probe: `warp_attributes`, `unit_checks.getAttr_time1_outTime` | ❓ |
| H-MY-3 | `keyframe -q -vc` と `keyframe -q -eval` は TT カーブで現在の時間単位（フレーム）の値を返す | probe: `unit_checks` | ❓ |
| H-MY-4 | TT カーブでは tan(接線角度) が無次元の傾き d(出力)/d(入力) | probe: `write_roundtrip`（非 weighted カーブ） | ❓ |
| H-MY-5 | weighted 接線の時間方向の長さ = weight × cos(角度) × c。c は未確定 | probe: `write_roundtrip` の `asymmetric_ease`。PASS した候補が c | ❓ |
| H-MY-6 | `setKeyframe` は animCurve ノード名を直接受け付ける | probe: `write_roundtrip` がエラーなく動くか | ❓ |
| H-MY-7 | 非 weighted 区間は Hermite（= 1/3 ハンドルの Bezier）で評価される（devkit の animEngine に基づく） | probe: `write_roundtrip`（`speed_ramp_bezier`） | ❓ |
| H-MY-8 | Scene Time Warp はバッチレンダリングにも適用される | V-MY-3（レンダー比較） | ❓ |

### After Effects

| ID | 仮説 | 判定方法 | 状態 |
|---|---|---|---|
| H-AE-1 | Time Remap の `keyTime`／`setValueAtTime`／`valueAtTime` はコンプ時間で扱われる（layer.startTime ≠ 0 でも） | probe: `@startTime0.5` の結果 | ❓ |
| H-AE-2 | Time Remap の値はレイヤーソース時間（秒） | probe: `slowmo_linear`, `identity` | ❓ |
| H-AE-3 | イーズ → ハンドル: dx = 影響度/100 × 区間長、dy = 速度 × dx | probe: `speed_ramp_bezier`, `asymmetric_ease` | ❓ |
| H-AE-4 | Time Remap のキー削除やイーズ設定は他の 1D プロパティと同様に動く | probe 全体がエラーなく動くか | ❓ |
| H-AE-5 | `setValueAtTime` でサブフレーム時刻にキーを置ける（フレームに丸められない） | probe の `readKeys[].time` と送信時刻の差 | ❓ |
| H-AE-6 | 片側 LINEAR・片側 BEZIER の区間は「LINEAR 側のハンドル = 弦の 1/3」で評価される | probe: `speed_ramp_bezier` の始点・終点の区間 | ❓ |
| H-AE-7 | 影響度の合計が 100% を超えても、AE はハンドルを縮めずにそのまま評価する | probe: `asymmetric_ease`（区間 2→3 秒） | ❓ |
| H-AE-8 | CEP パネルから `ws://127.0.0.1` に接続できる | V-AE-3 | ❓ |

---

## 5. 実装上のリスク

| ID | リスク | 影響 | 対策 |
|---|---|---|---|
| R-1 | Scene Time Warp の構造が H-MY-1/2 と違う | 高 | 接続の探索で特定、プローブで構造を記録、Phase 0 ではカーブを新規作成しない（D-7） |
| R-2 | Maya の weight の単位が不明（H-MY-5） | 中 | 読み取り時の自己キャリブレーション（D-6）、Precision モードは影響なし（D-4） |
| R-3 | AE のイーズの式が仮説と違う（H-AE-3/6/7） | 中 | プローブで判定、リードバック検証（D-5）で必ず検出 |
| R-4 | AE がサブフレームのキーをフレームに丸める（H-AE-5 が偽） | 中 | Precision は既定でフレーム位置にキーを置く。サブフレームの補助キーは `allow_subframe=False` で無効化できる |
| R-5 | ワープの二重適用（ワープありでレンダリングした素材に Time Remap） | 高（見た目が壊れる） | 手順書と UI で明示。将来は MappingContext に「レンダーにワープ適用済み」フラグを追加 |
| R-6 | Maya 2025 以降は PySide6 | 中 | UI は Qt.py などの互換層経由で書く（Phase 6） |
| R-7 | CEP の廃止・UXP への移行 | 中 | 通信層（CEP）と JSX 操作層を分離。変換は Python 側に集約（D-2） |
| R-8 | Maya はメインスレッド専用、AE は単一スレッド | 中 | サーバーは別プロセス。Maya は `executeDeferred`、AE は CEP 側でキューイング |
| R-9 | AE にキーフレーム変更イベントがない | 中 | ポーリング＋内容ハッシュで差分検出（Phase 5） |
| R-10 | 自動同期のループ・競合 | 高 | イベント ID、送信元 ID、リビジョン、重複の無視、競合時は自動上書きしない |
| R-11 | アップデートの真正性（ハッシュとパッケージが同じ場所にある） | 高 | 署名鍵（Ed25519 など）で署名し、公開鍵をアプリに同梱して検証 |
| R-12 | Private リポジトリの認証情報 | 高 | EXE に埋め込まない。配布経路は Phase 6 で別途設計 |
| R-13 | 会社 PC・リポジトリの利用規程 | 要確認 | 社内規程を確認してから会社 PC で clone・push する |
| R-14 | NTSC・ドロップフレーム | 低 | 時間は有理数の fps と秒で扱う。29.97df は表示上の問題 |
| R-15 | stretch ≠ 100%、ネストしたプリコンポジション | 中 | Phase 0 は stretch = 100% を前提とし、違えば確認を出す。ネストは 1 段のみ |
| R-16 | Time Remap の値がソースの長さでクランプされる可能性、最終フレームの扱い（ソース長 − 1 フレーム） | 中 | 範囲チェックと警告（Phase 3） |
| R-17 | Maya の pre/post infinity が cycle などの場合 | 低 | 警告を出して constant として扱う（実装済み） |
| R-18 | Maya 2023 の `stepnext` 接線 | 低 | Editable では警告、Precision を推奨（実装済み） |

---

## 6. 検証手順

すべての結果ファイルは `probe_results/`（Git 管理外）に置き、要約をこの文書の 4 章と `PROGRESS.md` に転記する。

### V-MY-1: Maya プローブ（H-MY-1〜7）

1. Maya 2023 で新規シーンを開き、UI から Scene Time Warp を作成する（例: 1001 → 1001、1100 → 1050 のスロー）。
2. Script Editor（Python）で次を実行する。
   ```python
   import sys
   sys.path.insert(0, r"E:/OG_Tools/SyncBridge/maya_plugin/scripts")
   import syncbridge_maya.probe as probe
   probe.run(r"E:/OG_Tools/SyncBridge/probe_results/maya_probe.json")
   ```
3. 表示された要約と JSON を確認する。プローブはシーンの Scene Time Warp を変更せず、一時 animCurveTT を作成して削除する。
4. 判定:
   - `Scene Time Warp:` の行にカーブ名と接続先プラグが出れば H-MY-1 は真。
   - `time1 warp attributes` に `enableTimewarp` があれば H-MY-2 の前半は真。
   - `write <curve>` の行がすべて PASS（最大 0.01 フレーム以下）なら H-MY-4/6/7 は真。
     `asymmetric_ease` で PASS した `weight_scale` が H-MY-5 の c。
     → `anim_curve.DEFAULT_WEIGHT_SCALE` をその値に変更する。

### V-MY-2: Maya → AE のエンドツーエンド

1. Maya: `import syncbridge_maya.exchange as sbx; sbx.export_timewarp(r".../probe_results/maya.json")`
   （`decode vs Maya` が PASS であることを確認する）
2. AE: Maya のワープなしレンダーを読み込んだコンプでレイヤーを 1 つ選び、`syncbridge_ae.jsx` → Export（`ae.json`）
3. PC: `python -m syncbridge.cli maya2ae probe_results/maya.json -o probe_results/ae_apply.json --ae-export probe_results/ae.json --origin 1001 --mode editable`
4. AE: `syncbridge_ae.jsx` → Apply… で `ae_apply.json` を選ぶ（`ae_apply_after.json` が出力される）
5. PC: `python -m syncbridge.cli readback probe_results/ae_apply.json probe_results/ae_apply_after.json`
6. `--mode precision` でも 3〜5 を繰り返す。

### V-MY-3: レンダー一致（H-MY-8、R-5）

1. Maya でフレーム番号を焼き込んだテストシーン（例: フレーム番号を表示する文字オブジェクト）を用意する。
2. (a) ワープを **無効** にしてレンダリング → AE に読み込み、V-MY-2 の手順で Time Remap を適用する。
3. (b) ワープを **有効** にしてレンダリングする。
4. (a) の AE 出力と (b) を同じフレームで比較し、焼き込まれたフレーム番号が一致することを確認する。

### V-AE-1: AE プローブ（H-AE-1〜7）

1. PC: `python -m syncbridge.cli probe-vectors -o probe_results/ae_probe_vectors.json`
2. AE 2024 以降で任意のプロジェクトを開き、`File > Scripts > Run Script File...` → `after_effects/jsx/probe_ae.jsx` → 1. のファイルを選ぶ。
   一時コンプ `SB_probe_inner` と `SB_probe_outer` を作成し、終了時に削除する（既存のコンプは変更しない）。
3. PC: `python -m syncbridge.cli verify-ae-probe probe_results/ae_probe_results.json`
4. 判定: 左列「送信キー vs AE の評価値」がすべて PASS なら H-AE-2/3/6/7 は真。
   `@startTime0.5` が PASS なら H-AE-1 は真。右列「AE が読み返したキー vs AE の評価値」が FAIL の場合は、
   AE がキーを書き換えている（丸め、正規化）ので `readKeys` と `sentKeys` を比較する（H-AE-5）。

### V-AE-2: AE → Maya のエンドツーエンド

1. AE: Time Remap を付けたレイヤーを選び、`syncbridge_ae.jsx` → Export（`ae.json`）
2. PC: `python -m syncbridge.cli ae2maya probe_results/ae.json -o probe_results/maya_apply.json --maya-fps 24 --origin 1001`
3. Maya: `sbx.apply_timewarp(r".../probe_results/maya_apply.json")` → 確認ダイアログ、JSON バックアップ、適用、リードバックの結果が表示される。

### V-AE-3: CEP から localhost への通信（H-AE-8、Phase 1 の前提）

1. 開発用に PlayerDebugMode を有効にする（Windows レジストリ `HKEY_CURRENT_USER\Software\Adobe\CSXS.<バージョン>` の
   `PlayerDebugMode` = `1`）。**システム設定の変更なので利用者自身が行う。** CSXS のバージョン番号は AE のバージョンごとに確認する。
2. Phase 1 で用意する最小 CEP パネルから `ws://127.0.0.1:8765` に接続し、echo の往復を確認する。

---

## 7. 合格条件（Phase 0）

| # | 条件 | 状態 |
|---|---|---|
| P0-1 | 単体・結合テスト（`python -m unittest discover -s tests -t .`）が全件 PASS（CI: Windows/Ubuntu × Python 3.9/3.11） | ✅ ローカル 52 件 PASS（Python 3.10）。CI は push 後に確認 |
| P0-2 | `python -m syncbridge.cli selftest` が全件 PASS（8 カーブ × 2 モード × 2 方向、誤差 0.1 フレーム以下） | ✅ |
| P0-3 | V-MY-1: H-MY-1〜7 の判定が記録され、`write_roundtrip` が少なくとも 1 つの weight 候補で全カーブ 0.01 フレーム以下 | 未実施 |
| P0-4 | V-AE-1: `verify-ae-probe` が全件 PASS（許容 0.01 フレーム）、`@startTime` 版も PASS | 未実施 |
| P0-5 | V-MY-2 / V-AE-2: 両方向・両モードでリードバックの誤差が 0.1 フレーム以下 | 未実施 |
| P0-6 | V-MY-3: レンダー比較で焼き込みのフレーム番号が一致 | 未実施 |

P0-3〜P0-6 の結果によって設計変更が必要になった場合は、`ARCHITECTURE.md` の「設計判断」に理由とともに追記する。
