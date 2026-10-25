# Pixel Mapping / BG Slide Sync

最終更新: 2026-10-25 / 状態: **Phase 0 / Phase 1 完了（AE ⇔ Maya の位置の差 最大 0.045 px）。Phase 2 完了（利用者が GUI で確認、2026-10-25）。Phase 2.5 相対モード実装済み（GUI の確認待ち）**

AE で大判 BG を Position でスライドさせたときの「元画像のどの範囲がコンプのどこに見えるか」を、Maya の対応カメラで
1 px 未満の位置誤差で再現する機能。仕様は利用者の「Pixel Mapping / BG Slide Sync 追加開発仕様書 v1.0」（2026-10-24）。
初期リリースは A（Coordinate Sync）+ B Lite（Pixel Accuracy Test）。B Full（見た目の一致）は将来。

## 1. 前提（利用者の回答、2026-10-24）

- Maya の BG は、キャラと同じく **3D の板ポリ**（BG 画像をテクスチャで貼る）。状況によって Image Plane もあり得る。
- 位置の検証に使うレンダー: **Maya Hardware 2.0 / Playblast** と **Maya Software**。
- 検証は自宅 PC で mayapy による自動検証を先に行い、AE の参照画像はあとで利用者が AE で作る。

## 2. 座標系

| 座標系 | 原点 | 向き | 単位・画素 |
|---|---|---|---|
| Source Pixel | 元画像の左上の角 | x 右、y 下 | px。画素 (i, j) は [i, i+1) × [j, j+1)、中心は (i + 0.5, j + 0.5) |
| AE Layer | レイヤーのソースの左上の角 | x 右、y 下 | Source Pixel と同じ（2D、スケール 100 %） |
| AE Comp / Maya Render Pixel | 画像の左上の角 | x 右、y 下 | Source Pixel と同じ決まり |
| Maya Film | フィルムの中心 | x 右、**y 上** | inch |
| NDC | フィルムの中心 | x 右、y 上 | 有効フィルム幅の半分 = 1（縦も同じ単位、正方ピクセル） |

すべて double で保持し、丸めない。y の向きが変わるのは Film / NDC ⇔ Render Pixel の境界だけ。

## 3. 変換（`src/syncbridge/core/pixel_mapping.py`）

**AE（H-AE-24、AE 26.5 で確認済み）:** `comp = Position + R(Rotation) · S(Scale) · (source − Anchor Point)`（3 × 3 のアフィン行列）。
Phase 1 で確かめる対象は Position だけ（Scale 100 %、Rotation 0、Parent なし、2D、エフェクトなし）。
3D レイヤー、親、形を変えるエフェクトは断る。Scale・Rotation は計算に入れるが、未確認として警告する。

**Maya（H-PM-1〜4、mayapy 2023 / 2024 のレンダーで確認済み）:** BG の板ポリは UV で元画像に対応する（v = 0 が画像の下）。
カメラ空間の点 (X, Y, Z) について、

```
透視:   film = (X / −Z, Y / −Z) × focalLength / 25.4                       [inch]
平行:   film = (X, Y) × 有効フィルム幅 / orthographicWidth
透視のみ: film −= (horizontalFilmOffset, verticalFilmOffset)
透視のみ、panZoomEnabled かつ renderPanZoom: film −= (horizontalPan, verticalPan)
NDC = film / (有効フィルム幅 / 2) − (filmTranslateH, filmTranslateV)
x_px = W/2 + NDC.x × W/2,  y_px = H/2 − NDC.y × W/2
panZoomEnabled かつ renderPanZoom: p = 中心 + (p − 中心) / zoom
```

**フィルム面の 2D 変換の順序（H-PM-8、mayapy 2024 のレンダーで確認、2026-10-25）:**

```
Film Offset → 2D Pan →（NDC へ）→ ÷ Zoom → × Pre Scale
  → Film Roll（Pivot、NDC・y 上）と Film Translate（Order: Rotate-Translate = 回転してから平行移動、Translate-Rotate = 逆）
  → × Post Scale → px
```

