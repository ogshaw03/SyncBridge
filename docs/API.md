# SyncBridge API（Phase 0）

Phase 0 はファイル経由で転送する。ファイルの形式は Phase 1 の WebSocket メッセージと共通にする予定。
JSON Schema: [`schemas/exchange.v0.schema.json`](../schemas/exchange.v0.schema.json)

## 1. エンベロープ

```json
{
  "schema": "syncbridge.exchange",
  "schema_version": "0.1",
  "kind": "maya.timewarp.export",
  "event_id": "uuid",
  "source_id": "maya | ae | core",
  "revision": 0,
  "created": "2026-10-15T00:00:00+00:00",
  "app": {"name": "maya", "version": "2023"},
  "data": {}
}
```

メジャーバージョン（`0.x`）が違うファイルは読み込まない。

## 2. kind ごとの data

| kind | 作成元 | data |
|---|---|---|
| `maya.timewarp.export` | Maya `exchange.export_timewarp` | `curve_node`, `time_plug`, `enabled`, `native`（Maya 形式）, `samples`（フレーム）, `calibration`, `scene` |
| `maya.timewarp.apply` | CLI `ae2maya` | `mode`, `context`, `native`, `report` |
| `ae.timeremap.export` | AE `syncbridge_ae.jsx` Export / Apply 後の `*_after.json` | `comp`, `layer`, `keys`（AE 形式）, `samples`（コンプ秒 → ソース秒） |
| `ae.timeremap.apply` | CLI `maya2ae` | `mode`, `context`, `comp_fps`, `keys`, `report` |
| `ae.probe.vectors` | CLI `probe-vectors` | `comp_fps`, `sample_oversample`, `vectors[{name, keys}]` |
| `ae.probe.results` | AE `probe_ae.jsx` | `comp_fps`, `environment`, `results[{name, sentKeys, readKeys, times, values, error}]` |

## 3. CLI

Windows ではリポジトリ直下の `.\syncbridge.cmd` で実行する（`src` を PYTHONPATH に入れ、`py -3` で起動する。`python` が Microsoft Store の仮のコマンドでも動く）。他の環境では `src` を `PYTHONPATH` に入れて `python -m syncbridge.cli` で実行する。

```
.\syncbridge.cmd maya2ae <maya_export> -o <ae_apply> [--ae-export <ae_export>] [mapping]
.\syncbridge.cmd ae2maya <ae_export> -o <maya_apply> (--maya-fps 24 | --maya-export <maya_export>) [mapping]
.\syncbridge.cmd readback <apply> <after>
.\syncbridge.cmd probe-vectors -o <file> [--fps 24]
.\syncbridge.cmd verify-ae-probe <results> [--tol 0.01]
.\syncbridge.cmd selftest [--fps 24]

mapping: --mode editable|precision --tol 0.1 --origin F --maya-in-origin F --maya-out-origin F
         --comp-offset S --source-offset S --source-scale X --key-subdivision N
         --range START END (Maya scene frames) | --no-range
```

終了コード: 0 = 成功（誤差が許容内）、2 = 誤差が許容外（出力ファイルは書き出す）、1 = 入力エラー。

## 4. Maya（`maya_plugin/scripts/syncbridge_maya`）

| 関数 | 説明 |
|---|---|
| `exchange.export_timewarp(path=None, oversample=4)` | Scene Time Warp を export。path 省略時はダイアログ |
| `exchange.apply_timewarp(path=None, confirm=True)` | apply ファイルを適用（確認 → バックアップ → 適用 → リードバック） |
| `anim_curve.read_curve(curve)` | 任意の animCurveTT → (native, samples, calibration) |
| `anim_curve.write_curve(curve, native)` | 任意の animCurveTT のキーを置き換える |
| `scene_timewarp.find_curve()` | Scene Time Warp のカーブと接続先プラグ |
| `scene_settings.read()` | FPS、範囲、解像度など |
| `probe.run(path)` | Phase 0 の実機検証 |

## 5. AE（`after_effects/jsx`）

