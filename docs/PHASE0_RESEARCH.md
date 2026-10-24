# Phase 0 技術検証レポート

最終更新: 2026-10-16 / 対象: Maya 2023+, After Effects 2024+, Windows 10/11

実機プローブの実行記録は 8 章。現在までに実行したのは **Maya 2024 のプローブ 4 回、AE 26.5 での Export 1 回とプローブ 2 回**
（Maya 2023 は未実施）。

> **重要:** この文書の「仮説（H-*）」は、状態欄が ✅ のもの以外は実機で確認していない。
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
| H-MY-1 | UI で作った Scene Time Warp は、`time1` の名前に "timewarp" を含む入力属性へ接続された animCurveTT である | probe: `time_node.connections`, `animCurveTT_nodes` | ✅ Maya 2024: `timewarp`（animCurveTT）の **`.apply`** → `time1.timewarpIn_Raw`（`.output` ではない） |
| H-MY-2 | `time1.enableTimewarp` で有効／無効が切り替わり、`time1.outTime` がワープ後の時間を出す | probe: `warp_attributes`, `unit_checks.getAttr_time1_outTime` | ✅ Maya 2024: `enableTimewarp`（bool）は存在し、`EnableTimeWarp` ランタイムコマンドもこの属性を反転する。`getAttr time1.outTime -time t` はワープ後の時間を返した（フレーム 10 → 15.685）。有効/無効を切り替えたときの挙動は未確認 |
| H-MY-3 | `keyframe -q -vc` と `keyframe -q -eval` は TT カーブで現在の時間単位（フレーム）の値を返す | probe: `unit_checks` | ✅ Maya 2024（film）: `-vc`、`-eval`、`getAttr curve.output` が全て同じフレームの値 |
| H-MY-4 | TT カーブでは tan(接線角度) が無次元の傾き d(出力)/d(入力) | probe: `write_roundtrip`（非 weighted カーブ） | ✅ Maya 2024: 非 weighted の 8 カーブを書き込み、Maya の評価が誤差 0 |
| H-MY-5 | weighted 接線の時間方向の長さ = weight × cos(角度) × c。c は未確定 | probe: `write_roundtrip` の `asymmetric_ease`。PASS した候補が c | ✅ Maya 2024（film / 24fps）: **c = 1（"w (frames)"）**。weighted の 3 カーブ全てで、この候補だけが誤差 0（他の候補は 5.9〜54 フレームずれ）。`DEFAULT_WEIGHT_SCALE` を変更済み。24fps 以外の時間単位では未確認 |
| H-MY-6 | `setKeyframe` は animCurve ノード名を直接受け付ける | probe: `write_roundtrip` がエラーなく動くか | ✅ Maya 2024: 書き込んだ値で Maya の評価が誤差 0 |
| H-MY-7 | 非 weighted 区間は Hermite（= 1/3 ハンドルの Bezier）で評価される（devkit の animEngine に基づく） | probe: `write_roundtrip`（`speed_ramp_bezier`） | ✅ Maya 2024: 誤差 0。シーンの Scene Time Warp（fixed 接線 3 キー）も誤差 0 で再現 |
| H-MY-8 | Scene Time Warp はバッチレンダリングにも適用される | V-MY-3（レンダー比較） | ❓ |
| H-MY-9 | animCurve ノードの `preInfinity` / `postInfinity` 属性（enum、`getAttr -asString`）で範囲外の扱いを読める | probe: `scene_warp.node.*_infinity` | ✅ Maya 2024: シーンの `timewarp` で `setInfinity -q` は `None`、`getAttr -asString` は `Linear` |
| H-MY-10 | Scene Time Warp は MEL の `sceneTimeWarp "add"` で作成でき、`"delete"` で削除できる | ランタイムコマンド `AddTimeWarp` の中身から推定。作成の実行は未確認 | ❓（D-7） |
| H-MY-11 | Linear 外挿は、最初の区間の出の傾き・最後の区間の入りの傾きで延びる（中立カーブの仮定） | probe: `scene_warp.extrapolation`、`write_roundtrip` の範囲外のサンプル | ❌ **偽**（Maya 2024、3 回目）。Maya は **最初のキーの入りの接線・最後のキーの出の接線** で延ばす（シーンのカーブの範囲外 24 点で誤差 0）。中立カーブの外側ハンドルとして扱うよう修正済み。UI で作った Scene Time Warp は外側の接線が 0° なので、Linear 外挿でも実際は水平 |
| H-MY-12 | `setInfinity <カーブノード> -preInfinite linear` で外挿の種類を設定できる | probe: `write_roundtrip` の `linear_infinity` の読み戻し | ❌ **偽**（Maya 2024、3 回目）。linear を設定しても Constant のまま。`anim_curve.set_infinity()` でノードの enum 属性に直接書くよう修正し、4 回目で linear が保存され範囲外も誤差 0 になることを確認 |
| H-MY-13 | 区間より長い weighted ハンドルを、Maya は「区間内に縮める」と同等に評価する | probe: 誤った weight の単位で書いたカーブの読み戻し | ❌ **偽・未解決**（Maya 2024、3 回目）。1 本のハンドルが区間より長い 2 カーブで 15〜20 フレームずれた。4 つの候補モデルも合わない。2 本の合計が区間を超えるだけなら一致する。デコード時に警告を出す。SyncBridge のエンコーダはこの形を出力しない |
| H-MY-19 | Python API 2.0 の `MPxLocatorNode` + `MPxDrawOverride`（`MUIDrawManager` の line / text）で、Viewport 2.0 にレンダーされない枠を描ける。`MFrameContext.getCurrentCameraPath()` で描画中のビューのカメラがわかる（解像度の枠、D-16） | `plug-ins/syncbridge_guide.py` を読み込み、AE から枠を送る。別のカメラのビューでは描かれないこと | 一部 ✅ Maya 2024（mayapy）: プラグインの読み込みとノードの登録・作成・属性は確認。**描画は GUI の Maya で未確認**。判明: Maya はプラグインのファイルを `__file__` なしで実行する（NameError で読み込みに失敗した）→ `MFnPlugin.loadPath()` で場所を取る。`loadPlugin` はプラグインのコードが失敗しても例外を出さず、そのあとの `createNode` は不明なノードを作る → ノードの種類が登録されたか確かめてから作る。**Maya 2023（利用者の PC、GUI）: 今見ているカメラの子に置いた描画ノードは、描画用のオブジェクトが作られるだけで `isBounded` / `prepareForDraw` が一度も呼ばれない**（普通のロケーターはカメラの子でも描かれ、同じ描画ノードをワールドに置くと呼ばれる）→ ワールドに置き、カメラとは `worldMatrix` の接続で結ぶ。描画のコールバックは作例どおり渡す。**ワールドに置いて画面に描かれた（Maya 2023、2026-10-17）** が、バウンディングボックスありではカメラを動かすと消えた → バウンディングボックスなし（`isBounded` = False）に変更し、カメラを動かしても消えないことを確認（Maya 2023、2026-10-17）。**Maya 2023 で ✅**（2024 / 2025 の GUI は未確認） |
| H-MY-20 | Maya の解像度ゲートは、Film Fit（Fill / Horizontal / Vertical / Overscan）に従ってフィルムゲートに合わせた、デバイスアスペクト比の矩形である（`core/comp_guide.resolution_gate`）。フィルムオフセットはそのまま平行移動 | **レンダー解像度と同じ大きさのコンプを送ると、枠が Maya の Resolution Gate と重なる**。Film Fit を 4 種類とも、正射影カメラでも | 一部 ✅ Maya 2024（mayapy）: 透視カメラで、Film Fit 4 種類 × 縦横比 3 種類（2112x1188、1000x1000、1440x1080）すべてで `MFnCamera.getRenderingFrustum()` と一致（誤差 1e-6 未満）。正射影カメラとフィルムオフセット、画面上で重なるかは未確認 |
| H-MY-21 | `playblast -activeEditor` が、最後に操作したモデルパネルを返す（AE から送ったとき、Maya にフォーカスがなくても） | ビューを 4 分割して、別々のカメラのビューを選んでから送る | 一部 ✅ Maya 2023（利用者の PC、1 分割で top ビュー）: `playblast -activeEditor` = `modelPanel1`、`getPanel -withFocus` = `modelPanel1`、`M3dView.active3dView()` = `top` で一致。4 分割では未確認 |
| H-MY-24 | プラグインの 2D 描画（`MUIDrawManager.text2d` / `circle2d`、`MFrameContext.getViewportDimensions()`）で、ビューの左上に文字と丸を描ける（キーのマーカー、D-18） | AE からマーカーを送り、キーのフレームでビューの左上に「AE キー 3/8　素材 36f」が出るか | ❓ 📘。mayapy 2023 / 2024 で、描画の直前までの処理（今のフレームの取得、表示する文字の決定）は確認。`MAnimControl` は `OpenMaya` ではなく `OpenMayaAnim` にあった |
| H-MY-26 | `timeChanged` の通知（`MEventMessage`）で `M3dView.scheduleRefreshAllViews()` を呼ぶと、「Update View: Active」でもほかのビューが描き直される（キーのマーカーを全ビューに、D-18） | 4 分割のビューで時間を動かし、キーのフレームで全ビューに表示が出るか | ❓ 📘。mayapy 2023 / 2024: どちらの API もあり、`playbackOptions -view` の既定は `active`。表示が変わるフレームでだけ呼ばれることを確認 |
| H-MY-27 | `MPxSurfaceShape.excludeAsPluginShape()` が True のプラグインのシェイプは「表示 → ロケーター」「プラグインのシェイプ」に左右されず、`pluginDisplayFilter`（`-classification` に描画の分類 `drawdb/geometry/...`）で登録した項目が「表示」メニューに出て、そのノードだけを出し入れできる（D-20） | GUI の Maya で、ロケーターを切っても枠とマーカーが出るか、「表示」メニューの 2 つの項目で消えるか | ✅（テスト用プラグイン）Maya 2025 の GUI（利用者の PC、2026-10-20）: シェイプはロケーターを切っても残り、専用の項目で消えた。**ロケーター（`MPxLocatorNode.excludeAsLocator()`）では効かず、「ロケーター」を切ると消えた。** 本番のプラグインの GUI での確認は未実施。mayapy 2023 / 2024: 登録・解除・読み込み直し、シェイプにした枠とマーカーの表示・保存・開き直し |
| H-MY-28 | プラグインの取り消しできるコマンド（`MPxCommand`、`isUndoable`）で `currentUnit`・`playbackOptions`・`defaultResolution` をまとめて変えると、1 回の取り消しで全部戻る（シーン設定、D-21） | GUI の Maya で AE → Maya の設定を適用し、Ctrl+Z を 1 回 | ✅ mayapy 2023 / 2024: 1 回の取り消しで FPS・両方の範囲・ピクセル縦横比・現在のフレームが戻り、キーはフレーム番号のまま。取り消しの記録は 1 つだけ。普通の取り消しのまとまりでは、2023 で `playbackOptions` が戻らなかった。GUI は未確認 |
| H-MY-29 | `MEventMessage` の `timeChanged` と `MConditionMessage` の `playingBack` で、スクラブ・コマ送り・再生の開始と停止がわかる。`cmds.play(q=True, state=True)` で再生中かがわかる（時間の同期、D-22） | GUI の Maya でスクラブ・再生・停止し、AE が追従するか | ❓ 📘。mayapy 2023 / 2024: `currentTime` で `timeChanged` が呼ばれ、送る・受け取った時間を送り返さない・間引きを確認。再生（mayapy では `play` が None）は未確認 |
| H-PM-1 | Maya の透視カメラで、フィルム面と平行な板ポリの元画像の画素は `film = (X/−Z, Y/−Z) × focal / 25.4` から、横合わせなら `x_px = W/2 + film.x / (hfa/2) × W/2`、`y_px = H/2 − film.y / (hfa/2) × W/2` に写る（D-23） | mayapy で 6000 × 4000 のテスト用 BG をレンダーし、目印を測る | ✅ mayapy 2023 / 2024（Hardware 2.0 / Maya Software）: 0.15 px 以内。3:2 のフィルムの Fill、カメラと BG の移動・回転も |
| H-PM-2 | Film Offset と 2D Pan（renderPanZoom オン）は film から inch で引かれる。Film Translate は NDC（幅の半分 = 1、縦も同じ単位）で引かれる。Zoom は画像の中心で割る | 同上 | ✅ 同上。Hardware 2.0（テクスチャの最大解像度オフ）で 0.010 px 以下、Maya Software（Mipmap）で 0.40 px 以下 |
| H-PM-3 | 平行投影のカメラでは、Film Offset と 2D Pan はレンダーに効かない（Film Translate と Zoom は効く） | 同上 | ✅ 同上（両方のレンダー） |
| H-PM-4 | Hardware 2.0 は既定でテクスチャを 2048 px に縮める（`hardwareRenderingGlobals.enableTextureMaxRes`）。6000 px の BG で最大 1.4 px ずれる | 同上 | ✅ mayapy 2024 の既定値と実測 |
| H-PM-5〜7 | 方式の同時使用の順序、縦合わせの Film Fit、GUI の Playblast（`docs/PIXEL_MAPPING.md` 6 章） | | ❓ |
| H-MY-25 | タイムスライダーのブックマークは `timeSliderBookmark` ノード（属性 `name`、`color`、`timeRangeStart`、`timeRangeStop`、`priority`）で、Autodesk の `timeSliderBookmark` プラグインが読み込まれていれば作れる。保存・開き直しで残る（D-18） | mayapy で作成・保存・開き直し | ✅ mayapy 2023 / 2024: mayapy ではプラグインが読み込まれていないので `loadPlugin` が必要。ファイルには `requires -nodeType "timeSliderBookmark" "timeSliderBookmark"`。日本語の名前も残る。GUI のタイムスライダーでの見え方は未確認 |
| H-MY-23 | Maya 2023 以降は起動時に `<ユーザー設定>\prefs\shelves\shelf_*.mel` を読み込み、シェルフのタブとして表示する（インストーラーが置いたものも）。`prefs\icons` はアイコンの検索先（D-17） | 0.1.5 をインストールしてから Maya を起動し、「SyncBridge」タブとアイコンが出るか | ✅ Maya 2023（利用者の PC、2026-10-19、インストール版 0.1.5）: タブが出てパネルが開いた。2024 / 2025 の GUI と日本語版は未確認（mayapy 2023 / 2024 で MEL として読めることは確認） |
| H-MY-22 | `MFnDependencyNode.setDoNotWrite(True)` にしたノードはシーンに保存されず、`requires "syncbridge_guide.py"` も書かれない | 枠を表示したまま .ma で保存し、ファイルに `syncBridgeCompGuide` と `requires` がないことを確認 | ❌ 一部偽（Maya 2024、mayapy）: ノードは保存されないが、`requires -nodeType "syncBridgeCompGuide" "syncbridge_guide.py"` は書かれる（`pluginInfo -writeRequires false` でも同じ）。枠がなければ書かれない → プラグインが保存の直前に枠を外し、直後に戻す（D-16）。3 回保存してファイルに記述がないことを確認。**この処理を undo に記録すると、保存のあとの undo で Maya がクラッシュした** → 枠の作成・削除は undo に記録しない |