- Pre / Post Scale: 値がそのまま倍率（> 1 で拡大）。中心は画像の中心。
- Film Roll: 正の値で時計回り（AE の回転と同じ向き）。Pivot の単位は NDC（幅の半分 = 1、y 上）。
- Film Offset と 2D Pan は Pre Scale・Roll・Post Scale の影響を受ける。Film Translate は Pre Scale と Zoom の影響を受けず、
  Post Scale の影響は受ける。
- 実測（Hardware 2.0、Maya Software は 0.3 px 以内で同じ）:

| 値 | 結果 |
|---|---|
| Pre Scale / Post Scale 1.05 | 1.05 倍 |
| Film Roll 3 | 3° 時計回り |
| Pivot (0.1, 0.05) | 画像の中心が (−2.37, −5.10) px（式では −2.38, −5.09） |
| Translate-Rotate | (−47.94, −2.52) px |
| Zoom 0.95 + Film Translate 0.05 | −48.01 px（Zoom の影響なし） |

- 最初のモデルは Zoom を最後にしていたので、Zoom と Film Translate を同時に使うときだけずれていた。

有効フィルム幅は Film Fit で決まる（横合わせなら horizontalFilmAperture。Fill は、フィルムの縦横比がレンダーの縦横比以下なら
横合わせになる）。板ポリがフィルム面と平行なら、元画像 → レンダーはアフィンになる。平行でなければ断る（遠近で形が変わり、
オフセットでは合わせられない）。

**ソルバー（`solve`）:** オフセットを 0 にしたときの Maya の対応（元画像 → レンダー）を求め、**AE がコンプの中心に映している
元画像の点** のずれ (dx, dy) から値を求める。大きさ・向きの違いは、比率ではなく **画面の四隅に残るずれ** で判断する。値はカメラのモデルを使って 2 つ同時に数値で解く
（Pre / Post Scale・Roll・Zoom があっても正しく求まる）。1 px 以上なら断り（オフセットで合わせられるのは位置だけ）、0.1 px 以上なら警告する（2026-10-25: 利用者がカメラの距離を
18.67092 ではなく 18.670 と入れた。大きさで 0.005 % の差、端で 0.05 px。最初の実装は相対差 1e-5 で断っていた）。

| 方式 | 値 |
|---|---|
| Film Offset | hfo = −dx × 有効フィルム幅 / W、vfo = dy × 有効フィルム幅 / W |
| 2D Pan/Zoom | hpan / vpan = Film Offset と同じ × zoom（panZoomEnabled と renderPanZoom をオン） |
| Film Translate | ftH = −dx × 2 / W、ftV = dy × 2 / W |
| Film Translate・Scale・Roll | 絶対モードでは Film Translate と同じ（位置だけ）。相対モードでは拡大縮小と回転も（8 章） |

求めた値で対応を計算し直して、AE との差（max_error_px）を返す（計算上は 1e-6 px 以下）。

**断るもの:**
- コンプとレンダーの解像度が違う、ピクセル縦横比が 1 でない。
- Lens Squeeze、Camera Scale、Film Fit Offset、Overscan が既定値でない。
- 縦合わせになる Film Fit（未確認）。
- 平行投影のカメラで Film Offset / 2D Pan を選んだ。

## 4. Phase 0 の実験（mayapy 2024、2026-10-24）

6000 × 4000 のテスト用 BG（`pixelcheck.testgrid`。10 px / 100 px の線、250 px ごとの目印、四隅の色が違う）を板ポリに貼った。
1920 × 1080 でレンダーし、目印の重心を測った（`pixelcheck.measure`）。

