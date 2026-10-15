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

## 6. Local Sync Server（Phase 1、1-A 実装済み）

起動: `.\syncbridge-server.cmd [--port 8765] [--idle-timeout 600]`（`.venv` が必要、`requirements-server.txt`）。

| 項目 | 内容 |
|---|---|
| 待ち受け | `127.0.0.1` のみ（既定ポート 8765）。`GET /health` → `{app: "syncbridge", version, protocol, clients}`（秘密情報なし） |
| WebSocket | `ws://127.0.0.1:<port>/ws`。JSON テキストフレーム 1 つ = エンベロープ 1 つ |
| セッションファイル | `%LOCALAPPDATA%\SyncBridge\session.json` = `{port, token, pid, version, started}`。クライアントはここから port と token を読む。`SYNCBRIDGE_SESSION_DIR` で場所を変更可 |
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
| `error` | どちらでも | `code`, `message`（要求への応答なら `reply_to` 付き） |

エラーコード: `bad_message`, `auth_failed`, `no_peer`, `timeout`, `peer_disconnected`, `app_error`, `conversion_failed`, `busy`。

### 転送の規則

- 送信元のアプリ（方向から決まる）は、要求元がそのアプリならその接続、違えば最後に接続したそのアプリ（`source` で指定可）。
  転送先も同様（`target` で指定可）。
- 変換が許容誤差を超えたら **転送先に何も送らない**（`status: failed` と誤差レポートを返す、SPEC 5 章）。
- 転送は同時に 1 つだけ（2 つ目は `busy`）。export は 60 秒、apply は利用者の確認を待つため 600 秒でタイムアウト。
- `apply.result` に `after` があれば、サーバーが読み戻しを検証して `readback` に入れる。
