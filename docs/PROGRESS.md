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

## テスト結果

### 2026-10-25（Windows 11, Python 3.10.6）

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

## 次にやること

0. **[利用者] Pixel Mapping の相対モードを GUI で確認する**（`docs/PIXEL_MAPPING.md` 8 章）→ Phase 3（アニメーション、
   Linear / Hold / Bezier のサンプリング、全フレームの精度確認）。Phase 2 は 2026-10-25 に GUI で確認済み。
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