| 条件 | 結果 |
|---|---|
| オフセットなし | 予想（元画像 − (2040, 1460)）と 0.15 px 以内。四隅の色も一致（反転なし） |
| 透視 × Film Offset / 2D Pan / Film Translate | 予想式どおり。Film Offset 1 inch（1355 px）でも 0.1 px 以下 |
| 平行投影 × Film Offset / 2D Pan | **レンダーに効かない**（Maya Software・Hardware 2.0 とも）。Film Translate と Zoom は効く |
| renderPanZoom オフ | 2D Pan はレンダーに効かない |
| **Hardware 2.0 のテクスチャの最大解像度**（既定でオン、2048） | 6000 px の BG が縮められ、**最大 1.4 px ずれる**。オフにすると 0.004 px |
| Maya Software、テクスチャのフィルターなし | 画素単位に丸められ、半ピクセルの移動で 0.5 px ずれる（1 px 未満） |
| Maya Software、Mipmap | 一定の約 0.2 px のずれ。最大 0.58 px |
| カメラの Image Plane（Hardware 2.0、透視） | Film Offset / 2D Pan では空間に固定され、位置は合う。ただし画素単位に丸められ、半ピクセルで 0.5 px ずれる。Film Translate では最大 12 px ずれる |
| カメラの Image Plane（Maya Software、透視） | オフセットなしでも約 3 px ずれる。**位置合わせの基準には使えない** |

**通しの確認（`tools/pixel_mapping/maya_render_check.py`）:** AE の BG の位置 → ソルバー → カメラに設定 → レンダー →
AE で見えるはずの位置と比較。位置は 5 通りで、整数・半ピクセル・4 分の 1 ピクセル・大きな移動を含む。

| レンダー | カメラ | Film Offset | Film Translate | 2D Pan/Zoom |
|---|---|---|---|---|
| Hardware 2.0（最大解像度オフ） | 透視（16:9 のフィルム、横合わせ） | ≤ 0.010 px | ≤ 0.010 px | ≤ 0.010 px |
| Hardware 2.0（最大解像度オフ） | 透視（3:2 のフィルム、Fill、カメラと BG を一緒に移動・回転）。Maya 2023 / 2024 | ≤ 0.010 px | ≤ 0.010 px | ≤ 0.010 px |
| Hardware 2.0（最大解像度オフ） | 平行投影 | 断る | ≤ 0.004 px | 断る |
| Maya Software（Mipmap） | 透視 | ≤ 0.40 px | ≤ 0.40 px | ≤ 0.40 px |

→ **Maya 側は、3 方式とも 1 px 未満で再現できる。** 精度を決めるのは方式ではなく、テクスチャの扱い（Hardware 2.0 の
最大解像度、Maya Software のフィルター）。

**AE の参照フレーム（利用者の PC、AE 26.5、2026-10-25）:** `pixel_mapping_reference.jsx` で 8 フレーム（整数・半ピクセル・
4 分の 1 ピクセル・大きな移動）を `saveFrameToPng` で保存し、`check_reference.py` で予測と比べた。
**最大 0.042 px（整数の位置は 0.000）で PASS。** 同じ位置の Maya のレンダー（Hardware 2.0、Film Offset）と目印ごとに直接
比べても **最大 0.045 px**。→ 「AE の元画像の座標 ⇔ Maya のレンダーの座標」が 1 px 未満でつながった（Phase 1 完了）。

## 5. 方式の選び方（Phase 1 の結論、D-23）

- **既定は Film Offset**（透視）。Maya の標準の属性で、レンダーにもビューにも効く。カメラにすでに Film Offset のキーや接続が
  あれば、上書きせずに断る（`syncbridge_maya.pixel_mapping.conflicts`）。
- **平行投影のカメラは Film Translate**（Film Offset と 2D Pan はレンダーに効かない）。
- **2D Pan/Zoom** は、Film Offset をレイアウトなどで使っているカメラのための選択肢。renderPanZoom をオンにする必要がある。
  アニメーターが 2D Pan/Zoom のツールでビューを動かすと、レンダーも動く点に注意。
- Image Plane は、Hardware 2.0 で Film Offset か 2D Pan のときだけ整数ピクセルで合う。基準にはしない。
- **Hardware 2.0 / Playblast で 1 px 未満にするには、テクスチャの最大解像度の制限を外すか、BG の幅以上にする**
  （Hardware 2.0 の設定の Texture → Max Texture Resolution）。シーンの設定なので、SyncBridge は変えずに利用者に知らせる。