**実機で確認した事実（Maya 2024）:**
- `setInfinity <animCurveノード> -q -preInfinite` は `None` を返す（一時 animCurveTT とシーンの `timewarp` の両方）。→ `anim_curve.query_infinity()` でノード属性から読む。
- UI で作った Scene Time Warp は **前後とも Linear 外挿** だった（このシーンの場合）。AE の Time Remap は範囲外で値を保持するだけなので、キーの範囲外は一致しない（R-20）。
- （利用者の観察、2026-10-16）Scene Time Warp の値の範囲は **作成した時点で決まる**。キーのタイミング（横方向）をずらしても値は変わらず、
  再生範囲を変えた場合は作り直しが必要だった。例: キー (1→0)、(16→174.1)、(48→220) で再生範囲 1〜47 のシーン。
  作成時に再生範囲の両端へ「値 = 時刻」のキーが作られる、という推定（H-MY-18 ❓、作成時の範囲を変えて確認する）。
  グラフエディタでキーの値（縦方向）を直接変えて済むかは未確認。
  影響: タイムワープの値の範囲 = AE で必要な素材の範囲。素材（ワープなしのレンダー）より広いと AE に適用できない（R-16）。

### After Effects

| ID | 仮説 | 判定方法 | 状態 |
|---|---|---|---|
| H-AE-1 | Time Remap の `keyTime`／`setValueAtTime`／`valueAtTime` はコンプ時間で扱われる（layer.startTime ≠ 0 でも） | probe: `@startTime0.5` の結果 | ✅ AE 26.5: `speed_ramp_bezier@startTime0.5` が誤差 0 |
| H-AE-2 | Time Remap の値はレイヤーソース時間（秒） | probe: `slowmo_linear`, `identity` | 一部 ✅ AE 26.5: プロパティ値は秒で、こちらの計算と一致。実際に表示されるソースのフレームとの対応はレンダー比較（V-MY-3）で確認する |
| H-AE-3 | イーズ → ハンドル: dx = 影響度/100 × 区間長、dy = 速度 × dx | probe: `speed_ramp_bezier`, `asymmetric_ease` | ✅ AE 26.5: Bezier の 3 ベクトルが誤差 0（許容 0.01 フレーム） |
| H-AE-4 | Time Remap のキー削除やイーズ設定は他の 1D プロパティと同様に動く | probe 全体がエラーなく動くか | ✅ AE 26.5: 10 回の実行でエラーなし。ただし設定の順序に注意（H-AE-11） |
| H-AE-5 | `setValueAtTime` でサブフレーム時刻にキーを置ける（フレームに丸められない） | probe: `subframe_keys` の時刻の変化（`verify-ae-probe` の右端の列） | ✅ AE 26.5: フレーム 24.5 と 48.25 のキーが時刻を変えずに保持され、評価も誤差 0 |
| H-AE-6 | 片側 LINEAR・片側 BEZIER の区間は「LINEAR 側のハンドル = 弦の 1/3」で評価される | probe: `ae_mixed_linear_bezier`（AE 形式で直接送る） | ❌ **偽**（AE 26.5）。1/3 では 2.85 フレームずれた。AE は LINEAR 側を **弦の方向に区間の 1/6** のハンドルとして評価する（誤差 0）。`ae_codec.LINEAR_SIDE_FRACTION` = 1/6 に修正済み。ただし、このモデルは同じ 1 ベクトル（向きの違う区間 2 つ）に合わせて決めたもの。エンコーダはこの形を出力しないので、AE 側で作られたキーを読むときにだけ影響する |
| H-AE-7 | 影響度の合計が 100% を超えても、AE はハンドルを縮めずにそのまま評価する | probe: `asymmetric_ease`（区間 2→3 秒） | ✅ AE 26.5: 影響度 30% + 90% の区間が誤差 0 |
| H-AE-8 | CEP パネルから `ws://127.0.0.1` に接続できる | V-AE-3 | ❓ |
| H-AE-9 | AE の「29.97」は 30000/1001 ではなく 2997/100（`frameDuration` = 1/29.97） | Export の `comp.frameDuration` と `duration` | ✅ AE 26.5（1 コンプで確認）: `frameDuration` = 0.03336670003337 = 1/29.97、`duration` 11.011011… = 1/29.97 でちょうど 330 フレーム（30000/1001 では 330.00033）。23.976 など他のレートは未確認 |
| H-AE-11 | `setTemporalEaseAtKey` を呼ぶと、そのキーの補間が BEZIER になる（イーズの値はそのまま） | probe の `interp` の変化 | ✅ AE 26.5: 補間の種類 → イーズの順に設定したら、全キーが BEZIER/BEZIER になった。`applyKeys` をイーズ → 補間の種類の順に修正し、2 回目のプローブで LINEAR/HOLD が保たれることを確認 |
| H-AE-12 | 補間を LINEAR にすると、AE はその側のイーズを（直線の傾き、影響度 16.667%）に書き換える | probe 2 回目の `readKeys` | ✅ AE 26.5: 全ベクトルの LINEAR 側で確認（例: `slowmo_linear` の 1 秒のキーは入り 1、出 0.5）。最初のキーの入りと最後のキーの出は速度 0 |
| H-AE-20 | `CompItem.width` / `height` / `pixelAspect` でコンプの解像度とピクセル縦横比を読める（解像度の枠、D-16） | AE のパネルで「解像度の枠を Maya へ」を押し、ログの大きさがコンプ設定と一致すること | ✅ AE 26.5（利用者の PC、2026-10-17、インストール版 0.1.4）: 枠が Maya に表示された |
| H-AE-21 | `comp.frameRate` / `duration` / `displayStartTime` / `workAreaStart` / `workAreaDuration` / `pixelAspect` をスクリプトで変えられ、1 つの取り消しのまとまりで 1 回の取り消しで戻る（D-21） | AE で「設定 Maya → AE」を適用し、コンポジション設定を見る。取り消しを 1 回 | ❓ 📘 |
| H-AE-22 | `displayStartTime` は AE が表示するフレーム番号だけを変え、`comp.time`、レイヤーの時間、タイムリマップのキーの時間は、コンプの始まり（0 秒）からのまま（D-21） | 開始フレームを Origin にしたあと、タイムワープの転送とキーのマーカーが前と同じ位置になるか | ❓（転送とマーカーの時間の対応がこれに頼る） |
| H-AE-23 | パネルから `comp.time` を書くと、現在の時間インジケーターとビューアが動く。0.05 秒ごとに `comp.time` を読んでも AE の操作が重くならない（D-22） | 同期をオンにして Maya でスクラブ、AE でスクラブ | 一部 ✅ 利用者の PC（2026-10-23、テスト版 0.1.8、0.15 秒ごと）: 両方向に追従した。少しラグあり → 0.05 秒に短縮（重さは未確認） |
| H-AE-24 | AE は 2D レイヤーの元画像の座標を `Position + (source − Anchor Point)` のコンプの座標に描く（画素の中心の扱いも同じ。半端な位置は補間）。Pixel Mapping（D-23） | `after_effects/jsx/pixel_mapping_reference.jsx` → `tools/pixel_mapping/check_reference.py` | ❓（Maya 側は確認済みで、AE と Maya をつなぐ最後の前提） |
| H-AE-25 | `CompItem.saveFrameToPng(time, file)` でコンプの 1 フレームを PNG に保存できる | 同じスクリプト | ❓ |
| H-AE-10 | Time Remap を有効にした直後は、レイヤーのイン点とアウト点に LINEAR のキーが 2 つでき、最後のキーの値はソースの長さ | Export の `keys` | ✅ AE 26.5（1 コンプで確認）: 0 秒 → 0、11.011 秒 → 11.011（ソース長）。「ソース長 − 1 フレーム」ではなかった |

