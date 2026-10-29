# 進捗

## 現在の状態

- **フェーズ:** **Phase 1（通信基盤）完了**（2026-10-16）。Maya 2024 と AE 26.5 のパネルから、ローカルサーバー経由で
  両方向の手動転送ができる（V-P1C 合格）。詳細は `docs/PHASE1_PLAN.md`。
- **先行配布 0.1.0 を作成**（D-14、`docs/RELEASE.md`）: ターミナル不要のインストーラー。**利用者の PC での確認は未実施**。
  Phase 0 は P0-1〜P0-4 合格、P0-5 は Editable のみ合格、Precision の実機転送とレンダー比較（P0-6）は先送り（下の「先送りにしたもの」）
- **最終更新:** 2026-10-16

## 実装済み

| 機能 | 場所 | 状態 |
|---|---|---|
| 有理数 fps、Maya 時間単位、フレーム ⇔ 秒 | `core/timebase.py` | ✅ テスト済 |
| 中立カーブ（LINEAR/BEZIER/HOLD、外挿、アフィン変換、JSON） | `core/curve.py` | ✅ テスト済 |
| AE Time Remap 形式 ⇔ 中立カーブ | `core/ae_codec.py` | ✅ AE 26.5 の実データで誤差 0（H-AE-3/6/12） |
| Maya animCurveTT 形式 ⇔ 中立カーブ | `core/maya_codec.py` | ✅ Maya 2024 の実データで誤差 0（H-MY-4/5/7/11）。区間より長いハンドル（H-MY-13）は未解決で警告のみ |
| Maya ⇔ AE の時間軸の対応 | `core/mapping.py` | ✅ テスト済 |
| Precision モード（適応的な区分線形、サブフレームでの検証） | `core/sampler.py` | ✅ テスト済 |
| 誤差計測とレポート | `core/validation.py` | ✅ テスト済 |
| 変換パイプライン（Editable/Precision、両方向、3 種類の誤差レポート） | `core/transfer.py` | ✅ テスト済 |
| 交換エンベロープ、JSON Schema | `core/envelope.py`, `schemas/` | ✅ テスト済 |
| CLI（maya2ae, ae2maya, readback, probe-vectors, verify-ae-probe, selftest） | `cli.py` | ✅ テスト済 |
| Maya アダプタ（検索、読み書き、export/apply、バックアップ、リードバック） | `maya_plugin/.../` | ⚠ Maya 2024 で読み書きとも確認（プローブ経由）。`export_timewarp` / `apply_timewarp` は未実行。ダミー cmds で回帰テスト |
| Maya プローブ | `maya_plugin/.../probe.py` | ✅ Maya 2024 で 4 回実行（PHASE0_RESEARCH.md 8 章 #5〜#7） |
| Maya の実データによる回帰テスト | `tests/fixtures/maya2024_probe_run3.json`, `tests/unit/test_maya_real_data.py` | ✅ |
| AE スクリプト（Export/Apply、バックアップ、undo） | `after_effects/jsx/syncbridge_ae.jsx` | ✅ AE 26.5 で Export と Apply（バックアップ、リードバック）を確認。ファイル選択の変更後の版は未実行 |
| AE プローブ | `after_effects/jsx/probe_ae.jsx` | ✅ AE 26.5 で 2 回実行、2 回目は 13 ベクトル全て誤差 0 |
| AE の実データによる回帰テスト | `tests/fixtures/ae26.5_probe_run2.json`, `tests/unit/test_ae_real_data.py` | ✅ |
| ES3 用 JSON | `after_effects/jsx/syncbridge_json.jsxinc` | ✅ Node で Python の json と往復確認 |
| CI（Windows/Ubuntu × Python 3.9/3.11） | `.github/workflows/tests.yml` | ✅ 2026-10-16 の push で実行、利用者が確認。サーバー用 job は追加後未実行 |
| 変換手順の共通化（CLI とサーバー） | `core/jobs.py` | ✅ テスト済（D-13） |
| プロトコル（Phase 1） | `protocol.py` | ✅ テスト済 |
| Local Sync Server（認証、二重起動防止、自動終了、手動転送の手順） | `server/`, `syncbridge-server.cmd` | ✅ 偽クライアントで 18 件のテスト。実際の Maya/AE とは未接続 |
| ハブの管理 API、転送の履歴、ログ、ハブごとのセッションファイル、ハブの発見・強制終了（P-A） | `server/admin.py`, `server/hubstate.py`, `hubs.py` | ✅ テスト済（16 件）。実際のハブで発見と停止を確認。インストール版では未確認 |
| モニター（ハブの一覧、接続中のアプリ、履歴、ログ、停止・強制終了・切断）、ハブのログファイル（P-B） | `monitor/`, `syncbridge-monitor.cmd` | ✅ テスト済（Qt は offscreen）。利用者の画面では未確認 |
| AE のコンプの解像度の枠を Maya のビューに表示（D-16） | `core/comp_guide.py`, `maya_plugin/plug-ins/`, `syncbridge_maya/comp_guide.py`, `server/guide_flow.py`, AE パネル | ⚠ テスト済（偽の maya、Node）。Maya と AE では未実行 |
| AE のタイムリマップのキーを Maya のマーカーに（D-18） | `core/markers.py`, `server/relay.py`, `syncbridge_maya/key_markers.py`, プラグイン, AE パネル | ⚠ テスト済、mayapy 2023 / 2024 で確認。GUI の描画と AE からの送信は未確認 |
| クライアント（stdlib の WebSocket、SyncClient、サーバーの自動起動） | `client/` | ✅ テスト済（stdlib のテストサーバーと本物のサーバーの両方） |
| Maya の接続（service）と最小パネル（ui） | `maya_plugin/.../service.py`, `ui.py` | ✅ Maya 2024 で V-P1B 合格（AE は代役）。その後のログ表示の改善は Maya で未確認 |
| AE の代役 | `tools/fake_ae.py` | ✅ 本物のサーバーと実データで両方向を確認 |
| AE の CEP パネル（manifest、画面、通信、ExtendScript の窓口） | `after_effects/CSXS`, `panel/`, `jsx/syncbridge_cep_host.jsx` | ✅ AE 26.5 で V-P1C 合格（両方向、取り消し、日本語の警告、切断）。通信部分は Node のテストも |

| 納品用のクリーンアップ（D-47） | `syncbridge_maya/cleanup.py`, `cleanup_dialog.py`, パネルの「その他」 | ✅ mayapy 2023 / 2024（`tools/maya_cleanup_check.py`）と GUI の Maya 2023 / 2024 で確認。接続中・リアルタイム同期中の実行は未確認 |

## テスト結果

### 2026-10-29（Windows 11, Python 3.10.6）

- **納品用のクリーンアップ（D-47、利用者の要望）:** Maya のパネルの「その他 → 納品 → 納品用のクリーンアップ…」。
  - 消すもの: レイヤーマップ、キーのマーカー（ブックマーク）、Origin frame の記録、ビューアー・解像度の枠などの表示用のノード。
  - 専用カメラは確認画面でその都度選ぶ（既定は「普通のカメラとして残す」= 目印の属性とロックを外し、キーと接続は保つ）。
  - Scene Time Warp は残す（利用者の決定）。JSON バックアップ、シーンのデータは 1 回の undo で戻る。ビューアーとレイヤーマップは閉じ、
    リアルタイム同期はオフにする。
  - `tools/maya_cleanup_check.py`: mayapy 2023 / 2024 で 13 項目すべて PASS。
    - 保存した .ma に SyncBridge のノードが残らない。`requires` は Maya だけ（利用者のブックマークがあれば `timeSliderBookmark` は残る）。
    - 残したカメラはキー 2 個と元のカメラからの接続を保つ。タイムワープと利用者のブックマークは残る。
  - モック（mayapy、offscreen）: パネルの「その他」タブと確認画面（カメラあり・なし）。
  - **GUI の Maya 2023 / 2024**（スクラッチの `gui_cleanup_check.py`、確認画面だけ差し替え）: パネル・ビューアー・レイヤーマップを開いた
    状態でボタンから実行 → 両方のウィンドウが閉じ、ビューアーのノード 0、取り消し 1 回で専用カメラの目印とデータが戻り、ビューアーを
    開き直せた。カメラを消す方も、取り消し 1 回で戻った。
    - 最初は 1 回目の取り消しが Maya の `selectionMaskResetAll` に使われた。ビューアーを閉じると Maya が少し後に積むため（H-MY-46）。
      ウィンドウを先に閉じ、本体を `evalDeferred`（lowestPriority）で後に回して直した。
  - ついでの修正: `viewer_camera._unwatch` が mayapy で落ちた（scriptJob が None を返す）。None を飛ばす。
  - テスト: 408 件 OK（`.venv` / `py -3`、106 件スキップ）。
  - **未確認:** SyncBridge のサーバーに接続中・リアルタイム同期中の実行（同期をオフにする処理）。
- **0.1.17 をリリース**（利用者の指示）: 版を 4 か所で 0.1.17 に、`build_release.py`（テスト込み）で zip と EXE を作り、
  GitHub Releases にプレリリースとして公開。記録は `docs/RELEASE.md` の 6 章、リリースノートは `docs/release_notes/0.1.17.md`。

### 2026-10-27（Windows 11, Python 3.10.6）

- **ビューアーの 2D Pan/Zoom・解像度の枠・ゲートの修正（未コミット、利用者の指示）:**
  - **2D Pan/Zoom:** 余白なし（Pan 0・Zoom 1）のときは、ビューカメラの `panZoomEnabled` を OFF にする（`viewer_camera.set_view`）。
    Maya の `panZoom` は値を変えても ON にしなかったので、ビューカメラの Pan/Zoom を scriptJob で見張り、値に合わせて ON/OFF する（H-MY-43）。
  - **解像度の枠:** ボタンを切り替え式にした（optionVar `syncBridgeViewerFrame`、既定 ON）。大きさは Maya のレンダー設定。
    プラグイン（r14）が描くたびに読むので、AE と接続していなくても、レンダー設定を変えるとすぐ合う。ラベルは「Maya 2048x858」。
    以前は、パネルの「解像度の枠」で最後に入力した大きさ（既定 1920×1080）の comp guide ノードを描いていた。そのため数値が Maya とも AE とも合わず、ボタンで消せなかった。
    AE パネルから送る枠（comp guide ノード）は、普通のビューにだけ出る。
  - **ゲート:** ビューカメラの解像度ゲート・フィルムゲートが ON になったら、scriptJob ですぐ OFF に戻し、Overscan を 1.0 に戻す。
    警告はスクリプトエディタ（`cmds.warning`）とビューアーの状態の欄に出す。編集中のレイヤーがないとき（元のカメラで見ているとき）は止めない。
  - **確認:** スクラッチの `gui_frame_check.py` で、Maya 2023 / 2024 の両方で次を確認した（撮影するときはビューアーを最前面に）。
    - 枠の ON/OFF とラベル「Maya 2048x858」。
    - 余白なしで OFF、20% で ON。
    - `panZoom` の後に ON（レイヤーを切り替えた後も同じ）。
    - ゲートとフィルムゲートが OFF に戻り、Overscan が 1.0 になる。
    - `inViewMessage` の表示は撮影では見えなかった（メインのビューに出る可能性）。
  - **任意の枠（利用者の指示: AE のメインのコンポが絵より少し広いことがある）:** バーに「任意の枠」と幅×高さを追加した
    （optionVar `syncBridgeViewerCustomFrame` / `syncBridgeViewerCustomSize`）。
    - 水色の枠で、レンダー解像度の枠と同じく中央に描く。大きさは、レンダー解像度を基準にした比率で決まる。
    - ラベル「Custom 2200x1000」は、枠の左下の外に出す。
    - レンダー解像度の枠を消すと、任意の枠の外を暗くする。
    - Maya 2023 / 2024 で、2200×1000（外側）、1920×800 だけ、OFF を撮影して確認した。
  - テスト 390 件 OK。
  - 利用者の指示で版を **0.1.14** に上げて zip を作った（リリースはまだ）。
    - `dist\SyncBridge-0.1.14.zip` 45.9MB、SHA-256 dac28f2c…、296 ファイル、ビルド中のテスト OK、AE パネルの署名と検証 OK。
    - プラグイン r14・ゲートの阻止・任意の枠が入っていて、証明書・シーンは入っていないことを確認。
- **マニピュレーターで動かすと選択が外れる問題の修正（未コミット、利用者の報告、0.1.12 の実機で。ずれは直ったと確認済み）:**
  - 原因: ビューのクリックは押した時点で取っていて、選択中のもののピボットから 60 px 以内だけ Maya に渡していた。
    移動の矢印の先（約 100 px）をつかむと、その下にある別レイヤーのメッシュに切り替わり、そちらが選ばれていた。
  - 修正（`viewer_window.eventFilter` / `_click`、`viewer_pick.on_selection`。`near_selection` は削除）:
    - マウスは常に Maya に渡す。
    - 押した位置のまま離したとき（4 px 以内）だけ、Maya の選択の後で（QTimer 0）切り替えを判定する。
    - 選択が変わらず、選択中のメッシュもカーソルの下にないときは、マニピュレーターのクリックとみなす。
  - 確認: スクラッチの `gui_manip_check.py`（CHAR を細くして、X の矢印の先が BG の上に来るようにした）。Maya 2023 / 2024 の両方で次を確認した。
    - 矢印の先のドラッグで CHAR が 0.4 → 0.91 動き、選択と編集中レイヤーはそのまま。
    - 矢印の先のクリックだけでは切り替わらない。
    - BG のクリックで BG へ、BG を選んだまま CHAR のクリックで CHAR へ切り替わる。
  - テスト 390 件 OK。未確認: 利用者の実際のシーンでの操作。
  - 利用者の指示で版を **0.1.13** に上げて zip を作った（リリースはまだ）。
    - `dist\SyncBridge-0.1.13.zip` 45.9MB、SHA-256 54e86103…、296 ファイル、ビルド中のテスト OK、AE パネルの署名と検証 OK。
    - 新しいクリック判定（`on_selection`）が入っていて、証明書・シーンは入っていないことを確認。
