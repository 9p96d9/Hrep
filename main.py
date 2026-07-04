"""HrepNext — Cloud Run用Flaskアプリ本体

構成: docs/infra.md（Cloud Run + Firestore + Firebase Auth）
純粋関数は scripts/（hand_converter / ai_prompt / ai_validator）からimportし、
このファイルはHTTP・認証・SSE・永続化の接続のみを担当する。
"""

from __future__ import annotations

import json
import os

from flask import Flask, Response, jsonify, redirect, render_template, request
from markupsafe import Markup, escape

from scripts import ai_prompt
from scripts.ai_validator import validate_detail_street_batch
from scripts.hand_converter import (
    STREET_LABELS_JA,
    annotate_hand,
    decision_street,
    select_improve_chances,
    select_nice_plays,
)
from services import ai_providers, firestore_store as store

app = Flask(__name__)

# /static/classify_result.js?v=YYYYMMDD — 変更時に必ず更新する（docs/features/classify_result.md）
# 同日内の再変更はサフィックスで区別する（-2, -3, …）
STATIC_VERSION = "20260704-2"

SUIT_META = {"s": ("♠", "#ccc"), "c": ("♣", "#4caf93"), "h": ("♥", "#e94560"), "d": ("♦", "#5b9bd5")}


# ---------------------------------------------------------------------------
# テンプレートフィルター
# ---------------------------------------------------------------------------

@app.template_filter("card_span")
def card_span(card: str) -> Markup:
    """"Ah" → スートカラーリング付きspan（docs/features/classify_result.md）。"""
    if not card or len(card) < 2:
        return Markup("<span>?</span>")
    rank, suit = card[:-1], card[-1].lower()
    symbol, color = SUIT_META.get(suit, ("?", "#ccc"))
    return Markup(f'<span class="card" style="color:{color}">{escape(rank)}{symbol}</span>')


@app.template_filter("score_dots")
def score_dots(score: float) -> str:
    """難易度スコア → ●●●●○（5段階、docs/features/nice_plays.md）。"""
    filled = max(0, min(5, round((score or 0.0) * 5)))
    return "●" * filled + "○" * (5 - filled)


@app.template_filter("pl_fmt")
def pl_fmt(value) -> str:
    return f"{value:+.1f}bb" if isinstance(value, (int, float)) else "—"


@app.template_global("street_ja")
def street_ja(hand: dict) -> str:
    return STREET_LABELS_JA[decision_street(hand)]


@app.template_global("opp_of")
def opp_of(hand: dict) -> dict:
    for p in hand.get("players") or []:
        if not p.get("is_hero"):
            return p
    return {}


# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------

def current_uid() -> str | None:
    """Authorization: Bearer <Firebase ID token> を検証してuidを返す。

    Firestore未設定のローカル開発では dev-local にフォールバックする。
    """
    header = request.headers.get("Authorization") or ""
    if header.startswith("Bearer "):
        uid = store.verify_uid(header.removeprefix("Bearer "))
        if uid:
            return uid
    if not store.available() or os.environ.get("DEV_ALLOW_UNAUTH") == "1":
        return "dev-local"
    return None


# ---------------------------------------------------------------------------
# ヘルスチェック・API
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "hrep", "firestore": store.available()})


@app.post("/api/hand-capture")
def api_hand_capture():
    """Chrome拡張からのハンド受信（docs/features/extension.md データフロー）。"""
    uid = current_uid()
    if uid is None:
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    raw_hands = payload.get("hands") or []
    if not raw_hands:
        return jsonify({"error": "hands が空です"}), 400

    hands = [annotate_hand(h) for h in raw_hands]
    if not store.available():
        return jsonify({"error": "firestore unavailable", "annotated": len(hands)}), 503
    analysis_id = store.save_analysis(
        uid, hands, meta=payload.get("meta"), bb_size=payload.get("bb_size")
    )
    return jsonify({"analysis_id": analysis_id, "hand_count": len(hands)})


@app.get("/api/analyses")
def api_analyses():
    uid = current_uid()
    if uid is None:
        return jsonify({"error": "unauthorized"}), 401
    if not store.available():
        return jsonify({"error": "firestore unavailable"}), 503
    return jsonify({"analyses": store.list_analyses(uid)})


@app.get("/api/analyses/<analysis_id>/hands")
def api_analysis_hands(analysis_id):
    uid = current_uid()
    if uid is None:
        return jsonify({"error": "unauthorized"}), 401
    if not store.available():
        return jsonify({"error": "firestore unavailable"}), 503
    return jsonify({"hands": store.get_hands(analysis_id)})


