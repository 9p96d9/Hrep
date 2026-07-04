"""AI解析プロンプト生成・プロバイダー判定（specs/ai_analysis.md §2・§3・§6・§7）。

純粋関数のみ。AI SDKをimportせず、API呼び出しは行わない（tests/PLAN.md）。
実際の呼び出し層は別モジュール（Cloud Run側）でこの出力を使う。
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# §2 プロバイダー判定

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"


def detect_provider(byok_key: str | None = None, env: dict | None = None) -> tuple[str, str, str] | None:
    """(provider, model, api_key) を返す。決定不能なら None。

    優先順位: 環境変数 GROQ_API_KEY → GEMINI_API_KEY → BYOKキーの形式判定
    （gsk_... = Groq / その他 = Gemini）。
    """
    env = env or {}
    if env.get("GROQ_API_KEY"):
        return ("groq", GROQ_MODEL, env["GROQ_API_KEY"])
    if env.get("GEMINI_API_KEY"):
        return ("gemini", GEMINI_MODEL, env["GEMINI_API_KEY"])
    if byok_key:
        if byok_key.startswith("gsk_"):
            return ("groq", GROQ_MODEL, byok_key)
        return ("gemini", GEMINI_MODEL, byok_key)
    return None


# ---------------------------------------------------------------------------
# §3 detail_street バッチプロンプト

DETAIL_STREET_SYSTEM_PROMPT = """あなたはGTOベースのポーカーコーチです。複数ハンドをストリート別に解析し、JSON配列のみを返してください。

## 出力形式（各ハンド必須フィールド）
[
  {
    "id": 1,
    "preflop_context": "Hero位置・RFI/3bet/Defend・レンジ概要（1〜2文）",
    "flop_read": "Flop board + Heroレンジ保持度 + 相手レンジ変化（1〜2文）",
    "turn_read": "Turn card + レンジ変化（1〜2文）。到達していない場合は空文字\\"\\"",
    "river_analysis": "River decision + [GTO数学]のMDF引用（1〜3文）。到達していない場合は空文字\\"\\"",
    "opp_exploit": "相手のGTOからの逸脱と搾取戦略（bet/raise/fold等のアクション名で具体的に）",
    "kaizen": "代替ライン or 「このラインで十分」"
  }
]

## ストリート分割ルール（厳守）
フィールドはストリートごとに分かれています。
各フィールドは該当ストリートの話のみ書いてください。
turn_read / river_analysis は、ハンドがそのストリートに到達していない場合は空文字を返してください。
MDF は river_analysis フィールドのみで言及してください。他のフィールドでは一切触れないこと。

## 品質ルール（全フィールド共通・厳守）
- 主語は必ずポジション名にする（CO, BB, BTN 等）。「ヒーロー」「相手」を主語にしない
- [GTO数学]ブロックに記載の数値のみ引用可。自前で計算・推定した数値は一切使用禁止。数値が不明な場合は言及しない
- 具体的なレンジ記法を使う（例: ATo+, KQs, 22-44, TT-JJ）。「強いハンド」等の曖昧表現を避ける
- 個別ハンドの勝敗ではなく「このスポットでHeroのレンジは均衡しているか」を軸にする。「良い/悪い/ミス」という結果論的評価を出さない
- OOPはMDF目安より多めのフォールドが均衡に近い場合がある（定義は変わらない）
"""

_STREET_ORDER = ("flop", "turn", "river")


def street_reached(hand: dict) -> str:
    """ハンドが到達した最深ストリート（board が配られたか）を返す。"""
    reached = "preflop"
    streets = hand.get("streets") or {}
    for name in _STREET_ORDER:
        street = streets.get(name) or {}
        if isinstance(street, dict) and street.get("board"):
            reached = name
    return reached


def _serialize_actions(actions: list[dict]) -> str:
    parts = []
    for a in actions:
        amount = a.get("amount_bb")
        suffix = f" {amount:g}bb" if amount is not None else ""
        parts.append(f"{a.get('position')} {a.get('action')}{suffix}")
    return ", ".join(parts) if parts else "(アクションなし)"


def serialize_hand_context(hand_id: int, hand: dict) -> str:
    """1ハンド分のプロンプトコンテキストを生成する。[GTO数学]はそのまま引用する（§7）。"""
    streets = hand.get("streets") or {}
    reached = street_reached(hand)
    lines = [
        f"### ハンド {hand_id}",
        f"Hero: {hand.get('hero_position')} {' '.join(hand.get('hero_cards') or []) or '(ハンド非公開)'}",
        f"分類: {(hand.get('bluered_classification') or {}).get('category_label', '未分類')}",
        f"到達ストリート: {reached}",
    ]
    preflop = streets.get("preflop") or []
    lines.append(f"preflop: {_serialize_actions(preflop)}")
    for name in _STREET_ORDER:
        street = streets.get(name) or {}
        if not (isinstance(street, dict) and street.get("board")):
            continue
        board = " ".join(street.get("board") or [])
        pot = street.get("pot_bb")
        pot_txt = f" pot={pot:g}bb" if pot is not None else ""
        lines.append(f"{name}: [{board}]{pot_txt} | {_serialize_actions(street.get('actions') or [])}")
    if hand.get("gto_math"):
        lines.append(hand["gto_math"])
    if reached != "river":
        lines.append(f"※ このハンドは {reached} で終了。turn_read/river_analysis の未到達分は空文字。")
    return "\n".join(lines)


def build_detail_street_prompt(hands: list[dict]) -> tuple[str, str]:
    """(system_prompt, user_prompt) を返す。hands は annotate_hand 適用済みを想定。"""
    contexts = [serialize_hand_context(i + 1, h) for i, h in enumerate(hands)]
    user = (
        f"以下の{len(hands)}ハンドを解析し、id 1〜{len(hands)} のJSON配列のみを返してください。\n\n"
        + "\n\n".join(contexts)
    )
    return DETAIL_STREET_SYSTEM_PROMPT, user


def parse_detail_street_response(text: str) -> list[dict]:
    """AI応答からJSON配列を取り出す。コードフェンス・前後の説明文を許容する。"""
    cleaned = text.strip()
    if "```" in cleaned:
        # 最初のフェンス内を取る（```json ... ```）
        inner = cleaned.split("```", 2)[1]
        cleaned = inner.split("\n", 1)[1] if inner.startswith(("json", "JSON")) else inner
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON配列が見つからない")
    return json.loads(cleaned[start : end + 1])