| ファイル / 関数 | 説明 |
|---|---|
| `syncbridge_ae.jsx` | 選択レイヤーの Export / Apply（ダイアログ） |
| `probe_ae.jsx` | Phase 0 の実機検証（一時コンプを作成して削除） |
| `SB.readKeys(prop)` / `SB.applyKeys(prop, keys)` | Time Remap キーの読み書き |
| `SB.sample(prop, t0, t1, frameDuration, oversample)` | `valueAtTime` でのサンプリング |
| `SB.buildExport(comp, layer, oversample)` | `ae.timeremap.export` を作る |
| `SBJSON.parse / stringify` | ES3 用 JSON |

## 6. クライアント（Phase 1-B、標準ライブラリのみ）

| モジュール / 関数 | 説明 |
|---|---|
| `syncbridge.client.ws.WebSocket` | 最小の WebSocket クライアント（テキスト、分割、ping/pong、close）。`connect(host, port, path)`, `send_text`, `recv`（閉じたら None）, `close` |
| `syncbridge.client.sync_client.SyncClient(app, handlers, dispatch, on_event)` | サーバーへの接続。`connect()`（セッションファイルを読む）、`request_transfer(direction, options, callback)`、`disconnect()`。受信は別スレッド、アプリへの処理と UI 通知は `dispatch` 経由 |
| `syncbridge.client.launcher.ensure_server(port)` | サーバーが動いていなければ起動して待つ（親の `PYTHONHOME` / `PYTHONPATH` は渡さない）。`session.json` のハブを優先し、`port` がほかのプログラムに使われていれば次の空きポート（最大 10 個、D-19）。戻り値は `/health` + `port`（+ 理由の `note`） |
| `syncbridge_maya.service` | Maya 用: `connect(start_server=True)`, `send_to_ae(options)`, `receive_from_ae(options)`, `disconnect()`, `add_listener(fn)` |
| `syncbridge_maya.ui.show()` | Maya の最小パネル（接続、モード、原点フレーム、許容誤差、2 つの送信ボタン、ログ） |
| `syncbridge_maya.exchange.apply_envelope(env, confirm=True)` | apply エンベロープを適用（確認、バックアップ、undo、読み戻し）。`{status, backup, after, app_readback}` を返す |
| `tools/fake_ae.py --export <AE export>` | 開発用の AE の代役（AE 側のパネルができるまでの確認用） |
| `syncbridge.core.warp_edit.retime(native, start, end)` | Scene Time Warp を時間方向に伸縮・移動（値は保持、形は保持）。`to_scene_fps` で fps 変換 |
| `syncbridge_maya.snapshots` | `save(name)`, `entries()`（保存と自動バックアップ、新しい順）, `restore(path, new_range)`, `retime_current(start, end)`。書き込みは `apply_envelope` 経由（確認、バックアップ、undo、読み戻し） |

## 7. Local Sync Server（Phase 1、1-A 実装済み）

起動: `.\syncbridge-server.cmd [--port 8765] [--idle-timeout 600]`（`.venv` が必要、`requirements-server.txt`）。

| 項目 | 内容 |
|---|---|
| 待ち受け | `127.0.0.1` のみ（既定ポート 8765）。`GET /health` → `{app: "syncbridge", version, protocol, clients}`（秘密情報なし） |
| WebSocket | `ws://127.0.0.1:<port>/ws`。JSON テキストフレーム 1 つ = エンベロープ 1 つ |
| セッションファイル | `%LOCALAPPDATA%\SyncBridge\session.json` = `{port, token, pid, version, started, executable, image}`。クライアントはここから port と token を読む。同じ内容をハブごとに `hubs\<pid>.json` にも書く（P-A）。`SYNCBRIDGE_SESSION_DIR` で場所を変更可 |
| 認証 | 最初のメッセージは `hello`（10 秒以内）。トークンが違えば `error auth_failed` を返して close 4401 |
| 二重起動 | 起動時に `/health` を確認し、SyncBridge が動いていれば何もせず終了（終了コード 0）。別のプログラムがポートを使っていれば 3 |
| 自動終了 | 接続が `--idle-timeout` 秒（既定 600、0 で無効）なければ終了し、セッションファイルを消す |

### メッセージ（`src/syncbridge/protocol.py`）

応答は `reply_to` に要求の `event_id` を入れる。