- **ビューアーの切り替え時のずれと、残っていた複数のマニピュレーターの修正（未コミット、利用者の報告、0.1.11 の実機で）:**
  - **ずれ:** `core.stack_view.match_view` を追加した。切り替える前の見え方を、新しいカメラで同じにする Pan/Zoom を求める。
    これを `ViewerWindow._current_view` / `_keep_view` で使う。単体テスト 1 件（ロール・Film Translate・Scale・縦のフィットの 3 カメラで一致）。
  - **マニピュレーター:** r12 のフィルターは `kRenderNonShadedItems` = `kRenderUIItems` で効いていなかった。
    プラグイン r13 で `objectTypeExclusions` を使い、32 ビットに収まるフラグだけで作った（H-MY-42）。
  - **Maya 2024 のクラッシュ:** 切り替えのとき `modelEditor -camera` の中で落ちた
    （`TmodelPane::cameraOrthographicModified`。今回のビューカメラの移動で起きたもので、利用者の環境では未発生）。
    ビューカメラの `orthographic` をつながない、パネルのカメラは UUID で比べる、で直した。
  - **確認（今回から GUI の Maya を自動で起動して撮影）:**
    - 方法: スクラッチの `gui_viewer_check.py`。`maya.exe -script`、`MAYA_APP_DIR` を別のフォルダにして利用者の設定には触れない。
    - Maya 2023 / 2024 の両方で次を確認した。
      - 切り替えの前後で、画像と見え方の数値が同じ。
      - マニピュレーターが 1 つ。
      - X の矢印のドラッグで、CHAR が X だけ 0.4 → 0.91 動く。
      - ビューのクリックで編集中のレイヤーと選択が替わる。
      - クラッシュなし。
    - テスト 390 件 OK。mayapy の移動の確認も PASS。
  - 未確認: 利用者の実際のシーン（リグ・キー付き）での操作感。
  - 利用者の指示で版を **0.1.12** に上げて zip を作った（リリースはまだ）。
    - `dist\SyncBridge-0.1.12.zip` 45.9MB、SHA-256 c2918039…、296 ファイル、テスト 390 件 OK。
    - プラグイン r13・`match_view`・版 0.1.12 が入っていて、証明書・シーンは入っていないことを確認。
- **ビューアーのチラつきと複数のマニピュレーターの修正（D-44 の追記、未コミット、利用者の報告）:**
  - 編集中のレイヤーを替えるとチラつく問題: `viewer_camera.ensure` は、ビューカメラを作り直さずに新しい専用カメラの子へ移し、
    つなぎ直すようにした（`_follow` / `_link` / `_fold_nodes`）。`ViewerWindow.set_editing` は、ビューカメラの移動・
    `publish`・パネルのカメラをその場で行う（`_sync_view`）。パネルのカメラは変わったときだけ設定する。
  - マニピュレーターが複数出て動かせない問題: プラグイン r12 で、レイヤーのパスは `renderFilterOverride` で UI を描かない。
    最後の `ManipulatorPass` が、ビューカメラで UI だけを全レイヤーの上に描く（H-MY-42 ❓）。
  - **確認:**
    - mayapy 2023 / 2024 の確認スクリプト（スクラッチ）が RESULT PASS。
      - A → B → A と移しても同じノードのまま。
      - B の焦点距離、Film Offset + Pan、Pre Scale ÷ Zoom（値を変えても追従）。
      - A へのつながりは残らず、ユーティリティノードは 4 つのまま。
      - 取り消しの履歴は変わらない。
      - プラグイン r12 が読み込める。
    - テスト 389 件 OK。
    - H-MY-41 は利用者の確認で ✅。
  - **GUI では未確認:** チラつきが消えたか、マニピュレーターが 1 つで動かせるか（H-MY-42）。
  - 会社の PC で試すために 0.1.10 の zip を作り直した（同じ版のまま上書き、リリースはしない）。
    `dist\SyncBridge-0.1.10.zip` 45.9MB、SHA-256 7629054e…、プラグイン r12 と `viewer_camera._follow` が入っていることを確認
  - 利用者の指示で版を **0.1.11** に上げた（`version.json`、`pyproject.toml`、`__init__.py`、AE の `manifest.xml` 2 か所）。
    `dist\SyncBridge-0.1.11.zip` 45.9MB、SHA-256 065364d3…、296 ファイル、テスト 389 件 OK、
    プラグイン r12、証明書・シーンなし。リリースはまだ（リリースノートとタグは未作成）
- **0.1.10 の zip を作成（リリースはまだ、利用者の指示）:** `packaging\build_release.py` でテスト → ビルド → 署名 → zip。
  `dist\SyncBridge-0.1.10.zip` 45.9MB、SHA-256 001245a6…、296 ファイル。新しいファイル（`viewer_camera.py`, `viewer_pick.py`,
  `live_sync.py`, `server/livesync.py`, プラグイン r11）が入り、証明書・シーンが入っていないことを確認。
  利用者の PC で film_roll への変更後に BG・BOOK・CHAR が AE と一致することを開発用の状態で確認。
  **ビューアーでの選択操作はまだ不安定（H-MY-38/40 未解決）、インストール版での確認は未実施、未コミット**
- **ビューアーの編集中レイヤーと 2D パン・ズーム（D-44、未コミット、利用者の要望）:** 新規 `viewer_camera.py`
  （SB ビューカメラ）、`viewer_pick.py`（クリックしたレイヤーの判定）、`core.stack_view` に `compose` / `invert` /
  `fold_pan_zoom` / `with_view` / `view_affine` / `ray_direction`、プラグイン r11（編集中はビューカメラ、ほかは同じ変化、枠も）、
  `layer_stack.editing`、ビューアー（「編集中: …」、一覧の行クリック・「（編集中）」、「ズームを戻す」、クリックの監視）。
  - テスト 389 件 OK（`test_stack_view` に 4 件）。mayapy 2023 で 18 項目 PASS（ビューカメラの描き方が専用カメラと一致、
    保存されない、プラグイン r11 の読み込み、CHAR / BG のクリック判定、ピボット付近の判定、片付け）。
  - **未確認（実機 GUI、H-MY-38・H-MY-40）:** Maya の選択・移動が編集中のレイヤーで見た目どおりか、\ キーの 2D Pan/Zoom で
    ほかのレイヤーと枠が一緒に動くか、ほかのレイヤーのクリックで切り替わるか、Alt＋ドラッグでビューカメラが動かないか、
    取り消しの履歴にビューカメラの作成が入らないか（mayapy では確かめられなかった）。
  - 実機 1 回目（利用者）: 編集中の CHAR だけ大きく見えた。`tools/viewer_diagnose.py` でビューカメラの値は正しいと確認
    （Zoom 1.3 = 余白）。パスはカメラ自身の投影で描き、Render Pan Zoom オフだと 2D Pan/Zoom が入らないと推定（H-MY-41）
    → ビューカメラの Render Pan Zoom をオンに（既存のビューカメラも次の更新で直す）。
  - 実機 2 回目（利用者）: レイヤーと枠は一緒に動いた。BG・BOOK が AE と合わない → D-43 の既定が Film Translate で、
    横 3 倍のプレートの拡大縮小が表せなかった。利用者の意図は Film Translate・Scale・Roll だったので既定を `film_roll` に。
    利用者のシーンの既存の接続は、スクリプトか右の欄で方式を変える。
- **AE の選択を追加すると、つないだ Maya レイヤーを自動で作る（D-43、未コミット、利用者の要望）:** 1 対 1、素材カメラ・
  Film Translate。カメラ・オブジェクトは手で設定。`core.layer_mapping.add_linked_layer` / `has_camera`、
  `layer_mapping.add_ae_layers`、`layer_map_window.add_ae_selection`。カメラ未設定の接続は転送・リアルタイム同期・1 回送信で
  理由を出して飛ばす。テスト 384 件 OK（単体テスト 1 件追加）。mayapy 2023 で: 3 個追加 → 3 レイヤー・3 接続、
  もう一度押しても増えない、取り消し 1 回で全部戻る・やり直し、カメラ設定で専用カメラができ接続が付く、転送の対象になる。
  マップの撮影 `docs/ui_audit/auto_layers_map.png`。**未確認: 実機の AE から追加すること。**
  - 続けて「新しい接続」の選択欄を外した（利用者の指示）。手でつなぐときも素材カメラ・Film Translate、線ごとの変更は右の欄で。
    同じ名前のつながっていない Maya レイヤーがあれば作らずに使う（`make_test_pan_scene.py` の CHAR / BOOK / BG もそれで使える）。
    検証ツール `maya_motion_check` / `maya_pan_margin_check` / `maya_source_camera_check` は方式とモードを明示して渡すように
    直し、mayapy 2023 で 3 本とも RESULT PASS。テスト 385 件 OK。
- **ビューアーの枠の外の濃さを調整できるように（未コミット、利用者の要望）:** `viewer_window.py` の上のバーに「枠の外」
  スライダー（0〜100%、既定 50%）。`layer_stack.shade` / `set_shade`（optionVar `syncBridgeViewerShade`）、
  プラグイン `syncbridge_layer_stack.py` は r10 で `shade_color` を使う。mayapy 2023 で設定 → プラグインへの受け渡しと
  範囲外の値の丸めを確認、`.venv` で 383 件 OK、バーのモック `docs/ui_audit/viewer_shade.png`。**未確認: 実機のビューで濃さが変わること**
  （SB Dev でプラグインも読み直される。ビューのレンダラー名が「r10」になっているか）。
- Maya パネルのタブの黒い縁: `QTabBar::tab` のスタイルシートを外して Maya 標準のタブに（利用者の指摘、実機で未確認）。
- AE パネルが古いまま: この PC は 0.1.10 のインストール版（リンクでない）だった。アンインストール → `tools\dev_env_on.ps1` を
  利用者が実行する手順を案内。
- **Maya パネル・AE パネルを改善案のとおりに実装（D-42、未コミット）:** `maya_plugin/scripts/syncbridge_maya/ui.py`
  （状態の ●、Origin frame、タブ 4 つ、詳細の折りたたみ、レイヤーのタブにリアルタイム同期とアニメーション転送、ログを日本語に）、
  `after_effects/panel/js/main.js`・`css/panel.css`（状態、選択中のレイヤーの枠、タイムワープ・Maya へ送る・同期・シーン設定、
  詳細は `<details>`）、`manifest.xml` の既定の高さ 460 → 680。ボタン名「レイヤーの初期位置を Maya へ」に合わせて
  `motion.py`・`core/motion.py` の案内文、`PIXEL_MAPPING.md` も直した。
  - テスト: `.venv` で 383 件 OK、`node --check main.js` OK。
  - 見た目: mayapy 2023 / 2024 で本物の `ui.py` を撮影（`docs/ui_audit/new_maya_panel.png`、接続中は service を差し替えた表示）、
    AE はブラウザで本物のパネルを幅 320 で撮影（`docs/ui_audit/new_ae_panel.png`、接続中は表示だけ書き換え）。
  - **未確認: 実機の Maya・AE で触ること**（タブの記憶、詳細の開閉、AE の `<details>` が CEP で開くか、状態の ● の更新）。
- **UI/UX の現状調査 `docs/UI_UX_AUDIT.md`（未コミット、利用者の依頼、調査のみ）:** 画面 7 つ・ダイアログ 12 種、構成図、各画面の詳細、
  ワークフロー 9 つとステップ数、UX の課題（事実と推測を区別）、整理の候補。実際の UI のコードを Maya・AE の外で描いたモック画像
  `docs/ui_audit/*.png`（実機のスクリーンショットではない）。
- **Maya パネル・AE パネルの改善案のモック（未コミット、利用者が検討中）:** `docs/ui_audit/proposal/`
  （`proposal_maya_compare.png` ほか。Maya はタブ 4 つ「タイムワープ / 同期・設定 / レイヤー / その他」、上に状態の ●、Origin frame は上、
  Mode・Tolerance は「詳細」にしまう（利用者: Mode はほぼ触らない）。AE は状態・選択中のレイヤー・タイムワープ・Maya へ送る・同期・
  シーン設定の順。作成スクリプト `maya_panel_mock.py`、`ae_panel_mock.html`）。→ 10-27 に利用者が承認し実装（上の D-42）。
  利用者の指示（10-27）: AE の「BG の位置を Maya のカメラへ」は実質は基準の設定なので「レイヤーの初期位置を Maya へ」にする
  （実装時は `motion.py`・`core/motion.py`・`ui.py`・`main.js` のログ・案内の文、`docs/PIXEL_MAPPING.md` の手順の名前も直す）。
  Maya のタブは「その他」（ひらがなにしない）。
  左右の順はモックのまま（そのパネルから見た向き）で実装した。元の未決: 送る / 読み込むボタンの左右の順（Maya 案は「AE へ」が左、AE 案は「Maya から」が左）を揃えるか。
- 未コミットのもの: リアルタイム同期（D-41）、テスト版 0.1.10 のバージョン（4 か所）、この調査とモック、`make_test_pan_scene.py`、
  `docs/STATUS_REPORT_2026-10-26.md`。テスト版 0.1.10 は会社の PC で実機確認待ち。

### 2026-10-26（Windows 11, Python 3.10.6）

