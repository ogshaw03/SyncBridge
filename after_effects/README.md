# After Effects 側（SyncBridge）

このフォルダそのものが CEP 拡張機能のルートです（Phase 1-C）。

| パス | 内容 |
|---|---|
| `CSXS/manifest.xml` | CEP 拡張機能の設定（パネル名 SyncBridge、AE 17 以降） |
| `panel/index.html`, `panel/css/`, `panel/js/main.js` | パネルの画面と、CEP の `evalScript` への橋渡し |
| `panel/js/sbclient.js` | サーバーとの通信（CEP にも DOM にも依存しない。Node でテストする） |
| `jsx/syncbridge_cep_host.jsx` | パネルから呼ぶ ExtendScript（セッションの読み取り、書き出し、適用） |
| `jsx/syncbridge_ae_lib.jsxinc` | Time Remap の読み書きの共通ライブラリ（Phase 0 から共通） |
| `jsx/syncbridge_ae.jsx`, `jsx/probe_ae.jsx` | Phase 0 のファイル経由の転送とプローブ（`File > Scripts > Run Script File...`） |

- JSX は ExtendScript（ES3）で、ファイルは ASCII のみ（CLAUDE.md）。`panel/js` はブラウザの JavaScript なので制限はない。
- **利用者向けのメッセージ（日本語）:** JSX は `SB.userError(英語の文, コード, 値)` を投げ、パネルの `sbclient.js` の `MESSAGES` が
  コードから日本語の文を作る（Maya にもこの文が届く）。新しい警告を追加するときは、コードと `MESSAGES` の文を両方追加する。
  英語の文は Phase 0 のスクリプト（`syncbridge_ae.jsx` など）の表示と、コードが未登録のときの代わりに使う。
- 開発中の導入手順（PlayerDebugMode、拡張機能フォルダへのリンク）は `docs/PHASE1_PLAN.md` の V-P1C。