---

## 5. 実装上のリスク

| ID | リスク | 影響 | 対策 |
|---|---|---|---|
| R-1 | Scene Time Warp の構造が H-MY-1/2 と違う | 中（Maya 2024 で H-MY-1 を確認） | 接続の探索で特定、プローブで構造を記録、Phase 0 ではカーブを新規作成しない（D-7）。Maya 2023 でも確認する |
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
| R-14 | NTSC・ドロップフレーム。AE の 29.97 は 2997/100 で、Maya や 30000/1001 と一致しない（H-AE-9） | 中（1 時間でおよそ 0.1 フレームのずれ） | 時間は有理数の fps と秒で扱う。AE の fps は `FrameRate.from_ae()` で `frameDuration` に最も合う値を選ぶ（実装済み）。Maya の 29.97fps の内部値は未確認。29.97df は表示上の問題 |
| R-15 | stretch ≠ 100%、ネストしたプリコンポジション | 中 | Phase 0 は stretch = 100% を前提とし、違えば確認を出す。ネストは 1 段のみ |
| R-16 | Time Remap の値がソースの長さでクランプされる可能性、最終フレームの扱い（既定の最後のキーはソース長そのもの、H-AE-10） | 高（**実際に発生**） | 2026-10-16、0.1.0 の利用者テストで発生: AE は 0〜素材の長さの外の値で `setValueAtTime` が例外（「値 7.26 は 0 から 2 の範囲外」、H-AE-19 ✅）。書き込みの途中で失敗し得る。→ サーバーが変換後のカーブ全体（Bezier の行き過ぎを含む）を素材の長さと比べ、超えていれば AE に送らず日本語で理由を返す（`jobs.check_source_range`）。AE 側も書き込み前に全キーを確認（`SB.checkSourceRange`）。0.1.1 で修正 |
| R-17 | Maya の pre/post infinity が cycle などの場合 | 低 | 警告を出して constant として扱う（実装済み） |
| R-20 | Scene Time Warp が Linear 外挿で、キーの範囲外にコンプやレンダー範囲がある | 中 | 対応済み（2026-10-16）: 転送に評価範囲（`t_range`）を追加。Precision は範囲外の外挿をキーに焼き込み、Editable は警告して不合格にする。CLI は既定で Maya の再生範囲／AE のコンプ範囲を使う（`--range`、`--no-range`）。外挿の傾きは外側の接線（H-MY-11 で確認） |
| R-19 | 文書化されたクエリが実機では期待した値を返さない（例: `setInfinity -q` が `None`） | 中 | クエリ結果が空なら明確なエラーにする（`_query_list`）。代替手段を用意し、ダミーの cmds で回帰テストする |
| R-18 | Maya 2023 の `stepnext` 接線 | 低 | Editable では警告、Precision を推奨（実装済み） |