- **リアルタイム同期 AE → Maya（D-41、未コミット、利用者の要望）:** つないだ AE のレイヤーを変え終えると、専用カメラのキーを自動で更新。
  スイッチはレイヤーマップ・ビューアー・AE パネルで共通（ハブの `LiveSync`、`live.sync` / `live.watch` / `live.changed`）。
  AE: `layersFingerprint`（JSX）、パネルが 0.4 秒ごとに読み、次の読み取りで同じなら送る。Maya: `live_sync.py`（確認なし、
  1 回ごとに 1 回の undo、最初だけバックアップ、Maya で変わったキーは上書きしない）。テスト 383 件 OK（ハブ・パネルの検出・
  プロトコル）。mayapy 2023: 偽の AE で、反映・2 回目の更新・Maya での編集を上書きしない・オンにし直すと上書き・1 回の undo・
  バックアップ 1 回を確認。**AE と Maya の実機で未確認（H-AE-34）。AE の再起動とハブの再起動が必要。**
  利用者が会社の PC で試すため、テスト版 `SyncBridge-0.1.10.zip`（45.8 MB、SHA-256 4a724d27…、バージョン 4 か所を 0.1.10 に。
  タグ・リリースなし）を作って送った。

- **横 PAN のテストシーン `tools/pixel_mapping/make_test_pan_scene.py`（未コミット）:** アニメの撮影の流れどおり、Maya のカメラは固定、
  キャラはその場歩き。BOOK・BG は望遠（200mm）の素材カメラ `PLATE_BOOK_CAM` / `PLATE_BG_CAM` で横 3 倍（5760×1080）の 1 枚、
  キャラは SHOT_CAM の連番（`render_material`）。Maya レイヤーは CHAR→SHOT_CAM、BOOK・BG→素材カメラ、新しい接続は素材カメラモード。
  mayapy 2023: 素材を 100% で ±1700px までスライドさせた見え方と、専用カメラのレンダーが平均差 0.001〜0.010 / 255 で一致。**GUI で未確認。**

- **0.1.9 をリリース:** バージョンを 4 か所で 0.1.9 に。`SyncBridge-0.1.9.zip`（45.8 MB、SHA-256 da410562…）、リリースノート
  `docs/release_notes/0.1.9.md`、タグ v0.1.9。GitHub Releases のページは利用者が作る（この PC に GitHub CLI がない）。

- **ビューアー: 一番上のレイヤーを非表示にすると枠が消える（利用者、未コミット）:** ビューアーのカメラを「表示中の一番上」から
  「表示に関係なく一番上のレイヤーの元のカメラ」に（`core.layer_mapping.view_camera_uuid`、`layer_stack.view_camera`）。
  そのカメラに枠がなければ、ほかのカメラの枠（同じ AE のコンプ）の大きさで描く（素材カメラモードで BG_CAM が一番上の場合）。
  テスト 371 件 OK、mayapy 2024 で 3 通り確認。**GUI で未確認。**
- **レイヤーマップに出す AE のレイヤーを AE の選択で決める（D-40、未コミット、利用者の要望: 実運用ではレイヤーが大量）:**
  マップには「AE の選択を追加」で出したものとつないだものだけ。プリコンポの中は AE でそのプリコンポを開いて選ぶ。メインのコンポを
  AE に渡して、メインからの経路ごと追加（外側の PAN を失わない）。「マップから外す」（Delete）、「コンポのすべてのレイヤー」で一時表示。
  JSX `layersInfo(args)`（`selected`、`active`）、ハブ、`core.layer_mapping`（`ae_shown`、`show_ae`、`hide_ae`、`main_comp`、`selected_in_ae`）。
  テスト 378 件 OK、mayapy 2023 で追加・外すが 1 回ずつ取り消せる。**AE の実機で未確認（H-AE-32）。AE の再起動が必要（JSX）。**
- **利用者の GUI 確認で PAN の分ずれた:** CHA と BG が「コンポ 1」（外側のコンポで PAN のために動かしているプリコンポ）を基準に
  記録されていて、メインのコンポもそこから推測していた。→ メインのコンポをシーンに記録（`main_comp`、「AE のレイヤーを読み込む」で
  AE で開いているコンポをメインに）、メインの中のコンポで記録された接続を確認してメインからの経路に直す（`reroutes`、`reroute`）、
  ノードと転送の確認に警告。テスト 379 件 OK、mayapy 2023 で記録と経路の修正が 1 回ずつ取り消せる。**GUI で未確認。**
- **利用者の再確認: 「AE の選択を追加」でメインが `コンポ 1` に変わる** → 古いハブがメインの指定を捨て、AE が開いているコンポを返したと
  推定（ハブのコードも変えたため、ハブの再起動が必要）。AE からメインと違うコンポが返ったら何も変えずに案内する安全策と、読み込んだ
  コンポがプリコンポなら外側をメインにするか確認（`usedIn`、H-AE-33）を追加。テスト 379 件 OK。**利用者の GUI で動作 OK（2026-10-26、ハブ再起動後）。**
- 相談: 任意のレイヤーだけコマ打ち。A（そのレイヤーの専用カメラのキーを N コマ打ち・ステップ）は作れる、B（ビューアーで
  レイヤーごとに別の時間を描く）は未確認で難しい、と回答。利用者の希望は B だったので**見送り**（利用者の判断）。

### 2026-10-25（Windows 11, Python 3.10.6）

- **0.1.8 をリリース:** `build_release.py`（テスト → ビルド → 署名 → zip）で `SyncBridge-0.1.8.zip`（45.8 MB、SHA-256 5f50720f…）。
  リリースノート `docs/release_notes/0.1.8.md` を 0.1.7 以降のすべての変更で書き直した。タグ v0.1.8。
  この PC に GitHub CLI がないため、GitHub Releases のページは利用者が作る。**インストール版での確認はこれから。**

- **ビューアーからアニメーションを転送（未コミット、利用者の要望: レイヤーマップは常に開いていない）:** 転送の手順を
  `syncbridge_maya/motion_transfer.py`（`MotionTransfer`、範囲のダイアログ）に切り出し、レイヤーマップとビューアーで共有。
  ビューアーの上の「すべてのアニメーションを転送…」と、レイヤー一覧の右クリック「このレイヤーのアニメーションを転送…」（そのレイヤーの接続だけ）。
- **レイヤーマップ: 中ボタンのドラッグでトラック**（ノードエディターと同じ操作。スクロールバーなし、ノードのまわりに余裕を持たせた
  シーン範囲、最初はノードを中央に）。余裕を持たせたシーン範囲でビューの希望サイズが画面の 2/3 近くになり、ウィンドウが巨大に
  なったので、ビューの sizeHint を 560×360 に固定した。
- **SB Dev ボタン:** ビューアーを開いたまま押すと「Internal C++ object (QMenu) already deleted」（ビューアーを閉じると
  モデルパネルのメニューも消えるのに、先に取った一覧を回していた）。窓を探してから閉じるように直し、処理を
  `tools/dev_reload.py` に移した（ボタンはそれを実行するだけ。今後の修正でボタンの入れ直しは不要）。mayapy 2023 で再現して確認。
- `tools/pixel_mapping/make_test_plate.py`: 今のビューのカメラでレンダー解像度の 2 倍の BG 大判を書き出す（素材カメラモードの試験用）。
- テスト 370 件 OK。mayapy 2023 / 2024 で読み込みと右クリックの信号を確認。**GUI で動作 OK（利用者、2026-10-25）。**

- **素材カメラモード（D-39、未コミット）:** Maya レイヤーのカメラ = AE の素材を書き出したカメラにすると、素材の大きさと AE の行列から
  基準なしで直接合わせる（`pixel_mapping.solve_source`）。レイヤーマップの「新しい接続」で素材カメラ / 相対を選ぶ。
  mayapy 2023 / 2024: 大判（フィルムバック 3 倍）の切り抜きと専用カメラのレンダーがピクセル単位で一致（差 0）。テスト 368 件 OK。
  **GUI で動作 OK（利用者、2026-10-25）。** カメラワーク用のノード（PAN を 1 か所で持ち、Maya で直すと全レイヤーに反映する案）は、
  ヌル・プリコンポの PAN が各レイヤーの行列に入って届くので今は不要（利用者の判断で保留）。

- **Origin frame と範囲をツールで 1 つに（D-38、未コミット）:** Origin frame は Maya のシーンに保存（`timing.py`）、ハブが
  `timing.set` / `timing.state` で AE のパネルと共有、範囲は Maya の再生範囲。転送のダイアログの Origin frame は表示だけに。
  テスト 363 件 OK（ハブ・AE パネルの共有のテストを追加）、mayapy 2024: 保存・undo されない・開き直しても残る。**GUI で未確認。**

- **PAN（ヌルの親）と余白付きのレンダー（D-36、未コミット）:** AE が親を順にたどって返し、core が掛け合わせる（3D の親は断る）。
  レンダー解像度がコンポより大きくても、コンポは中央・画素は同じとしてレンダーの画素で解く（利用者の指摘: 余白を出すために一致しないことがある）。
  mayapy 2023 / 2024: `maya_pan_margin_check.py` 5 項目合格。テスト 360 件 OK。**GUI で未確認（H-AE-30）。** 次はプリコンポ、AE のカメラ。
- **プリコンポごと動かす PAN と、基準は規定値（D-37、未コミット）:** レイヤーの一覧にプリコンポの中のレイヤー（3 段まで）、接続は道筋 `via` を持つ。
  AE が外のプリコンポのレイヤーの変換と中の時間（`sourceTime`、H-AE-31 ❓）を返し、core が掛ける。線の欄に「基準を記録（今のフレーム）」。
  パネルからプリコンポの中のレイヤーを送ると案内して断る。基準のカメラの値は元のカメラの値（前の転送のキーを拾わない、利用者の要望）。
  mayapy 2023 / 2024: `maya_pan_margin_check.py` 9 項目合格（キー入りでも基準は 0、外のプリコンポが 80 px 動くと中の BG のカメラも 80 px）。
  既存の確認ツールも合格、テスト 361 件 OK。**GUI で未確認。** 次は AE のカメラレイヤー。
  → GUI で「ExtendScript error: 関数 containers[i].sourceTime は未定義です」（利用者）。`AVLayer.sourceTime` は AE 26.5 にない。
  タイムリマップが有効ならその値、それ以外は（時間 − startTime）× 100 ÷ stretch で求めるように直した（H-AE-31）。
- **キャラ役の素材のスクリプト（利用者の要望）:** `tools/pixel_mapping/make_test_char.py`。今のビューのカメラの真ん中にスフィアを作り、
  Hardware 2.0（`ogsRender`）で 1 枚、背景が透明の PNG を書き出す（レンダー設定は戻す）。mayapy 2024 で確認（真ん中は不透明、隅はアルファ 0）。
  Maya Software の `render` は mayapy ではファイルを書かなかったので使わない。
  → GUI で「BG も一緒に書き出された」（利用者）。レンダーの間だけスフィア以外の形状の `lodVisibility` をオフにし、終わったら戻す
  （undo に残さない。ロック・接続のあるものは触らず知らせる）。mayapy 2024: BG の板を置いても PNG はスフィアだけ、BG は表示に戻る。

- **SyncBridge ビューアー（D-33、未コミット）:** 上に重ねて表示する Maya のビュー、下に AE のようなレイヤーの一覧（並べ替え・表示）。
  `viewer_window.py`、`layer_stack_view.py`、`core.layer_mapping.reorder_layers / set_layer_visible`。モックを撮って利用者に見せた。
  mayapy 2024: 並べ替えと表示の切り替えが 1 回ずつ undo で戻る。テスト 350 件 OK。**GUI で未確認（H-MY-34: ウィンドウに Maya のビューを置く）。**
  開発用の「SB Dev」ボタンは、ビューアーも閉じてから読み直すように変えた（`tools/dev_maya_shelf.py` をドラッグし直す）。
  - GUI で開けなかった（`setParent: Object 'SyncBridgeViewer|||' not found`）→ ビューの置き場所までの部品とレイアウトに objectName を付けた。
  - **表示・非表示を頻繁に切り替えると Maya が落ちた** → 原因と考えたもの: (1) プラグインが切り替えのたびに描画パスを作り直し、
    Maya がまだ使っているパスを Python が捨てた、(2) チェックの信号の途中で一覧を作り直してその行を消した、(3) 強制の描き直しが
    何度も重なった。対策: パスは一度作って使い回す（中身だけ差し替え）、ビューアーの読み直しは 30 ms あとにまとめて 1 回、
    強制の描き直しをやめて `scheduleRefreshAllViews`。mayapy 2023 / 2024 で 200 回の切り替えでもパスは 6 個のまま。
    「SB Dev」はプラグインも外して読み直す（重ねて表示のビューを Viewport 2.0 に戻してから）。
    **GUI:** 利用者が再起動して試し「落ちなくなりました」（2026-10-25）。ビューアーが開いて使えたので H-MY-34 ✅。
    アルファ・半透明の重なり（H-MY-35）はまだ報告なし。
  - **解像度ゲートが効かない／ゲートで Overscan が 1.3 になる（利用者の指摘）** → 既存の AE の解像度の枠（D-16）を、重ねた
    レイヤーの上に元のカメラで描く最後のパスを足し、ビューアーに「解像度の枠」ボタン。専用カメラの Overscan は元のカメラから
    つなぐ。mayapy 2023 / 2024: Overscan の追従・古いカメラのつなぎ直し・枠のノードがパスに入ることを確認。既存の確認ツール
    （専用カメラ・アニメーション）も合格、テスト 350 件 OK。
    → GUI で「解像度の枠」を押しても枠が出なかった（ボタンは成功、スクリプトエディタは無言）。枠のノードの描画が絞り込んだ
    描画では呼ばれないため（H-MY-36）。プラグインの HUD で D-16 と同じ計算を投影して描く形に変えた。mayapy 2023 / 2024:
    `tools/pixel_mapping/maya_stack_frame_check.py` 192 通りで最大 0.0027 px。**GUI で再確認待ち。**
    → まだ出ない、の診断（プラグインに版 r3 と `SYNCBRIDGE_STACK_DEBUG` の出力を入れた）で、利用者の「SB Dev」ボタンが最初の版の
    ままで、重ねて表示のプラグインも古いまま（uiName に r3 がない）と分かった。枠の情報はプラグインに渡っていた。
    **注意:** `tools/dev_maya_shelf.py` の中身を変えたら、ドラッグし直さないとボタンは古いまま。プラグインは Maya の再起動か
    新しい「SB Dev」でしか入れ替わらない。
    → 再起動とドラッグし直しで「枠出ました」（H-MY-36 ✅）。要望: ビューアーの枠は外側を暗くして見やすく（本体の枠はそのまま）。
    → HUD で枠の外の 4 つの帯を半透明の黒（アルファ 0.5）で塗る（プラグイン r4）。帯がビュー全体を覆うことを mayapy の
    `maya_stack_frame_check.py` に足した（192 通り合格）。テスト 350 件 OK。**GUI で未確認（半透明の塗りが効くか）。**
  - 要望: 枠表示のときに少し縮小して余白を見せたい → 方式を相談中（シンプルな案: 枠を出している間だけ元のカメラの Overscan を
    上げる。複雑な案: ビューアーの中だけ投影を組み直す `core/stack_view.py`、作りかけ・未使用）。利用者が Overscan を手で変えて確認中。
  - その確認中に「レイヤーのカメラの Film Translate を入れると枠も動く」（利用者）→ 枠を表示行列で置いていたのが原因。
    D-34: `core/view_frame.py` でフィルムバック・Film Fit・Overscan だけから置く（プラグイン r5）。mayapy 2023 / 2024: 384 通り
    （Film Translate・Film Offset・Pan 入りも）で最大 0.000001 px。テスト 357 件 OK。**GUI で再確認待ち。**
  - Overscan の手の確認: 元のカメラを 1.2 にすると、レイヤーと枠は両方縮んだが位置がずれた（利用者）。Maya のビューは 2D のずらしを
    Overscan で縮めないため。→ Overscan で余白を作る案はやめた。**専用カメラの Overscan は常に 1.0（つながない）、ビューアーの枠も
    1.0 で置く**（プラグイン r6、D-33 に追記）。前の版の専用カメラはビューアーを開いたときに直す。mayapy 2023 / 2024: 専用カメラの
    決まり 6 項目、枠 384 通り合格。**GUI で未確認。**
  - **余白（D-35、利用者の決定: カメラに触らずビューアーの中だけで縮める）:** 枠を表示中、各レイヤーの描画の投影をカメラの式から組み、
    中心から 1/余白 に縮める（`core/stack_view.py`、プラグイン r7）。ビューアーに「余白」（なし・10%・20%・30%、既定 20%）。
    mayapy 2023 / 2024: `maya_stack_margin_check.py` 128 通りで Maya の視野と最大 0.0008 px。テスト 357 件 OK。
    **GUI で未確認（H-MY-37: 投影の差し替えが効くか、Film Translate・Roll 入りでもずれないか）。**
  - 枠の解像度の文字を枠の外の左上へ（利用者の要望。いったん右上にしたが左上に訂正）。左端を枠にそろえて 4 px 上。枠がビューの
    上端まであるとき（余白なし）は内側の左上（プラグイン r9）。本体の枠（D-16）はそのまま。**GUI: 利用者が確認して OK。**
  - **レイヤーごとの解像度（BG は大判、キャラはフル HD など、利用者の指摘）:** 利用者の回答で、書き出しの設定は持たず
    ビューアーで見えれば OK。Maya レイヤーのカメラにはコンポの画角のショットのカメラを選ぶ運用（D-33 に追記）。コードの変更なし。

