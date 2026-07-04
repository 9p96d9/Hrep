/* classify_result.js — 解析結果画面（docs/features/classify_result.md / cart.md）
 * 変更時は classify_result.html 側の ?v=YYYYMMDD（main.py STATIC_VERSION）を必ず更新する */
(function () {
  "use strict";

  var cart = new Set();
  var TOKENS_PER_HAND = 400; // detail_street バッチ（docs/features/cart.md）

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---- タブ ---- */
  $all(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      $all(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      $all(".tab-panel").forEach(function (p) { p.classList.add("hidden"); });
      $("#" + btn.dataset.tab).classList.remove("hidden");
    });
  });

  /* ---- フィルター（カテゴリグリッドとフィルターバーは排他） ---- */
  function applyFilter(fn) {
    $all(".hcard").forEach(function (card) {
      card.classList.toggle("hidden", !fn(card));
    });
  }

  $all(".filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      $all(".cat-cell").forEach(function (c) { c.classList.remove("cat-active-filter"); });
      $all(".filter-btn").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      var f = btn.dataset.filter;
      applyFilter(function (card) {
        if (f === "all") return true;
        if (f === "blue" || f === "red") return card.dataset.line === f; // gray/warnは対象外・意図的
        if (f === "ai") return card.dataset.ai === "1";
        if (f === "3bet") return card.dataset["3bet"] === "1";
        return true;
      });
    });
  });

  $all(".cat-cell").forEach(function (cell) {
    cell.addEventListener("click", function () {
      var wasActive = cell.classList.contains("cat-active-filter");
      $all(".cat-cell").forEach(function (c) { c.classList.remove("cat-active-filter"); });
      $all(".filter-btn").forEach(function (b) { b.classList.remove("active"); });
      if (wasActive) {
        $('.filter-btn[data-filter="all"]').classList.add("active");
        applyFilter(function () { return true; });
      } else {
        cell.classList.add("cat-active-filter");
        applyFilter(function (card) { return card.dataset.category === cell.dataset.category; });
      }
    });
  });

  /* ---- ソート（同じボタン再クリックでデフォルト順に戻す） ---- */
  var POSITION_ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];
  var defaultOrder = $all(".hcard");
  var activeSort = null;

  function renderOrder(cards) {
    var list = $("#hand-list");
    cards.forEach(function (c) { list.appendChild(c); });
  }

  $all(".sort-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      $all(".sort-btn").forEach(function (b) { b.classList.remove("active"); });
      if (activeSort === btn.dataset.sort) {
        activeSort = null;
        renderOrder(defaultOrder);
        return;
      }
      activeSort = btn.dataset.sort;
      btn.classList.add("active");
      var cards = defaultOrder.slice();
      if (activeSort === "pl-desc" || activeSort === "pl-asc") {
        cards.sort(function (a, b) {
          var d = parseFloat(a.dataset.plNum) - parseFloat(b.dataset.plNum);
          return activeSort === "pl-desc" ? -d : d;
        });
      } else if (activeSort === "position") {
        cards.sort(function (a, b) {
          return POSITION_ORDER.indexOf(a.dataset.position) - POSITION_ORDER.indexOf(b.dataset.position);
        });
      }
      renderOrder(cards);
    });
  });

  /* ---- セクションカード → ハンドカードへスクロールジャンプ ---- */
  $all(".np-card, .ic-card").forEach(function (card) {
    card.addEventListener("click", function () {
      var target = document.getElementById(card.dataset.target);
      if (target) target.scrollIntoView({ behavior: "smooth" });
    });
  });

  /* ---- AIパネル折りたたみ ---- */
  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("ai-toggle")) {
      e.target.closest(".ai-panel").classList.toggle("open");
    }
  });

  /* ---- カート ---- */
  function refreshCart() {
    $("#cart-badge").textContent = String(cart.size);
    $("#token-estimate").textContent = "概算: " + cart.size * TOKENS_PER_HAND + " tok";
    var items = $("#cart-items");
    items.innerHTML = "";
    cart.forEach(function (hnum) {
      var card = document.getElementById("hcard-" + hnum);
      var pl = card ? card.dataset.plNum : "?";
      var pos = card ? card.dataset.position : "?";
      var row = document.createElement("div");
      row.className = "cart-item";
      row.innerHTML = "<span>H" + hnum + " " + pos + " " + pl + "bb</span>";
      var del = document.createElement("button");
      del.textContent = "✕";
      del.addEventListener("click", function () { toggleCart(hnum, false); });
      row.appendChild(del);
      items.appendChild(row);
    });
    $all(".hcard").forEach(function (c) {
      c.classList.toggle("in-cart", cart.has(c.id.replace("hcard-", "")));
    });
    updateRunButton();
  }

  function toggleCart(hnum, force) {
    hnum = String(hnum);
    var add = force !== undefined ? force : !cart.has(hnum);
    if (add) cart.add(hnum); else cart.delete(hnum);
    refreshCart();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".cart-add");
    if (btn && !btn.disabled) toggleCart(btn.dataset.hnum);
  });

  $("#cart-open").addEventListener("click", function () { $("#cart-drawer").classList.add("open"); });
  $("#cart-close").addEventListener("click", function () { $("#cart-drawer").classList.remove("open"); });

  /* ---- APIキー（セッションストレージのみ・サーバーに保存しない） ---- */
  var keyInput = $("#api-key");
  keyInput.value = sessionStorage.getItem("hrep_api_key") || "";

  function updateRunButton() {
    var key = keyInput.value.trim();
    $("#provider-hint").textContent =
      !key ? "" : key.indexOf("gsk_") === 0 ? "Groq (llama-3.3-70b-versatile)" : "Gemini (gemini-2.5-flash)";
    $("#run-analysis").disabled = cart.size === 0 || !key;
  }
  keyInput.addEventListener("input", function () {
    sessionStorage.setItem("hrep_api_key", keyInput.value.trim());
    updateRunButton();
  });
  updateRunButton();

  /* ---- 解析実行（SSE: detail_street） ---- */
  function log(msg) {
    var el = $("#analysis-log");
    el.textContent = msg;
  }

  function renderAiPanel(hnum, item) {
    var panel = document.getElementById("hai-" + hnum);
    var card = document.getElementById("hcard-" + hnum);
    if (!panel) return;
    var fields = ["preflop_context", "flop_read", "turn_read", "river_analysis", "opp_exploit", "kaizen"];
    var body = fields.filter(function (f) { return item[f]; }).map(function (f) {
      var div = document.createElement("div");
      div.innerHTML = "<strong></strong>: ";
      div.querySelector("strong").textContent = f;
      div.appendChild(document.createTextNode(item[f]));
      return div.outerHTML;
    }).join("");
    panel.innerHTML = '<button class="ai-toggle">AI解析結果</button><div class="ai-body">' + body + "</div>";
    panel.classList.add("open");
    if (card) card.dataset.ai = "1";
  }

  $("#run-analysis").addEventListener("click", function () {
    var btn = $("#run-analysis");
    btn.disabled = true;
    log("解析を開始…");
    fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analysis_id: window.ANALYSIS_ID,
        hand_numbers: Array.from(cart).map(Number),
        api_key: keyInput.value.trim(),
        mode: "detail_street"
      })
    }).then(function (resp) {
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) { btn.disabled = false; return; }
          buffer += decoder.decode(r.value, { stream: true });
          var events = buffer.split("\n\n");
          buffer = events.pop();
          events.forEach(function (block) {
            var event = (block.match(/^event: (.+)$/m) || [])[1];
            var dataLine = (block.match(/^data: (.+)$/m) || [])[1];
            if (!event || !dataLine) return;
            var data = JSON.parse(dataLine);
            if (event === "progress") log(data.message + "（概算 " + data.estimated_tokens + " tok）");
            if (event === "result" && data.item) renderAiPanel(data.hand_number, data.item);
            if (event === "error") log("エラー: " + data.message);
            if (event === "done") log("完了: " + data.count + "ハンド解析済み");
          });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      log("通信エラー: " + err);
      btn.disabled = false;
    });
  });
})();
