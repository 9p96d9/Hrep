/**
 * adapter_roundtrip.test.mjs — 実機なしで adapter 往復を検証する。
 *
 * 実行: node --test extension/tests/adapter_roundtrip.test.mjs
 *
 * 本物の interceptor.js / background.js を vm サンドボックス（擬似ブラウザ）で
 * ロードし、T4の Socket.IO フレームを流し込んで:
 *   WebSocket hook → decodeT4Frame/toSnapshot/extractCompletedHand
 *     → CustomEvent("hrep:hand") → normalizeHand
 * が docs/data_schema.md 形のハンドJSONを出すことを確認する。
 *
 * ※ T4の生フレーム/actionHistory文法は GTO-/scripts/hand_converter.py（本番実績の
 *   パーサ）を唯一の出典とする。実サイトの傍受確認はストア申請時の実機テストで行う。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EXT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function makeSandbox() {
  class FakeWebSocket extends EventTarget {
    constructor(url, protocols) { super(); this.url = url; this.protocols = protocols; }
    send() {} close() {}
  }
  FakeWebSocket.CONNECTING = 0; FakeWebSocket.OPEN = 1; FakeWebSocket.CLOSING = 2; FakeWebSocket.CLOSED = 3;

  const win = new EventTarget();
  win.WebSocket = FakeWebSocket;
  const hands = [];
  win.addEventListener("hrep:hand", (ev) => hands.push(ev.detail.hand));

  const noop = () => {};
  const chromeStub = {
    runtime: { onMessage: { addListener: noop }, onInstalled: { addListener: noop }, sendMessage: noop },
    storage: {
      sync: { get: (d, cb) => cb(d), set: (_o, cb) => cb && cb() },
      local: { get: (d, cb) => cb(typeof d === "object" ? d : {}), set: (_o, cb) => cb && cb() },
      onChanged: { addListener: noop },
    },
  };

  const sandbox = {
    window: win, WebSocket: FakeWebSocket, CustomEvent, EventTarget, chrome: chromeStub,
    console: { debug: noop, log: noop, warn: noop, error: noop }, setTimeout, clearTimeout,
  };
  sandbox.self = sandbox; sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(`${EXT}/interceptor.js`, "utf8"), sandbox, { filename: "interceptor.js" });
  vm.runInContext(fs.readFileSync(`${EXT}/background.js`, "utf8"), sandbox, { filename: "background.js" });

  const ws = new sandbox.window.WebSocket("wss://tenfourpoker.com/socket.io/");
  const feed = (event, data) => {
    const ev = new Event("message");
    ev.data = "42" + JSON.stringify([event, data]);
    ws.dispatchEvent(ev);
  };
  return { sandbox, hands, feed };
}

test("normal completion: fastFoldTableState(isHandInProgress:false) → schema hand", () => {
  const { sandbox, hands, feed } = makeSandbox();
  feed("fastFoldTableState", {
    tableId: "tA", mySeatIndex: 5, buttonPosition: 0, isHandInProgress: false,
    communityCards: ["Qh", "5d", "2c", "Kh"],
    seats: [
      { playerName: "P0" }, { playerName: "P1" }, { playerName: "P2" }, { playerName: "P3" },
      { playerName: "Villain", isFolded: true },
      { playerName: "Hero", isFolded: false, cards: ["Ah", "Kd"] },
    ],
    handResults: [
      { seatIndex: 5, position: "CO", playerName: "Hero", profit: 11.5, isWinner: true, hand: ["Ah", "Kd"] },
      { seatIndex: 4, position: "BB", playerName: "Villain", profit: -11.5, isWinner: false, hand: [] },
    ],
    actionHistory: [
      "# PREFLOP", "CO Raise 2.5", "BB Call",
      "# FLOP (5.5bb)", "BB Check", "CO Bet 3", "BB Call",
      "# TURN (11.5bb)", "BB Check", "CO Bet 7", "BB Fold",
      "# CO wins 11.5bb", "# RESULTS", "Rake: 0.5bb",
    ],
  });

  assert.equal(hands.length, 1, "1ハンドが emit される");
  const h = JSON.parse(JSON.stringify(sandbox.normalizeHand(hands[0])));
  assert.equal(h.hero_position, "CO");
  assert.deepEqual(h.hero_cards, ["Ah", "Kd"]);
  assert.equal(h.hero_result_bb, 11.5);
  assert.equal(h.is_3bet_pot, false);
  // アクションは小文字（annotate_hand の AGGRESSIVE_ACTIONS 契約）
  assert.equal(h.streets.preflop[0].action, "raise");
  assert.deepEqual(h.streets.flop.board, ["Qh", "5d", "2c"]);
  assert.equal(h.streets.flop.pot_bb, 5.5);
  assert.deepEqual(h.streets.turn.board, ["Kh"]);
  assert.equal(h.streets.turn.actions.at(-1).action, "fold");
  assert.equal(h.streets.river, null, "リバー未到達は null");
  assert.equal(h.result.rake_bb, 0.5);
});

test("10 rank & hidden cards: '10s' → 'Ts', '**' は除去", () => {
  const { sandbox, hands, feed } = makeSandbox();
  feed("fastFoldTableState", {
    tableId: "tC", mySeatIndex: 0, buttonPosition: 0, isHandInProgress: false,
    communityCards: ["10s", "Jd", "2c"],
    seats: [{ playerName: "Hero" }, { playerName: "V" }],
    handResults: [
      { seatIndex: 0, position: "BTN", playerName: "Hero", profit: 3, isWinner: true, hand: ["10h", "Ah"] },
      { seatIndex: 1, position: "BB", playerName: "V", profit: -3, isWinner: false, hand: ["**", "**"] },
    ],
    actionHistory: ["# PREFLOP", "BTN Raise 2.5", "BB Call", "# FLOP (5bb)", "BB Check", "BTN Bet 2", "BB Fold"],
  });
  const h = JSON.parse(JSON.stringify(sandbox.normalizeHand(hands[0])));
  assert.deepEqual(h.hero_cards, ["Th", "Ah"], "10h→Th");
  assert.deepEqual(h.streets.flop.board, ["Ts", "Jd", "2c"], "10s→Ts");
  assert.deepEqual(h.players.find((p) => !p.is_hero).hole_cards, [], "伏せ札は除去");
});

test("fold-leave: fastFoldTableRemoved で stash から hero カードを補完", () => {
  const { sandbox, hands, feed } = makeSandbox();
  // 進行中フレームで hero の席カードが見えている（後で消える）
  feed("fastFoldTableState", {
    tableId: "tB", mySeatIndex: 5, buttonPosition: 0, isHandInProgress: true,
    seats: [
      { playerName: "P0" }, { playerName: "P1" }, { playerName: "P2" },
      { playerName: "UTG" }, { playerName: "P4" },
      { playerName: "Hero", cards: ["7c", "2d"] },
    ],
    handResults: [],
    actionHistory: ["# PREFLOP", "UTG Raise 3", "CO Fold"],
  });
  assert.equal(hands.length, 0, "進行中は emit しない");
  // 離席イベント → 直近stateを確定
  feed("fastFoldTableRemoved", "tB");
  assert.equal(hands.length, 1, "離席で1ハンド確定");
  const h = JSON.parse(JSON.stringify(sandbox.normalizeHand(hands[0])));
  assert.deepEqual(h.hero_cards, ["7c", "2d"], "フォールドで消えた hero カードを stash から復元");
  assert.equal(h.hero_position, "CO", "buttonPosition+seats から CO を算出");
});

test("重複 actionHistory は二重 emit しない", () => {
  const { hands, feed } = makeSandbox();
  const state = {
    tableId: "tD", mySeatIndex: 0, buttonPosition: 0, isHandInProgress: false,
    communityCards: [], seats: [{ playerName: "Hero" }, { playerName: "V" }],
    handResults: [{ seatIndex: 0, position: "BTN", playerName: "Hero", profit: 1, isWinner: true, hand: ["Ah", "Kd"] }],
    actionHistory: ["# PREFLOP", "BTN Raise 2.5", "BB Fold"],
  };
  feed("fastFoldTableState", state);
  feed("fastFoldTableState", state); // 同一 actionHistory の再送
  assert.equal(hands.length, 1, "同じ actionHistory は1回だけ");
});

test("非T4フレーム・バイナリは無視される", () => {
  const { hands, feed } = makeSandbox();
  feed("someOtherEvent", { foo: 1 });
  feed("fastFoldTableState", { tableId: "tE", isHandInProgress: true, actionHistory: [] });
  assert.equal(hands.length, 0);
});
