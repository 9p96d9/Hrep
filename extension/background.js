// background.js — Service Worker (MV3)
// -----------------------------------------------------------------------------
// content.js から届くハンドを受け取り、data_schema.md のハンドJSON形式
// (hand_converter互換) に整形して POST /api/hand-capture へ送る。
//
// MV3 制約: Service Worker はインアクティブ時にメモリから解放される。
//   → 状態（設定・バッファ・最終ハンド）はすべて chrome.storage に置く。
//     グローバル変数に永続状態を持たせない。
// -----------------------------------------------------------------------------

"use strict";

const DEFAULTS = {
  endpoint: "https://hrep.app", // chrome.storage.sync で変更可能
  autoAnalyze: false,           // ハンド取得後に自動解析するか
};

const FLUSH_THRESHOLD = 25;     // バッファがこの件数に達したら送信
const FLUSH_DEBOUNCE_MS = 5000; // 最終ハンドからこの時間で送信（best-effort）

// ---------------------------------------------------------------------------
// 設定・状態アクセス（すべて chrome.storage 経由）
// ---------------------------------------------------------------------------
function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(DEFAULTS, (v) => resolve(v));
  });
}

function getLocal(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function setLocal(obj) {
  return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
}

// ---------------------------------------------------------------------------
// T4生ハンド → data_schema.md 互換 hand_json への整形
// ---------------------------------------------------------------------------
function normalizeHand(raw) {
  // interceptor.js の extractCompletedHand が返す生ハンド（T4 fastFoldTableState）を、
  // サーバーの annotate_hand が期待するハンドJSON（docs/data_schema.md）へ写像する。
  // 分類・GTO数学・スコアは annotate_hand が付与するので送らない。
  //
  // 参考実装: GTO-/scripts/hand_converter.py convert_hand_json。
  //   ただし本サーバーの契約に合わせて (a) アクション名は小文字、
  //   (b) カードは treys 記法（"As" / "Th"、ランク大文字・スート小文字）で出す。
  if (!raw || typeof raw !== "object") return raw;
  // 既に schema 形（hero_position + streets を持つ）ならそのまま通す。
  if (raw.hero_position !== undefined && raw.streets !== undefined) return raw;
  // T4 raw の目印が無ければ変換しない（未知の形を壊さない）。
  if (raw.handResults === undefined && raw.actionHistory === undefined) return raw;

  const handResults = Array.isArray(raw.handResults) ? raw.handResults : [];
  const seats = Array.isArray(raw.seats) ? raw.seats : [];
  const mySeatIndex = raw.mySeatIndex != null ? raw.mySeatIndex : -1;
  const communityRaw = Array.isArray(raw.communityCards) ? raw.communityCards : [];

  // position → playerName（actionHistory パース用）
  const posToName = {};
  for (const r of handResults) {
    if (r && r.position != null) posToName[r.position] = r.playerName || "";
  }

  // players[] を handResults から構築
  const players = handResults.map((r) => ({
    name: r.playerName || "",
    position: r.position || "",
    is_hero: r.seatIndex === mySeatIndex,
    hole_cards: (Array.isArray(r.hand) ? r.hand : []).map(convertCard).filter(Boolean),
    result_bb: Number(r.profit || 0),
  }));

  // actionHistory を streets / result / is_3bet_pot へ
  const parsed = parseActionHistory(Array.isArray(raw.actionHistory) ? raw.actionHistory : [], posToName);
  const streets = parsed.streets;

  // communityCards を各ストリートの board へ補完
  const board = communityRaw.map(convertCard).filter(Boolean);
  if (board.length >= 3 && streets.flop && !(streets.flop.board || []).length) streets.flop.board = board.slice(0, 3);
  if (board.length >= 4 && streets.turn && !(streets.turn.board || []).length) streets.turn.board = [board[3]];
  if (board.length >= 5 && streets.river && !(streets.river.board || []).length) streets.river.board = [board[4]];

  // hero
  const hero = players.find((p) => p.is_hero) || null;
  const heroPosition = hero ? hero.position : "";
  const heroCards = hero ? hero.hole_cards : [];
  let heroResultBb = hero ? hero.result_bb : 0;

  // フォールドプレイヤーの profit が 0 で返る場合、アクション履歴から投資額を補正
  const heroIsWinner = hero && parsed.result.winners.some(
    (w) => w.name === (hero.name || heroPosition)
  );
  if (hero && heroResultBb === 0 && !heroIsWinner) {
    heroResultBb = -calcHeroInvestment(streets, heroPosition);
  }

  // winners が actionHistory から取れなければ handResults で補完
  if (parsed.result.winners.length === 0) {
    for (const r of handResults) {
      if (r && r.isWinner) parsed.result.winners.push({ name: r.playerName || "", amount_bb: Number(r.profit || 0) });
    }
  }

  return {
    hand_number: raw.hand_number ?? null,
    hero_position: heroPosition,
    hero_cards: heroCards,
    hero_result_bb: heroResultBb,
    is_3bet_pot: parsed.is_3bet_pot,
    players,
    streets,
    result: parsed.result,
  };
}

// "As" → "As", "Td"/"10d" → "Td"/"Th"（treys 記法: ランク大文字・スート小文字）。
// 伏せ札("**")・不正値は null。
function convertCard(card) {
  if (typeof card !== "string" || card.length < 2 || card === "**") return null;
  let rank = card.slice(0, -1).toUpperCase();
  const suit = card.slice(-1).toLowerCase();
  if (rank === "10") rank = "T";
  if (!/^[2-9TJQKA]$/.test(rank) || !/^[shdc]$/.test(suit)) return null;
  return rank + suit;
}

const T4_ACTION_MAP = { FOLD: "fold", CHECK: "check", CALL: "call", BET: "bet", RAISE: "raise", ALLIN: "allin" };

function parseBb(s) {
  const m = String(s).trim().replace(/[bB]+$/, "");
  const n = parseFloat(m);
  return Number.isFinite(n) ? n : 0;
}

// GTO-/scripts/hand_converter.py parse_action_history の JS 移植。
function parseActionHistory(actionHistory, posToName) {
  const streets = { preflop: [], flop: null, turn: null, river: null };
  const result = { winners: [], rake_bb: 0, allin_ev: {} };

  let currentStreet = null;
  let currentActions = [];
  let currentPot = 0;
  let inResults = false;

  function flush() {
    if (currentStreet === "preflop") {
      streets.preflop = currentActions.slice();
    } else if (currentStreet === "flop" || currentStreet === "turn" || currentStreet === "river") {
      streets[currentStreet] = { board: [], pot_bb: currentPot, actions: currentActions.slice() };
    }
    currentActions = [];
    currentPot = 0;
  }

  for (let line of actionHistory) {
    line = String(line).trim();
    if (!line) continue;

    if (line.startsWith("#")) {
      const content = line.slice(1).trim();
      const mStreet = content.match(/^(PREFLOP|FLOP|TURN|RIVER)(?:\s+\((\d+\.?\d*)bb?\))?$/i);
      if (mStreet) {
        flush();
        inResults = false;
        currentStreet = mStreet[1].toLowerCase();
        currentPot = mStreet[2] ? parseFloat(mStreet[2]) : 0;
        continue;
      }
      const mWin = content.match(/^(\w[\w+]*)\s+wins\s+([\d.]+)bb?$/i);
      if (mWin) {
        const pos = mWin[1];
        result.winners.push({ name: posToName[pos] || pos, amount_bb: parseFloat(mWin[2]) });
        continue;
      }
      if (content.toUpperCase() === "RESULTS") {
        flush();
        inResults = true;
        continue;
      }
      continue;
    }

    if (inResults) {
      const mRake = line.match(/^Rake:\s*([\d.]+)bb?$/i);
      if (mRake) result.rake_bb = parseFloat(mRake[1]);
      continue; // プレイヤー結果行は handResults で取得済み
    }

    const parts = line.split(/\s+/);
    if (parts.length < 2) continue;
    const pos = parts[0];
    const action = T4_ACTION_MAP[parts[1].toUpperCase()];
    if (action && currentStreet) {
      const entry = { position: pos, name: posToName[pos] || pos, action };
      if ((action === "bet" || action === "raise" || action === "call" || action === "allin") && parts.length >= 3) {
        entry.amount_bb = parseBb(parts[2]);
      }
      currentActions.push(entry);
    }
    // POST（ブラインド）は記録しない
  }

  if (currentStreet && currentActions.length) flush();

  const raiseCount = streets.preflop.filter((a) => a.action === "raise").length;
  return { streets, result, is_3bet_pot: raiseCount >= 2 };
}

// GTO-/scripts/hand_converter.py _calc_hero_investment の JS 移植。
function calcHeroInvestment(streets, heroPos) {
  let total = heroPos === "BB" ? 1.0 : heroPos === "SB" ? 0.5 : 0.0;

  let facing = 1.0;
  for (const a of streets.preflop || []) {
    const amount = a.amount_bb || 0;
    if ((a.action === "raise" || a.action === "bet") && amount > 0) facing = amount;
    if (a.position === heroPos && (a.action === "raise" || a.action === "bet" || a.action === "call")) {
      total = Math.max(total, amount > 0 ? amount : facing);
    }
  }

  for (const key of ["flop", "turn", "river"]) {
    const s = streets[key];
    if (!s || typeof s !== "object") continue;
    let stFacing = 0;
    let stInvested = 0;
    for (const a of s.actions || []) {
      const amount = a.amount_bb || 0;
      if ((a.action === "raise" || a.action === "bet") && amount > 0) stFacing = amount;
      if (a.position === heroPos) {
        if (a.action === "bet" || a.action === "raise") { stInvested = amount; stFacing = amount; }
        else if (a.action === "call") stInvested = amount > 0 ? amount : stFacing;
      }
    }
    total += stInvested;
  }
  return total;
}

// ---------------------------------------------------------------------------
// バッファリング（1セッション=1解析になるよう、複数ハンドをまとめて送る）
// ---------------------------------------------------------------------------
async function bufferHand(hand) {
  const normalized = normalizeHand(hand);
  const { handBuffer = [] } = await getLocal({ handBuffer: [] });
  handBuffer.push(normalized);

  await setLocal({
    handBuffer,
    lastHand: summarizeHand(normalized),
    lastCapturedAt: Date.now(),
  });

  if (handBuffer.length >= FLUSH_THRESHOLD) {
    await flushBuffer();
  } else {
    scheduleDebouncedFlush();
  }
}

let debounceTimer = null; // SWが生きている間だけ有効。死んでも threshold/手動flushで回収。
function scheduleDebouncedFlush() {
  // TODO(session-end): T4の「セッション終了」イベントが判れば、debounce ではなく
  //   その境界で確実に flush したい。現状は SW 生存中のみ効く best-effort。
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => { flushBuffer(); }, FLUSH_DEBOUNCE_MS);
}