## 6. 未確認（仮説）

| ID | 内容 | 確認方法 |
|---|---|---|
| H-AE-24 | ✅ AE 26.5: 2D レイヤーの元画像の座標は `Position + (source − Anchor)` のコンプの座標に描かれる（Position のみ、Best、最大 0.042 px）。Scale・Rotation は未確認 | 済み |
| H-AE-25 | ✅ AE 26.5: `CompItem.saveFrameToPng(time, file)` でフレームを PNG に保存できた | 済み |
| H-PM-5 | Film Offset・Film Translate・2D Pan を同時に使ったときの順序（今の式の順） | 組み合わせのレンダー |
| H-PM-6 | 縦合わせ・Overscan の Film Fit、Film Fit Offset | 該当するカメラでのレンダー |
| H-PM-7 | Maya の GUI のビューポートと Playblast も ogsRender と同じ位置になる | GUI で Playblast を撮って check |

## 7. Phase 2: Virtual Layer Mapping とハブ経由の転送（2026-10-25、D-24）

**使い方:**
1. Maya の SyncBridge パネルの「Pixel Mapping（BG スライド）」欄で、カメラ・BG の板ポリ・方式を選ぶ。
2. AE のパネルで BG のレイヤーを選び、「BG の位置を Maya のカメラへ」を押す。

**動き:**
- 初めてのレイヤーは、確認のうえで対応付けを作る。2 回目からは確認なしで、今のフレームの位置を設定する。
- 取り消しは 1 回。カメラの値と対応付けが一緒に戻る。前の値は `backups/pixelmap_*.json` に残る。

**対応付け（Virtual Layer、`core/layer_mapping.py`）:**
- 内容: ID、名前、AE（コンプ ID・名前、レイヤー ID・名前、元画像の名前と大きさ）、Maya（カメラと BG の UUID と名前）、
  有効・無効、方向（ae2maya）、同期する項目（pan）、方式。
- 保存場所: Maya のシーンの network ノード `syncBridgeLayerMappings`（JSON）。シーンと一緒に別の PC へ移る。
  パネルで選んだ既定値は optionVar（PC ごと）。
- 見分け方:
  - AE はコンプ ID + レイヤー ID（H-AE-26）。ID がなければ名前で探す。
  - Maya は UUID なので、名前やネームスペースが変わっても追える（mayapy で、名前を変えても同じ対応付けが使われることを確認）。
- 同じカメラを、別の AE レイヤーが同じ方式で使っていれば警告する（仕様 4.2）。

**通信:** `pixelmap.request`（AE のパネル → ハブ）→ `pixelmap.apply.request`（ハブ → Maya）。既存の「AE → Maya の中継」
（`server/relay.py` の `PixelMapFlow`）を使う。転送の履歴に「Pixel Mapping」として残り、モニターにも出る。

**AE（`SBCep.pixelMapInfo`）:**
- 選択中のレイヤーの今の時刻の Position・Anchor Point・Scale・Rotation・3D・親・エフェクト、元画像の大きさ、コンプの ID と大きさ。
- 次元を分割した Position も読む（H-AE-27）。エフェクトがあれば警告する（形を変えるかは名前ではわからないため）。

**確認（mayapy 2024）:**
- 案内付きで断る: カメラ未選択、キーのある属性。
- 初回の対応付け、取り消し 1 回での復元、名前を変えたあとの再送、同じカメラの警告。
- 設定後のレンダーで、AE の位置との差 0.005 px。
- ハブ（3 件）と AE パネル（Node、2 件）の自動テスト。
- Maya のパネルは欄が増えて縦に長くなったので、中の欄をスクロールできるようにした。高さが足りないと Qt が部品をつぶして
  文字が切れていた（モックで確認）。

**利用者の確認（2026-10-25、テスト版 0.1.8）: 動作 OK。** カメラの距離を 18.670（正確には 18.67092）と入れると最初の実装は
断ったため、大きさの判定を画面の端のずれ（1 px で拒否、0.1 px で警告）に直した（mayapy: 同じ設定で 0.041 px）。

