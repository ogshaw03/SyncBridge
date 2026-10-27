# SyncBridge 実装状況レポート（2026-10-26 時点）

対象: `main` ブランチ（最新リリース 0.1.9、タグ `v0.1.9` = 5d78e21）。根拠はリポジトリのソースコードと、
`docs/PROGRESS.md`（作業記録）、`docs/PHASE0_RESEARCH.md`（仮説 H-* の検証状態）、`docs/ARCHITECTURE.md`（設計判断 D-*）。

**状態の表記**

| 表記 | 意味 |
|---|---|
| ✅ 実機確認 | Maya / AE の GUI で利用者が動作を確認した |
| 🧪 自動確認 | 単体・結合テスト、または mayapy（Maya のバッチ）で確認した。GUI では未確認 |
| 🟡 一部実装 | 一部だけ実装、または制約つき |
| ⬜ 未実装 | コードがない（構想・仕様のみ） |

自動テストは 379 件（`tests/unit`, `tests/integration`、unittest、DCC 不要）。Maya 2023 / 2024 の mayapy による検証スクリプトが
`tools/pixel_mapping/*.py` にある。

---

## 1. システム構成

```
 Maya（Python 3.9〜）            Local Sync Server（ハブ）           After Effects（CEP パネル + ExtendScript）
 maya_plugin/scripts/            src/syncbridge/server/             after_effects/panel/js/ (HTML/JS)
   syncbridge_maya/   ◀─WebSocket─▶  FastAPI + uvicorn   ◀─WebSocket─▶   after_effects/jsx/ (ES3)
 maya_plugin/plug-ins/           127.0.0.1、トークン認証
        │                                 │
        └──── src/syncbridge/core/（変換ロジック。純 Python・標準ライブラリのみ。Maya とハブで共用）
```

### 1.1 共通ロジック `src/syncbridge/core/`（標準ライブラリのみ、Maya / AE を import しない）

| ファイル | 役割 |
|---|---|
| `timebase.py` | 有理数の fps、フレーム ⇔ 秒（時間は内部ですべて秒） |
| `curve.py`, `ae_codec.py`, `maya_codec.py`, `mapping.py`, `sampler.py`, `transfer.py`, `validation.py`, `jobs.py` | タイムワープ / タイムリマップの中立カーブ（2D 3 次 Bezier）、両アプリの形式との変換、Editable / Precision の 2 モード、誤差レポート |
| `envelope.py` | 交換データのエンベロープ（`schemas/` の JSON Schema） |
| `scene_sync.py` | シーン設定（FPS・範囲・ピクセル縦横比）の変換（D-21） |
| `time_sync.py` | タイムスライダー同期の時間変換（D-22） |
| `markers.py`, `comp_guide.py` | AE のキーのマーカー（D-18）、コンプの解像度の枠（D-16） |
| `pixel_mapping.py` | Pixel Mapping の座標変換: AE レイヤーの行列 `ae_layer_matrix`、Maya カメラの投影モデル `project`、ソルバー `solve` / `solve_relative` / `solve_source`、`camera_affine`、`to_render_space` |
| `motion.py` | アニメーション転送（各フレームの値 → キー）`solve_motion`, `frame_times`, `curves` |
| `layer_mapping.py` | レイヤーマップのデータ（Maya レイヤー、接続、`ae_shown`、`main_comp`）と操作 |
| `view_frame.py`, `stack_view.py` | ビューアーの解像度の枠の位置、余白用の投影行列 |

### 1.2 Maya 側 `maya_plugin/`

