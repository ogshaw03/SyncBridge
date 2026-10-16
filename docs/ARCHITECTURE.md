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