## 8. 相対モード（3D の BG・カメラワーク対応、Phase 2.5、2026-10-25、D-25）

利用者の要望: BG は板ポリとは限らず、建物や町並みのモデル。大判 BG は Maya のレンダー・それを元に描いたもの・手描きのいずれも
ある。Maya のカメラにカメラワーク（アニメーション）が入ることもあり、最終的には AE で 2D の調整をする。
→ 利用者の考え: 「AE での見え方を基準に、Maya でフィルムオフセットを加算すれば再現できる」。

- Film Offset / 2D Pan / Film Translate は画像全体の 2D の平行移動（レンズの中心は動かない）なので、どの深さの物も同じ
  ピクセル数だけ動く（視差なし）。BG の板ポリがなくても、AE で BG を 2D でどれだけ動かしたか（差分）を足せば再現できる。
- **基準:** 「AE の BG がこの位置のとき、Maya のカメラ（SyncBridge の補正なし）と見え方が合う」という位置 P0 を対応付けに
  持たせる。送るのは (P − P0) をピクセルからオフセットに直した値（スケール 100 % なら差分そのもの）。
- **カメラワークと両立:** AE の 2D 補正は、カメラ自身のアニメーションが使わない別の属性（2D Pan か Film Translate）に入れる。
  3 つのオフセットが足し算で効くことは Phase 0 で確認済み（同時に使ったときの順序 H-PM-5 は未確認）。
- AE で BG をスケールしているときは、2D Pan/Zoom の Zoom（画面の中心で拡大縮小、検証済み）で表せる見込み。
- カメラの位置が動くカット（トラック・ドリー）は、カメラの動き自体は Maya のアニメーションのまま。AE の 2D の調整だけを足す。
- 今の板ポリ基準は「絶対モード」（元画像の画素まで合わせる）として残す。
- Phase 3（アニメーション）は、この相対モードの上で、フレームごとの差分をキーにする。

**実装（2026-10-25）:**
- `core.pixel_mapping.solve_relative(method, camera, render, comp, reference, current)`: AE の変化 S = current × reference⁻¹
  （コンプの画素）を求める。回転は断る。2D Pan/Zoom は拡大縮小を zoom（基準の zoom ÷ 倍率）で表す。
  オフセット 2 つは、画像の中心での一次の関係から解き、画面の 9 点で誤差を確かめる（1 px 以上で断り、0.1 px 以上で警告）。
- 対応付けに `mode`（relative / absolute）と `reference`（AE の行列、方式の属性の値、コンプの時刻）。D-25 より前の記録は絶対モード。
- Maya: 初回の送信は基準を記録するだけ（`status: unchanged`、`reference_recorded`、取り消し可）。2 回目からは、基準の値に差分を
  足して設定する。パネルにモードの選択と「基準をやり直す」。新しく選ぶときの既定は **相対・2D Pan/Zoom**。
  相対モードでは BG の板ポリを選ばない。

**確認（`tools/pixel_mapping/maya_relative_check.py`、mayapy 2024、Hardware 2.0）:**
- シーン: 深さの違う 3 枚の板（手前・中間・奥、それぞれテクスチャが 1 画素 = 1 画素）。カメラワークあり（translateX と
  Film Offset のキー）。フレーム 10。

| ケース | 結果（手前 / 中間 / 奥の最大） |
|---|---|
| 基準のレンダー ⇔ カメラのモデル | 0.005 / 0.002 / 0.004 px |
| 2D Pan/Zoom、スライド 2 通り | 0.007 px 以下（すべての深さ） |
| 2D Pan/Zoom、スライド + 拡大 110 % | 0.094 / 0.082 / 0.056 px |
| Film Translate、スライド 2 通り | 0.007 px 以下 |
| Film Offset | カメラワークのキーがあるので断る（カメラワークを壊さない） |