| ファイル | 役割 |
|---|---|
| `scripts/syncbridge_maya/service.py` | ハブとの接続、リクエスト（`request_ae_layers`, `request_ae_motion` など）、受信の振り分け |
| `ui.py` | メインのパネル（PySide2/6）。タイムワープ転送、シーン設定、時間の同期、解像度の枠、Pixel Mapping 欄 |
| `scene_timewarp.py`, `anim_curve.py`, `exchange.py`, `snapshots.py` | Scene Time Warp の読み書き、バックアップ、保存・復元・範囲変更 |
| `scene_settings.py`, `time_sync.py`, `timing.py` | シーン設定の適用、タイムスライダー同期、Origin frame（シーンに保存、D-38） |
| `key_markers.py`, `comp_guide.py` | マーカー、解像度の枠 |
| `pixel_mapping.py` | Maya のカメラの値の読み書き、AE からの 1 回送信の適用（`apply_from_ae`） |
| `layer_mapping.py` | レイヤーマップの保存（network ノード `syncBridgeLayerMappings` に JSON、1 操作 = 1 undo） |
| `layer_camera.py` | 専用カメラ `SB_<レイヤー>_CAM`（元のカメラの子、D-29） |
| `motion.py`, `motion_transfer.py` | アニメーション転送の計画・適用（`plan`, `apply_all`）、範囲のダイアログと手順（`MotionTransfer`） |
| `layer_map_view.py`, `layer_map_window.py` | レイヤーマップのノードエディター（`LayerMapEditor`, `LayerMapView`, `LayerMapWindow`） |
| `layer_stack.py`, `layer_stack_view.py`, `viewer_window.py`, `layer_view.py` | 専用ビューアー（`ViewerWindow`, `LayerStackList`）、レイヤー表示の切り替え |
| `plug-ins/syncbridge_layer_stack.py` | Viewport 2.0 のレンダーオーバーライド（`LayerStackOverride`, `LayerPass`, `FrameHUD`） |
| `plug-ins/syncbridge_guide.py` | 解像度の枠・マーカーのシェイプノード、取り消しできるシーン設定コマンド `syncBridgeApplySettings` |

### 1.3 AE 側 `after_effects/`

| ファイル | 役割 |
|---|---|
| `panel/js/sbclient.js` | ハブとの WebSocket、メッセージ処理（`_layersExport`, `_motionExport` など）、日本語メッセージ `MESSAGES` |
| `panel/js/main.js` | パネルの UI |
| `jsx/syncbridge_cep_host.jsx` | ExtendScript（ES3、ASCII のみ）: `exportSelected`, `applyEnvelope`, `sceneSettings`, `applySceneSettings`, `compTime`, `setTime`, `pixelMapInfo`, `layersInfo`, `layerMotion` |
| `jsx/syncbridge_ae_lib.jsxinc`, `syncbridge_json.jsxinc` | 共通処理、ES3 用 JSON（`SBJSON`） |

### 1.4 ローカルサーバー（ハブ）`src/syncbridge/server/`

| ファイル | 役割 |
|---|---|
| `app.py` | FastAPI アプリ、メッセージの種類ごとの処理の登録 |
| `connections.py` | `ConnectionManager`, `Client`（接続、相手の選択、要求と応答の対応） |
| `flow.py` | `TransferFlow`（タイムワープの手動転送: 片方から export → 変換 → もう片方へ apply） |
| `settings_flow.py` | `SettingsFlow`（シーン設定） |
| `relay.py` | `GuideFlow`, `MarkerFlow`, `PixelMapFlow`, `LayersFlow`, `MotionFlow`（片方のアプリへの中継） |
| `timesync.py` | `TimeSync`（同期のオン・オフと Origin frame の状態、時間の中継） |
| `admin.py`, `hubstate.py` | 管理 API、転送の履歴、ログ（モニター用） |
| `session.py` | セッションファイル（ポートとトークン） |

そのほか: `src/syncbridge/client/`（標準ライブラリの WebSocket クライアント、Maya 内で動く）、`hubs.py`（ハブの発見・停止）、
`monitor/`（PySide6 のモニター）、`cli.py`（ファイル経由の変換、Phase 0）、`pixelcheck/`（PNG の読み込みと測定、標準ライブラリ）、
`packaging/build_release.py`（配布 zip。PyInstaller の EXE、署名した ZXP）。

### 1.5 通信 API とデータ形式

- WebSocket（127.0.0.1）、JSON。各メッセージは `{kind, event_id, reply_to?, data}`。必須項目は `protocol.py` の `REQUIRED` で検証。
  接続時に `hello {token, app}` → `welcome`。
- 主なメッセージ（`protocol.py`、詳細は `docs/API.md`）

