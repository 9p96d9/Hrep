"""detail_street AI出力のバリデーター — specs/ai_analysis.md §8 準拠。

純粋関数。テストと本番のAI出力受入ゲートの両方から使う（AIクライアントSDKをimportしない）。
"""

REQUIRED_FIELDS = (
    "preflop_context",
    "flop_read",
    "turn_read",
    "river_analysis",
    "opp_exploit",
    "kaizen",
)

# specs/ai_analysis.md §3 フィールド別MDFルール（river_analysis のみ許可）
MDF_FORBIDDEN_FIELDS = (
    "preflop_context",
    "flop_read",
    "turn_read",
    "opp_exploit",
    "kaizen",
)

# 主語・ストリート叙述フィールド（ポジション名を含むべき対象）
NARRATIVE_FIELDS = ("preflop_context", "flop_read", "turn_read", "river_analysis")

POSITION_TOKENS = ("UTG", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB")

ACTION_TOKENS = (
    "bet", "raise", "fold", "call", "check",
    "cbet", "c-bet", "3bet", "4bet", "donk", "allin", "all-in",
)

STREET_ORDER = ("preflop", "flop", "turn", "river")


def validate_detail_street(output, street_reached):
    """1ハンド分の detail_street 出力を検証し、違反メッセージのリストを返す（空リスト=合格）。

    street_reached: そのハンドが到達した最深ストリート（"preflop"〜"river"）。
    """
    violations = []

    for field in REQUIRED_FIELDS:
        if field not in output:
            violations.append(f"{field}: フィールドが存在しない（未到達ストリートも空文字で必須）")

    reached = STREET_ORDER.index(street_reached) if street_reached in STREET_ORDER else 0

    for field in MDF_FORBIDDEN_FIELDS:
        if "MDF" in _text(output, field):
            violations.append(f"{field}: MDF言及は禁止（MDFは river_analysis のみ）")

    if reached < STREET_ORDER.index("turn") and _text(output, "turn_read"):
        violations.append("turn_read: ターン未到達ハンドでは空文字にする")
    if reached < STREET_ORDER.index("river") and _text(output, "river_analysis"):
        violations.append("river_analysis: リバー未到達ハンドでは空文字にする")

    if reached >= STREET_ORDER.index("river"):
        river = _text(output, "river_analysis")
        if not river:
            violations.append("river_analysis: リバー到達ハンドで空文字は不可")
        elif "MDF" not in river and "必要エクイティ" not in river:
            violations.append(
                "river_analysis: [GTO数学]の引用（\"MDF\" または \"必要エクイティ\"）を含むこと"
            )

    for field in REQUIRED_FIELDS:
        if "ヒーロー" in _text(output, field):
            violations.append(f"{field}: 主語は「ヒーロー」でなくポジション名（CO, BB, BTN 等）にする")

    for field in NARRATIVE_FIELDS:
        text = _text(output, field)
        if text and not any(pos in text for pos in POSITION_TOKENS):
            violations.append(f"{field}: ポジション名（CO, BB, BTN 等）を主語とする文を含むこと")

    opp_exploit = _text(output, "opp_exploit")
    if opp_exploit and not any(action in opp_exploit.lower() for action in ACTION_TOKENS):
        violations.append("opp_exploit: 具体的なアクション名（bet/raise/fold 等）で搾取戦略を書くこと")

    return violations


def _text(output, field):
    return output.get(field) or ""