@app.post("/api/analyze")
def api_analyze():
    """AI解析（SSE）。カートから detail_street バッチ、または explain 1ハンド。

    body: {"analysis_id"?, "hands"?, "hand_numbers"?, "api_key"?, "mode"?}
    BYOKキーはこのリクエスト内でのみ使用し、保存しない（docs/features/cart.md）。
    """
    uid = current_uid()
    if uid is None:
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "detail_street")
    api_key = payload.get("api_key")
    analysis_id = payload.get("analysis_id")

    hands = payload.get("hands")
    if hands is None and analysis_id and store.available():
        wanted = set(payload.get("hand_numbers") or [])
        hands = [
            h.get("hand_json") or {}
            for h in store.get_hands(analysis_id)
            if not wanted or (h.get("hand_json") or {}).get("hand_number") in wanted
        ]
    hands = hands or []
    # preflop_only はカート追加不可（分析素材不足 — docs/features/cart.md）
    hands = [
        h for h in hands
        if (h.get("bluered_classification") or {}).get("category") != "preflop_only"
    ]

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream():
        if not hands:
            yield sse("error", {"message": "解析対象ハンドがありません"})
            return
        yield sse("progress", {
            "message": f"{len(hands)}ハンドを解析中",
            "estimated_tokens": ai_prompt.estimate_tokens(len(hands), mode),
        })
        try:
            if mode == "explain":
                prompt = ai_prompt.build_explain_prompt(hands[0])
                text = ai_providers.run_chat(prompt["system"], prompt["user"], api_key)
                yield sse("result", {"hand_number": hands[0].get("hand_number"),
                                     "mode": "explain", "text": text})
            else:
                prompt = ai_prompt.build_detail_street_prompt(hands)
                text = ai_providers.run_chat(prompt["system"], prompt["user"], api_key)
                items = ai_providers.parse_json_array(text)
                flags = [
                    {"id": i + 1, **ai_prompt.streets_reached_flags(h)}
                    for i, h in enumerate(hands)
                ]
                violations = validate_detail_street_batch(items, flags)
                by_id = {item.get("id"): item for item in items}
                for i, hand in enumerate(hands):
                    item = by_id.get(i + 1)
                    hnum = hand.get("hand_number")
                    if item is None:
                        yield sse("result", {"hand_number": hnum, "error": "AI出力なし"})
                        continue
                    if analysis_id and store.available():
                        store.save_ai_result(analysis_id, hnum, item, mode)
                    yield sse("result", {
                        "hand_number": hnum,
                        "mode": mode,
                        "item": item,
                        "violations": violations.get(i + 1, []),
                    })
        except ai_providers.AIProviderError as e:
            yield sse("error", {"message": str(e)})
            return
        yield sse("done", {"count": len(hands)})

    return Response(stream(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return redirect("/sessions")


@app.get("/sessions")
def sessions_page():
    uid = current_uid() or "dev-local"
    analyses = store.list_analyses(uid) if store.available() else []
    return render_template("sessions.html", analyses=analyses,
                           firestore_available=store.available())


@app.get("/result/<analysis_id>")
def result_page(analysis_id):
    if not store.available():
        return render_template("classify_result.html", analysis_id=analysis_id,
                               hands=[], summary=_summary([]), category_counts={},
                               nice_plays=[], improve_chances=[], ev_diffs=None,
                               position_stats=[], chip_series=[],
                               static_version=STATIC_VERSION)
    docs = store.get_hands(analysis_id)
    hands = [d.get("hand_json") or {} for d in docs]
    analysis = store.get_analysis(analysis_id) or {}
    ev_diffs = (analysis.get("meta") or {}).get("allin_ev_diffs")
    return render_template(
        "classify_result.html",
        analysis_id=analysis_id,
        hands=hands,
        summary=_summary(hands),
        category_counts=_category_counts(hands),
        nice_plays=select_nice_plays(hands),
        improve_chances=select_improve_chances(hands),
        ev_diffs=ev_diffs,
        position_stats=_position_stats(hands),
        chip_series=_chip_series(hands),
        static_version=STATIC_VERSION,
    )


def _summary(hands: list) -> dict:
    lines = [(h.get("bluered_classification") or {}).get("line") for h in hands]
    return {
        "total": len(hands),
        "blue": lines.count("blue"),
        "red": lines.count("red"),
        "preflop_only": lines.count("preflop_only"),
    }


POSITION_ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]


def _position_stats(hands: list) -> list:
    """タブ②ポジション別: ハンド数と損益合計（UTG→BB の配列順）。"""
    stats: dict = {}
    for h in hands:
        pos = h.get("hero_position") or "?"
        s = stats.setdefault(pos, {"position": pos, "count": 0, "pl": 0.0})
        s["count"] += 1
        s["pl"] += h.get("hero_result_bb") or 0.0
    ordered = [stats[p] for p in POSITION_ORDER if p in stats]
    ordered += [s for p, s in stats.items() if p not in POSITION_ORDER]
    for s in ordered:
        s["pl"] = round(s["pl"], 2)
    return ordered


def _chip_series(hands: list) -> list:
    """タブ③チップ推移: ハンド順の累積損益（bb）。"""
    cum = 0.0
    series = []
    for h in hands:
        cum += h.get("hero_result_bb") or 0.0
        series.append({"hand_number": h.get("hand_number"), "cum": round(cum, 2)})
    return series


def _category_counts(hands: list) -> dict:
    counts: dict = {}
    for h in hands:
        cls = h.get("bluered_classification") or {}
        key = cls.get("category")
        if not key:
            continue
        entry = counts.setdefault(key, {"label": cls.get("category_label", key), "count": 0})
        entry["count"] += 1
    return counts


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