| 機能 | 依頼側 → ハブ | ハブ → 相手 | 方向 |
|---|---|---|---|
| タイムワープ転送 | `transfer.request {direction}` | `export.request` / `apply.request` | Maya ⇔ AE |
| シーン設定 | `settings.request {direction}` | `settings.export.request` / `settings.apply.request` | Maya ⇔ AE |
| 解像度の枠 | `guide.request {comp}` | `guide.apply.request` | AE → Maya |
| キーのマーカー | `markers.request {export}` | `markers.apply.request` | AE → Maya |
| BG の位置（1 回送信） | `pixelmap.request {info}` | `pixelmap.apply.request` | AE → Maya |
| AE のレイヤー一覧 | `layers.request {[main_comp_id, main_comp]}` | `layers.export.request` | Maya が AE に問い合わせ |
| レイヤーの動き | `motion.request {comp_id, layer_id, via, times}` | `motion.export.request` | Maya が AE に問い合わせ |
| 時間の同期 | `time.sync {enabled}`, `time.update {t}` | `time.sync.state`, `time.set {t}` | Maya ⇔ AE |
| Origin frame | `timing.set {origin}` | `timing.state` | Maya ⇔ AE |

- 時間は秒（AE のコンプ時間）で送り、フレームへの換算は各アプリの境界で行う。Maya と AE の時間の対応は
  「Maya の Origin frame = AE のコンプの 0 秒」。
- タイムワープの交換データは中立カーブ（`schemas/`、`core/envelope.py`）。

---

## 2. 実装済み機能

