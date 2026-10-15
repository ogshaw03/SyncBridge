# AE CEP パネル（Phase 1 で実装予定）

Phase 0 では CEP パネルは作らず、`../jsx/` のスクリプトを
`File > Scripts > Run Script File...` から直接実行する。

Phase 1 での予定:

- CEP の HTML/JS 側が WebSocket（`ws://127.0.0.1:8765`）でサーバーと通信し、
  `CSInterface.evalScript()` で `../jsx/syncbridge_ae_lib.jsxinc` の関数を呼ぶ。
- ExtendScript から直接ソケット通信はしない（仕様 3.B）。
- AE の後継拡張方式（UXP）へ移行しやすいよう、通信層（CEP 依存）と
  JSX のアプリ操作層を分けておく。
- 未署名拡張を開発中に読み込むには PlayerDebugMode の設定が必要
  （Windows レジストリの変更になるため、手順のみ記載し利用者が実施する）。
  詳細は `docs/PHASE0_RESEARCH.md` の「検証手順 V-AE-3」。
