# SyncBridge アーキテクチャ

最終更新: 2026-10-16（Phase 0）

## 1. 構成

```
┌──────────── Maya (Python 3.9+) ────────────┐        ┌──────── After Effects ────────┐
│ maya_plugin/scripts/syncbridge_maya        │        │ after_effects/panel (CEP)     │
│   scene_timewarp  : Scene Time Warp の特定  │        │   HTML/JS: WebSocket 通信     │
│   anim_curve      : animCurveTT 読み書き    │        │        │ evalScript           │
│   exchange        : export / apply         │        │ after_effects/jsx             │
│   probe           : Phase 0 実機検証       │        │   syncbridge_ae_lib.jsxinc    │
│        │ import (同一プロセス)               │        │   syncbridge_ae.jsx / probe   │
│ src/syncbridge/core  ◄──────────────────────┼─┐      └──────────────┬────────────────┘
└────────────────────────────────────────────┘ │                     │
                                               │   Phase 0: JSON ファイル
                                               │   Phase 1+: ws://127.0.0.1:8765
┌──────────── Local Sync Server (別プロセス) ──┼─────────────────────┴───────────────┐
│ src/syncbridge/cli.py      (Phase 0 の変換ハブ)                                        │
│ src/syncbridge/server      (Phase 1: FastAPI/WebSocket、接続管理、リビジョン、競合)     │
│ src/syncbridge/core  ◄───── Time Mapping Core（純 Python、標準ライブラリのみ）          │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Time Mapping Core（`src/syncbridge/core`）

| モジュール | 役割 |
|---|---|
| `timebase.py` | 有理数 fps（`Fraction`）、Maya 時間単位名、フレームと秒の変換 |
| `curve.py` | 中立カーブ `TimeCurve`（入力秒 → 出力秒）、評価、アフィン変換、JSON |
| `ae_codec.py` | AE の Time Remap キー（速度・影響度）⇔ 中立カーブ |
| `maya_codec.py` | Maya の animCurveTT キー（フレーム、傾き、ハンドル長）⇔ 中立カーブ |
| `mapping.py` | `MappingContext`: Maya の時間軸と AE の時間軸の対応（原点、オフセット、スケール） |
| `sampler.py` | Precision モード: 適応的な区分線形の再サンプリング |
| `validation.py` | 誤差計測（出力フレーム単位）、`ErrorReport` |
| `transfer.py` | 変換パイプライン（デコード → 写像 → モード → エンコード → 検証） |
| `envelope.py` | 交換用エンベロープ（ファイル、将来の WebSocket メッセージ共通） |
| `testcurves.py` | 参照カーブ（単体テストとプローブで共用） |

## 2. データの流れ（Phase 0）

```
Maya → AE
  Maya: export_timewarp() ──► maya.timewarp.export
        { native(フレーム単位のキー), samples(Maya 自身の評価値), scene(fps/範囲/解像度), calibration }
  AE:   syncbridge_ae.jsx Export ──► ae.timeremap.export（対象レイヤーのコンプ fps、startTime など）
  PC:   cli maya2ae ──► ae.timeremap.apply { keys(AE 形式), context, report }
  AE:   syncbridge_ae.jsx Apply ──► 確認 → JSON バックアップ → undo グループで適用 → *_after.json
  PC:   cli readback apply after ──► AE が実際に評価した値と比較

AE → Maya
  AE:   Export ──► ae.timeremap.export { keys, samples(valueAtTime) }
  PC:   cli ae2maya ──► maya.timewarp.apply
  Maya: apply_timewarp() ──► 確認 → JSON バックアップ → undo チャンクで適用 → リードバック比較を表示