| 機能 | 状態 | 根拠（主なコード） | 確認の範囲 |
|---|---|---|---|
| タイムワープ ⇔ タイムリマップの手動転送（両方向、Editable / Precision） | ✅ | `core/transfer.py`, `server/flow.py`, `syncbridge_maya/scene_timewarp.py`, `jsx` の `exportSelected` / `applyEnvelope` | Phase 1 で Maya 2024 ⇔ AE 26.5 の両方向を実機確認（Editable は誤差 0）。Precision は単体テストのみ（実機転送は先送り） |
| タイムワープの保存・復元・範囲変更（Maya） | ✅ | `snapshots.py`, `core/warp_edit.py` | 0.1.1 で配布 |
| AE ⇔ Maya のタイムスライダー同期（双方向） | ✅ | `core/time_sync.py`, `server/timesync.py`, `syncbridge_maya/time_sync.py`, `sbclient.js` | 利用者の PC で両方向を確認（少し遅れあり、H-AE-23 一部 ✅） |
| シーン設定の転送（FPS・再生範囲・アニメーション範囲・ピクセル縦横比、両方向） | 🧪 | `core/scene_sync.py`, `server/settings_flow.py`, `scene_settings.py`, プラグインのコマンド | mayapy 2023 / 2024 で 1 回の取り消しまで確認。GUI は未確認 |
| Origin frame と範囲の一元化（シーンに保存、AE と共有） | 🧪 | `timing.py`, `server/timesync.py`（`timing.*`） | テスト・mayapy。GUI は個別確認なし |
| AE のコンプの解像度の枠を Maya のビューに表示 | ✅ | `core/comp_guide.py`, `plug-ins/syncbridge_guide.py` | 利用者の PC（0.1.4） |
| AE のタイムリマップのキーを Maya のマーカーに | 🟡 | `core/markers.py`, `key_markers.py` | mayapy で確認。表示メニューでの出し入れはテスト用プラグインで Maya 2025 の GUI を確認 |
| **座標のアフィン変換**（AE レイヤー → コンプ、Maya カメラ → レンダー） | ✅ | `core/pixel_mapping.py`（`ae_layer_matrix`, `project`, `camera_affine`） | AE 26.5 の参照フレームと最大 0.042 px（H-AE-24）。Maya のレンダーで 0.010 px 以下（H-PM-1〜5, 8） |
| BG の位置の 1 回送信（AE パネル → Maya のカメラ） | ✅ | `PixelMapFlow`, `syncbridge_maya/pixel_mapping.py` `apply_from_ae` | 利用者が GUI で確認 |
| **Position / Rotation / Scale の転送** | 🟡 | `core/pixel_mapping.py`（`solve`, `solve_relative`）、方式 `film_roll` | 位置は GUI で確認。回転・拡大縮小は mayapy（42° で 0.036 px、170 % で 0.067 px）。GUI での回転・拡大縮小の再確認の記録はない |
| **Film Translate などによる構図の再現**（方式: Film Offset / Film Translate / 2D Pan/Zoom / Film Translate・Scale・Roll） | ✅ | `core/pixel_mapping.py` `METHODS`, `METHOD_ATTRS` | 位置は GUI。4 方式とも mayapy のレンダーで 0.010 px 以下 |
| **サブピクセル精度の座標合わせ** | ✅（位置）/ 🧪（その他） | 全て double で丸めない。解いた値で再計算して 9 点の誤差を確認（1 px 以上は断る、0.1 px 以上は警告） | レンダー比較で平均差 0.001〜0.010 / 255（素材カメラモードの切り抜き）。画素単位の比較は mayapy |
| 相対モード（基準のフレームからの動き、C = M₁·M₀⁻¹） | ✅ | `solve_relative`、`motion.record_reference` | GUI で転送を確認 |
| 素材カメラモード（素材を書き出したカメラから直接、基準なし） | ✅ | `solve_source`（C = 余白 · M · A(素材) · A(今の解像度)⁻¹） | mayapy でピクセル完全一致。利用者の GUI で動作 OK |
| レイヤーマップ（AE レイヤーと Maya レイヤーをノードでつなぐ） | ✅ | `layer_map_view.py`, `layer_map_window.py`, `core/layer_mapping.py` | GUI で確認 |
| Maya レイヤーごとの専用カメラ | ✅ | `layer_camera.py` | GUI で確認 |
| **アニメーション転送**（AE のレイヤーの動きを各フレームのキーに、全接続を 1 回で） | ✅ | `motion.py`, `motion_transfer.py`, `MotionFlow`, `jsx` の `layerMotion` | GUI で確認（1 本ずつ・まとめて） |
| ヌルの親による PAN | 🧪 | `ae_layer_matrix`（`parents`）、`jsx` の `parentChain` | mayapy で 80 px が正確。GUI は未確認（H-AE-30） |
| プリコンポごと動かす PAN（経路 `via`、`containers`） | ✅ | `findLayer`, `throughContainers`、`core/layer_mapping.py` | 利用者の GUI で PAN 込みの転送が合った（2026-10-26）。プリコンポの時間の伸縮・タイムリマップは未確認（H-AE-31） |
| レンダー解像度 ≠ コンプサイズ（余白） | 🧪 | `to_render_space` | mayapy |
| AE の選択でマップに出すレイヤーを決める、メインのコンポの記録（D-40） | ✅ | `layersInfo(args)`、`core/layer_mapping.py`（`show_ae`, `main_comp`, `reroutes`） | 利用者の GUI で動作 OK |
| **複数カメラのレイヤー合成**（専用ビューアー） | ✅ | `plug-ins/syncbridge_layer_stack.py`, `viewer_window.py` | GUI で重ねて表示・並べ替え・表示切り替え・枠を確認 |
| **Viewport 2.0 を利用した専用ビューアー** | ✅ | 同上 | 同上 |
| ビューアーからのアニメーション転送 | ✅ | `motion_transfer.MotionTransfer` | GUI で確認 |
| モニター（ハブの一覧・履歴・ログ・停止） | ✅ | `monitor/` | 0.1.3 から配布 |
| インストーラー（ターミナル不要、Maya のシェルフ、署名した AE パネル） | ✅ | `packaging/` | 0.1.4〜0.1.5 で利用者の PC。0.1.8 / 0.1.9 のインストール版は未確認 |

---

## 3. 専用ビューアーの技術構成

### 3.1 Viewport 2.0 の利用方法
- Viewport 2.0 の **レンダーオーバーライド**（`MRenderOverride`）をプラグイン `syncbridge_layer_stack.py` で登録
  （`LayerStackOverride`、名前 `SyncBridgeLayerStack`）。
- ビューアーのウィンドウ（`viewer_window.ViewerWindow`）は自前の `modelPanel` を Qt のレイアウトに埋め込み（H-MY-34 ✅）、
  そのパネルだけにオーバーライドを設定する。普通のビューポートやシーンは変えない。
