/* classify_result.js — 解析結果画面（docs/features/classify_result.md / cart.md）
 * 変更時は classify_result.html 側の ?v=YYYYMMDD（main.py STATIC_VERSION）を必ず更新する */
(function () {
  "use strict";

  var cart = new Set();
  var TOKENS_PER_HAND = 400; // detail_street バッチ（docs/features/cart.md）

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---- タブ ---- */
  function activateTab(tabId) {
    var btn = $('.tab-btn[data-tab="' + tabId + '"]');
    if (!btn) return;
    $all(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    $all(".tab-panel").forEach(function (p) { p.classList.add("hidden"); });
    $("#" + tabId).classList.remove("hidden");
    if (tabId === "tab-chips") renderChipChart();
  }
  $all(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () { activateTab(btn.dataset.tab); });
  });
  if (location.hash && $(location.hash + ".tab-panel")) {
    activateTab(location.hash.slice(1));
  }

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

  /* ---- チップ推移チャート（単一系列ライン・凡例なし・ホバー付き） ---- */
  var chipChartRendered = false;
  function renderChipChart() {
    if (chipChartRendered) return;
    var series = window.CHIP_SERIES || [];
    var host = $("#chip-chart");
    if (!host) return;
    if (series.length < 2) {
      host.innerHTML = '<div class="sub">チャート表示には2ハンド以上が必要です。</div>';
      chipChartRendered = true;
      return;
    }
    chipChartRendered = true;

    var W = 720, H = 260, PAD = { top: 12, right: 16, bottom: 26, left: 48 };
    var innerW = W - PAD.left - PAD.right, innerH = H - PAD.top - PAD.bottom;
    var LINE = "#3987e5"; // ダークサーフェス上で検証済み（lightness band / contrast PASS）
    var GRID = "#2a323d", TEXT = "#9aa4af";

    var vals = series.map(function (p) { return p.cum; });
    var yMin = Math.min(0, Math.min.apply(null, vals));
    var yMax = Math.max(0, Math.max.apply(null, vals));
    if (yMax === yMin) { yMax += 1; yMin -= 1; }
    var yPadding = (yMax - yMin) * 0.08;
    yMin -= yPadding; yMax += yPadding;

    function x(i) { return PAD.left + (i / (series.length - 1)) * innerW; }
    function y(v) { return PAD.top + (1 - (v - yMin) / (yMax - yMin)) * innerH; }

    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");

    function el(tag, attrs, text) {
      var node = document.createElementNS(ns, tag);
      Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
      if (text !== undefined) node.textContent = text;
      svg.appendChild(node);
      return node;
    }

    // 控えめなグリッド + yラベル（4本）
    for (var t = 0; t <= 3; t++) {
      var v = yMin + ((yMax - yMin) * t) / 3;
      el("line", { x1: PAD.left, x2: W - PAD.right, y1: y(v), y2: y(v),
                   stroke: GRID, "stroke-width": 1 });
      el("text", { x: PAD.left - 6, y: y(v) + 4, "text-anchor": "end",
                   fill: TEXT, "font-size": 11 }, v.toFixed(0) + "bb");
    }
    // ゼロ基準線（損益の正負の境界）
    if (yMin < 0 && yMax > 0) {
      el("line", { x1: PAD.left, x2: W - PAD.right, y1: y(0), y2: y(0),
                   stroke: TEXT, "stroke-width": 1, "stroke-dasharray": "4 3" });
    }
    // xラベル（先頭・中間・末尾のみ）
    [0, Math.floor((series.length - 1) / 2), series.length - 1].forEach(function (i) {
      el("text", { x: x(i), y: H - 8, "text-anchor": "middle",
                   fill: TEXT, "font-size": 11 }, "H" + series[i].hand_number);
    });
    // データライン（2px）
    var d = series.map(function (p, i) {
      return (i === 0 ? "M" : "L") + x(i).toFixed(1) + " " + y(p.cum).toFixed(1);
    }).join(" ");
    el("path", { d: d, fill: "none", stroke: LINE, "stroke-width": 2,
                 "stroke-linejoin": "round", "stroke-linecap": "round" });

    // ホバー: クロスヘア + マーカー + ツールチップ
    var crosshair = el("line", { x1: 0, x2: 0, y1: PAD.top, y2: H - PAD.bottom,
                                 stroke: TEXT, "stroke-width": 1, opacity: 0 });
    var marker = el("circle", { r: 4, fill: LINE, stroke: "#1a2028",
                                "stroke-width": 2, opacity: 0 });
    var tooltip = $("#chip-tooltip");
    svg.addEventListener("mousemove", function (e) {
      var rect = svg.getBoundingClientRect();
      var px = ((e.clientX - rect.left) / rect.width) * W;
      var i = Math.round(((px - PAD.left) / innerW) * (series.length - 1));
      i = Math.max(0, Math.min(series.length - 1, i));
      crosshair.setAttribute("x1", x(i)); crosshair.setAttribute("x2", x(i));
      crosshair.setAttribute("opacity", 0.4);
      marker.setAttribute("cx", x(i)); marker.setAttribute("cy", y(series[i].cum));
      marker.setAttribute("opacity", 1);
      tooltip.hidden = false;
      tooltip.textContent = "H" + series[i].hand_number + ": " +
        (series[i].cum > 0 ? "+" : "") + series[i].cum.toFixed(1) + "bb";
      tooltip.style.left = (e.clientX + 12) + "px";
      tooltip.style.top = (e.clientY - 28) + "px";
    });
    svg.addEventListener("mouseleave", function () {
      crosshair.setAttribute("opacity", 0);
      marker.setAttribute("opacity", 0);
      tooltip.hidden = true;
    });

    host.appendChild(svg);
  }

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