---

## 6. 検証手順

すべての結果ファイルは `probe_results/`（Git 管理外）に置き、要約をこの文書の 4 章と `PROGRESS.md` に転記する。

### V-MY-1: Maya プローブ（H-MY-1〜7, 9）

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

準備: Maya は **テスト用に保存したシーン**（Scene Time Warp あり）。AE は **テスト用プロジェクト** に、Maya と同じ fps（例: 24）の
コンプ `SB_test` を作り、別のコンプ `SB_src`（同じ fps、ワープ後の時間より長い尺）をレイヤーとして置き、Time Remap を有効にする。
`--origin` は Maya の再生範囲の開始フレーム（Maya の開始フレーム ⇔ コンプ時間 0、ソース時間 0）。以下は開始フレーム 1 の例。

1. Maya: `sbx.export_timewarp(r"<repo>/probe_results/v2_maya.json")`（`decode vs Maya` が PASS であること）
2. AE: `SB_src` のレイヤーを選び、`syncbridge_ae.jsx` → Export → `v2_ae_before.json`
3. PC: `.\syncbridge.cmd maya2ae probe_results\v2_maya.json -o probe_results\v2_ae_apply.json --ae-export probe_results\v2_ae_before.json --origin 1 --mode editable`
4. AE: 同じレイヤーを選び、`syncbridge_ae.jsx` → Apply… → `v2_ae_apply.json`（`v2_ae_apply_after.json` が出力される）
5. PC: `.\syncbridge.cmd readback probe_results\v2_ae_apply.json probe_results\v2_ae_apply_after.json`
6. `--mode precision`（出力名 `v2_ae_apply_precision.json`）でも 3〜5 を繰り返す。
7. AE で「編集 → 取り消し」1 回で元に戻ることも確認する。