- 描くレイヤーの情報は、Python 側（`layer_stack.publish`）が `__main__._syncbridge_layer_stack =
  {version, layers, overlay, margin}` に置き、プラグインが描く直前に読む（スクリプトの再読み込みとプラグインを分けるため）。

### 3.2 複数カメラの描画・合成方式
- 1 コマの描画 = レイヤーごとの `LayerPass`（`MSceneRender`）+ `FrameHUD` + 表示。
  - `LayerPass.cameraOverride()`: そのレイヤーの**専用カメラ**で描く（Film Offset / Pan / Zoom なども効く）。
  - `LayerPass.objectSetOverride()`: そのレイヤーのオブジェクト（と子）だけを描く。
  - `clearOperation()`: 最初のパスは全部消し、2 つ目以降は**奥行きだけ消す**（色は残す）→ 上のレイヤーが必ず手前。
- パスはプールで使い回す（表示の切り替えを速く繰り返すと Maya が落ちた問題の対策）。
- **余白**（枠のまわりを見せる）: カメラの値は変えず、`core/stack_view.py` でカメラのモデルから投影行列を作り、
  `MCameraOverride.mProjectionMatrix` に渡す（奥行きの列は Maya の投影から写す）。mayapy で Maya の視野と 0.0008 px 以内。
  GUI での確認は未記録（H-MY-37 ❓）。
- **解像度の枠**: `FrameHUD` が `core/view_frame.frame_rect` で、フィルムバック・Film Fit・余白だけから位置を決めて描く
  （Film Translate などで枠が動かない、D-34）。枠の外を暗くする帯、左上の外にラベル。
- ビューアーのパネル自体のカメラは、表示・非表示に関係なく**一番上のレイヤーの元のカメラ**
  （`core.layer_mapping.view_camera_uuid`）。枠の大きさはそのカメラの枠、なければほかのカメラの枠の大きさ。

### 3.3 Alpha 処理・レイヤー順序
- **レイヤー順序**: ビューアー下の一覧（`layer_stack_view.LayerStackList`）でドラッグして並べ替え、シーンに保存（1 回の undo）。
  順序は奥行きの消去で強制する（3D の前後関係ではなく、一覧の順番が優先）。
- **Alpha**: 専用の合成処理はない。各パスは Viewport 2.0 の普通の描画なので、テクスチャの透明度やマテリアルの
  透明度が効き、下のレイヤーが透けて見える**はず**という仮説（H-MY-35 ❓、未確認）。後処理（SSAO・DOF など）の
  レイヤーごとの効き方は不明。

### 3.4 キャラクター操作と描画更新の仕組み
- **ビューアーの中での操作のための専用機能はない**（⬜）。ビューアーは Maya の `modelPanel` なので、Maya 標準の選択・
  マニピュレーターの操作が技術的には効く可能性があるが、**検証していない**。
  - 注意（構造上のリスク）: 選択や操作は Maya がパネルのカメラ（一番上のレイヤーの元のカメラ）で行う。ほかのカメラ・
    2D の値で描かれたレイヤーでは、見えている位置とクリックの位置が合わない可能性が高い。
- **描画の更新**:
  - 時間の移動やアニメーションの再生は、Maya が普通にビューを描き直すので、そのまま反映される。
  - レイヤー構成の変更（並べ替え・表示・レイヤーマップの編集・undo/redo・シーンを開く）は `scriptJob` とサービスの
    イベントで受け、30 ms のタイマーでまとめてから `layer_stack.publish()`（`scheduleRefreshAllViews`、強制再描画はしない）。

### 3.5 パフォーマンス上の制約
- 1 回の描画でレイヤーの数だけシーンを描く（N レイヤー = N パス）。重いシーンでは単純に N 倍近くかかると考えられるが、
  **計測していない**。
- 速い切り替えでのクラッシュは、パスの使い回しと遅延した更新で解消（利用者の GUI で確認）。
- 平行投影のカメラには余白を効かせない（警告のみ）。

---

## 4. 同期の仕組み

