# docs/features/extension.md — Chrome拡張仕様

**種別: UI仕様（テストなし）**
**対応サイト:** T4ポーカーサイト（WebSocket通信）
**実装参考:** `GTO-/extension/`（background.js / interceptor.js / content.js / popup.html/js）

---

## アーキテクチャ（MV3）

```
interceptor.js  (MAIN world)
  WebSocketをhookしてメッセージを傍受
  フォールド離脱時は seats[mySeatIndex].cards / buttonPosition からカード・ポジションを退避
    ↓ CustomEvent
content.js  (ISOLATED world)
  CustomEventを受信してchrome.runtime.sendMessageへ転送
    ↓ chrome.runtime.sendMessage
background.js  (Service Worker)
  ハンドデータを受信・整形してサーバーに送信
  自動解析トリガーを管理
```

---

## データフロー

```
T4サイト WebSocket
  → interceptor.js でハンドデータ傍受
  → content.js で転送
  → background.js でデータ整形 (hand_converter互換形式に変換)
  → POST /api/hand-capture へ送信（Cloud Run）
  → サーバー側でFirestoreに保存
  → 自動解析パイプライン起動（設定済みの場合）
```

---

## ポップアップUI

| 要素 | 内容 |
|---|---|
| 接続状態 | サーバーへの接続状態インジケータ |
| 傍受ON/OFF | WebSocket傍受の有効化/無効化 |
| 最終取得ハンド | 最後に取得したハンドのサマリー |
| 自動解析設定 | ハンド取得後に自動解析を実行するかのトグル |

---

## 注意事項

- Chrome拡張コンソール（`chrome://extensions` → background）と `/sessions` ページのコンソールは別物
- `/sessions` ページのコンソールから `chrome.runtime` APIは呼べない
- Service Workerはインアクティブ時にメモリから解放される（Chrome MV3の制約）
- インフラ移行時（Cloudflare Tunnel → Cloud Run）に拡張側のエンドポイントURL更新を忘れない

---

## 実装状況（2026-07）

`extension/` にMV3スキャフォールドを作成済み（manifest / interceptor / content / background / popup）。
アーキテクチャ・データフロー・ポップアップUIは本仕様どおり配線済み。

**未実装（TODO）:** T4サイトの実WebSocketメッセージ形式が本リポジトリに未記録のため、
`interceptor.js` の adapter 関数（`decodeT4Frame` / `toSnapshot` / `extractCompletedHand`）と
`background.js` の `normalizeHand` はスケルトンのまま。実装参考 `GTO-/extension/interceptor.js` を見て埋める。
併せて未実装: (1) `manifest.json` の `t4-placeholder.example` を実ホストへ差し替え、
(2) Firebase ID token を `chrome.storage.local.idToken` へ供給するログイン導線（`background.js` authHeader）、
(3) セッション終了イベントでのバッファ確実flush（現状はしきい値＋debounceのbest-effort）。

## ストアリリース（未完了・V1ゴールに含める）

- [ ] Chrome Web Storeへの公開準備
- [ ] manifest.json のpermissions最小化
- [ ] プライバシーポリシーページ