### V-MY-3: レンダー一致（H-MY-8、R-5）

1. Maya でフレーム番号を焼き込んだテストシーン（例: フレーム番号を表示する文字オブジェクト）を用意する。
2. (a) ワープを **無効** にしてレンダリング → AE に読み込み、V-MY-2 の手順で Time Remap を適用する。
3. (b) ワープを **有効** にしてレンダリングする。
4. (a) の AE 出力と (b) を同じフレームで比較し、焼き込まれたフレーム番号が一致することを確認する。

### V-AE-1: AE プローブ（H-AE-1〜7）

1. PC: `.\syncbridge.cmd probe-vectors -o probe_results/ae_probe_vectors.json`
2. AE 2024 以降で任意のプロジェクトを開き、`File > Scripts > Run Script File...` → `after_effects/jsx/probe_ae.jsx` → 1. のファイルを選ぶ。
   一時コンプ `SB_probe_inner` と `SB_probe_outer` を作成し、終了時に削除する（既存のコンプは変更しない）。
3. PC: `.\syncbridge.cmd verify-ae-probe probe_results/ae_probe_results.json`
4. 判定: 左列「送信キー vs AE の評価値」がすべて PASS なら H-AE-2/3/6/7 は真。
   `@startTime0.5` が PASS なら H-AE-1 は真。右列「AE が読み返したキー vs AE の評価値」が FAIL の場合は、
   AE がキーを書き換えている（丸め、正規化）ので `readKeys` と `sentKeys` を比較する（H-AE-5）。

### V-AE-2: AE → Maya のエンドツーエンド