| kind | 向き | data |
|---|---|---|
| `hello` | クライアント → サーバー | `token`, `app`（maya / ae / test）, `version`, `pid`, `document` |
| `welcome` | サーバー → クライアント | `client_id`（例 `maya-1`）, `server_version`, `protocol` |
| `peers` | サーバー → 全員 | `clients: [{client_id, app, version, pid, document, connected_at}]`（接続・切断のたび） |
| `transfer.request` | クライアント → サーバー | `direction`（maya2ae / ae2maya）, `options`（`core.jobs.TransferOptions` の JSON）, 省略可 `source` / `target`（client_id） |
| `transfer.result` | サーバー → 要求元 | `status`（applied / cancelled / failed）, `direction`, `source`, `target`, `report`（変換の誤差）, `readback`, `backup`, `message` |
| `export.request` / `export.result` | サーバー ⇔ アプリ | `{}` / `{export: <maya.timewarp.export か ae.timeremap.export のエンベロープ>}` |
| `apply.request` / `apply.result` | サーバー ⇔ アプリ | `{apply: <apply エンベロープ>}` / `{status, after?: <適用後の export エンベロープ>, backup?, message?}` |
| `guide.request` | クライアント（AE）→ サーバー | `comp: {name, width, height, pixelAspect}`, 省略可 `target`（Maya の client_id）。D-16 |
| `guide.apply.request` / `guide.apply.result` | サーバー ⇔ Maya | `{guide: {name, width, height, pixelAspect}}` / `{status, camera, render: [w, h], comp: [w, h], warnings}` |
| `guide.result` | サーバー → 要求元 | `guide.apply.result` の内容 + `source`, `target`, `message`（注意の要約） |
| `markers.request` | クライアント（AE）→ サーバー | `export`（選択中のレイヤーの `ae.timeremap.export`）, `options`（転送と同じ。`origin` など）。D-18 |
| `markers.apply.request` / `markers.apply.result` | サーバー ⇔ Maya | `{export, options}` / `{status, count, first, last, bookmarks, overlay, comp, layer}` |
| `markers.result` | サーバー → 要求元 | `markers.apply.result` の内容 + `source`, `target` |
| `settings.request` | クライアント（Maya / AE）→ サーバー | `direction`（maya2ae / ae2maya）, `items`（省略時は全部: `fps`, `playback_range`, `animation_range`, `pixel_aspect`）, `options: {origin}`。D-21 |
| `settings.export.request` / `settings.export.result` | サーバー ⇔ アプリ | `{}` / `{settings}`（Maya: `scene_settings.read()`、AE: `SBCep.sceneSettings()`） |
| `settings.apply.request` / `settings.apply.result` | サーバー ⇔ 転送先 | `{plan: core.scene_sync の計画, message: 確認の文（日本語）}` / `{status, after?, backup?}` |
| `settings.result` | サーバー → 要求元 | `status`（applied / unchanged / cancelled）, `direction`, `changes: [{item, label, before, after}]`, `warnings`, `readback: {passed, problems}`, `source`, `target`, `message` |
| `layers.request` / `layers.result` | Maya → サーバー → Maya | `{}` / `{comp, layers, source, target}`。AE のアクティブなコンプのレイヤー一覧（レイヤーマップ、D-28）。履歴に残さない |
| `layers.export.request` / `layers.export.result` | サーバー ⇔ AE | `{}` / `SBCep.layersInfo()`: `comp: {id, name, width, height, frameRate, duration, time}`, `layers: [{id, index, name, kind（still / sequence / movie / comp / solid / null / camera / light / text / shape / other）, enabled, source, source_id, width, height, inPoint, outPoint, threeD, parent, keyed: {position, scale, rotation}}]` |
| `motion.request` / `motion.result` | Maya → サーバー → Maya | `{comp_id, comp, layer_id, layer, times: [AE のコンプ時間（秒）]}` / `{comp, layer, samples, source, target}`。Phase 3（D-30）。履歴に残さない |
| `motion.export.request` / `motion.export.result` | サーバー ⇔ AE | 同じ問い合わせ / `SBCep.layerMotion()`: `comp`, `layer`（`pixelMapInfo` の layer と同じ形）, `samples: [{t, position, anchorPoint, scale, rotation}]` |
| `time.sync` | クライアント → サーバー（応答なし） | `enabled`, `follow_playback`。全員で共有する 1 つのスイッチ。D-22 |
| `time.sync.state` | サーバー → 全員 | `enabled`, `follow_playback`, `by`（切り替えた client_id）。接続した直後にも送る |
| `time.update` / `time.set` | アプリ → サーバー / サーバー → もう片方のアプリ（応答なし） | `t`（AE のコンプ時間、秒）/ `t`, `source`（maya / ae）。同期がオフなら中継しない |
| `timing.set` / `timing.state` | アプリ → サーバー（応答なし）/ サーバー → 全員 | `{origin}`（Maya のフレーム）/ `{origin, by}`。ツールで 1 つの Origin frame（D-38）。接続した直後にも送る |
| `error` | どちらでも | `code`, `message`（要求への応答なら `reply_to` 付き） |

