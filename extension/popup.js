// popup.js
// -----------------------------------------------------------------------------
// 仕様書 (docs/features/extension.md) の4要素:
//   1. 接続状態インジケータ（サーバーの /health を叩く）
//   2. WebSocket傍受 ON/OFF トグル
//   3. 最終取得ハンドのサマリー
//   4. 自動解析トグル
//
// 設定は chrome.storage 経由（background と共有）。
//   - endpoint / autoAnalyze : chrome.storage.sync
//   - captureEnabled / lastHand : chrome.storage.local
// -----------------------------------------------------------------------------

"use strict";

const DEFAULTS = { endpoint: "https://hrep.app", autoAnalyze: false };

const $ = (id) => document.getElementById(id);

function syncGet(defs) {
  return new Promise((r) => chrome.storage.sync.get(defs, r));
}
function localGet(defs) {
  return new Promise((r) => chrome.storage.local.get(defs, r));
}

// ---------------------------------------------------------------------------
// 1. 接続状態インジケータ
// ---------------------------------------------------------------------------
async function checkHealth() {
  const dot = $("conn-dot");
  const text = $("conn-text");
  const { endpoint } = await syncGet({ endpoint: DEFAULTS.endpoint });
  const url = endpoint.replace(/\/+$/, "") + "/health";
  dot.className = "dot";
  text.textContent = "確認中…";
  try {
    const res = await fetch(url, { method: "GET" });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.status === "ok") {
      dot.className = "dot ok";
      text.textContent = `接続OK${data.firestore === false ? "（DB未接続）" : ""}`;
    } else {
      dot.className = "dot bad";
      text.textContent = `異常 (${res.status})`;
    }
  } catch (e) {
    dot.className = "dot bad";
    text.textContent = "接続できません";
  }
}

// ---------------------------------------------------------------------------
// 2. 傍受トグル
// ---------------------------------------------------------------------------
function renderToggle(btn, on) {
  btn.textContent = on ? "ON" : "OFF";
  btn.className = on ? "on" : "off";
}

async function initCaptureToggle() {
  const btn = $("capture-toggle");
  const { captureEnabled } = await localGet({ captureEnabled: true });
  let on = captureEnabled !== false;
  renderToggle(btn, on);
  btn.addEventListener("click", () => {
    on = !on;
    renderToggle(btn, on);
    chrome.storage.local.set({ captureEnabled: on });
  });
}

// ---------------------------------------------------------------------------
// 3. 最終取得ハンドのサマリー
// ---------------------------------------------------------------------------
function fmtCards(cards) {
  return Array.isArray(cards) && cards.length ? cards.join(" ") : "??";
}

async function renderLastHand() {
  const el = $("last-hand");
  const { lastHand } = await localGet({ lastHand: null });
  if (!lastHand) {
    el.className = "hand muted";
    el.textContent = "まだありません";
    return;
  }
  // 傍受データ（T4サイト由来・非信頼）をDOMに入れるため textContent のみ使う
  el.className = "hand";
  el.textContent = "";
  const num = lastHand.hand_number != null ? `#${lastHand.hand_number}` : "";
  const pos = lastHand.hero_position || "?";
  const line1 = document.createElement("div");
  line1.textContent = `${num} ${pos} — ${fmtCards(lastHand.hero_cards)}`;
  const line2 = document.createElement("div");
  const res = lastHand.hero_result_bb;
  const resSpan = document.createElement("span");
  if (typeof res === "number") {
    resSpan.style.color = res >= 0 ? "var(--green)" : "var(--red)";
    resSpan.textContent = `${res >= 0 ? "+" : ""}${res}bb`;
  } else {
    resSpan.className = "muted";
    resSpan.textContent = "結果未確定";
  }
  line2.appendChild(resSpan);
  el.append(line1, line2);
}

// ---------------------------------------------------------------------------
// 4. 自動解析トグル
// ---------------------------------------------------------------------------
async function initAutoToggle() {
  const btn = $("auto-toggle");
  const { autoAnalyze } = await syncGet({ autoAnalyze: DEFAULTS.autoAnalyze });
  let on = autoAnalyze === true;
  renderToggle(btn, on);
  btn.addEventListener("click", () => {
    on = !on;
    renderToggle(btn, on);
    chrome.storage.sync.set({ autoAnalyze: on });
  });
}

// ---------------------------------------------------------------------------
// endpoint 入力
// ---------------------------------------------------------------------------
async function initEndpoint() {
  const input = $("endpoint");
  const { endpoint } = await syncGet({ endpoint: DEFAULTS.endpoint });
  input.value = endpoint;
  input.addEventListener("change", () => {
    const v = input.value.trim() || DEFAULTS.endpoint;
    chrome.storage.sync.set({ endpoint: v }, checkHealth);
  });
}

// ---------------------------------------------------------------------------
// 起動
// ---------------------------------------------------------------------------
(async function init() {
  await Promise.all([
    initEndpoint(),
    initCaptureToggle(),
    initAutoToggle(),
    renderLastHand(),
  ]);
  checkHealth();
  // ハンド更新をリアルタイム反映
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.lastHand) renderLastHand();
  });
})();