1. AE: V-MY-2 で適用したレイヤーの Time Remap を少し編集する（例: 中間のキーの値を変える）。レイヤーを選び Export → `v2_ae_edited.json`
2. PC: `.\syncbridge.cmd ae2maya probe_results\v2_ae_edited.json -o probe_results\v2_maya_apply.json --maya-export probe_results\v2_maya.json --origin 1 --mode editable`
3. Maya: `sbx.apply_timewarp(r"<repo>/probe_results/v2_maya_apply.json")` → 確認ダイアログ、JSON バックアップ、適用、
   リードバックの結果（`SyncBridge: readback PASS ...`）が Script Editor に表示される。
4. Maya で Ctrl+Z 1 回で元に戻ることを確認する。

### V-AE-3: CEP から localhost への通信（H-AE-8、Phase 1 の前提）

1. 開発用に PlayerDebugMode を有効にする（Windows レジストリ `HKEY_CURRENT_USER\Software\Adobe\CSXS.<バージョン>` の
   `PlayerDebugMode` = `1`）。**システム設定の変更なので利用者自身が行う。** CSXS のバージョン番号は AE のバージョンごとに確認する。
2. Phase 1 で用意する最小 CEP パネルから `ws://127.0.0.1:8765` に接続し、echo の往復を確認する。

---

## 7. 合格条件（Phase 0）

| # | 条件 | 状態 |
|---|---|---|
| P0-1 | 単体・結合テスト（`python -m unittest discover -s tests -t .`）が全件 PASS（CI: Windows/Ubuntu × Python 3.9/3.11） | ✅ ローカル 82 件 PASS（Python 3.10）。CI は 2026-10-16 の push で実行し、利用者が確認 |
| P0-2 | `.\syncbridge.cmd selftest` が全件 PASS（10 カーブ × 2 モード × 2 方向、誤差 0.1 フレーム以下） | ✅ |
| P0-3 | V-MY-1: H-MY-1〜7, 9 の判定が記録され、`write_roundtrip` が少なくとも 1 つの weight 候補で全カーブ 0.01 フレーム以下 | ✅ Maya 2024（2 回目）: H-MY-1〜7, 9 を判定、全カーブが "w (frames)" で誤差 0。Maya 2023 では未実施。3 回目で範囲外の評価（H-MY-11）も判定し、実データを回帰テスト化 |
| P0-4 | V-AE-1: `verify-ae-probe` が全件 PASS（許容 0.01 フレーム）、`@startTime` 版も PASS | ✅ AE 26.5（2 回目、13 ベクトル全て誤差 0。ただし `ae_mixed_linear_bezier` は H-AE-6 のモデル修正後の再判定）。AE 2024/2025 では未実施 |
| P0-5 | V-MY-2 / V-AE-2: 両方向・両モードでリードバックの誤差が 0.1 フレーム以下 | 実施中: **Editable は両方向とも合格**（リードバックとアプリ間の直接比較が誤差 0、8 章 #8・#9）。Precision モードの実機テストは先送り（利用者の判断、PROGRESS.md 参照） |
| P0-6 （先送り） | V-MY-3: レンダー比較で焼き込みのフレーム番号が一致 | 未実施 |

P0-3〜P0-6 の結果によって設計変更が必要になった場合は、`ARCHITECTURE.md` の「設計判断」に理由とともに追記する。

---

## 8. 実機プローブの実行記録

### 2026-10-16 #1 — Maya 2024（V-MY-1）

- 環境: Maya 2024（API 20240000）、Python 3.10.8、PySide2 5.15.2.1、Windows 11（26200）、時間単位 film（24fps）
- シーン: UI で Scene Time Warp を作成済み、`enableTimewarp` = true
- 結果:
  - `time1` の関連属性: `enableTimewarp`, `timewarpIn`（compound）, `timewarpIn_Raw`, `timewarpIn_Hidden`,
    `timewarpIn_Inmap`(`From`/`To`), `timewarpIn_Outmap`(`From`/`To`), `unwarpedTime`
  - 接続: `timewarp.apply` → `time1.timewarpIn_Raw`（animCurveTT は `timewarp` の 1 つだけ）→ H-MY-1 ✅
  - 関連コマンド: `sceneTimeWarp "add" / "delete" / "select"`、`EnableTimeWarp` = `enableTimewarp` を反転して `currentTime` を再設定
  - **読み取りは全て失敗:** `setInfinity -q` が `None` を返し `read_raw` が TypeError で停止。
    書き込み（`setKeyframe`, `cutKey`, `keyTangent`, `setInfinity` 編集）は全カーブでエラーなし。
- 対応: `query_infinity()`（ノード属性へのフォールバック）、クエリ結果の検査、プローブの記録項目の追加
  （トレースバック、カーブの属性、`.apply` の評価、`unwarpedTime`）。ダミー cmds の回帰テストを追加。
- 次: 修正版で V-MY-1 を再実行し、H-MY-3〜7, 9 を判定する。

### 2026-10-16 #2 — After Effects 26.5（`syncbridge_ae.jsx` Export、V-AE-1 ではない）

- 環境: AE `app.version` = 26.5x89、日本語 UI、Windows 11
- 経緯: スクリプトの起動と `#include` は問題なし。レイヤー未選択や平面レイヤーで前提チェックが働いた
  （表示を案内文に改善、平面などは Time Remap を使えない旨を表示）。プリコンのレイヤーで Export に成功。
- データ: コンプ「コンポ 1」3840×2160、29.97fps、11.011 秒。レイヤー「コンポ 2」（プリコン、startTime 0、stretch 100%）。
  Time Remap は有効にした直後の状態で、キーは 2 つ（0 → 0、11.011 → 11.011、LINEAR）。
- 結果:
  - 日本語の名前は UTF-8 で正しく書き出された（Python のコンソール表示が cp932 で文字化けしただけ）
  - `ae_codec` の評価と AE の `valueAtTime`（1321 点）が誤差 0 で一致
  - **AE の 29.97 は 2997/100**（H-AE-9）→ `FrameRate.from_ae()` を追加し、CLI で使用
  - 既定の最後のキーの値はソース長そのもの（H-AE-10）