### 4.1 AE → Maya
| 何を | 流れ |
|---|---|
| タイムリマップ → Scene Time Warp | AE パネル → `transfer.request` → ハブが AE から export → `core/transfer` で変換 → Maya に apply（確認、バックアップ、1 回の undo、読み戻しで検証） |
| BG の位置（1 回） | AE パネルで選んだレイヤー → `pixelMapInfo` → `pixelmap.request` → Maya が `core.pixel_mapping` で解いてカメラに設定 |
| レイヤーの動き（アニメーション） | Maya のレイヤーマップ / ビューアーから範囲を指定 → `motion.request`（接続ごと、各フレームの AE 時間）→ AE の `layerMotion` が各時間の変換・親・プリコンポを返す → Maya が `core.motion` で解く → 確認 → キー（全接続で 1 回の undo）→ 読み戻し |
| マーカー・解像度の枠・シーン設定 | 各フロー（`MarkerFlow`, `GuideFlow`, `SettingsFlow`） |

### 4.2 Maya → AE
| 何を | 状態 |
|---|---|
| Scene Time Warp → タイムリマップ | ✅（手動） |
| シーン設定 | 🧪（手動） |
| 時間（タイムスライダー） | ✅ |
| **カメラの動き → AE のレイヤーの位置（Pixel Mapping の逆方向）** | ⬜ 未実装（`core/layer_mapping.DIRECTIONS = ("ae2maya",)`） |

### 4.3 自動同期と手動同期
- **手動同期**: タイムワープ、シーン設定、BG の位置、アニメーション転送、マーカー、枠。すべてボタンで送る。
- **自動（ライブ）**: タイムスライダーの同期だけ。
  - Maya → AE: `timeChanged` で、スクラブ中は 1 秒に 30 回まで（最後の位置は必ず送る）。再生中に送るかは切り替え（既定はオフ）。
  - AE → Maya: AE には時間の通知がないので、パネルが 0.05 秒ごとに `comp.time` を読む。
  - 往復の防止: 受け取った時間は送り返さない（Maya の `EchoGuard`、AE は最後に適用した時間と比較）。
- **仕様の Phase 5（タイムワープ・レイヤーなどの片方向 → 双方向の自動同期）**: ⬜ 未実装。
  イベント ID・リビジョン・差分検出などの仕組みは仕様のみ（`docs/SPEC.md`）。

### 4.4 座標変換アルゴリズム（Pixel Mapping）
- 共通の座標は**元画像（素材）の画素座標**（左上が原点、y 下、double）。
- **AE**: `M = 位置 · R(回転) · S(スケール) · (−アンカー)`。親は左から掛け、プリコンポのレイヤーも外側から順に掛ける
  （`ae_layer_matrix`）。M は「素材 → コンプ」の 3×3 アフィン行列。3D レイヤーは断る。
- **Maya**: 透視の割り算のあと、Film Offset → 2D Pan →（NDC）→ ÷ Zoom → × Pre Scale → Film Roll / Film Translate →
  × Post Scale → 画素。透視の割り算のあとはすべて 2D のアフィン変換（`project`、mayapy のレンダーで順序を確認、H-PM-8）。
- **ソルバー**:
  - 絶対モード: BG の板ポリ（UV）から「素材 → レンダー」を求め、AE と合うカメラの値を解く（`solve`）。
  - 相対モード: 基準 M₀ からの動き `C = M₁ · M₀⁻¹` を専用カメラの値にする（`solve_relative`。相似変換 → 平行移動の順で解く）。
  - 素材カメラモード: `C = 余白 · M · A(素材カメラ, 素材の大きさ) · A(素材カメラ, 今の解像度)⁻¹`（`solve_source`）。
  - 解いた値で再計算し、画面の 9 点の誤差が 1 px 以上なら断り、0.1 px 以上なら警告。
- 余白つきのレンダー（レンダー解像度 ≠ コンプ）: `to_render_space` でコンプをレンダーの中央に同じ画素の大きさで置く。

