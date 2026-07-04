// content.js — ISOLATED world
// -----------------------------------------------------------------------------
// interceptor.js (MAIN world) が投げる CustomEvent を受け取り、
// chrome.runtime.sendMessage で background.js へ転送するだけの薄い層。
//
// ここは chrome.* API が使える唯一のページ内文脈。ロジックは持たない。
// 傍受ON/OFFのゲートだけここで行う（interceptor は chrome.storage を読めないため）。
// -----------------------------------------------------------------------------

(() => {
  "use strict";

  const EVENT_HAND = "hrep:hand";

  let captureEnabled = true;

  // 初期値と以後の変更を chrome.storage.local から取得（popup のトグルと同期）
  chrome.storage.local.get({ captureEnabled: true }, (v) => {
    captureEnabled = v.captureEnabled !== false;
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.captureEnabled) {
      captureEnabled = changes.captureEnabled.newValue !== false;
    }
  });

  window.addEventListener(EVENT_HAND, (ev) => {
    if (!captureEnabled) return;
    const hand = ev && ev.detail && ev.detail.hand;
    if (!hand) return;
    try {
      chrome.runtime.sendMessage({ type: "hrep:hand", hand });
    } catch (e) {
      // Service Worker が寝ている等で失敗しても握りつぶす（次のメッセージで復帰）
      console.debug("[hrep] sendMessage failed", e);
    }
  });
})();