- 次: `probe_ae.jsx`（V-AE-1）で H-AE-1〜7 を判定する。23.976fps などのコンプで H-AE-9 を追加確認する。

### 2026-10-16 #3 — After Effects 26.5 プローブ 1 回目（V-AE-1）

- 環境: AE 26.5x89、ExtendScript 4.5.6、Windows 11。ベクトル 8 種 + `@startTime0.5` 版 2 種、24fps、エラー 0
- Time Remap を有効にした直後のキー（60 秒の内側コンプ）: 0 → 0、60 → 60（H-AE-10 と一致）
- 結果（`probe_results/ae_probe_results_run1.json`）:

| ベクトル | 送ったキー vs AE の評価 | AE が読み返したキー vs AE の評価 |
|---|---|---|
| speed_ramp_bezier / asymmetric_ease / nonmonotonic_bezier / speed_ramp_bezier@startTime0.5 | PASS（誤差 0） | PASS |
| identity / slowmo_linear / freeze_hold / jump_hold / reverse / slowmo_linear@startTime0.5 | FAIL（2.3〜48 フレーム） | PASS |

- 原因: 送った LINEAR / HOLD が全て BEZIER/BEZIER になっていた（時刻・値・イーズの値は送ったとおり）。
  `applyKeys` が補間の種類 → イーズの順に設定しており、イーズの設定で BEZIER に戻ったと判断（H-AE-11）。
- 判定: H-AE-1 ✅、H-AE-3 ✅、H-AE-4 ✅、H-AE-7 ✅、H-AE-2 一部 ✅、H-AE-11 ✅（新規）。
  H-AE-5 と H-AE-6 は、ベクトルが該当する状況を含んでいなかったため未判定。
- 対応: `applyKeys` をイーズ → 補間の種類の順に変更。ベクトル `linear_then_ease`（途中のキーの片側が LINEAR）、
  `subframe_keys`（H-AE-5）、`ae_mixed_linear_bezier`（AE 形式で直接送る、H-AE-6）を追加。
  `verify-ae-probe` に送ったキーと読み返したキーの差（キー数、時刻、補間の種類、イーズ）の列を追加。
- 次: 修正版で V-AE-1 を再実行する（11 ベクトル + `@startTime` 版 2 種）。

### 2026-10-16 #4 — After Effects 26.5 プローブ 2 回目（V-AE-1）

- 実行: 13 回（11 ベクトル + `@startTime0.5` 版 2 種）、エラー 0
- 1 回目の判定（修正前のデコーダ）: `ae_mixed_linear_bezier` 以外の 12 ベクトルが誤差 0、キーの時刻と補間の種類は送ったとおり。
  `ae_mixed_linear_bezier` だけ 2.85 フレームのずれ。全ベクトルで LINEAR 側のイーズの値が書き換わっていた。
- 分析: `ae_mixed_linear_bezier` の AE のサンプルに候補モデルを当てはめた。
  弦の 1/3（従来）2.85 フレーム、長さ 0 のハンドル 3.02 フレーム、**弦の方向に区間の 1/6：誤差 0**。
  AE が LINEAR 側に保存するイーズ（直線の傾き、16.667%）をそのまま使っても同じ結果（H-AE-12）。
- 判定: H-AE-5 ✅、H-AE-6 ❌（1/6 に修正）、H-AE-11 修正の効果を確認、H-AE-12 ✅（新規）。
- 対応: `ae_codec` の片側 LINEAR の区間を 1/6 で評価するよう修正 → 13 ベクトル全て誤差 0。
  `verify-ae-probe` は BEZIER 側のイーズだけを比較するよう変更。
  実データの一部を `tests/fixtures/ae26.5_probe_run2.json` として保存し、回帰テスト（`tests/unit/test_ae_real_data.py`）を追加。
- 残り: AE 2024/2025 では未確認。片側 LINEAR の 1/6 モデルを別のデータで確かめる。

### 2026-10-16 #5 — Maya 2024 プローブ 2 回目（V-MY-1）

- 環境: 1 回目と同じ（Maya 2024、film / 24fps）。モジュールを読み込み直して修正版を実行
- シーンの Scene Time Warp: キー 3 つ（1→1、10→15.685、24→24）、接線 fixed、非 weighted、**前後とも Linear 外挿**
- 結果:
  - `setInfinity -q` はシーンのカーブでも `None`、`getAttr -asString` は `Linear`（H-MY-9 ✅）
  - `keyframe -vc` / `-eval` / `getAttr curve.output` は同じフレーム値（H-MY-3 ✅）。`getAttr time1.outTime -time t` はワープ後の時間（H-MY-2 ✅）
  - シーンのカーブのデコード vs Maya の評価: 誤差 0（93 サンプル）
  - 書き込みテスト: 非 weighted の 8 カーブ（HOLD、サブフレームのキーを含む）が誤差 0（H-MY-4/6/7 ✅）
  - weighted の 3 カーブ（`asymmetric_ease`、`nonmonotonic_bezier`、`linear_then_ease`）は **"w (frames)" だけが誤差 0**、
    他の候補は 5.9〜54 フレームずれ（H-MY-5 ✅、c = 1）
- 対応: `DEFAULT_WEIGHT_SCALE` を "w (frames)" に変更。換算式を `angle_weight_to_tangent` / `tangent_to_angle_weight` にまとめ、
  逆変換のテストを追加（計 65 件 OK）。
  プローブを拡張: キーの範囲外 ±12 フレームもサンプル、Linear 外挿のテストカーブを追加、
  シーンのカーブの範囲外の値を記録（H-MY-11）、書き込みテストのサンプル値を保存（次回の結果を回帰テストのデータにする）。
- 次: プローブ 3 回目で H-MY-11 を判定する。24fps 以外の時間単位で H-MY-5 を確認する。Maya 2023 でも実行する。

### 2026-10-16 #6 — Maya 2024 プローブ 3 回目（V-MY-1）