→ どの深さも同じだけ動き（視差なし）、カメラワークの Film Offset には触らない。Film Offset と 2D Pan を同時に使ったときの
順序（H-PM-5）も、この組み合わせで確認できた。

**方式「Film Translate・Scale・Roll」（2026-10-25、利用者の要望）:**
- 利用者が GUI で 170 % と 42° を送ったところ、2D Pan/Zoom 以外の方式で断られた。
  → Film Translate（位置）・Post Scale（拡大縮小）・Film Roll（回転）で、AE の 2D の変化をすべて表す方式を足した。
- 相対モードでは、Post Scale = 基準 × 倍率、Film Roll = 基準 + 回転とし、Film Translate を数値で解く
  （Roll の Pivot や Order が既定値でなくても正しく求まる）。
- 確認（`maya_relative_check.py film_roll`、3 つの深さとカメラワーク）:

| AE の変化 | 最大誤差 |
|---|---|
| スライド | 0.007 px |
| 110 % | 0.094 px |
| **42°** | **0.036 px** |
| **170 %** | **0.067 px** |
| 130 % + −12.5° + スライド | 0.011 px |

- パネルに「方式を変更」（選んだ対応付けの方式を変える。相対モードは次の送信で基準を取り直す）。
- 方式の並びは、2D Pan/Zoom（既定）、Film Translate・Scale・Roll、Film Translate、Film Offset。

**未確認:** GUI の Maya と AE での一連の流れ（基準の記録 → AE で BG を動かして送る → 見え方が合う）。

## 9. 次の段階

1. ~~AE の参照フレーム（H-AE-24 / 25）~~ → 2026-10-25 PASS（最大 0.042 px、AE ⇔ Maya 0.045 px）。
2. ~~Phase 2~~ → 実装済み（7 章）。**[利用者] GUI の AE と Maya で確認する。**
3. Phase 3: Position のアニメーション（Linear / Hold、Bezier はフレームごとのサンプリング）、全フレームの精度確認。
4. Phase 4（B Lite の残り）: 重ね合わせ・差分画像、結果の保存と UI。

## 10. ファイル

| パス | 内容 |
|---|---|
| `src/syncbridge/core/pixel_mapping.py` | 座標変換（AE の行列、Maya のカメラのモデル、ソルバー）。標準ライブラリのみ |
| `src/syncbridge/pixelcheck/` | B Lite: PNG の読み書き、テスト用 BG、目印の位置の測定。標準ライブラリのみ（numpy なしで動く） |
| `maya_plugin/scripts/syncbridge_maya/pixel_mapping.py` | Maya: カメラと BG の板ポリの読み取り（UV から角の位置）、値の適用（取り消し 1 回、キー・接続・ロックがあれば断る）、AE からの転送（`apply_from_ae`） |
| `src/syncbridge/core/layer_mapping.py` | Virtual Layer の記録（作成、検索、競合、保存形式） |
| `maya_plugin/scripts/syncbridge_maya/layer_mapping.py` | Maya: 対応付けをシーンに保存、UUID でノードを探す、パネルの既定値 |
| `after_effects/jsx/pixel_mapping_reference.jsx` | AE: 参照フレームを作るスクリプト（利用者が AE で実行） |
| `tools/pixel_mapping/make_testgrid.py` | テスト用 BG を書き出す |
| `tools/pixel_mapping/maya_render_check.py` | mayapy で Maya 側を通しで確認する |
| `tools/pixel_mapping/make_test_town.py` | 相対モードのテスト用の町並み（建物の箱）、`SHOT_CAM`、AE 用の大判 BG（3 倍の画角で書き出し）。Maya のスクリプトエディタか mayapy で実行 |
| `tools/pixel_mapping/maya_relative_check.py` | mayapy で相対モードを確認する（3 つの深さ + カメラワーク） |
| `tools/pixel_mapping/check_reference.py` | AE の参照フレーム（など）を予測と比べる |
| `tests/unit/test_pixel_mapping.py`, `tests/unit/test_pixelcheck.py` | 自動テスト |
