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
| クライアント（stdlib の WebSocket、SyncClient、サーバーの自動起動） | `client/` | ✅ テスト済（stdlib のテストサーバーと本物のサーバーの両方） |
| Maya の接続（service）と最小パネル（ui） | `maya_plugin/.../service.py`, `ui.py` | ✅ Maya 2024 で V-P1B 合格（AE は代役）。その後のログ表示の改善は Maya で未確認 |
| AE の代役 | `tools/fake_ae.py` | ✅ 本物のサーバーと実データで両方向を確認 |
| AE の CEP パネル（manifest、画面、通信、ExtendScript の窓口） | `after_effects/CSXS`, `panel/`, `jsx/syncbridge_cep_host.jsx` | ✅ AE 26.5 で V-P1C 合格（両方向、取り消し、日本語の警告、切断）。通信部分は Node のテストも |

## テスト結果

### 2026-10-16（Windows 11, Python 3.10.6）

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

## 次にやること

1. **[実機・利用者]** 0.1.0 をこの PC にインストールして確認する（RELEASE.md 5 章: Maya の `.py` ドロップ、
   PlayerDebugMode なしでの AE パネル、Python のない PC）。問題がなければ利用者に配布する。
2. **Phase 2（基本設定の同期）:** FPS、解像度、ピクセルアスペクト比、フレーム範囲（Maya の再生範囲・アニメーション範囲・
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
