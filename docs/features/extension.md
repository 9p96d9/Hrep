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

**adapter実装済み:** T4は Socket.IO（over WebSocket）で、イベントフレームは `"42"` +
JSON配列 `[eventName, payload]`。ハンドは `fastFoldTableState` イベントで運ばれ、
`isHandInProgress===false`（またはフォールド離脱時の `fastFoldTableRemoved`）で1ハンド完了とみなす。
この知識に基づき実装参考 `GTO-/extension/interceptor.js` ＆ `GTO-/scripts/hand_converter.py` を移植:

- `interceptor.js` の adapter（`decodeT4Frame` / `toSnapshot` / `extractCompletedHand`）を実装。
  T4依存の知識は adapter セクション内に閉じ込め、フォールド離脱時の hero カード/ポジション退避
  （stash）と、`actionHistory` 重複送信の抑止を含む。
- `background.js` の `normalizeHand` を実装。T4生ハンド → `docs/data_schema.md` のハンドJSON
  への写像（アクション名は小文字、カードは treys 記法 `"As"`/`"Th"`、`is_3bet_pot` 判定、
  フォールドプレイヤーの profit=0 をアクション履歴から補正）。分類・GTO数学・スコアは送らず
  サーバーの `annotate_hand` に任せる。
- `manifest.json` の `t4-placeholder.example` を実ホスト（`tenfourpoker.com` / `tenfour-poker.com`
  / `t4poker.com`）へ差し替え。

**検証:** `extension/tests/adapter_roundtrip.test.mjs`（`node --test`）で、本物の interceptor.js /
background.js を擬似ブラウザ（vm）でロードし、T4フレーム流し込み → adapter → `normalizeHand` の
往復が data_schema 形になることを確認（通常完了・フォールド離脱・10ランク/伏せ札・重複抑止・
非T4無視の5ケース pass）。さらに出力を実サーバー `scripts/hand_converter.annotate_hand` に通し、
例外なく分類・GTO数学が付与されることを確認済み（extension→server 契約の疎通確認）。
実サイトでの実機傍受確認はブラウザ/T4アカウントが要るためストア申請時の実機テストで行う（本リポジトリに
生フレーム記録は無く、フレーム文法の出典は本番実績のある `GTO-/scripts/hand_converter.py` パーサ）。

**未実装（TODO・adapter外）:**
(1) Firebase ID token を `chrome.storage.local.idToken` へ供給するログイン導線（`background.js` authHeader）、
(2) セッション終了イベントでのバッファ確実flush（現状はしきい値＋debounceのbest-effort）。

## ストアリリース（未完了・V1ゴールに含める）

- [ ] Chrome Web Storeへの公開準備
- [ ] manifest.json のpermissions最小化
- [ ] プライバシーポリシーページ