### 4.5 同期精度と検証方法
| 対象 | 方法 | 結果 |
|---|---|---|
| タイムワープの変換 | 単体テスト、AE / Maya の実データの回帰テスト、読み戻し | Editable は実機で誤差 0。Precision は最大 0.0495 フレーム（テスト） |
| AE の行列 | AE 26.5 で参照フレームを書き出して測定（`pixel_mapping_reference.jsx`） | 最大 0.042 px |
| Maya のカメラのモデル | mayapy でテスト用の格子 BG をレンダーし、目印の重心を測定（`pixelcheck`、`tools/pixel_mapping/*.py`） | Hardware 2.0 で 0.010 px 以下（テクスチャの最大解像度オフ） |
| 素材カメラモード | 大判の切り抜きと専用カメラのレンダーを画素ごとに比較 | 差 0（完全一致）〜平均 0.010 / 255 |
| ビューアーの枠・余白 | mayapy で 192〜384 通り | 最大 0.0027 px / 0.0008 px |
| 応答性 | 利用者の操作感 | タイムスライダー同期に少し遅れ（AE の描き直しが主因）。数値の計測はない |

---

## 5. 未実装・開発途中の機能

### 5.1 現在の制約
- Pixel Mapping とアニメーション転送は **AE → Maya の片方向**だけ。
- AE の **3D レイヤー・カメラレイヤー（3D カメラでの PAN）** は断る（`ae_layer_matrix`）。次に対応する予定の候補。
- 形を変えるエフェクト（モーションタイルなど）は名前から判断できないので、注意を出すだけ。
- プリコンポは 3 段まで（`MAX_DEPTH = 3`）。
- Hardware 2.0 の「テクスチャの最大解像度」（既定オン）で大判の BG が縮められ、最大 1.4 px ずれる。シーンの設定は変えず、知らせるだけ。
- Image Plane は位置合わせの基準に使えない（画素単位に丸められる・Software で約 3 px ずれる）。
- Overscan は 1.0 で確認する方針（解像度ゲートの表示中は Overscan 1.3 になり、ビューポートとレンダーで見え方が違う）。
  専用カメラは常に 1.0。
- 平行投影のカメラでは Film Offset / 2D Pan がレンダーに効かない（Film Translate を使う）。
- レイヤーごとに別の時間（コマ打ち）でビューアーに描くことはできない（利用者の判断で見送り）。

### 5.2 未確認のケース（コードはあるが実機で未確認）
- ヌルの親の PAN（H-AE-30）、プリコンポの時間の伸縮・タイムリマップ（H-AE-31）、`CompItem.usedIn`（H-AE-33）。
- ビューアーの余白（H-MY-37）、ビューアーでの半透明の重なり（H-MY-35）、一番上のレイヤーを非表示にしたときの枠。
- シーン設定の転送の GUI での一連の流れ（H-MY-28 は mayapy のみ）。
- 回転・拡大縮小の転送の GUI での再確認。
- Precision モードの実機転送。
- 0.1.8 / 0.1.9 のインストール版での動作、Python のない PC（H-PKG-2）、ウイルス対策ソフト（H-PKG-1）。
- ビューアーの中での Maya 標準の選択・操作。

### 5.3 既知の不具合・注意
- 古いハブが動いたままだと、新しいメッセージの項目を落とす（例: メインのコンポの指定）。サーバー側のコードを変えたら
  ハブの再起動が必要。Maya 側は、AE から違うコンポが返ったら何も変えずに知らせる安全策あり。
- Maya の `animCurveTT` で区間より長い接線のハンドル（H-MY-13）は未解決（警告のみ）。
- 0.1.0 で見つかった、素材より長いタイムワープで AE の書き込みが失敗する問題は、事前の長さ確認で対処済み。

### 5.4 今後の開発予定・構想
| 項目 | 段階 |
|---|---|
| AE のカメラレイヤー（3D）での PAN | 次の候補（未着手） |
| PAN を 1 か所で持つ「カメラワーク用のノード」 | 構想（利用者の判断で保留） |
| Maya → AE の Pixel Mapping（カメラの動き → レイヤーの位置） | 構想（仕様に方向の項目のみ） |
| 自動同期（Phase 5） | 仕様のみ |
| アップデーター（Phase 6） | 未実装（`src/syncbridge/updater/` は空） |
| 仕様の B Full（見た目の一致の検証） | 将来 |