- **レイヤーを重ねて見るビュー（D-32、試作・未コミット）:** レイヤーマップの「重ねて表示（試作）」で、今のビューを
  Viewport 2.0 のレンダーオーバーライド `SyncBridgeLayerStack` に切り替え、Maya レイヤーをそれぞれの専用カメラで描いて重ねる。
  `plug-ins/syncbridge_layer_stack.py`、`syncbridge_maya/layer_stack.py`、`core.layer_mapping.stack`（順番の単体テスト）。
  mayapy: API の存在、プラグインの読み込み、レイヤーの順番は確認。テスト 346 件 OK。
  **GUI:** 利用者が試して「動作OK」（H-MY-33 ✅）。ボタンの信号が PySide2 で値を渡さない不具合（`stack_requested(bool) needs
  1 argument`）を直した。次の要望: 重なり順を任意に、専用のビューアーの下部に AE のようなレイヤー構成。

- **Maya レイヤーの表示の切り替え（D-31、未コミット）:** レイヤーマップの「このレイヤーで見る」（ノードのダブルクリックでも）で、
  今のビューを専用カメラにして表示するオブジェクトだけを Isolate Select で見せる。「表示を戻す」で解除。表示中のノードは
  明るい緑で［表示中］。`syncbridge_maya/layer_view.py`。シーンの値は変えない（利用者の決定）。
  テスト 345 件 OK（ダブルクリックの Qt テスト）。**GUI:** 利用者が Maya で試して「動作OK」（H-MY-32 ✅）。

- **Phase 3 アニメーションの転送（D-30、未コミット）:** レイヤーマップの線の「アニメーションを転送…」で、範囲の各フレームの
  AE のレイヤーの動きを専用カメラのキーにする。`core/motion.py`、`syncbridge_maya/motion.py`、ハブの `motion.request`、
  AE の `SBCep.layerMotion`（H-AE-29 ❓）。
  **mayapy 2023 / 2024:** `tools/pixel_mapping/maya_motion_check.py` 13 項目合格。48 フレームの移動と拡大で、キーの値が各フレームの
  1 回送信の計算と差 0、読み戻し一致、元のカメラは不変、範囲外のキーは残る、打ち直しと undo（H-MY-31 ✅）。
  テスト 344 件 OK。範囲と確認のダイアログはモックを撮って利用者に見せた。
  **GUI:** 利用者が Maya と AE で線からの転送を試して「動作OK」（H-AE-29 ✅）。
- **すべてのアニメーションを 1 ボタンで（利用者の要望）:** レイヤーマップのツールバー（2 段にした）に「すべてのアニメーションを転送…」。
  範囲と確認は 1 回、キーは 1 回の undo。基準のない接続などは理由を出して飛ばす。`motion.apply_all` / `transferable`。
  mayapy 2023 / 2024: `maya_motion_check.py` に 3 項目を足して 16 項目合格（BG と CHAR が逆向きに打たれ、undo 1 回で両方消える、
  基準のない接続は飛ばす）。ウィンドウの流れも AE を差し替えて mayapy で確認。テスト 344 件 OK。
  **GUI:** 利用者が Maya と AE でまとめて転送を試して「動作OK」（2026-10-25）。
- **レイヤーマップ:** つなぐときに範囲選択の枠が出て邪魔（利用者の指摘）→ 範囲選択をなくし、つなぎ始めのクリックを受け取るようにした。

- **Pixel Mapping の設定をレイヤーマップに一本化（D-28 に追記）:** パネルの欄は接続の数と「レイヤーマップを開く…」だけにした。
  つないでいないレイヤーの送信は断る（mayapy 2024: 断ってカメラは不変、つないだあとは基準を記録）。新しい接続の方式は
  レイヤーマップのツールバー。`tools/pixel_mapping/maya_relative_check.py` は先につなぐ形に直した（レンダーでの再実行は未実施）。
  テスト 336 件 OK。
- **Maya レイヤーごとの専用カメラ（D-29、利用者の決定）:** BG とキャラが同じカメラでも、別々の動きを同時に再生できるように、
  Maya レイヤーにカメラを設定すると元のカメラの子に `SB_<レイヤー名>_CAM` を作り、接続はそれを動かす
  （`syncbridge_maya/layer_camera.py`）。名前の変更・カメラの変更・削除も専用カメラに反映、どれも 1 回の undo。
  **mayapy 2023 / 2024:** `tools/pixel_mapping/maya_layer_camera_check.py` の 19 項目すべて合格（見え方とレンダーの差 0、
  BG / CHAR の送信がそれぞれの専用カメラだけを動かす、H-MY-30）。ついでに、グループを選んで「選択中を追加」すると
  中身まで全部入っていた不具合を直した。テスト 337 件 OK。
  **残り:** 元のカメラが 2D の値（Film Offset など）にキーを持つときは、その動きが専用カメラに入らない（注意を出すだけ。
  足し合わせは今後）。
  **GUI:** 利用者が開発用の状態（SB Dev）で、レイヤーマップ・専用カメラ・パネルの整理を試して「動作OK」（2026-10-25）。

- **開発用の状態（利用者の要望: 毎回インストールし直さない）:** Maya の「SB Dev」ボタン（`tools/dev_maya_shelf.py` をドラッグ）は
  押すたびに `syncbridge*` を読み直してパネルを開き直す（mayapy 2024 で 2 回押して読み直しとパネル 1 枚を確認）。
  リポジトリから動かすときは、インストール版があっても `.venv` のサーバーを使うようにした（`launcher.in_repository`）。
  手順は `docs/RELEASE.md`「開発用の状態」。AE は既存の `tools/dev_env_on.ps1`。**GUI の Maya では未確認。**

- **レイヤーマップ（ノードエディター、D-28、作業中・未コミット）:** 対応付けの保存形式を schema 2 に
  （`maya_layers` = SyncBridge の Maya レイヤー: カメラと表示するオブジェクト。schema 1 は読み込み時にカメラごとの
  レイヤーへ移す）。ハブに `layers.request`（Maya → AE、`LayersFlow`）、AE に `SBCep.layersInfo()`（H-AE-28 ❓）、
  Maya に `service.request_ae_layers`。画面は `syncbridge_maya/layer_map_view.py`（Qt だけ、Maya を import しない）、
  Maya とつなぐのは `layer_map_window.py`（パネルの Pixel Mapping 欄の「レイヤーマップ…」で開く）。モックを利用者に見せて了承。
  操作（レイヤーの追加・カメラ・オブジェクト・名前・接続・モード・方式・基準・削除）はそれぞれ 1 回の undo。
  **mayapy 2023 / 2024 で確認:** 選択からのレイヤー作成、カメラなしの接続の拒否、板ポリなしの絶対モードの拒否、
  接続を外す → undo で戻り画面も戻る、方式とモードの undo。ドラッグでの接続と Delete は `.venv` の Qt で疑似マウス操作のテスト。
  テスト 335 件 OK（`.venv`、`py -3` は 89 件スキップ。`test_maya_drag_install` の偽 PySide2 に QtGui がなく、
  PySide6 のない環境で失敗していたのも直した）。
  **未確認（GUI）:** Maya の GUI でのウィンドウ（暗い配色、マウスでの接続、undo の scriptJob）、AE の `layersInfo`（H-AE-28）。
  アニメーションの転送（Phase 3）は未着手。

- **Overscan の方針（D-27）:** 利用者が GUI で、解像度ゲートの表示で Overscan が 1.3 / 1.0 に自動で変わること、ゲートの表示中の
  ビューポートではゲートの枠に対する BG の位置もずれることを確認（H-PM-10）。→ ツールで確認するときは Overscan 1.0 にして
  もらう方針（利用者の決定）。Overscan が 1 でないときは両方のパネルのログで促し、パネルの説明にも一文。「AE の素材に
  Overscan の余白が写っている」チェックは外した。作りかけのビューポート計測スクリプトは消した（未コミット）。

- **Overscan に対応（H-PM-9、未リリース）:** 利用者のカメラの基準値は Overscan 1.3（Playblast を AE へ）。以前は 1 以外を断っていた。
  mayapy: レンダーには Overscan が効かない。Playblast では画像が 1 ÷ Overscan に縮むとして、モデルに `view_overscan` を足し、
  パネルに「AE の素材に Overscan の余白が写っている」（既定オフ: 利用者は余白なしで Playblast するため）。Maya でも AE の 100 px が Film Translate で 1.3 倍
  になることを確認。テスト 325 件 OK。**Playblast が本当に Overscan を含むかは GUI で確認する。**

- **フィルム面の 2D 変換のすべてと、回転・拡大縮小の送信（D-26、未リリース）:** 利用者が GUI で 170 % と 42° を送って
  断られた → Pre / Post Scale・Film Roll の効き方を mayapy で測り（H-PM-8）、core のモデルに入れた（Zoom の位置の誤りも修正）。
  ソルバーを数値で解く方式に揃えた。新しい方式「Film Translate・Scale・Roll」、パネルの「方式を変更」。
  `pixelcheck.measure` に画面全体からの目印の検出とアフィンの当てはめ。
  mayapy: 3 つの深さ + カメラワークで 42° 0.036 px、170 % 0.067 px。絶対モードも 4 方式とも 0.010 px 以下のまま。
  テスト 324 件 OK。テスト版 zip（0.1.8、SHA-256 68a6cab7…）を作って利用者が GUI で確認する。

- 利用者の依頼でテスト用の町並みを作るツール `tools/pixel_mapping/make_test_town.py`（建物の箱・`SHOT_CAM`・AE 用の
  5760×3240 の大判 BG）。mayapy: 大判 BG の中央の切り出しとショットのレンダーが一致（平均差 0.003 / 255）、AE で (+300, −100)
  ずらして送ったあとも一致（平均 0.002、最大 2）。テスト版 zip（0.1.8、SHA-256 ff419cf8…、テスト 318 件 OK）。
- **Pixel Mapping Phase 2.5: 相対モード（D-25、`docs/PIXEL_MAPPING.md` 8 章、未リリース）。** 3D の BG・カメラワーク対応。
  `core.pixel_mapping.solve_relative`、対応付けの `mode` / `reference`、Maya の基準の記録と差分の適用、パネルのモードの選択と
  「基準をやり直す」（一覧は折り返し表示に）。既定は相対・2D Pan/Zoom。
  mayapy（3 つの深さ + カメラワーク）: スライド 0.007 px 以下、拡大 110 % で 0.094 px 以下、カメラワークの Film Offset は
  触らない（Film Offset 方式は断る）。テスト 318 件 OK。テストで作った `pixelmap_*.json` は消した。
  シェル経由の編集で `\n` が本物の改行になった（CLAUDE.md の注意どおり）→ Edit ツールで直した。