```

`transfer` の 1 回の変換は最大 3 つの誤差レポートを持つ。

| レポート | 比較対象 | 検出するもの |
|---|---|---|
| `source_fidelity` | 転送元カーブのデコード結果 vs 転送元アプリ自身の評価値 | 転送元アプリの接線解釈の誤り（H-MY-4/5, H-AE-3） |
| `conversion` | 出力キーを再デコードしたカーブ vs 写像後の転送元カーブ | コーデックやモードによる損失 |
| `readback` | 転送先アプリが適用後に評価した値 vs 送ったカーブ | 転送先アプリの解釈の誤り、単位・オフセットの誤り |

## 3. 設計判断（変更履歴）

仕様書 v0.1 からの変更と、Phase 0 で決めた方針。変更するときは理由とともにここへ追記する。

### D-1: ディレクトリ構成の変更（仕様 11 章からの変更）

- 仕様の `maya/` を **`maya_plugin/`** に変更した。
  **理由:** `maya/` を Python パッケージとして sys.path に置くと、Autodesk の `maya` モジュール
  （`import maya.cmds`）を隠してしまい、Maya 内で致命的な名前衝突になる。
- 仕様の `core/`, `server/`, `updater/` は **`src/syncbridge/` パッケージの下** に置いた。
  **理由:** `core` のような汎用名をトップレベルに置くと他のツールと衝突しやすい。また Maya とサーバーの両方から
  同じ `syncbridge.core` を import する必要がある。`src/` レイアウトにより、テストがインストール済みのコードを
  誤って参照する事故も防げる。

### D-2: 変換ロジックは Python に一元化する

- JSX は AE 形式のキーの読み書きとサンプリングだけを担い、Bezier の変換は実装しない。
- Phase 0 は CLI が変換ハブ、Phase 1 からはサーバーが同じ `syncbridge.core` を呼ぶ。Maya は同じプロセス内で core を import できる。
- **理由:** 変換を JS と Python で二重実装すると、精度の検証対象が 2 つになり、食い違いの原因になる（仕様 13 章 1・2）。

### D-3: 中立カーブは「明示的な 2D 3 次 Bezier（秒）」

- 各キーが in／out の補間（LINEAR／BEZIER／HOLD）とハンドル (dt, dv) を持つ。
- Maya の傾きと weight、AE の速度と影響度は、どちらもこの形式に損失なく写せる（範囲の制約を除く）。
- アフィン変換（オフセット、fps の違い、ソーススケール）を厳密に適用できる。

### D-4: Precision モードは LINEAR／HOLD キーだけを出力する

- 直線補間は Maya と AE で評価が一致するため、未検証の接線の数式（H-MY-4/5, H-AE-3/6/7）に依存しない。
- キーは既定でフレーム位置に置き（`key_subdivision=1`）、点と点の間もサブフレーム（既定 8 分割）で誤差を確認する。
- フレーム位置のキーだけでは許容誤差に収まらない箇所に限り、サブフレームのキーを追加する（`allow_subframe`）。
- 内部では許容誤差の 50% を目標に当てはめ（`FIT_MARGIN`）、最後に全範囲を再検証する。

### D-5: 適用後のリードバック検証

- 適用後に、転送先アプリ自身の評価値（Maya `keyframe -eval`、AE `valueAtTime`）をサンプルし、送ったカーブと比較する。
- 未検証の仮説が外れていても、誤ったデータを「成功」として扱わないための安全網。

### D-6: Maya 読み取り時の自己キャリブレーション

- weighted 接線の単位（H-MY-5）が未確定のため、読み取り時に候補のスケールを全て試し、
  Maya 自身の評価値に最もよく一致するものを採用する。採用した候補と誤差は export に記録する。

### D-7: Phase 0 では Scene Time Warp を新規作成しない

- 作成コマンドや内部構造が未確認のため、UI で作成済みのカーブを探して読み書きするだけにする。
- 2026-10-16 追記: Maya 2024 のプローブで、UI の作成コマンドが MEL の `sceneTimeWarp "add"` であることがわかった
  （H-MY-10）。ただし作成を実行したときの副作用（既存カーブの扱い、undo）は未確認のため、方針は維持する。
  自動作成は Phase 1 以降で、プローブで挙動を確認してから追加する。

### D-8: テストは標準ライブラリの unittest

- Maya の Python でもそのまま実行でき、外部依存がない。pytest からも実行できる。

### D-9: 時間軸の対応は `MappingContext` で明示する

- 「どの Maya フレームが、どのコンプ時間・ソース時間に対応するか」を暗黙にしない（仕様 4.3）。
- CLI の既定: `--origin` で Maya 側の原点フレームを指定し、AE 側のコンプオフセットはレイヤーの startTime。

### D-10: 転送は「評価範囲」で一致を判定する（2026-10-16 追加、R-20）

- Maya 2024 のプローブで、UI で作った Scene Time Warp が前後 Linear 外挿だとわかった。AE の Time Remap は範囲外で値を保持するだけなので、
  キーの範囲だけで一致を判定すると、コンプやレンダー範囲のうちキーの外側のずれを見落とす。
- そこで転送に評価範囲（転送先の入力時間）を持たせ、Precision は範囲外の外挿をキーに焼き込み、誤差レポートは範囲全体で計る。
  Editable は表現できない外挿を警告し、不合格として報告する（黙って捨てない、SPEC 5 章 6）。
- 既定の範囲は、Maya の再生範囲と AE のコンプ範囲。どちらも「利用者が見る時間」なので、これで一致すれば見た目は一致する。

### D-11: サーバーは FastAPI + uvicorn、開発環境はリポジトリ内の `.venv`（2026-10-16、Phase 1）

- 仕様どおり FastAPI。依存は `requirements-server.txt` にバージョンを固定し、リポジトリ内の `.venv`（Git 管理外）に入れる。
  PC の Python 本体には入れない（利用者の選択）。配布時は PyInstaller で EXE に含める（Phase 6）。
- uvicorn の WebSocket 実装は `websockets-sansio`（旧実装は非推奨警告が出るため）。
- `syncbridge.core` と `syncbridge.protocol`、`server/session.py` は標準ライブラリだけで書く（Maya のクライアントが import するため）。

### D-12: Maya のクライアントは標準ライブラリだけで書く（Phase 1-B で実装予定）

- Maya の Python に外部パッケージを入れずに済むようにするため。必要なのはテキストフレーム、ping/pong、close だけ。

### D-13: 変換手順は `core/jobs.py` に置き、CLI とサーバーで共有する（2026-10-16）

- Phase 0 の CLI にあった「オプション → 時間の対応 → 評価範囲 → 変換 → 読み戻しの検証」を移した。CLI とサーバーで結果が食い違わないようにするため。
- サーバーは、変換が許容誤差を超えたら転送先に適用を依頼しない（CLI はファイルを書くだけなので従来どおり書き出す）。

### D-14: Phase 1 の機能だけで先行配布する（2026-10-16、利用者の要望）

- タイムワープ転送が急ぎで必要なため、Phase 6 の一部（サーバーの EXE 化、インストーラー）を先に作り、0.1.0 として配布する（`docs/RELEASE.md`）。
- 利用者はターミナルを使わない前提: zip を解凍して `Install.bat` をダブルクリック。管理者権限は使わず、各ユーザーのフォルダに入れる。
- Maya は「モジュール」ではなく、ドラッグ＆ドロップでシェルフにボタンを追加する方式（利用者の要望）。Maya 起動時の自動読み込みはしない。
- AE パネルは自己署名した ZXP を配布し、利用者の PC の PlayerDebugMode（レジストリ）を変えない（利用者の選択）。
- サーバーは PyInstaller の onedir（onefile は起動ごとの展開とウイルス対策ソフトの誤検知が増えるため避けた）。

### D-15: ハブ・ランチャー・モニター（2026-10-16、利用者の要望）

- AE と Maya 以外のアプリ、タイムワープ以外のデータにも広げる予定のため、サーバーを「ハブ」として一般化し
  （能力の申告、データ種別レジストリ、アプリ形式 → 中立形式 → アプリ形式の変換）、
  管理用のランチャーとモニターを別プロセスで用意する。詳細は `docs/PLATFORM_DESIGN.md`。
- 利用者の決定: 対応アプリは未定（一般的な仕組みで受ける）、更新の配布元は GitHub Releases（利用者ごとの読み取り専用トークン、
  EXE に埋め込まない）、ランチャーは普通のウィンドウ、順番はモニターから（P-A → P-B → P-C → P-D）。

### D-16: AE のコンプの解像度の枠を Maya のビューに表示する（2026-10-16、利用者の要望）

- 目的: Maya で余白付きでレンダーし、AE で最終サイズに切り出す作業のため、最終の範囲を Maya のビューで確認する。
- 利用者の決定: 枠の位置は **アクティブコンポの幅と高さだけ** を使い、Maya のレンダーがコンプの中央に等倍で置かれている前提。
  描き方は **ビューポートにだけ描くノード**（Python API 2.0 のプラグイン、レンダーされない）。送り方は **AE のパネルのボタン**。
- 流れ: AE `guide.request {comp}` → ハブ（検証して中継、履歴は data_type `comp_guide`）→ Maya `guide.apply.request` → `guide.result`。
  確認ダイアログは出さない（表示用のノードを足すだけで、既存のデータを変えない）。
- 枠の計算は `core/comp_guide.py`（純 Python）。プラグインは描画のたびにカメラとレンダー解像度から求め直すので、カメラの設定や
  解像度を変えても追従する。カメラ空間で枠を求め、カメラの行列でワールドへ移して描く（パン・ズームやオーバースキャンにも追従）。
- ノードは **ワールドに置き**（アウトライナーには出さない）、カメラとは `cameraShape.worldMatrix[0] → guide.cameraMatrix` の接続で結ぶ。
  最初はカメラの子に置いたが、Maya 2023 では、今見ているカメラの子にあるプラグインの描画ノードは描かれなかった（利用者の PC で確認、
  2026-10-16）。接続により、カメラを動かすと枠が再計算され、カメラを消すと枠も描かれなくなる。
- ガイドは表示の補助であり、シーンのデータではない。**ファイルにも undo の履歴にも残さない**（2026-10-16、Maya 2024 の mayapy で確認）。
  - ノードは `setDoNotWrite` で保存されない。ただし枠があるあいだ、Maya は `requires "syncbridge_guide.py"` を書く（H-MY-22）。
    プラグインのない PC やレンダーファームで警告が出ないよう、プラグインが保存の直前に枠を外し、直後に戻す（`MSceneMessage` の
    kBeforeSave / kAfterSave）。3 回保存して、ファイルに SyncBridge の記述がないことを確認した。
  - 枠の作成・削除は undo に記録しない。最初は作成を undo 1 回で消せるようにしていたが、作成が履歴にある状態で保存の前後に
    消して作り直し、そのあと undo すると **Maya 2024 がクラッシュした**（`TsetAttrCmd::undoIt`）。消すときはパネルの「枠を消す」を使う。
    開発ルール 2 の「1 回で undo できること」は元データを変える操作のための決まりで、データを変えないこの枠は対象外とした。
    利用者の他の操作の undo / redo は影響を受けないこと、利用者が undo を無効にしていても状態を変えないことも確認した。
  - シーンを開き直すと枠はなくなる（保存されないため）。AE からもう一度送る。
- P-E（ハブの一般化）の前なので、新しいメッセージの種類として最小限で追加した。P-E ではデータ種別レジストリに移す。
- （2026-10-17、利用者の要望）AE に最終サイズのコンポがあるとは限らないため、Maya のパネルでも幅と高さ（プリセットあり）を
  入れて枠を出せるようにした。同じ `comp_guide.show()` を通る。前回の大きさは Maya の optionVar `syncBridgeGuideSize` に保存。
  枠のラベルは、AE から送ったときだけ「AE コンポ名」を付ける（手入力は「1920x1080 / Maya 2112x1188」）。

### D-17: Maya のシェルフはインストーラーが専用タブとして置く（2026-10-19、利用者の要望）

- 利用者の要望: `Install.bat` だけで、サーバー・AE・Maya のすべてを使える状態にしたい（ドラッグ＆ドロップを不要にする）。
  決定: Maya の **専用タブ「SyncBridge」**。ドラッグ＆ドロップのファイルは予備として残す。
- インストーラーが、Maya 2023 以降で一度起動されたバージョンのユーザー設定フォルダ（`MAYA_APP_DIR`、なければ
  ドキュメント\maya。英語版と `ja_JP`）に `prefs\shelves\shelf_SyncBridge.mel` と `prefs\icons\syncbridge_shelf.png` を置き、
  `install.json` に記録する。アンインストーラーは記録したファイルのうち、SyncBridge の名前のものだけを消す。
- Maya のモジュール（.mod）や `userSetup.py` は使わない（D-14 の利用者の要望、ほかのツールに影響させない）。
- シェルフのファイルは ASCII のみ。ボタンのコマンドは、既定の場所なら `%LOCALAPPDATA%` から SyncBridge の場所を求める
  （ユーザー名に日本語があっても文字化けしない）。
- 既存のシェルフ（Custom など）にボタンを足す方法は取らない: Maya が終了時に読み込み中のシェルフを保存し直すため、
  インストーラーからは確実に書けない。同じ理由で、アンインストールの前に Maya を終了してもらう。

### D-18: AE のタイムリマップのキーを Maya のマーカーにする（2026-10-20、利用者の要望）

- 利用者の決定: 表示は **タイムスライダーのブックマークとビューの重ね表示の両方**、内容は **キーの番号と素材のフレーム**
  （「AE キー 3/8　素材 36f」）、送り方は **AE のパネルのボタン**。**一度送れば、AE を開いていなくても表示される**こと。
- 時間の対応は転送と同じ `jobs.mapping_context()`（Origin frame、レイヤーの開始時間）。マーカーは AE → Maya の転送で
  タイムワープのキーが置かれるフレームと一致する（`core/markers.py`）。
- 流れ: AE `markers.request {export, options}` → ハブ（書き出しとキーの有無を確認して中継、`server/relay.py`）→
  Maya `markers.apply.request` → Maya が自分のシーンの fps で計算して保存。ハブの中継は解像度の枠と共通にした（`RelayToMaya`）。
- **シーンに保存するもの（1 回の取り消しで戻せる）:** network ノード `syncBridgeKeyMarkers` の文字列属性に JSON、
  キーごとのタイムスライダーのブックマーク（Autodesk の `timeSliderBookmark`、目印の属性 `syncBridgeMarker` 付き）。
  どちらも Maya 標準のものなので、SyncBridge のない PC で開いても問題ない（ファイルの `requires` は `timeSliderBookmark` だけ）。
  送り直したときと「マーカーを消す」では、SyncBridge のものだけを置き換える・消す（利用者のブックマークは残す）。
- **表示だけのもの（保存しない、undo に記録しない）:** ビューの左上に 2D で描くプラグインのノード `syncBridgeKeyMarker`。
  今のフレームがキーから半フレーム以内のときだけ表示する。描画のたびに network ノードを名前で読む（接続すると、
  `delete` が上流の network ノードまで消し、送り直すと新しいノードにつながらなかった。mayapy で確認）。
  保存の前後で外して戻す（D-16 と同じ）。シーンを開いたあとは、プラグインの `kAfterOpen` か SyncBridge のパネルを開いたときに
  出し直す。SyncBridge を起動していない Maya では、ブックマークだけが見える（起動処理には手を入れない、D-17）。
- （2026-10-20、利用者の要望）表示は **すべてのビュー** に出す。Maya の既定の「Update View: Active」（`playbackOptions -view`
  が `active`）では、時間を動かすとアクティブなビューだけが描き直されるため、表示する文字が変わったとき（キーに乗った・外れた）
  だけ `timeChanged` の通知から `M3dView.scheduleRefreshAllViews()` で全ビューを描き直す。利用者の設定は変えない。

### D-19: ポート 8765 がほかのプログラムに使われていたら、次の空きポートでハブを起動する（2026-10-20、利用者の決定）

- 実際に起きたこと: 別のプロジェクトのテスト用の Web サーバー（`py -m http.server 8765`）が残っていて、Maya の Connect が
  「port 8765 is used by another program」で止まった（2 回）。
- 決定: `launcher.ensure_server()` は、まず `session.json` のポートで SyncBridge のハブを探し、なければ 8765〜8774 のうち
  最初の空きポートで起動する（途中で SyncBridge のハブが見つかればそれを使う）。クライアント（Maya、AE、モニター）は
  もともと `session.json` からポートを読むので、変更は起動側だけ。
- 8765 を飛ばしたときは、使っているプログラムの名前と PID（`netstat -ano`、`hubs.port_owner()`）を日本語で Maya のパネルに出す。
  10 個とも使えなければ日本語のエラー。

### D-20: 解像度の枠とキーのマーカーを、ビューの「表示」メニューの専用の項目で出し入れする（2026-10-20、利用者の要望）

- 理由: 枠とマーカーはプラグインのロケーター（`MPxLocatorNode`）なので、ロケーターを隠すと一緒に消えていた。
  利用者は作業中にロケーターを隠すことが多い。
- 最初の案（ロケーターのまま `excludeAsLocator()` で「ロケーター」の表示から外す）は、Maya 2025 の GUI で効かなかった
  （テスト用プラグイン、2026-10-20。「ロケーター」を切ると消えた）。
- 決定: 2 つのノードを **プラグインのシェイプ（`MPxSurfaceShape`、`registerShape`）** に変え、`excludeAsPluginShape()` で
  「プラグインのシェイプ」の表示から外し、`pluginDisplayFilter` で「SyncBridge 解像度の枠」「SyncBridge キーのマーカー」を
  ビューの「表示」メニューに登録する（プラグインの読み込み時に登録、解除時に削除）。描画（`MPxDrawOverride`）、属性、
  ノード ID、保存時に取り外す仕組みはそのまま。ノードはシーンに保存されないので、古いシーンとの互換の問題はない。
  同じ方法のテスト用プラグインは Maya 2025 の GUI で、ロケーターを切っても残り、専用の項目でだけ消えた。H-MY-27。

### D-21: シーン設定（FPS・再生範囲・アニメーション範囲・ピクセル縦横比）の転送（2026-10-20、Phase 2、利用者の決定を含む）

- 両方のパネルから、両方向に送れる。項目はチェックで選ぶ（パネルごとに記憶）。変換はハブの `core.scene_sync`（D-2）。
  転送と同じく、転送先で確認ダイアログ → バックアップ → 1 回の取り消しで戻せる適用 → 読み戻し（SPEC 5 章）。
- 時間の対応は転送と同じ「Origin frame（Maya）= AE のコンプの 0 秒」。**AE のコンプの開始フレームも Origin frame にする**
  （利用者の決定。AE と Maya で同じフレーム番号が表示される）。アニメーション範囲 ⇔ コンプ（Origin frame から始まり、
  長さ = 終わり − Origin + 1）、再生範囲 ⇔ ワークエリア。始まりが Origin と違うときは注意を出す。
- Maya の FPS を変えるとき、**キーはフレーム番号のまま**（利用者の決定。`currentUnit -updateAnimation false`）。
  再生範囲は秒で保たれて動くので、FPS のあとで範囲を設定し直す。現在のフレーム番号も保つ。
  Maya が持たない FPS（18、72 など）は日本語で断る。AE の 29.97 と Maya の 29.97fps は同じとみなす（差 0.01 未満）。
- Maya の適用はプラグインの取り消しできるコマンド `syncBridgeApplySettings`（H-MY-28）: Maya 2023 では取り消しのまとまりで
  `playbackOptions` が戻らなかった（mayapy）。コマンドが前の値を持ち、取り消しで全部戻す。中で呼ぶコマンドは記録しない。
- Maya の `pixelAspect` を変えても `deviceAspectRatio` は変わらないので、幅 / 高さ × ピクセル縦横比を一緒に設定する。

### D-22: タイムスライダーの同期（2026-10-20、Phase 2、利用者の決定を含む）

- **双方向**（利用者の決定）。スイッチは 1 つで、どちらのパネルで切り替えても両方に反映（ハブが状態を持ち、接続時にも送る）。
  オンにしたパネルのアプリの時間に、もう片方が合わせる。
- メッセージの時間 `t` は AE のコンプ時間（秒）。Maya が自分の Origin frame と FPS で変換する（`core.time_sync`）。
  ハブは中継だけ（履歴に残さない）。
- Maya → AE: `timeChanged` の通知。スクラブ中は 1 秒に 30 回まで（最後の位置は必ず送る）。**再生中も追従するかは切り替え可能**
  （利用者の決定、既定はオフ: 再生中は送らず、止めた位置を送る）。
- AE → Maya: AE には時間が動いた通知がないので、パネルが 0.05 秒ごとに `comp.time` を読みに行き、変わっていれば送る
  （最初は 0.15 秒。利用者のテストで両方向とも少しラグがあり、2026-10-23 に短くした）。Maya から時間を受け取った直後の
  0.3 秒は読みに行かない（AE の evalScript は 1 つずつ実行されるので、読み取りが時間の設定の前に割り込むと遅れる）。
  Maya → AE の残りの遅れは、主に AE がフレームを描き直す時間（ビューアの解像度を下げると速くなる）。
- 往復の防止: 受け取って動かした時間は、自分の変化として送らない（Maya: `EchoGuard`、AE: 最後に適用した時間と比べる）。
  Maya が再生中は、AE からの時間で動かさない。

### D-23: Pixel Mapping（AE の BG スライドを Maya のカメラで再現）の座標と方式（2026-10-24、Phase 0 / 1）

- 仕様は利用者の「Pixel Mapping / BG Slide Sync 追加開発仕様書 v1.0」。詳細は `docs/PIXEL_MAPPING.md`。
- 共通の座標は **元画像の画素座標**（左上の角が原点、y 下、画素の中心は +0.5、double）。画素ごとの ID は使わない。
  AE は「元画像 → コンプ」の 3 × 3 アフィン行列、Maya は「元画像 → レンダー」をカメラの投影から求めて比べる。
- 変換は `core/pixel_mapping.py`（DCC 非依存、標準ライブラリのみ）、画像の比較は `pixelcheck/`（同期と独立。numpy が
  どの Python にもないので標準ライブラリで PNG を読む）。
- Maya の BG は利用者の制作に合わせて **3D の板ポリ** を基準にする（UV から元画像の角の位置を求める）。
  Image Plane は mayapy の検証で位置が丸められる・ずれるため、基準にしない。
- 方式は 3 つとも実装し、既定は **Film Offset**（透視）。平行投影では Film Offset と 2D Pan がレンダーに効かないので
  **Film Translate**。カメラの Transform とリグは変えない。キー・接続・ロックのある属性は上書きしない。
- 1 px 未満を妨げるのは方式ではなくテクスチャの扱い（Hardware 2.0 のテクスチャの最大解像度、既定 2048）。
  シーンの設定は変えず、利用者に知らせる。

### D-24: Virtual Layer Mapping とハブ経由の BG の位置の転送（2026-10-25、Pixel Mapping Phase 2）

- 対応付けは **Maya のシーン**（network ノード `syncBridgeLayerMappings`、JSON）に保存する。キーのマーカーと同じ方式で、
  シーンと一緒に別の PC へ移る。AE のプロジェクトには書かない（AE のどこに安全に書けるかは未確認のため）。
- AE のレイヤーは **コンプ ID + レイヤー ID**（ID がなければ名前）で、Maya のノードは **UUID** で見分ける。名前、
  インデックス、ネームスペースの変化に強い。
- 値の計算は **Maya の中で core を使う**（キーのマーカーと同じ。カメラと BG の情報は Maya にあるので、往復が 1 回で済む）。
  ハブは AE のデータを確かめて中継するだけ（`PixelMapFlow`）。
- 初回（対応付けを作るとき）だけ確認ダイアログを出す。BG の位置の調整のたびに確認させないため。毎回、バックアップと
  1 回の取り消し、キー・接続・ロックのある属性は上書きしない（開発ルール 2）。
- Phase 2 は今のフレームだけ。アニメーション（Phase 3）では、同じ対応付けでフレームごとに値を求めてキーにする予定。

## 4. 将来の構成（Phase 1 以降の方針）

- **サーバー:** FastAPI + WebSocket、`127.0.0.1` のみで待ち受ける。起動時にセッショントークンを発行し、
  ユーザーごとの一時ファイルで共有する。多重起動はロックファイル＋ポート確認で防ぐ。
  クライアント（Maya／AE のインスタンス）は接続時に `source_id`（アプリ名、PID、シーン／プロジェクト）を名乗る。
- **同期:** メッセージは `envelope.make()` の形式（`event_id`、`source_id`、`revision`）。サーバーはリビジョンを管理し、
  自分が送った変更の反映（エコー）を無視する。同時編集は競合として利用者に選ばせる。
- **Maya:** 受信処理は `maya.utils.executeDeferred` でメインスレッドに渡す。
- **AE:** CEP 側でメッセージをキューに入れ、`evalScript` で順に JSX を呼ぶ。変更検出はポーリング＋ハッシュ。
- **配布・更新（Phase 6）:** `SyncServer.exe` と `SyncUpdater.exe` を PyInstaller で作る。更新パッケージは
  署名し、アプリに同梱した公開鍵で検証する（SHA-256 だけでは真正性を保証できない）。
  更新チャンネルは development／stable を分け、stable はタグ付きリリースだけにする。
