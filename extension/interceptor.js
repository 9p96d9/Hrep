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
  // adapter 関数（T4依存の唯一の場所）
  //   ここ以外に T4 メッセージ形式の知識を漏らさないこと。
  //   実装参考: GTO-/extension/interceptor.js（Socket.IO 傍受）。
  //
  //   T4の通信は Socket.IO（over WebSocket）。イベントフレームは
  //   "42" プレフィックス + JSON配列 [eventName, payload] のテキスト。
  //   ハンドは "fastFoldTableState" イベントで運ばれ、isHandInProgress===false
  //   （または fastFoldTableRemoved によるフォールド離脱）で1ハンド完了と判定する。
  // ---------------------------------------------------------------------------

  // ハンド境界検出のための adapter 内部状態（T4依存なのでここに閉じ込める）。
  const _lastState = {};    // tableId → 直近の raw fastFoldTableState
  const _lastHandKey = {};  // tableId → 送信済み actionHistory のキー（重複防止）

  // 生の WebSocket メッセージ（文字列 or ArrayLike）を JSON などにデコードする。
  function decodeT4Frame(data) {
    // T4は Socket.IO テキストフレーム。バイナリ（Blob/ArrayBuffer）は対象外。
    if (typeof data !== "string") return null;
    // Socket.IO EVENT パケットは "42" 始まり（"42/namespace," が付くこともある）。
    if (!data.startsWith("42")) return null;
    const start = data.indexOf("[");
    if (start < 0) return null;
    let arr;
    try { arr = JSON.parse(data.slice(start)); } catch { return null; }
    if (!Array.isArray(arr) || arr.length === 0) return null;
    return { event: arr[0], data: arr[1] };
  }

  // デコード済みメッセージから「正規化済みテーブル状態スナップショット」を作る。
  // 返す形（このファイル内でのみ使う中間表現）:
  //   { tableId, mySeatIndex, buttonPosition, seats: [{ cards:[...], ... }], ... }
  // stash 用に、席のホールカード欄を .cards へ正規化しておく
  // （T4は cards / hand / holeCards のいずれかで持つ）。
  function toSnapshot(msg) {
    if (!msg || msg.event !== "fastFoldTableState") return null;
    const d = msg.data;
    if (!d || d.tableId == null) return null;
    const seats = (Array.isArray(d.seats) ? d.seats : []).map((s) => {
      if (!s) return s;
      const cards = s.cards || s.hand || s.holeCards;
      return Array.isArray(cards) ? { ...s, cards } : s;
    });
    return {
      tableId: d.tableId,
      mySeatIndex: d.mySeatIndex,
      buttonPosition: d.buttonPosition,
      seats,
    };
  }

  // 6-max: buttonPosition + 着席プレイヤーから Hero のポジション名を算出する。
  //   offset 0=BTN,1=SB,2=BB,3=UTG,4=HJ,5=CO（人数に応じて縮約）。
  function calcHeroPosition(state) {
    const btn = state.buttonPosition != null ? state.buttonPosition : stash.buttonPosition;
    const mySeat = state.mySeatIndex != null ? state.mySeatIndex : stash.mySeatIndex;
    if (btn == null || mySeat == null) return "";
    const active = (state.seats || [])
      .map((s, i) => (s && s.playerName ? i : -1))
      .filter((i) => i >= 0);
    const n = active.length;
    const btnPos = active.indexOf(btn);
    const heroPos = active.indexOf(mySeat);
    if (n === 0 || btnPos < 0 || heroPos < 0) return "";
    const offset = (heroPos - btnPos + n) % n;
    const NAMES = {
      2: ["BTN", "BB"],
      3: ["BTN", "SB", "BB"],
      4: ["BTN", "SB", "BB", "UTG"],
      5: ["BTN", "SB", "BB", "UTG", "CO"],
      6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    };
    return (NAMES[n] || [])[offset] || "";
  }

  // メッセージ列から「1ハンド完了」を検出し、完成ハンドオブジェクトを返す。
  // stash（退避したhero情報）を使って、フォールドで欠けた情報を補完する。
  // 返す形は background.js の normalizeHand が hand JSON へ整形する前段の生ハンド
  // （= T4 fastFoldTableState そのもの。handResults/seats/actionHistory/… を持つ）。
  function extractCompletedHand(msg, snapshot) {
    if (!msg) return null;
    const ev = msg.event;
    const d = msg.data;

    // 通常完了: fastFoldTableState が isHandInProgress:false を運んでくる
    if (ev === "fastFoldTableState" && d && d.tableId != null) {
      _lastState[d.tableId] = d;
      if (d.isHandInProgress === false) {
        return _finishHand(d.tableId);
      }
      return null;
    }

    // フォールド離脱: fastFoldTableRemoved で退席 → 直近stateを確定させる
    if (ev === "fastFoldTableRemoved") {
      const tableId =
        d && typeof d === "object" && d.tableId != null ? d.tableId
        : (typeof d === "string" || typeof d === "number") ? d
        : null;
      if (tableId != null) return _finishHand(tableId);
    }
    return null;
  }

  // tableId の直近stateを1ハンドとして確定する。重複・空はスキップ。
  function _finishHand(tableId) {
    const state = _lastState[tableId];
    if (!state) return null;
    const history = state.actionHistory;
    if (!Array.isArray(history) || history.length === 0) return null; // 空スキップ
    const key = JSON.stringify(history);
    if (_lastHandKey[tableId] === key) return null;                    // 重複スキップ
    _lastHandKey[tableId] = key;

    const hand = _fillHeroFromStash(state);
    delete _lastState[tableId];
    return hand;
  }

  // フォールドで消えた hero 情報（カード・ポジション）を stash から補完する。
  // 完了stateの handResults に hero エントリが無ければ追加、欠けたフィールドだけ埋める。
  function _fillHeroFromStash(state) {
    const out = { ...state };
    if (out.buttonPosition == null && stash.buttonPosition != null) {
      out.buttonPosition = stash.buttonPosition;
    }
    const mySeat = out.mySeatIndex != null ? out.mySeatIndex : stash.mySeatIndex;
    if (out.mySeatIndex == null && mySeat != null) out.mySeatIndex = mySeat;
    if (mySeat == null) return out;

    const position = calcHeroPosition(out);
    const results = Array.isArray(out.handResults) ? out.handResults.map((r) => ({ ...r })) : [];
    let hero = results.find((r) => r.seatIndex === mySeat);
    if (!hero) {
      hero = { seatIndex: mySeat, hand: [], position: "", profit: 0, playerName: "", isWinner: false };
      results.push(hero);
    }
    if ((!hero.hand || hero.hand.length === 0) && stash.heroCards && stash.heroCards.length) {
      hero.hand = stash.heroCards.slice();
    }
    if (!hero.position && position) hero.position = position;
    out.handResults = results;
    return out;
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