- **Pixel Mapping Phase 2 を利用者が GUI で確認: 動作 OK。** カメラの距離 18.670（正確には 18.67092）で断られる問題を、
  画面の端のずれ（1 px で拒否、0.1 px で警告）で判断するように直した（mayapy で 0.041 px）。テスト 313 件 OK。
  要望: BG は建物・町並みのモデルのこともあり、カメラワークもある → **相対モード（Phase 2.5）の案**を `docs/PIXEL_MAPPING.md` 8 章に。
- **Pixel Mapping Phase 2（D-24、`docs/PIXEL_MAPPING.md` 7 章、未リリース）:**
  - core `layer_mapping.py`（Virtual Layer）、ハブの `PixelMapFlow`（`pixelmap.*`）、Maya の `layer_mapping.py`
    （シーンに保存、UUID）と `pixel_mapping.apply_from_ae`、パネルの「Pixel Mapping（BG スライド）」欄、
    AE の `pixelMapInfo` と「BG の位置を Maya のカメラへ」、モニターのラベル。
  - Maya のパネルの中の欄をスクロールできるようにした（縦に長くなり、モックで部品がつぶれていた）。
  - mayapy 2024: 対応付けの作成・取り消し・名前を変えたあとの再送・キーのある属性の拒否・同じカメラの警告、レンダーで 0.005 px。
    Maya と AE のパネルをモックで確認。テスト: 全 312 件 OK（新規 10 件）。
  - テストで利用者の `Documents/maya/SyncBridge/backups` に作った `pixelmap_*.json` は消した。同じ秒の保存でファイル名が重なって
    いたので、マイクロ秒まで入れた。
  - **未確認（GUI）:** AE の `pixelMapInfo`（H-AE-26 / 27）、Maya の GUI での一連の流れ。

- **Pixel Mapping の Phase 1 完了。** 利用者が AE 26.5 で `pixel_mapping_reference.jsx` を実行（`saveFrameToPng` で 8 フレーム、
  H-AE-25 ✅）。`check_reference.py`: 予測との差 最大 0.042 px で PASS（H-AE-24 ✅、Position のみ）。同じ位置の Maya のレンダー
  （Hardware 2.0、Film Offset）と直接比べて最大 0.045 px。検証の画像は `tools/pixel_mapping/` に置かれ、Git 管理外にした。
  次は Phase 2（Virtual Layer Mapping、ハブ経由の転送、UI）。

### 2026-10-24（Windows 11, Python 3.10.6）

- **Pixel Mapping（BG スライドの再現）の Phase 0 / Phase 1（D-23、`docs/PIXEL_MAPPING.md`）。** 利用者の仕様書 v1.0。
  - 利用者の回答: Maya の BG は 3D の板ポリ（Image Plane の可能性もある）、レンダーは Hardware 2.0 / Playblast と Maya Software、
    自宅 PC の自動検証から。
  - 新規: `core/pixel_mapping.py`（座標変換・ソルバー）、`pixelcheck/`（PNG・テスト用 BG・目印の測定、標準ライブラリのみ）、
    Maya の `pixel_mapping.py`（カメラと BG の読み取り、適用）、AE の `pixel_mapping_reference.jsx`、`tools/pixel_mapping/`。
  - mayapy の検証: Film Offset / Film Translate / 2D Pan/Zoom とも予想式どおり（H-PM-1〜3）。平行投影では Film Offset と 2D Pan が
    レンダーに効かない。Hardware 2.0 のテクスチャの最大解像度（既定 2048）で最大 1.4 px ずれる（H-PM-4）。Image Plane は基準に
    向かない。通しの確認（AE の位置 → ソルバー → レンダー）: Hardware 2.0 で 0.010 px 以下（Maya 2023 / 2024、カメラの移動・回転・
    3:2 のフィルムを含む）、Maya Software で 0.40 px 以下。
  - テスト: 全 302 件 OK（`.venv`）。新規 19 件（core 13、pixelcheck 6）。
  - **未確認:** AE 側の前提 H-AE-24（AE の画素の座標）と H-AE-25（saveFrameToPng）。利用者が AE でスクリプトを実行して確認する。
  - タイムスライダーの同期の件（AE でドラッグ中は追従しない）は計測の結果待ちのまま。

### 2026-10-20（Windows 11, Python 3.10.6）

- **Phase 2 の一部を実装（未リリース）: シーン設定の転送（D-21）とタイムスライダーの同期（D-22）。**
  - core: `scene_sync.py`（計画・確認の文・読み戻し）、`time_sync.py`（変換・間引き・送り返し防止）。
  - ハブ: `server/settings_flow.py`（`settings.*`、履歴の種類 `scene_settings`）、`server/timesync.py`（`time.*` の中継と
    共有のスイッチ）。`SyncClient` に応答のいらない通知（`notices`）と `send` / `request`。
  - Maya: `scene_settings.apply`（確認 → バックアップ → プラグインの取り消しできるコマンド `syncBridgeApplySettings`）、
    `time_sync.py`、パネルに「シーン設定と時間の同期」欄。確認ダイアログの本文の最小幅を広げた（日本語の長い行が切れていた）。
  - AE: `syncbridge_cep_host.jsx` に `sceneSettings` / `applySceneSettings` / `compTime` / `setTime`、パネルに同じ欄。
  - テスト: 全 281 件 OK（`.venv`）。新規: core 17 件、ハブ 9 件、AE パネル（Node）3 件。システムの Python では
    `test_maya_drag_install` の 2 件が PySide6 なしでエラー（変更前から）。
  - mayapy 2023 / 2024: 設定の適用と 1 回の取り消し（記録は 1 つだけ、キーはフレーム番号のまま）、時間の同期の送信・
    送り返し防止・間引き・オフ。Maya のパネル、確認ダイアログ、AE のパネルをモックで確認。
  - 利用者の確認用に、未コミットのまま 0.1.8 のテスト版 zip を作成（`dist\SyncBridge-0.1.8.zip`、45.7MB、
    SHA-256 fe944a39…、ビルド中のテスト 281 件 OK。GitHub には出していない）。
  - **利用者の確認（2026-10-23、テスト版 0.1.8）:** タイムスライダーの同期は動いた。ただし完全なリアルタイムではなく
    少しラグがある（両方向）。→ AE のパネルが時間を読む間隔を 0.15 → 0.05 秒にし、Maya から受け取った直後の 0.3 秒は
    読まないようにした（読み取りが時間の設定の前に割り込むため）。Maya → AE の残りは主に AE の描き直し。テスト版 zip を作り直した
    （SHA-256 c6042456…、ビルド中のテスト 282 件 OK）。→ 利用者: あまり変わらない。
    原因を探すため、遅れの計測を入れた（`time.update` に送った時刻 `sent_at`、受け取り・設定・AE の読み取りと間隔を測り、
    同期をオフにしたときにパネルのログへ 1 行出す。core `LatencyStats`）。テスト版 zip を作り直した（SHA-256 fa51fcbd…、
    テスト 283 件 OK）。計測の結果待ち。
    2026-10-23 利用者: **AE で時間インジケーターをドラッグしている間は Maya が追従せず、離したときに反映される。**
    見立て: ドラッグ中の AE は evalScript を実行しない（溜めて離したときに実行）。ポーリングの間隔では直らない。
    計測の行（読み取り・間隔の最大がドラッグの長さになるか）で確認する。コマ送り・ルーラーのクリックは追従するはず。疑っている点: パネルが見えていないときの CEP のタイマーの遅れ、evalScript の往復、
    Maya のシーンの評価。
  - **未確認（GUI）:** H-MY-28（GUI での取り消し）、H-MY-29（スクラブ・再生）、H-AE-21〜23（AE での設定の変更と取り消し、
    開始フレームを変えても転送の時間がずれないこと、`comp.time` の書き込みとポーリングの重さ）。

- **0.1.7 の配布用 zip を作成**（`dist\SyncBridge-0.1.7.zip`、45.7MB、SHA-256 153f9d68…）。ビルド中のテスト 252 件 OK、
  zip に新しいプラグイン（`registerShape` / `excludeAsPluginShape`）とバージョン 0.1.7 が入っていることを確認。
  コミット・タグ・GitHub のリリースは未実施。

- **枠とマーカーをロケーターの表示から分けた（D-20、未リリース）:** 「表示」メニューに「SyncBridge 解像度の枠」
  「SyncBridge キーのマーカー」（`pluginDisplayFilter`）。最初の `excludeAsLocator` は Maya 2025 の GUI で効かなかったので、
  2 つのノードをプラグインのシェイプ（`MPxSurfaceShape` + `excludeAsPluginShape`）に変えた。テスト用プラグインで
  Maya 2025 の GUI で効くことを利用者が確認。本番のプラグインは mayapy 2023 / 2024 で、表示・保存時の取り外し・
  保存後の取り消し・開き直し・解除を確認。全テスト 252 件 OK。本番のプラグインの GUI での確認は次のリリースの前に（H-MY-27）。

- **0.1.6 をリリース（利用者の判断、タグ v0.1.6、SHA-256 3a4d3c20…）。** GUI の Maya / AE での確認がまだのもの:
  キーのマーカーのビューの表示（すべてのビュー、H-MY-24 / 26）とタイムスライダーの見え方、AE からの送信、Qt の確認ダイアログ、
  スタートメニューとタスクバーのアイコン、Maya 2025 での 0.1.6 の新機能。次に利用者が使うときに確認する。

- **Maya 2025（利用者の報告）:** 会社の PC の Maya 2025 で、以前の版（0.1.x、タイムワープの転送）が動いていた。
  Maya 2025 は PySide6 / Python 3.11 だが、パネルは PySide6 を先に試す作りで問題なかった。README と 0.1.6 のリリースノートの
  動作確認に 2025 を追加。**0.1.6 で増えたもの（解像度の枠とキーのマーカーのプラグイン、Qt の確認ダイアログ、シェルフのタブ）は
  Maya 2025 では未確認。** この自宅の PC には Maya 2025 がない（mayapy で確認できない）。
  0.1.6 を作り直し（README の更新のみ、45.7 MB、SHA-256 3a4d3c20…、未リリース・未コミット）。

- **停止済みのハブのファイルがたまる（利用者の報告）:** インストーラーの強制終了などで止まったハブの `hubs\<pid>.json` が残り、
  モニターに「ファイルのみ（停止済み）」が増えていた。→ `hubs.clean_stale_files()`（プロセスのない PID のファイルだけ消す。
  再利用された PID は生きているので残る）をハブの起動時とモニターの一覧の更新時に呼ぶ。テストを追加。
- **モニターのダークテーマ（利用者の要望）:** `monitor/theme.py`（Fusion + パレット + スタイルシート、アイコンの青緑 → 青の
  グラデーションをアクセントに）。ヘッダー、状態の色付きの丸（選択中も色が残る）、転送の結果の色分け、ログのレベルの色分け、
  Windows のダークのタイトルバー（このウィンドウだけ）。利用者とモックを見ながら、背景を 2 段暗くし、ヘッダー左上の
  グラデーションの明るさを決めた（利用者の確認済み）。テスト **251 件 OK**。0.1.6 を作り直し（45.5 MB、
  SHA-256 db06bcb0…、未リリース・未コミット）。
- **モニターの名前を英語に（利用者の要望）:** 「SyncBridge モニター」→「SyncBridge Monitor」（ウィンドウのタイトル、ヘッダー、
  スタートメニュー、インストーラーのメッセージ、README）。インストーラーが 0.1.3〜0.1.5 の古い名前のスタートメニューの項目を消す
  （テストを追加）。過去の記録は当時の名前のまま。
- **スタートメニューとタスクバーのアイコン（利用者の要望）:** EXE には新しいアイコンが入っていたが、Windows が 0.1.5 までの EXE の
  アイコン（PyInstaller の標準）を覚えている、また ICO が 256 の 1 サイズだけ、が原因と推定。→ `make_icon.py` が 16〜256 の 9 サイズの ICO を
  自前で書く、ICO を `app\syncbridge.ico` にも置いてスタートメニューの項目のアイコンに直接指定、モニターに AppUserModelID
  `SyncBridge.Monitor`（タスクバー）。テスト **252 件 OK**。0.1.6 を作り直し（45.7 MB、SHA-256 4b569d3b…、未リリース・未コミット）。
  **スタートメニューとタスクバーでの見え方は未確認。**

- **確認ダイアログがパネルの裏に隠れる（利用者の報告）:** AE → Maya の転送の確認（`cmds.confirmDialog`）が、常に Maya の前に出る
  SyncBridge のパネルの裏に出て、モーダルなので Maya を操作できなくなった。→ `syncbridge_maya/dialogs.py`（Qt の `QMessageBox`、
  表示中の SyncBridge パネルを親に、なければ Maya のメインウィンドウ、最前面）に置き換え。モックで親の選び方と見た目を確認。
  **GUI の Maya では未確認。**
- **アイコンをモニターと AE にも（利用者の要望）:** `make_icon.py` が各サイズを作る（シェルフ 32、パネル 64、モニター 256、
  EXE の ICO、AE 64 と 23）。Maya のパネル・AE のパネル・モニターの左上にアイコン（利用者の指定で右上から左上に変更）、
  モニターのウィンドウとタスクバー、`SyncBridge.exe` と `SyncServer.exe` のファイルのアイコン、AE の manifest の `<Icons>`。
  あわせて、Maya のパネルの「解像度の枠」欄の説明文が切れていたのを、モックで見つけて直した。
  モック: Maya のパネル（mayapy 2023、offscreen）、AE のパネル（ブラウザ、`.claude/launch.json` の `ae-panel-mock`）、モニター。

- **Maya のシェルフのアイコンを利用者のデザインに（利用者の要望）:** 元の画像を `maya_plugin/icons/source/syncbridge_icon.webp`
  に置き、`packaging/make_icon.py`（PySide6 で WebP を読み、余白を切って 32×32 に縮小）で `syncbridge_shelf.png` を作るように。
  元の画像は配布物に入れない。インストール済みの PC では、インストールし直すと `prefs\icons` のアイコンも置き換わる（Maya の再起動が必要）。
  テスト 250 件 OK。0.1.6 を作り直し（45.2 MB、SHA-256 798b264e…、未リリース・未コミット）。

