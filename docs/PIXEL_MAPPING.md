# Pixel Mapping / BG Slide Sync

最終更新: 2026-10-24 / 状態: **Phase 0（調査）完了、Phase 1（最小プロトタイプ）は Maya 側まで確認、AE 側の確認待ち**

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

**AE（H-AE-24、AE での確認待ち）:** `comp = Position + R(Rotation) · S(Scale) · (source − Anchor Point)`（3 × 3 のアフィン行列）。
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

有効フィルム幅は Film Fit で決まる（横合わせなら horizontalFilmAperture。Fill は、フィルムの縦横比がレンダーの縦横比以下なら
横合わせになる）。板ポリがフィルム面と平行なら、元画像 → レンダーはアフィンになる。平行でなければ断る（遠近で形が変わり、
オフセットでは合わせられない）。

**ソルバー（`solve`）:** オフセットを 0 にしたときの Maya の対応（元画像 → レンダー）を求める。AE の行列と比べて、大きさと向きが
同じ（相対差 1e-5 以下）ことを確かめる。違えば断る（オフセットで合わせられるのは位置だけ）。そのうえで、元画像の中心のずれ
(dx, dy) から値を求める。

| 方式 | 値 |
|---|---|
| Film Offset | hfo = −dx × 有効フィルム幅 / W、vfo = dy × 有効フィルム幅 / W |
| 2D Pan/Zoom | hpan / vpan = Film Offset と同じ × zoom（panZoomEnabled と renderPanZoom をオン） |
| Film Translate | ftH = −dx × 2 / W、ftV = dy × 2 / W |

求めた値で対応を計算し直して、AE との差（max_error_px）を返す（計算上は 1e-6 px 以下）。

**断るもの:**
- コンプとレンダーの解像度が違う、ピクセル縦横比が 1 でない。
- Lens Squeeze、Camera Scale、Film Roll、Pre/Post Scale、Film Fit Offset、Overscan が既定値でない。
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
| H-AE-24 | AE は 2D レイヤーの元画像の座標を `Position + (source − Anchor)` のコンプの座標に描く（画素の中心の扱いも Source / Comp で同じ）。半端な位置は補間で描く | `after_effects/jsx/pixel_mapping_reference.jsx` で AE の参照フレームを作り、`tools/pixel_mapping/check_reference.py` で 1 px 未満か |
| H-AE-25 | `CompItem.saveFrameToPng(time, file)` で、スクリプトからコンプの 1 フレームを PNG に保存できる | 同じスクリプトで ae_ref_*.png ができるか（できなければレンダーキューで PNG 連番） |
| H-PM-5 | Film Offset・Film Translate・2D Pan を同時に使ったときの順序（今の式の順） | 組み合わせのレンダー |
| H-PM-6 | 縦合わせ・Overscan の Film Fit、Film Fit Offset | 該当するカメラでのレンダー |
| H-PM-7 | Maya の GUI のビューポートと Playblast も ogsRender と同じ位置になる | GUI で Playblast を撮って check |

## 7. 次の段階

1. **[利用者] AE の参照フレーム（H-AE-24 / 25）:** AE で `pixel_mapping_reference.jsx` を実行 → `check_reference.py` で確認。
   合格すれば「AE の元画像の座標 ⇔ Maya のレンダーの座標」が 1 px 未満でつながる（Phase 1 完了）。
2. Phase 2: Virtual Layer Mapping（AE のレイヤー ⇔ Maya のカメラ・BG の対応付け、ID で識別）、ハブ経由の AE → Maya の転送
   （既存のハブのメッセージと履歴を使う）、パネルの UI。
3. Phase 3: Position のアニメーション（Linear / Hold、Bezier はフレームごとのサンプリング）、全フレームの精度確認。
4. Phase 4（B Lite の残り）: 重ね合わせ・差分画像、結果の保存と UI。

## 8. ファイル

| パス | 内容 |
|---|---|
| `src/syncbridge/core/pixel_mapping.py` | 座標変換（AE の行列、Maya のカメラのモデル、ソルバー）。標準ライブラリのみ |
| `src/syncbridge/pixelcheck/` | B Lite: PNG の読み書き、テスト用 BG、目印の位置の測定。標準ライブラリのみ（numpy なしで動く） |
| `maya_plugin/scripts/syncbridge_maya/pixel_mapping.py` | Maya: カメラと BG の板ポリの読み取り（UV から角の位置）、値の適用（取り消し 1 回、キー・接続・ロックがあれば断る） |
| `after_effects/jsx/pixel_mapping_reference.jsx` | AE: 参照フレームを作るスクリプト（利用者が AE で実行） |
| `tools/pixel_mapping/make_testgrid.py` | テスト用 BG を書き出す |
| `tools/pixel_mapping/maya_render_check.py` | mayapy で Maya 側を通しで確認する |
| `tools/pixel_mapping/check_reference.py` | AE の参照フレーム（など）を予測と比べる |
| `tests/unit/test_pixel_mapping.py`, `tests/unit/test_pixelcheck.py` | 自動テスト |