async function flushBuffer() {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
  const { handBuffer = [], sessionMeta = null, bbSize = null } =
    await getLocal({ handBuffer: [], sessionMeta: null, bbSize: null });
  if (handBuffer.length === 0) return { sent: 0 };

  try {
    const result = await sendHands(handBuffer, sessionMeta, bbSize);
    await setLocal({ handBuffer: [], lastAnalysisId: result.analysis_id || null });
    if (result.analysis_id) {
      const { autoAnalyze } = await getSettings();
      if (autoAnalyze) triggerAnalysis(result.analysis_id).catch(() => {});
    }
    return { sent: handBuffer.length, ...result };
  } catch (e) {
    // 送信失敗時はバッファを保持したまま（次回リトライ）。
    console.debug("[hrep] flush failed", e);
    await setLocal({ lastError: String(e && e.message || e) });
    return { sent: 0, error: String(e && e.message || e) };
  }
}

// ---------------------------------------------------------------------------
// サーバー送信
// ---------------------------------------------------------------------------
async function authHeader() {
  // /api/hand-capture は Authorization: Bearer <Firebase ID token> を要求する
  // （main.py current_uid）。
  // TODO(auth): ログインフローで取得した Firebase ID token を
  //   chrome.storage.local.idToken に入れる導線を用意する。ここでは読むだけ。
  const { idToken = null } = await getLocal({ idToken: null });
  return idToken ? { Authorization: `Bearer ${idToken}` } : {};
}