- **AE のタイムリマップのキーを Maya のマーカーに（D-18、利用者の要望）:** `core/markers.py`（転送と同じ時間の対応）、
  ハブの中継を `server/relay.py` にまとめた（解像度の枠と共通、`guide_flow.py` は削除）、AE のパネルに「キーのマーカーを Maya へ」、
  Maya の `syncbridge_maya/key_markers.py`（network ノードに JSON、目印付きのタイムスライダーのブックマーク、ビューの 2D 表示）、
  プラグインに `syncBridgeKeyMarker`（左上に「● AE キー 3/8  素材 36f」）と `kAfterOpen` での出し直し、Maya のパネルに
  「AE のキーのマーカー」欄（「マーカーを消す」）。テスト **247 件 OK**。
  mayapy 2023 / 2024 で確認: 作成、保存（`requires` は `timeSliderBookmark` だけ）、開き直しで残り表示も出し直される、
  送り直しで置き換え、取り消し、「マーカーを消す」（利用者のブックマークは残る）、描画の直前の文字の決定。
  途中で見つかった問題: 表示用ノードを network ノードに接続すると `delete` で network ノードまで消えた／送り直すと新しいノードに
  つながらなかった → 描画のたびに名前で読む形に。`MAnimControl` は `OpenMayaAnim` にあった（推測が誤り）。
  **GUI の Maya でのビューの描画（H-MY-24）とタイムスライダーの見え方、AE からの送信は未確認。**
- **ポート 8765 がほかのプログラムに使われていても接続（D-19、利用者の決定）:** 利用者の確認中に、別のプロジェクト（LayCAT）の
  Claude がテスト用に起動した `py -m http.server 8765` が残っていて、Maya の Connect がまた止まった（2 回目）。
  `launcher.ensure_server()` が `session.json` のハブを優先し、8765〜8774 の空きポートで起動するように。
  使っているプログラムは `hubs.port_owner()`（`netstat -ano`）で調べ、Maya のパネルに日本語で表示。
  テスト **250 件 OK**（ほかのプログラム役の Web サーバーでふさいで次のポートで起動、2 回目は起動しない、すべてふさがれていれば
  日本語のエラー、netstat の解析）。0.1.6 を作り直し（45.2 MB、SHA-256 95562f70…、未リリース・未コミット）。
  LayCAT 側のテスト用のポートは変えていない（別のプロジェクトのため）。
- **キーのマーカーをすべてのビューに（利用者の要望）:** 利用者の確認で、表示がアクティブなビューにしか出なかった。プラグインは
  ビューで絞り込んでいないので、Maya の既定の「Update View: Active」で、ほかのビューが描き直されていないためと推定
  （mayapy で既定値が `active` であることを確認）。表示が変わるフレームでだけ `scheduleRefreshAllViews()` を呼ぶように（H-MY-26）。
  テスト 250 件 OK。

### 2026-10-19（Windows 11, Python 3.10.6）

- **Install.bat だけで Maya も使える状態に（D-17、利用者の要望）:** インストーラーが、Maya 2023 以降で一度起動された
  バージョンのユーザー設定フォルダ（`MAYA_APP_DIR` / ドキュメント\maya、英語版と `ja_JP`）に専用タブ
  `shelf_SyncBridge.mel` とアイコンを置き、`install.json` に記録。アンインストールで削除（Maya の終了を確認してから）。
  ドラッグ＆ドロップのファイルは予備として残す。テスト **235 件 OK**（インストーラーのテスト 5 件を追加: 一時フォルダで
  対象のバージョンだけに置かれる、ASCII、ボタンのコマンドが Python として正しい、既定と別の場所、アンインストールで
  自分のファイルだけ消す、Maya のフォルダがない場合）。mayapy 2023 / 2024 で、シェルフのファイルが MEL として読めることと、
  ボタンのコマンドでパネルのモジュールが import できることを確認。0.1.5 をビルド（45.2 MB、SHA-256 c57b5130…）。
- **利用者の確認（インストール版 0.1.5、Maya 2023）: OK。** 起動時に「SyncBridge」タブが出てパネルが開いた（H-MY-23 ✅）。
  0.1.5 をリリース（タグ v0.1.5）。
- **README.md を更新（利用者の指摘）:** Phase 0 のままだった内容を、0.1.5 の機能、使う人向けの導入、開発する人向けのコマンド、
  フォルダ構成、ドキュメントの一覧に書き直した。`after_effects/README.md` にも解像度の枠と配布版の導入を追記。

### 2026-10-16（Windows 11, Python 3.10.6）

- **AE のコンプの解像度の枠を Maya のビューに表示（D-16、利用者の要望）:** `core/comp_guide.py`（解像度ゲートと枠の計算）、
  Maya のプラグイン `maya_plugin/plug-ins/syncbridge_guide.py`（`syncBridgeCompGuide`、Viewport 2.0 の描画のみ）、
  `syncbridge_maya/comp_guide.py`（アクティブなビューのカメラの下に作成、シーンに保存しない）、Maya のパネルに「枠を消す」、
  ハブの `guide.request`（`server/guide_flow.py`、履歴は「解像度の枠」）、AE のパネルに「解像度の枠を Maya へ」。
  テスト **224 件 OK**（core の計算 13 件、偽の maya での作成・置き換え・削除 8 件、ハブ 4 件、Node の AE パネル 2 件）。
  確認用に 0.1.4 をビルド（未リリース・未コミット）。
  - **利用者の確認 1 回目（Maya 2024）:** 「setAttr: No object matches name: top|syncBridgeCompGuide|…compWidth」で失敗。
    この PC の mayapy で再現: Maya がプラグインを `__file__` なしで実行するため読み込みに失敗し、`loadPlugin` は例外を出さず、
    `createNode` が不明なノードを作っていた → `MFnPlugin.loadPath()` を使い、ノードの種類が登録されたか確かめてから作るよう修正。
  - mayapy で追加の確認: 解像度ゲートの計算が Maya の `getRenderingFrustum()` と一致（H-MY-20 一部 ✅）。
    枠があると保存時に `requires` が書かれる（H-MY-22 一部偽）→ 保存の直前に外して直後に戻す。
    その処理を undo に記録すると、保存のあとの undo で **Maya がクラッシュ** → 枠は undo に記録しない（D-16）。
    修正後、保存 3 回・利用者の操作の undo / redo を組み合わせて、クラッシュせずファイルにも残らないことを確認。
  - 修正後のテスト **228 件 OK**。0.1.4 を作り直し（45.2 MB）、配布物の `payload/maya` の構成（開発用の `src` なし）でも
    mayapy で枠の作成と保存を確認。
  - **利用者の確認 2 回目:** 「カメラ top のビューに表示しました」と出たが、枠が見えない。候補は (1) 見ていたビューと違うカメラに
    付いた（H-MY-21）、(2) 描画のカメラの比較が一致しない（シェイプとトランスフォーム）。(2) はトランスフォーム同士の比較に直し、
    計算の例外をスクリプトエディタに警告で出すようにした（mayapy で読み込みを確認）。(1) は推測で直さず、
    `tools/maya_guide_diagnose.py`（GUI の Maya で実行: ビューごとのカメラ・レンダラー・ロケーター表示、アクティブなビューの判定、
    修正版プラグインでの試し描き）の結果を待つ。
  - **診断の結果（利用者の PC、Maya 2023、1 分割で top ビュー）:** アクティブなビューの判定は正しい（H-MY-21 一部 ✅）。
    Viewport 2.0、ロケーターの表示もオン。それでも修正版プラグインで枠が描かれない → 描画の問題（H-MY-19）。
    GUI の Maya ではプラグインの読み込み直しも「# Error: (syncbridge_guide)」で失敗した（mayapy の 2023 / 2024 では再現しない）。
    → プラグインに描画の各段階のデバッグ出力（`SYNCBRIDGE_GUIDE_DEBUG`）と、初期化・終了の失敗時の traceback を追加し、
    診断スクリプトで描き直させて結果を待つ。
  - **再診断（Maya 2023、persp ビュー）:** 描画用のオブジェクトは作られる（`override created`）が、`prepareForDraw` が一度も
    呼ばれず、枠も見えない。mayapy で `GuideData()` と枠の計算を直接呼ぶと正常 → Viewport 2.0 が描画の対象から外している。
    バウンディングボックスなし（`isBounded` = False）と申告していたため、と推定（未確認）。Autodesk の作例（footPrintNode）と同じく、
    枠の 4 隅から計算したバウンディングボックスを返すように変更し、`isBounded` / `boundingBox` にもデバッグ出力を追加。
    mayapy でバウンディングボックスの値を確認。
  - **再診断 3 回目:** それでも `override created` のあと何も呼ばれない（`isBounded` も `boundingBox` も出ない）→ バウンディングボックスは
    原因ではなかった。作例（footPrintNode の Python API 2.0 版）との違いは、`MPxDrawOverride` の初期化で描画のコールバック関数を
    渡しているか（SyncBridge は None）。空のコールバックを渡すように変更（mayapy で作成を確認）。
  - **切り分け（利用者の PC、Maya 2023）:** 普通のロケーターはカメラの子でも見える。保存しない設定もロックもない描画ノードを
    persp の子に置くと、やはり何も呼ばれない。ワールドに置くと `isBounded` → `boundingBox` → `prepareForDraw` → `addUIDrawables`
    が呼ばれる → **今見ているカメラの子のプラグインの描画ノードは描かれない**、が原因。
    → 枠をワールドに置き（アウトライナーに出さない）、カメラとは `worldMatrix` の接続で結ぶ作りに変更（D-16 に追記）。
    mayapy の 2023 / 2024 で、バウンディングボックスがカメラの前に来てカメラの移動に付いていくこと、保存したファイルに何も残らないこと、
    取り消し、別のカメラへの置き換え、「枠を消す」を確認。テスト 228 件 OK。
  - **画面で枠が見えた（2026-10-17、利用者の PC、Maya 2023、H-MY-19 ✅）。** ただしカメラを動かすと消えた → 枠の座標は描画のたびに
    計算し直しているが、Viewport 2.0 がバウンディングボックスを作成時のまま使い、カメラの移動で視野外と判断して描かなくなった、と推定。
    → 枠を「バウンディングボックスなし」と申告し、視野外の判定をさせないよう変更（ワールドに置いた今は、この申告でも描かれるはず）。
    mayapy 2023 / 2024 とテスト 228 件で確認。
  - **カメラを動かしても枠が消えなくなった（2026-10-17、利用者の PC、Maya 2023）。** README に枠の使い方と Maya の
    「Untrusted Plugin Loading」への対処（「Apply to all plugins in this location」+「Allow」）を追加。
    0.1.4 を作り直し（45.2 MB、SHA-256 96e37dde…、未リリース・未コミット）、配布物の構成で mayapy 2023 / 2024 を確認。
  - **Maya のパネルで任意の大きさの枠（2026-10-17、利用者の要望）:** AE に最終サイズのコンポがあるとは限らないため、
    「解像度の枠」欄に幅・高さ・プリセット・「枠を表示」を追加（`comp_guide.show_size`、前回の値を optionVar に保存）。
    ラベルは AE から送ったときだけ「AE」を付ける。注意文も「コンプ」から「枠」に。テスト 230 件 OK。
    mayapy 2023 で、画面なしでパネルを組み立ててプリセット・表示・記憶・「枠を消す」を確認。GUI の Maya では未確認。
    0.1.4 を作り直し（45.2 MB、SHA-256 3e1390ff…）。
  - **利用者の確認（2026-10-17、インストール版 0.1.4、Maya 2023 + AE 26.5）: OK。** Maya のパネルの手入力・プリセットと、
    AE の「解像度の枠を Maya へ」の両方で枠が表示された（H-AE-20 ✅）。0.1.4 をリリース（タグ v0.1.4）。
  - **未確認:** 画面上で Resolution Gate とぴったり重なるかの明示的な確認（H-MY-20 の残り）、4 分割のビュー、正射影カメラ、Maya 2024 / 2025 の GUI。
  - **画面上の描画（H-MY-19 の残り）、4 分割でのアクティブなビューの判定、AE（H-AE-20）は未確認。**
- **利用者の報告:** 両方のアプリが切断してもハブが残る → 仕様（10 分で自動終了）。利用者の判断で 10 分のまま。
  10 分たっても終了しない場合は不具合として調べる（未確認）。

