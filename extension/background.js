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
  // interceptor.js の extractCompletedHand が返す生ハンドを、サーバーの
  // annotate_hand が期待するフィールド名（docs/data_schema.md）へ写像する。
  //
  // TODO(GTO-/extension/interceptor.js と対で埋める):
  //   interceptor 側の生ハンド形が確定したら、ここで下記フィールドへマップする:
  //     hand_number, hero_position, hero_cards, hero_result_bb, is_3bet_pot,
  //     players[], streets{preflop, flop, turn, river}
  //   分類・GTO数学・スコアはサーバーの annotate_hand が付与するので送らない。
  //
  // 現状は pass-through。生ハンドが既に schema 形なら素通しで動く。
  return raw;
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
