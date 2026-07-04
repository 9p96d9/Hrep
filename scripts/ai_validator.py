"""ai_validator — AI出力（detail_street）の受入ゲート（純粋関数）

仕様: specs/ai_analysis.md §8 受入基準。
テスト専用にせず、本番でもAI出力の受入ゲートとして再利用する（tests/PLAN.md）。
"""

from __future__ import annotations

from scripts.ai_prompt import DETAIL_STREET_FIELDS

# MDF言及が禁止されるフィールド（riverのみ許可 — specs/ai_analysis.md §3）
MDF_FORBIDDEN_FIELDS = ["preflop_context", "flop_read", "turn_read", "opp_exploit", "kaizen"]

ACTION_WORDS = [
    "bet", "raise", "fold", "call", "check",
    "ベット", "レイズ", "フォールド", "コール", "チェック",
]


def validate_detail_street_item(item: dict, turn_reached: bool = True,
                                river_reached: bool = True) -> list:
    """1ハンド分の detail_street 出力を検証し、違反メッセージのリストを返す（空=合格）。"""
    errors = []

    for field in DETAIL_STREET_FIELDS:
        if field not in item:
            errors.append(f"フィールド欠落: {field}")
    if errors:
        return errors

    for field in MDF_FORBIDDEN_FIELDS:
        if "MDF" in (item.get(field) or ""):
            errors.append(f"MDF言及禁止フィールドにMDFが含まれる: {field}")

    river = item.get("river_analysis") or ""
    turn = item.get("turn_read") or ""
    if river_reached:
        if not river:
            errors.append("river到達ハンドなのに river_analysis が空")
        elif "MDF" not in river and "必要エクイティ" not in river:
            errors.append("river_analysis に MDF / 必要エクイティ の引用がない")
    else:
        if river:
            errors.append("river未到達なのに river_analysis が非空")
    if not turn_reached and turn:
        errors.append("turn未到達なのに turn_read が非空")

    for field in DETAIL_STREET_FIELDS:
        text = item.get(field) or ""
        if "ヒーロー" in text:
            errors.append(f"主語ルール違反（「ヒーロー」を使用）: {field}")

    opp = item.get("opp_exploit") or ""
    if opp and not any(w in opp for w in ACTION_WORDS):
        errors.append("opp_exploit にアクション名が含まれない")

    return errors


def validate_detail_street_batch(items: list, hands_flags: list) -> dict:
    """バッチ出力を検証する。

    Args:
        items: AI出力のJSON配列（各要素に id を含む）
        hands_flags: 各ハンドの {"id": int, "turn": bool, "river": bool} 到達フラグ

    Returns:
        {id: [違反メッセージ]} — 全ハンド合格なら {}
    """
    flags_by_id = {f["id"]: f for f in hands_flags}
    result = {}
    for item in items:
        item_id = item.get("id")
        flags = flags_by_id.get(item_id, {"turn": True, "river": True})
        errors = validate_detail_street_item(
            item, turn_reached=flags.get("turn", True), river_reached=flags.get("river", True)
        )
        if item_id is None:
            errors.append("id フィールドが欠落")
        if errors:
            result[item_id] = errors
    missing = set(flags_by_id) - {i.get("id") for i in items}
    for mid in sorted(missing, key=str):
        result[mid] = ["AI出力にこのハンドが含まれない"]
    return result