- **0.1.2 のインストール（会社 PC、利用者）:** 問題なし。
- **0.1.3（モニターの配布）:** 会社 PC には開発環境がないため、モニターを `SyncBridge.exe`（PyInstaller、windowed）にして
  インストーラーに追加（`app\`、スタートメニュー「SyncBridge モニター」、アンインストールで削除）。P-C のランチャーも同じ EXE に入れる予定。
  テスト 196 件 OK。一時フォルダにインストールし、インストールした `SyncServer.exe` と `SyncBridge.exe`（offscreen）を起動して
  モニターがハブの `/admin/events` に接続することを確認、アンインストールでショートカットとフォルダが消えることを確認。
  **利用者の画面でのモニターの操作は未確認。**

- **P-B（モニター、D-15）:** `monitor/model.py`（Qt なし）、`monitor/window.py`（PySide6-Essentials 6.11.2 を `.venv` に追加、
  `requirements-monitor.txt`）、`syncbridge-monitor.cmd`。ハブのログファイル `logs/hub-<pid>.log`、停止時にアプリへ `hub_stopping` を通知。
  テスト **195 件 OK**（`.venv`、画面は offscreen の Qt で確認）、システムの py 3.10 では 52 件スキップで OK。
  実際のハブ（`python -m syncbridge.server`）と偽の Maya / AE で転送してから、モニターの画面を offscreen で撮影し、
  一覧・接続中のアプリ・履歴・ログが日本語で表示されることを確認。**利用者の画面での操作（停止、強制終了、切断）は未確認。**
  - 利用者の確認の途中: Maya のパネルはインストール版 0.1.1 の `SyncServer.exe` を起動するため、管理 API がなく
    「404 Not Found」とだけ出た → 古い版のハブだと日本語で説明し、「停止」を無効にした（強制終了は可能）。
    テスト 196 件（1 件はこの PC で動いている `SyncServer.exe` が一覧に出て行数が合わず失敗 → 自分のハブの行を探すように修正し、モニターのテスト 8 件 OK）。
  - ポート 8765 を `python -m http.server`（SyncBridge と無関係）が使っていて、Maya の接続が英語の「port 8765 is used by another program」で止まった。
    日本語にしてプロセス名を出す改善は未着手。

- **P-A（ハブの管理 API・履歴・ログ、D-15）:** `server/admin.py`（管理 API、トークン必須）、`server/hubstate.py`（転送の履歴、
  ログの保持、イベント配信）、ハブごとのセッションファイル `hubs/<pid>.json`、`hubs.py`（ハブの発見、確認、強制終了、片付け）。
  テスト **179 件 OK**（`.venv`）、システムの py 3.10 では 179 件中 45 件スキップで OK、selftest PASS。
  実際のハブ（`python -m syncbridge.server`）を起動し、`discover()` で `running`・確認済み、管理 API で状態とログを取得、
  `POST /admin/shutdown` で終了してファイルが消えることを確認。venv ではハブのプロセスが `sys.executable` と別のファイルで動くことが判明し、
  実際のイメージも記録するようにした。強制終了は偽のハブ（sleep する python）で確認。インストール版の `SyncServer.exe` では未確認。

- **タイムワープの保存・復元・範囲変更（利用者の要望）:** `core/warp_edit.py`（時間方向の伸縮、fps 変換）、
  `syncbridge_maya/snapshots.py`（保存先 `<userAppDir>/SyncBridge/snapshots`、自動バックアップも復元対象）、
  Maya のパネルに「保存」「復元…」「範囲変更…」。書き込みは転送と同じ安全策（確認、バックアップ、undo 1 回、読み戻し）。
  Maya の確認ダイアログとエラーを日本語に。テスト **163 件 OK**。Maya では未確認。
- **0.1.0 の利用者テスト（この PC、GitHub Releases からダウンロード）:** インストール版の AE パネルが PlayerDebugMode なしで
  読み込まれ、Maya と接続。Maya → AE で素材が短いと AE がエラー（R-16 が実際に発生）→ サーバーと AE の両方で事前に確認し、
  日本語で理由を出すよう修正。テスト **151 件 OK**。0.1.1 として配布し直す必要あり（RELEASE.md）。
- **先行配布 0.1.0（D-14）:** PyInstaller で `SyncServer.exe`（onedir、21MB）、`launcher` がインストール版の exe を優先、
  Maya のドラッグ＆ドロップ用ファイル（シェルフにボタン、再ドラッグで置き換え、`.mel` の予備）とアイコン、
  AE パネルを自己署名した ZXP（タイムスタンプ付き、検証 OK）、`Install.bat` / `Uninstall.bat`（PowerShell、日本語の案内）、
  利用者向けの `README_SyncBridge.txt`、ビルドスクリプト `packaging/build_release.py` を作成。zip 10.7MB。
  確認: exe 単体での起動・転送・自動終了、一時フォルダへのインストール → インストールされたコードだけで転送 → アンインストール、
  開発用ジャンクションはリンクだけ消えること。テスト **148 件 OK**。
  ビルドのログに証明書のパスワードが出ていたので、表示を伏せて証明書を作り直した（配布前）。
- **V-P1C（AE 26.5 + Maya 2024）合格 → Phase 1 完了:** パネルの読み込みと接続、Maya → AE、AE → Maya
  （確認ダイアログ、取り消し 1 回で復元）、日本語の警告、Disconnect 後に送れないことを確認。途中で 3 件を修正:
  Time Remap が無効な適用先を拒否していた、警告が英語で Phase 0 用の説明が混ざっていた（コード化して日本語に）、
  モジュールの読み込み直しで古い Maya の接続が残っていた（サーバーが同じプロセスの古い接続を置き換え、Maya 側も前回の接続を切断）。
  テスト **142 件 OK**。詳細は PHASE1_PLAN.md 7 章。
- **Phase 1-C:** CEP 拡張機能（ルートは `after_effects/`）を実装。AE の適用処理を `SB.applyToLayer` に共通化し、
  Phase 0 の `syncbridge_ae.jsx` もこれを使う。パネルの通信部分 `sbclient.js` は CEP・DOM に依存しない形にして、
  Node（組み込みの WebSocket）から本物のサーバーにつなぐテストを追加（Maya → AE、AE → Maya、AE 側のエラー、トークン違い）。
  パネルの見た目はブラウザで確認（AE の外なので未接続の表示）。テスト: `.venv` で **137 件 OK**、標準 Python で 137 件 OK（28 件スキップ）。
- **V-P1B（Maya 2024 + AE の代役）合格:** サーバーの自動起動、接続中も Maya が固まらない、Maya → AE、AE → Maya
  （確認ダイアログ、バックアップ、読み戻し誤差 0、Undo 1 回で復元）、キャンセル、切断を確認（H-MY-14/15/16）。
  パネルのログに AE 側から送られたときの結果と AE の接続・切断を出すよう改善（**132 件 OK**）。詳細は PHASE1_PLAN.md 7 章。
- **Phase 1-B:** 標準ライブラリだけの WebSocket クライアント（`client/ws.py`）、`SyncClient`（受信は別スレッド、
  アプリへの処理は dispatch 経由）、サーバーの自動起動（`launcher`、Maya の `PYTHONHOME`/`PYTHONPATH` を外す）、
  Maya の `service` と最小パネル、`exchange.apply_envelope`（適用結果を返す、Scene Time Warp がないシーンでも export できる）、
  `tools/fake_ae.py` を実装。`describe_result` を `protocol.py` に移動。
  テスト: `.venv` で **131 件 OK**、標準 Python で 131 件 OK（サーバー関連 24 件はスキップ）。
  通し確認: launcher でサーバーを起動 → `fake_ae.py`（実際の AE の export）と Maya の代わりのクライアント（実際の Maya の export）で
  Maya → AE、AE → Maya とも変換誤差 0・読み戻し誤差 0。Maya 本体ではまだ動かしていない。
- **Phase 1-A:** `.venv` に FastAPI 0.143.2 / uvicorn 0.54.0 / websockets 16.1.1 / httpx を導入（`requirements-server.txt`）。
  CLI の変換手順を `core/jobs.py` に移し、プロトコル、セッション、サーバー、転送の手順を実装。
  偽の Maya/AE クライアントを本物の WebSocket でつなぐテストで、両方向の転送、取り消し、未接続、アプリのエラー、切断、
  タイムアウト、変換失敗時に適用しないこと、同時実行の拒否を確認。
  実際に起動して、二重起動の検出、セッションファイル、8 秒の自動終了とファイル削除を確認。
  テスト: 標準 Python で 106 件 OK（サーバーの 16 件はスキップ）、`.venv` で **106 件 OK**。
- AE の Apply も「編集 → 取り消し」1 回で元に戻ることを利用者が確認（V-MY-2 の残り）。
- GitHub に初回 push（`main`）。GitHub Actions の結果は利用者がブラウザで確認済み（ローカルのブラウザ操作では未確認）。
- 転送テスト V-AE-2（PHASE0_RESEARCH.md 8 章 #9）: AE 26.5 → Maya 2024、Editable。AE で中間のキーの時刻と値を編集 →
  Maya に 17→8.58 として反映、Maya の readback 誤差 0、AE の評価と Maya のカーブの直接比較も誤差 0。Maya の取り消し 1 回で復元。
  入力式の Export も動作。
- 転送テスト V-MY-2（PHASE0_RESEARCH.md 8 章 #8）: Maya 2024 → AE 26.5、Editable。export / Apply を初めて実機で使用し、
  リードバック誤差 0、**Maya の評価と AE の Time Remap の直接比較も誤差 0**。AE のファイル選択がスクリプトのフォルダで開く問題を修正、
  傾きのない Linear 外挿の誤警告を修正（**82 件 OK**）。
- Maya 2024 プローブ #4（PHASE0_RESEARCH.md 8 章 #7）: 範囲外の誤差 0、`linear_infinity` も誤差 0 で
  H-MY-11/12 の修正を実機で確認。結果を fixture に追加（**81 件 OK**）。
- Maya 2024 プローブ #3（PHASE0_RESEARCH.md 8 章 #6）: Linear 外挿は外側の接線で延びると判明（H-MY-11 は偽 → 修正、
  範囲外 24 点で誤差 0）。`setInfinity` の設定がカーブノードに効かない（H-MY-12）→ enum 属性へ直接書くよう修正。
  区間より長いハンドルは Maya と一致しない（H-MY-13、未解決、警告を追加）。実データを回帰テスト化（**80 件 OK**）。
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

- Maya（2024）: H-MY-1〜7, 9, 11 は確認（11 は修正後のモデルで）。H-MY-5 は 24fps でのみ確認。
  H-MY-8（レンダー）、H-MY-10（自動作成）は未判定。H-MY-12 の修正（`set_infinity`）は 4 回目で確認。
  H-MY-13（区間より長いハンドル）は未解決。Maya 2023 では未実施。
- UI で作った Scene Time Warp は Linear 外挿だが、外側の接線が 0° なので実際は水平に延びる（R-20 は対応済み）。
- AE（26.5）: H-AE-1/3/4/5/7/11/12 は確認、H-AE-6 は偽（1/6 に修正）、H-AE-2 は一部、H-AE-9/10 は 1 コンプで確認。
  H-AE-8（CEP の通信）は未判定。AE 2024/2025 では未実施。片側 LINEAR の 1/6 モデルは 1 ベクトルのみで決定。
- AE の Apply（`syncbridge_ae.jsx`）とリードバックは未実行（V-MY-2）。
- AE で読んだ片側 LINEAR のキーを Maya に送ると、ハンドルが 1/3 でないため weighted 接線になる（H-MY-5 は確認済み、エンドツーエンドは未確認）。
- Maya の「29.97fps」単位が 30000/1001 なのか 29.97 なのかは未確認（AE とずれる可能性、R-14）。
- Scene Time Warp の自動作成: コマンドは `sceneTimeWarp "add"` と判明、実行時の挙動は未確認（H-MY-10, D-7）。
- Python 3.9 での実行は CI で確認する（このPCには 3.10 しかない）。
- 社内のセキュリティ規程（会社 PC での clone/push）の確認（R-13）。
- **配布先の検討（2026-10-21、利用者の判断待ち）:** このリポジトリは公開で、持ち主のプロフィールからほかの公開リポジトリが
  見える。案: ほかを非公開にする / 組織に移す / 別のアカウントの新しいリポジトリに履歴なし（1 コミット、新しいアカウントの
  noreply アドレス）で入れ、ここを非公開にする。コミットのアドレスは noreply のみで、個人のメールは出ていない。
  非公開にする場合、アップデーター（P-D）の「公開の GitHub Releases から取る」前提を見直す。
- **ビューアーの編集中レイヤーの自動切り替えの調査（2026-10-28、コードは変えていない）:** `docs/VIEWER_CAMERA_SELECTION_AUDIT.md`。
  - 切り替えは選択の変化ではなく、ビューアー内のクリックと一覧の行のクリックだけで動く（アウトライナー・普通のビューの選択では変わらない）。
  - ❌ P-4: Maya の Shift のクリックはトグルなのに、コードは追加として扱う。
  - ⚠️ P-2: 編集中でないレイヤーを選んでいると、マニピュレーターの位置が見た目とずれる。
  - ❓ P-1: Maya のクリック選択・囲み選択が、描かれていないオブジェクトを拾うか。
  - 実機のテストケース T-1〜T-16 と、改善案の優先順位はレポートにある。
  - **同じ日に Maya 2023 / 2024 の GUI を自動で操作して検証した**（レポートの 8 章）。
    - P-1 は ❌ と確認した。Maya の囲み選択・クリック選択が、描かれていないオブジェクトを選ぶ（H-MY-44）。
    - **新しい不具合 P-11:** 編集中のレイヤーを替えると、選択が `SB_VIEWER_CAM` などに置き換わる。
      `cmds.parent` / `createNode` が選択を変えるため。一覧の行のクリック・Shift のクリック・レイヤーの削除で、利用者の選択が消える。
    - 外部のレビュー（GPT）の意見を、Claude が判断した（レポートの 9.11）。P-7 を 5 番目に上げた。
      アウトライナーで選んだときの切り替えは採る（オフにする設定は最初は付けない）。
    - **Phase 1 を実装した（レポートの 10 章）。** P-11（選択を取っておいて戻す）、P-4（Shift = トグル、Ctrl+Shift = 追加）、
      P-5（非表示のレイヤーを編集中にしない）。
      - テスト: 390 OK（標準ライブラリ、106 スキップ）、390 OK（`.venv`）。
      - Maya 2023 / 2024 の GUI を自動で操作して、3 つとも直ったことを確認した。
      - 利用者の実際のシーンでは、まだ確かめていない。
    - **P-1 を直した（レポートの 11 章）。**
      - H-MY-45 ❌: Isolate Select は選択を絞れるが、オーバーライドのほかのレイヤーも消えるので採らなかった。
      - 代わりに、ビューアーで左ボタンを離した後、編集中のレイヤーと関係ないもの（登録ノード・子・親以外）を外す。
        Shift / Ctrl で外れたものは戻す。この補正は undo に積まない。
      - テスト: 392 OK（標準ライブラリ、106 スキップ）、392 OK（`.venv`）。
      - Maya 2023 / 2024 の自動検証で、見えないものは選ばれなくなった。
      - 階層選択モード、成分の選択、利用者の実際のリグは、まだ確かめていない。
    - **P-7 を直した（レポートの 12 章）。** ほかのレイヤーの NURBS カーブ（線から 6px 以内）とロケーター（中心から 10px 以内）も、クリックで当たる。
      同じレイヤーの中では、メッシュより優先する。
      - テスト: 393 OK（標準ライブラリ、106 スキップ）、393 OK（`.venv`）。
      - Maya 2023 / 2024 の自動検証で確認した。
      - コントローラーの多いリグでの速さは、まだ確かめていない。
    - **9.5 を実装した（レポートの 13 章）。**
      - 選択がすべて 1 つの表示中のレイヤーなら、どこで選んでもそのレイヤーに切り替える。アウトライナー・ほかのビュー・Undo のどれでも同じ。
      - 混ざった選択と、未登録・非表示のものの選択では、カメラを保ち、状態の行で知らせる。
      - テスト: 396 OK（標準ライブラリ、106 スキップ）、396 OK（`.venv`）。
      - Maya 2023 / 2024 の自動検証で確認した。
      - Maya 2023 では、起動直後の最初の選択の変化に `SelectionChanged` が届かないことがあった（Maya 側）。
    - 残りは P-6（選べない設定のもの）と P-8（透明な部分）。どちらも、利用者の素材と使い方を見てから決める。
- **インストーラーの EXE（2026-10-28、D-45、まだ版を上げていない・配布していない）:**
  - Inno Setup 6.7.3 を winget で利用者ごとに入れた（利用者の許可を得て）。
  - `packaging/installer/SyncBridge.iss` を追加。`build_release.py` が `dist/SyncBridge-Setup-<version>.exe` も作る。
  - 入れ方の本体は `install.ps1` / `uninstall.ps1` に `-Setup` を足して使い回す。「アプリ」からアンインストールできる。
  - テスト: 397 OK（`.venv`）、397 OK（標準ライブラリ、106 スキップ）。
    `SetupExeTest` は、テスト用の中身で EXE を作り、一時フォルダへの黙ったインストールとアンインストールを行う。
    `/SBTest=1` なので、レジストリには書かない。
  - ウィザードの準備完了・完了のページを、一時フォルダへのインストールで撮って確認した（日本語、アイコン、完了のページの案内）。
  - **未確認:** 実際の中身（46MB）での EXE、会社の PC での SmartScreen とウイルス対策ソフト（H-PKG-3）、「アプリ」からのアンインストールの実機確認。
- **0.1.15 をビルドした（2026-10-28、まだコミット・配布していない）:**
  - 版を 5 か所で 0.1.15 にした。
  - `dist/SyncBridge-0.1.15.zip`: 45.9MB、296 ファイル、SHA-256 `e01e644c5485b317f72fc7f204fe3446fb4dfca92353304e037fd1b0eac675f3`。
  - `dist/SyncBridge-Setup-0.1.15.exe`: 34.4MB、SHA-256 `0c6efb30ac771a7afcc31e71d438f07c1b2badadd1ccefc62f4d7936dec6d532`。
  - 中身: 今日の選択の修正（P-1/4/5/7/11、9.5）、プラグイン r14。証明書とシーンは入っていない。`install.ps1` は BOM 付き。
  - ビルドの中のテストは 397 OK。ZXP の署名と検証も通った。
  - 本番の EXE を一時フォルダへ黙ってインストールした（`/SBTest=1`、7 秒）。
    - サーバー・モニター・Maya のファイル・AE パネル・スタートメニュー・シェルフ（2023 / 2024）が入り、`Uninstall.bat` はなかった。
    - インストールした `SyncServer.exe` の `/health` が 0.1.15 を返した。
    - アンインストーラーで、すべて消えた。
  - **未確認:** 会社の PC（SmartScreen、ウイルス対策ソフト、H-PKG-3）、画面付きでのインストール、「アプリ」からのアンインストール、zip で入れた 0.1.14 からの上書き。
- **パネルからの更新（2026-10-28、D-46、一時的な形。まだコミット・ビルドしていない）:**
  - Maya と AE のパネルにメニューバーを付けた（「ヘルプ → SyncBridge について / 更新…」）。
    GitHub のリリースの一覧から選んだ版の EXE（なければ zip）をダウンロードし、SHA-256 を照合してインストーラーを起動する。
  - 共通の処理は `syncbridge.updater`（`releases.py`・`install.py`・`__main__.py`）。
  - AE は Node.js を有効にし（マニフェスト）、`SyncServer.exe update ...` を呼ぶ。開発中は `.venv` で呼ぶ。
  - テスト: 408 OK（`.venv`）、408 OK（標準ライブラリ、106 スキップ）。`test_updater` を追加した（ネットワークなし）。
  - 実際に確かめたこと:
    - 本物の GitHub から一覧を取得できた: `python -m syncbridge.updater list`、mayapy 2023 / 2024、PyInstaller で作った `SyncServer.exe update list`。
    - v0.1.9 の zip をダウンロードし（5 秒）、SHA-256 の照合と展開ができ、`Install.bat` が見つかった（インストール自体は実行していない）。
  - モックを撮った: Maya のメニューバー・About（mayapy）、AE のメニュー・About・確認（Edge headless、幅 320）。
  - **未確認:**
    - 実際の AE でパネルの Node が動くか（H-AE-19）。
    - Maya / AE を開いたままの更新（H-UPD-1）。
    - EXE を起動してからの流れの実機確認。
  - 0.1.16 として GitHub に公開すると使えるようになる。v0.1.10〜v0.1.15 は GitHub にない。
- **0.1.16 をビルドした（2026-10-28、まだコミット・GitHub への公開はしていない）:**
  - 版を 5 か所で 0.1.16 にした。
  - 同じ日に言い回しを直してビルドし直した（利用者の指摘）。
    - ボタン: 「この版に更新…」→「インストール」。
    - 確認の文: 「SyncBridge 0.1.9 をインストールします（今は …。古い版に戻ります）」。
    - AE の確認中は、下のボタンの行を隠す。
  - `dist/SyncBridge-0.1.16.zip`: 45.9MB、300 ファイル、SHA-256 `e42af820fe6d1e14485148dce7b3f1152f6b9470b0a00ed67c7cd2373e60c81b`。
  - `dist/SyncBridge-Setup-0.1.16.exe`: 34.4MB、SHA-256 `56ec8ad4756001adbd41a3ed1d8810588bd9dd15f6dc1bfaabda7162d1b94ea0`。
  - リリースノート `docs/release_notes/0.1.16.md`、タグ v0.1.16 = 7b2c96b（利用者の指示でリリース）。
  - **GitHub Releases に公開した（2026-10-28、プレリリース）:** https://github.com/ogshaw03/SyncBridge/releases/tag/v0.1.16
    - GitHub CLI 2.103.3 を winget で利用者ごとに入れ、利用者が `gh auth login` で認証した（ogshaw03、keyring）。
      以後のリリースは Claude が `gh release create` で作れる。gh は PATH に入っていないので、次の場所を指定して使う:
      `%LOCALAPPDATA%\Microsoft\WinGet\Packages\GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\gh.exe`
    - 添付: EXE と zip。About の処理で一覧を取ると、0.1.16 が EXE 付きで出た（0.1.15 からは「新しい版」）。
      GitHub からダウンロードした EXE は SHA-256 が一致した。
  - 中身: 0.1.15 に About / 更新（D-46）を足したもの。証明書とシーンは入っていない。AE パネルのマニフェストに `--enable-nodejs`、`about.js` が入っている。
  - ビルドの中のテストは 408 OK。
  - 本番の EXE を一時フォルダへ黙ってインストールした（`/SBTest=1`）。
    - すべてのファイルが入り、`SyncServer.exe` の `/health` が 0.1.16 を返した。
    - インストールした `SyncServer.exe update list` が GitHub の一覧を返した（v0.1.9 以下は「古い」）。
    - アンインストーラーで、すべて消えた。

## 次にやること

0. **PAN（利用者の指摘、2026-10-25）:** 今は AE の各レイヤー自身の 2D の動きだけ。利用者は PAN を (1) ヌルの親、(2) プリコンポごと、
   (3) AE のカメラレイヤー のどれでも付ける。提案した順: (1) 親の 2D の変換を掛け合わせる → (2) 入れ子のコンポを掛け合わせる
   （レイヤーマップでプリコンポの中のレイヤーもつなぐ）→ (3) AE のカメラで 3D のレイヤーを投影（カメラに平行な板なら 2D で表せる）。
   レイヤーごとの解像度は設定不要（相対モードは変化だけを足す。条件: レンダー解像度 = コンポ、基準のときに見え方を合わせる）。
0. **Pixel Mapping:** レイヤーマップ（D-28）・専用カメラ（D-29）・Phase 3 のアニメーション転送（D-30）・表示の切り替え（D-31）は
   GUI で確認済み（2026-10-25）。元のカメラの 2D の値（Film Offset など）のキーが専用カメラに入らない件は、**注意を出すだけで
   進める**（利用者の決定、2026-10-25。足し合わせは必要になったら）。**0.1.8 の配布用 zip はまだ作らない**（利用者の決定。
   リリースノートの下書き `docs/release_notes/0.1.8.md` は未コミットのまま）。
0. **[実機・利用者] シーン設定の転送とタイムスライダーの同期（D-21 / D-22）を GUI で確認する:** 両方向の設定の転送と取り消し、
   開始フレームを変えたあとでもタイムワープの転送とマーカーが同じ位置か（H-AE-22）、スクラブ・コマ送り・再生と停止での追従、
   「再生中も追従」、AE でスクラブしたときの Maya の追従と AE の重さ。確認できたら 0.1.8 として配布する。
1. **[実機・利用者]** 0.1.1 を GitHub Releases から入れて確認する（0.1.0 からの更新、保存・復元・範囲変更、
   素材が短いときの日本語メッセージ）。Python のない PC での確認（H-PKG-2）も残っている。
2. **[実機・利用者] 解像度の枠（D-16）を Maya 2024 + AE 26.5 で確認する:** レンダー解像度と同じ大きさのコンプで枠が
   Resolution Gate と重なるか（H-MY-20、Film Fit 4 種類）、余白付きのレンダーで中央に小さい枠、別のカメラのビューでは出ない、
   「枠を消す」、保存しても枠が残りファイルに記述がない、保存のあとに取り消し・やり直しをしても問題ない。
3. **ハブ・ランチャー・モニター（D-15、`docs/PLATFORM_DESIGN.md`）:** P-A・P-B は実装済み（11・12 章）。
   **[利用者]** 0.1.3 を入れ、スタートメニューの「SyncBridge モニター」を開き、Maya / AE をつないだ状態で一覧・履歴・ログ・停止・切断を確認する。
   次は P-C（ランチャー、モニターと合わせて `SyncBridge.exe` に）→ P-D（アップデーター）。
3. **Phase 2（基本設定の同期）:** FPS、解像度、ピクセルアスペクト比、フレーム範囲（Maya の再生範囲・アニメーション範囲・
   レンダー範囲 ⇔ AE のコンプの長さ・ワークエリア）、現在フレーム（SPEC 6 章）。Maya 側の読み取りは Phase 0 で実装済み。
3. **[実機・利用者]** 余裕があれば: 30fps のシーンでの Maya プローブ（H-MY-5）、Maya 2023 / AE 2024 での再確認。

### 先送りにしたもの

- **レンダー比較 V-MY-3（2026-10-16、利用者の判断）:** テストシーンの準備とレンダリングに時間がかかるため、Phase 1 を先に進める。
  未確認のまま残るのは H-MY-8（Maya のバッチレンダーに Scene Time Warp がかかるか）と、レンダー開始フレームと
  AE のソース 0 秒の対応が実際の素材で正しいか。実制作で使う前、遅くとも Phase 2 の終わりまでに行う。手順は PHASE0_RESEARCH.md の V-MY-3。

- **Precision モードの実機転送テスト（2026-10-16、利用者の判断）:** UI で作った Scene Time Warp は Editable で
  両方向とも誤差 0 だったため、優先度を下げた。Precision モード自体は実装済みで、単体テストと selftest では合格している。
  必要になるのは、Maya → AE で AE が表せない形（区間より長いハンドル、傾きのある Linear 外挿、Cycle 外挿、stepnext）を
  含むときと、未検証の環境（Maya 2023、24fps 以外など）で安全側に送りたいとき。再開時は V-MY-2 / V-AE-2 を `--mode precision` で行う。

- **Maya → AE の区間より長いウェイト付きハンドル（2026-10-29、利用者の判断で Todo として残す）:**
  - 想定する流れ: AE でレイアウト → AE → Maya（キーの数を保つためウェイト付きになる。ハンドルは AE の 100% 以内なので区間に収まる）
    → Maya で調整 → Maya → AE。Maya で最初からレイアウトする場合は多くがノンウェイトで、AE に誤差 0 で送れる（H-MY-7 / H-AE-3）。
  - 問題になるのは、Maya の調整で **1 本のハンドルが区間より長くなったとき**（隣のキーを越えて伸ばした、キーを動かして区間が
    短くなった）だけ。AE の影響度は 100% が上限で、今のエンコーダは 100% に丸めて警告する（その区間の形がずれる）。
    2 本の合計が区間を超えるだけなら AE でもそのまま表せる（H-AE-7 ✅）。
  - 提案した順:
    - **A. 知らせる:** Maya → AE の前に、はみ出したキーを「フレーム 17 の出のハンドルが区間より長い」のように示し、
      Maya 側で直してもらう（キーの数を変えずに戻せる）。
    - **B. 自動で対応:** はみ出した区間だけキーを足す。Bezier の分割（de Casteljau、形は変わらずハンドルが短くなる）か、
      Maya の評価値への当てはめ。分割で完全一致にするには、Maya が長いハンドルをどう評価するか（H-MY-13、未解決）を
      先に調べる必要がある。分からなければ当てはめにする。フルベイク（Precision）は最後の手段。
  - A を入れて実作業ではみ出しがどのくらい起きるかを見てから、B が要るかを決める。
