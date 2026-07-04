"""ai_prompt — AI解析プロンプト生成（純粋関数）

仕様: specs/ai_analysis.md（detail_street が正式版・品質ルール §6・[GTO数学] §7）
AI SDK・HTTPクライアントをimportしない。プロバイダー呼び出しは services/ai_providers.py。
"""

from __future__ import annotations

from scripts.hand_converter import STREET_LABELS_JA, street_reached

# トークン見積もり（docs/features/cart.md）
TOKENS_PER_HAND = {"detail_street": 400, "detail": 400, "explain": 1700}

# 品質ルール（specs/ai_analysis.md §6 — 全モード共通・厳守）
QUALITY_RULES = """\
## 品質ルール（厳守）
- 主語は必ずポジション名にする（CO, BB, BTN 等）。「ヒーロー」「相手」を主語にしない。
- [GTO数学] ブロックに記載の数値のみ引用可。自前で計算・推定した数値は一切使用禁止。数値が不明な場合は言及しない。
- MDF はリバーのみ言及する。フロップ/ターンでは MDF に触れず、エクイティ・ドロー・レンジ構成で論じる。
- レンジは具体的な記法で書く（例: ATo+, KQs, 22-44, TT-JJ）。「強いハンド」等の曖昧表現を避ける。
- 個別ハンドの勝敗ではなく「このスポットでHeroのレンジは均衡しているか」を軸にする。「良い/悪い/ミス」という結果論的評価を出さない。"""

DETAIL_STREET_FIELDS = [
    "preflop_context",
    "flop_read",
    "turn_read",
    "river_analysis",
    "opp_exploit",
    "kaizen",
]

DETAIL_STREET_SYSTEM_PROMPT = f"""\
あなたはGTOベースのポーカーコーチです。入力された各ハンドについて、以下のフィールドを持つJSONオブジェクトの配列のみを出力してください（コードフェンス・前置き・後置きは不要）。

{{
  "id": ハンド番号（入力のidと一致させる）,
  "preflop_context": "Hero位置・RFI/3bet/Defend・レンジ概要（1〜2文）",
  "flop_read": "Flop board + Heroレンジ保持度 + 相手レンジ変化（1〜2文）",
  "turn_read": "Turn card + レンジ変化（1〜2文）。到達していない場合は空文字\\"\\"",
  "river_analysis": "River decision + [GTO数学]のMDF引用（1〜3文）。到達していない場合は空文字\\"\\"",
  "opp_exploit": "相手のGTOからの逸脱と搾取戦略（アクション名で）",
  "kaizen": "代替ライン or 「このラインで十分」"
}}

フィールドはストリートごとに分かれています。
各フィールドは該当ストリートの話のみ書いてください。
turn_read / river_analysis は、ハンドがそのストリートに到達していない場合は空文字を返してください。
MDF は river_analysis フィールドのみで言及してください。他のフィールドでは一切触れないこと。

{QUALITY_RULES}"""

EXPLAIN_SYSTEM_PROMPT = f"""\
あなたはGTOベースのポーカーコーチです。入力された1ハンドについて、400〜1200文字のフリーテキスト（JSON不要）で解説してください。

必須セクション（段落で展開）:
1. 均衡レンジとHeroのポジション（OOP/IP）
2. GTO数学的観点（MDF/必要成功率/バリューターゲット）
3. 相手レンジの変化と読み
4. 相手への搾取戦略
5. 代替ライン

{QUALITY_RULES}"""


def _fmt_cards(cards) -> str:
    return " ".join(cards) if cards else "不明"


def _opponent_summary(hand: dict) -> str:
    parts = []
    for p in hand.get("players") or []:
        if p.get("is_hero"):
            continue
        cards = _fmt_cards(p.get("hole_cards"))
        parts.append(f"{p.get('position', '?')}（{cards}）")
    return " / ".join(parts) if parts else "不明"


def _fmt_action(a: dict) -> str:
    amount = a.get("amount_bb")
    if amount:
        return f"{a.get('position', '?')} {a.get('action', '?')} {amount:g}bb"
    return f"{a.get('position', '?')} {a.get('action', '?')}"


def format_hand_block(hand: dict, hand_id: int) -> str:
    """1ハンド分のプロンプトテキスト。[GTO数学]ブロック（§7）を必ず含める。"""
    lines = [
        f"### ハンド id={hand_id}",
        f"Hero: {hand.get('hero_position', '?')} {_fmt_cards(hand.get('hero_cards'))}"
        f" | 相手: {_opponent_summary(hand)}",
    ]
    cls = hand.get("bluered_classification") or {}
    if cls.get("category_label"):
        lines.append(f"分類: {cls['category_label']}")

    streets = hand.get("streets") or {}
    for street in ("preflop", "flop", "turn", "river"):
        s = streets.get(street)
        if s is None:
            continue
        label = STREET_LABELS_JA[street]
        if isinstance(s, list):
            actions = s
            header = f"{label}:"
        else:
            board = " ".join(s.get("board") or [])
            pot = s.get("pot_bb")
            pot_txt = f" pot={pot:g}bb" if pot else ""
            header = f"{label}: [{board}]{pot_txt}" if board else f"{label}:{pot_txt}"
            actions = s.get("actions") or []
        acts = " → ".join(_fmt_action(a) for a in actions) if actions else "(アクションなし)"
        lines.append(f"{header} {acts}")

    if hand.get("gto_math"):
        lines.append(hand["gto_math"])
    result = hand.get("hero_result_bb")
    if result is not None:
        lines.append(f"Hero損益: {result:+g}bb（参考値。評価軸には使わない）")
    return "\n".join(lines)


def build_detail_street_prompt(hands: list) -> dict:
    """detail_street モード（正式版）のバッチプロンプト。

    Returns: {"system": str, "user": str}
    """
    blocks = [format_hand_block(h, i + 1) for i, h in enumerate(hands)]
    user = (
        f"以下の{len(hands)}ハンドを解析し、JSON配列のみを出力してください。\n\n"
        + "\n\n".join(blocks)
    )
    return {"system": DETAIL_STREET_SYSTEM_PROMPT, "user": user}


def build_explain_prompt(hand: dict) -> dict:
    """explain モード（1ハンド詳細解説）のプロンプト。"""
    return {"system": EXPLAIN_SYSTEM_PROMPT, "user": format_hand_block(hand, 1)}


def estimate_tokens(hand_count: int, mode: str = "detail_street") -> int:
    """解析実行前の概算トークン数（docs/features/cart.md）。"""
    return hand_count * TOKENS_PER_HAND.get(mode, TOKENS_PER_HAND["detail_street"])


def streets_reached_flags(hand: dict) -> dict:
    """turn/river到達フラグ。AI出力バリデーションの空文字判定に使う。"""
    reached = street_reached(hand)
    order = ["preflop", "flop", "turn", "river"]
    idx = order.index(reached)
    return {"turn": idx >= order.index("turn"), "river": idx >= order.index("river")}
