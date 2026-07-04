// interceptor.js — MAIN world
// -----------------------------------------------------------------------------
// T4ポーカーサイトの WebSocket をhookし、ハンド関連メッセージを傍受して
// CustomEvent 経由で content.js (ISOLATED world) へ渡す。
//
// このファイルは chrome.* API にアクセスできない（MAIN world / ページ文脈）。
// ページ外への唯一の出口は window への CustomEvent ディスパッチのみ。
//
// !!! 重要 !!!
// T4サイトの実際の WebSocket メッセージ形式は本リポジトリに記録がない。
// パース処理はすべて下の「adapter 関数」に隔離してあり、中身は未実装（TODO）。
// 実装参考: GTO-/extension/interceptor.js（別リポジトリ）を見て埋めること。
// 憶測でメッセージ形式をでっち上げないこと。
// -----------------------------------------------------------------------------

(() => {
  "use strict";

  const EVENT_HAND = "hrep:hand";      // 1ハンド完成時に content.js へ渡す
  const EVENT_RAW = "hrep:raw";        // デバッグ用（生メッセージ・任意）

  // ---------------------------------------------------------------------------
  // フォールド離脱時の退避バッファ
  //   自分がフォールドすると以降のメッセージから自分のカード/ポジションが
  //   消えることがあるため、見えているうちに退避しておく。
  // ---------------------------------------------------------------------------
  const stash = {
    mySeatIndex: null,     // 自席のインデックス（T4メッセージから確定させる）
    heroCards: null,       // seats[mySeatIndex].cards の退避
    buttonPosition: null,  // buttonPosition の退避（ポジション算出用）
  };

  function stashFromSnapshot(snapshot) {
    // snapshot: adapter が返す正規化済みテーブル状態（下記 parseT4Message 参照）
    if (!snapshot) return;
    if (snapshot.mySeatIndex != null) stash.mySeatIndex = snapshot.mySeatIndex;
    if (snapshot.buttonPosition != null) stash.buttonPosition = snapshot.buttonPosition;

    const seats = snapshot.seats;
    if (Array.isArray(seats) && stash.mySeatIndex != null) {
      const mine = seats[stash.mySeatIndex];
      // カードが見えている間だけ退避を更新する（フォールド後に空で上書きしない）
      if (mine && Array.isArray(mine.cards) && mine.cards.length > 0) {
        stash.heroCards = mine.cards.slice();
      }
    }
  }

  function resetStash() {
    stash.mySeatIndex = null;
    stash.heroCards = null;
    stash.buttonPosition = null;
  }

  // ---------------------------------------------------------------------------
  // adapter 関数（T4依存の唯一の場所） — すべて TODO
  //   ここ以外に T4 メッセージ形式の知識を漏らさないこと。
  // ---------------------------------------------------------------------------

  // 生の WebSocket メッセージ（文字列 or ArrayLike）を JSON などにデコードする。
  function decodeT4Frame(data) {
    // TODO(GTO-/extension/interceptor.js): T4のフレーム形式に合わせてデコード。
    //   JSON テキストなのか、独自バイナリなのか、複数メッセージ連結なのかを確認する。
    if (typeof data === "string") {
      try { return JSON.parse(data); } catch { return null; }
    }
    return null; // バイナリ形式なら要実装
  }

  // デコード済みメッセージから「正規化済みテーブル状態スナップショット」を作る。
  // 返す形（このファイル内でのみ使う中間表現）:
  //   { mySeatIndex, buttonPosition, seats: [{ cards:[...], ... }], ... }
  function toSnapshot(msg) {
    // TODO(GTO-/extension/interceptor.js): T4メッセージ → snapshot への写像。
    //   seats / buttonPosition / mySeatIndex に相当するフィールドを特定する。
    return null;
  }

  // メッセージ列から「1ハンド完了」を検出し、完成ハンドオブジェクトを返す。
  // stash（退避したhero情報）を使って、フォールドで欠けた情報を補完する。
  // 返す形は background.js 側で hand_converter 互換へ整形する前段の生ハンド。
  function extractCompletedHand(msg, snapshot) {
    // TODO(GTO-/extension/interceptor.js): ハンド境界（開始/終了）検出ロジック。
    //   ハンド終了イベントを受けたら、そのハンドのアクション列・ボード・結果を
    //   組み立てて返す。フォールドで消えたhero情報は stash から補完する:
    //     heroCards        <- stash.heroCards
    //     buttonPosition   <- stash.buttonPosition
    //   ハンド完了後は resetStash() を呼ぶこと。
    return null;
  }

  // adapter の統合エントリ。生フレーム1つを受け取り、必要なら完成ハンドを emit する。
  function parseT4Message(data) {
    const msg = decodeT4Frame(data);
    if (msg == null) return;

    if (EMIT_RAW_FOR_DEBUG) emit(EVENT_RAW, { msg });

    const snapshot = toSnapshot(msg);
    stashFromSnapshot(snapshot);

    const hand = extractCompletedHand(msg, snapshot);
    if (hand) {
      emit(EVENT_HAND, { hand });
      resetStash();
    }
  }

  const EMIT_RAW_FOR_DEBUG = false; // 開発中の生メッセージ観察に使う

  // ---------------------------------------------------------------------------
  // CustomEvent 出口
  // ---------------------------------------------------------------------------
  function emit(type, detail) {
    try {
      window.dispatchEvent(new CustomEvent(type, { detail }));
    } catch (e) {
      // MAIN world からログ以上のことはしない
      console.debug("[hrep] emit failed", e);
    }
  }

  // ---------------------------------------------------------------------------
  // WebSocket hook
  //   document_start で走らせ、ページが WebSocket を作る前に差し替える。
  // ---------------------------------------------------------------------------
  const NativeWebSocket = window.WebSocket;
  if (!NativeWebSocket) return;

  function HookedWebSocket(url, protocols) {
    const ws = protocols === undefined
      ? new NativeWebSocket(url)
      : new NativeWebSocket(url, protocols);

    ws.addEventListener("message", (ev) => {
      try {
        parseT4Message(ev.data);
      } catch (e) {
        console.debug("[hrep] parse failed", e);
      }
    });

    // TODO(任意): 送信側（ws.send）も観察が要るなら send をラップする。

    return ws;
  }

  // プロトタイプ・静的定数を引き継ぐ（instanceof / OPEN 等の互換維持）
  HookedWebSocket.prototype = NativeWebSocket.prototype;
  HookedWebSocket.CONNECTING = NativeWebSocket.CONNECTING;
  HookedWebSocket.OPEN = NativeWebSocket.OPEN;
  HookedWebSocket.CLOSING = NativeWebSocket.CLOSING;
  HookedWebSocket.CLOSED = NativeWebSocket.CLOSED;

  try {
    window.WebSocket = HookedWebSocket;
    console.debug("[hrep] WebSocket hooked");
  } catch (e) {
    console.debug("[hrep] failed to install WebSocket hook", e);
  }
})();