エラーコード: `bad_message`, `auth_failed`, `no_peer`, `timeout`, `peer_disconnected`, `app_error`, `conversion_failed`, `busy`,
`replaced`, `hub_stopping`（モニターから停止）, `disconnected_by_admin`（モニターから切断）。

### 転送の規則

- 送信元のアプリ（方向から決まる）は、要求元がそのアプリならその接続、違えば最後に接続したそのアプリ（`source` で指定可）。
  転送先も同様（`target` で指定可）。
- 変換が許容誤差を超えたら **転送先に何も送らない**（`status: failed` と誤差レポートを返す、SPEC 5 章）。
- 転送は同時に 1 つだけ（2 つ目は `busy`）。export は 60 秒、apply は利用者の確認を待つため 600 秒でタイムアウト。
- `apply.result` に `after` があれば、サーバーが読み戻しを検証して `readback` に入れる。
- シーン設定（D-21）: 両方の設定を読み、`core.scene_sync` で変える値だけの計画を作る。変える値がなければ転送先に何も送らず
  `unchanged`。転送先は確認ダイアログ → バックアップ → 1 回の取り消しで戻せる適用 → 適用後の設定を返し、サーバーが比べる。
  時間の対応は転送と同じ（Maya のフレーム F ⇔ AE のコンプ時間 (F − origin) / Maya の FPS）。AE のコンプの開始フレームは origin にする。
- 時間の同期（D-22）: `t` は AE のコンプ時間。Maya は自分のパネルの Origin frame で `frame = origin + t × fps` に直す。
  Maya はスクラブ中は 1 秒に 30 回まで、再生中は `follow_playback` のときだけ送る（オフなら止めた位置を送る）。
  AE のパネルは 0.05 秒ごとに `comp.time` を読み、変わっていれば送る（Maya から受け取った直後の 0.3 秒は読まない）。受け取って動かした時間は送り返さない。

### 管理 API（P-A、`server/admin.py`、D-15）

モニターとランチャー用。ループバックのみ。HTTP はヘッダー `Authorization: Bearer <token>` が必要（ないか違えば 401）。
`WS /admin/events` は接続後の最初のメッセージ `{"token": "<token>"}` で認証する（違えば `{"event": "error"}` を送って close 4401）。

| API | 応答 |
|---|---|
| `GET /admin/status` | `{app, version, protocol, pid, port, started, uptime_s, clients: [peers と同じ], transfer_running, transfers_recorded}` |
| `GET /admin/transfers?limit=50` | `{transfers: [{id, started, finished, requester, direction, data_type, source, target, status, error_code, message, conversion_max_error, readback_max_error, readback_passed}]}`（古い順、`status` は running / applied / cancelled / failed / error） |
| `GET /admin/log?tail=200` | `{lines: [{time, level, logger, message}]}`（古い順） |
| `WS /admin/events` | 最初に `{event: "status", status}`、以降 `client.connected` / `client.disconnected`（`client`）、`transfer.started` / `transfer.finished`（`transfer`）、`log`（`entry`） |
| `POST /admin/shutdown` | 接続中のアプリに `error hub_stopping` を送り、`{status: "stopping"}` を返した後に正常終了 |
| `POST /admin/clients/{client_id}/disconnect` | アプリに `error disconnected_by_admin` を送って close 4410。`{status: "disconnected"}`、いなければ 404 |

`syncbridge.hubs`（標準ライブラリのみ）: `discover()` → `[HubInfo]`（`state`: running / not_responding / stale / unknown）、
`admin_call(hub, method, path)`、`force_kill(hub)`（SyncBridge のハブと確認できなければ `ValueError`）、`remove_stale(hub)`。