- 出力先が 2 回目と同じ名前だったため、結果ファイルを `maya_probe_run3.json` に改名した（2 回目の内容は #5 に記録済み）
- 結果:
  - シーンのカーブの範囲外（前後 12 フレーム）: 従来のデコードは最大 12 フレームずれ（Maya 24.0、デコード 36.0）。
    「最初のキーの入り・最後のキーの出の接線で延ばす」モデルで 24 点すべて誤差 0（H-MY-11 は偽 → 修正）
  - `linear_infinity` の書き込み: 6 フレームのずれ。Maya に残った外挿は Constant（`setInfinity` の設定が効いていない、H-MY-12）。
    加えて、エンコーダが外側の接線を傾き 0 で書いていた
  - 書き込みテストの他のカーブは 2 回目と同じ（weighted は "w (frames)" のみ誤差 0）
  - 誤った単位で書いた 20 件の読み戻しを正しい単位で再デコード → 18 件は誤差 0、
    1 本のハンドルが区間より長い 2 件だけ 15〜20 フレームずれた（H-MY-13、未解決）
- 対応:
  - 中立カーブ: 外挿の傾きに外側ハンドル（最初のキーの入り・最後のキーの出）を使う（`TimeCurve.edge_slope`）
  - Maya コーデック: 外側の接線をデコード／エンコードする。区間より長いハンドルを警告する
  - Maya アダプタ: 外挿の種類を enum 属性に直接書き、書いた後に読み戻して確認する（`set_infinity`）
  - 実データを `tests/fixtures/maya2024_probe_run3.json` に保存し、回帰テスト（`tests/unit/test_maya_real_data.py`）を追加（計 80 件 OK）
- 次: プローブ 4 回目で `set_infinity` の修正（H-MY-12）を確認する。24fps 以外、Maya 2023 でも実行する。

### 2026-10-16 #7 — Maya 2024 プローブ 4 回目（V-MY-1）

- 結果（`probe_results/maya_probe_run4.json`）:
  - シーンのカーブの範囲外: 誤差 0（3 回目は 12 フレーム）→ 外側の接線で延ばす修正（H-MY-11）を確認
  - `linear_infinity` の書き込み: 誤差 0（3 回目は 6 フレーム）。Maya に残った外挿は linear/linear、外側の接線は 26.565°（傾き 0.5）、
    キーの前後 12 フレームで 18.0 / 42.0 → `set_infinity`（H-MY-12 の修正）を確認
  - その他の書き込みテストは 3 回目と同じ（weighted は "w (frames)" のみ誤差 0、区間より長いハンドルは H-MY-13 のまま）
- 対応: `linear_infinity` の結果を `tests/fixtures/maya2024_probe_run3.json` の `run4_linear_infinity` に追加し、回帰テストを追加（計 81 件 OK）
- 残り（Maya）: 24fps 以外の時間単位（H-MY-5）、Maya 2023、レンダー（H-MY-8）、自動作成（H-MY-10）、H-MY-13

### 2026-10-16 #8 — 転送テスト V-MY-2（Maya 2024 → AE 26.5、Editable）

- 構成: Maya のシーン（film、Scene Time Warp 3 キー、前後 Linear・外側の接線 0°）、AE のコンプ `SB_test`（24fps）に
  プリコン `SB_src`（startTime 0、stretch 100%）、`--origin 1`
- 手順と結果:
  - Maya `export_timewarp` → 成功（初めての実行）
  - CLI `maya2ae --mode editable`: conversion PASS（誤差 0）、source fidelity PASS、評価範囲 0〜2 秒（AE のコンプ範囲）
  - AE Apply → 3 キー適用、JSON バックアップ作成（初めての実行）
  - `readback`: **PASS（誤差 0、185 点）**
  - Maya の評価値と AE の Time Remap の直接比較（Maya フレーム 1 ⇔ コンプ 0 秒・ソース 0 秒）: **PASS（誤差 0、92 点）**
- 見つかった問題と対応:
  - AE の保存・読み込みダイアログが `probe_results` ではなくスクリプトのフォルダで開き、適用ファイルが見つからなかった
    → Export はファイル名の入力で `probe_results` に保存、Apply は `probe_results` の適用ファイルを新しい順に一覧から選ぶ形に変更。
    存在しないファイルは「File not found」と表示。`after_effects/jsx/*.json` を `.gitignore` に追加
  - 外側の接線が 0° の Linear 外挿にも「表現できない」警告が出ていた → 傾きがあるときだけ警告するよう変更（transfer、ae_codec）
- 次: 取り消しの確認、Precision モード、AE → Maya（V-AE-2）
- 追記: AE の Apply は「編集 → 取り消し」1 回で元に戻ることを利用者が確認

### 2026-10-16 #9 — 転送テスト V-AE-2（AE 26.5 → Maya 2024、Editable）

- AE で中間のキーを編集（時刻 9 → 16 フレーム、値 約 14.7 → 7.58 フレーム）し、入力式の Export で `v2_ae_edited.json` を保存
- CLI `ae2maya --mode editable --origin 1`: source fidelity PASS（誤差 0）、conversion PASS（誤差 0）、3 キー、警告なし
- Maya のキー: 1→1、**17→8.58**、24→24（AE のフレーム + 1 の対応どおり）。非 weighted、外挿は Constant（AE に Linear 外挿は無い）
- Maya `apply_timewarp`（初めての実行）: 確認ダイアログ → JSON バックアップ → 適用 → **readback PASS（誤差 0、93 点）**
- AE の評価値と、Maya に適用したカーブの直接比較: **誤差 0（93 点）**
- 取り消し: Maya で Ctrl+Z 1 回で元のカーブ（10→15.69）に戻ることを利用者が確認
- 結論: Editable モードで Maya ⇔ AE の両方向を実機で確認（Maya 2024・AE 26.5、24fps、stretch 100%、startTime 0）。
  Precision モード、AE の取り消し、startTime ≠ 0 や fps 違いの構成は未確認