async function sendHands(hands, meta, bbSize) {
  const { endpoint } = await getSettings();
  const url = endpoint.replace(/\/+$/, "") + "/api/hand-capture";
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const body = JSON.stringify({ hands, meta: meta || {}, bb_size: bbSize });

  const res = await fetch(url, { method: "POST", headers, body });
  if (!res.ok) {
    throw new Error(`hand-capture ${res.status}`);
  }
  return res.json(); // { analysis_id, hand_count }
}

async function triggerAnalysis(analysisId) {
  // 自動解析トリガー。/api/analyze は SSE を返すが、ここでは起動のみ行い
  // ストリームは消費しない（結果はサーバー保存 → Webアプリで閲覧）。
  // TODO: 進捗をpopupに出したいならSSEを読む実装を足す。
  const { endpoint } = await getSettings();
  const url = endpoint.replace(/\/+$/, "") + "/api/analyze";
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const body = JSON.stringify({ analysis_id: analysisId, mode: "detail_street" });
  await fetch(url, { method: "POST", headers, body });
}

// ---------------------------------------------------------------------------
// サマリー（popup の「最終取得ハンド」表示用）
// ---------------------------------------------------------------------------
function summarizeHand(h) {
  h = h || {};
  return {
    hand_number: h.hand_number ?? null,
    hero_position: h.hero_position ?? null,
    hero_cards: h.hero_cards ?? null,
    hero_result_bb: h.hero_result_bb ?? null,
    at: Date.now(),
  };
}

// ---------------------------------------------------------------------------
// メッセージ受信（content.js / popup.js）
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case "hrep:hand":
      bufferHand(msg.hand).then(() => sendResponse({ ok: true }))
        .catch((e) => sendResponse({ ok: false, error: String(e) }));
      return true; // async

    case "hrep:flush":
      flushBuffer().then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: String(e) }));
      return true;

    default:
      return;
  }
});

// 初回インストール時に既定設定を書き込む
chrome.runtime.onInstalled.addListener(async () => {
  const cur = await getSettings();
  chrome.storage.sync.set({ ...DEFAULTS, ...cur });
});
