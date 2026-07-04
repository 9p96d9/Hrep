"""AI出力（detail_street）バリデーター（specs/ai_analysis.md §3・§6・§8）。

純粋関数。AI SDKをimportしない（tests/PLAN.md）。
テストだけでなく本番のAI出力受入ゲートとしても使用する。
"""
from __future__ import annotations

# §3 出力フィールド定義（id を除く6テキストフィールド）
REQUIRED_FIELDS = (
    "preflop_context",
    "flop_read",
    "turn_read",
    "river_analysis",
    "opp_exploit",
    "kaizen",
)

# §3 フィールド別MDFルール: river_analysis 以外は言及禁止
MDF_FORBIDDEN_FIELDS = (
    "preflop_context",
    "flop_read",
    "turn_read",
    "opp_exploit",
    "kaizen",
)

# §6 主語ルール: 主語はポジション名。「ヒーロー」を主語にしない
POSITION_TOKENS = ("UTG", "EP", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB")
FORBIDDEN_SUBJECTS = ("ヒーロー",)

# §8 opp_exploit はアクション名を含む具体的な搾取戦略
ACTION_WORDS = (
    "bet", "raise", "fold", "call", "check",
    "ベット", "レイズ", "フォールド", "コール", "チェック",
)


def validate_detail_street(
    entry: dict,
    *,
    reached_turn: bool,
    reached_river: bool,
) -> list[str]:
    """detail_street 1ハンド分の出力を検証し、違反メッセージのリストを返す。

    空リスト = 合格。reached_turn / reached_river はハンドデータ側の事実
    （street_reached）から与える。AI出力自身に到達判定させない。
    """
    violations: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if f not in entry]
    if missing:
        violations.append(f"必須フィールド欠落: {', '.join(missing)}")
        return violations  # フィールドが無いと以降の検査が無意味

    # MDFルール（riverのみ言及可）
    for field in MDF_FORBIDDEN_FIELDS:
        if "MDF" in str(entry[field]):
            violations.append(f"{field} にMDF言及がある（riverのみ許可）")

    # 未到達ストリートは空文字
    if not reached_turn and entry["turn_read"] != "":
        violations.append("turn未到達なのに turn_read が非空")
    if not reached_river and entry["river_analysis"] != "":
        violations.append("river未到達なのに river_analysis が非空")

    # river到達ハンドは river_analysis 必須 + [GTO数学]数値の引用
    if reached_river:
        river = str(entry["river_analysis"])
        if not river:
            violations.append("river到達なのに river_analysis が空")
        elif "MDF" not in river and "必要エクイティ" not in river:
            violations.append("river_analysis に MDF / 必要エクイティ の引用がない")

    # 主語ルール
    text_fields = [str(entry[f]) for f in REQUIRED_FIELDS if str(entry[f])]
    all_text = " ".join(text_fields)
    for word in FORBIDDEN_SUBJECTS:
        if word in all_text:
            violations.append(f"主語ルール違反: 「{word}」でなくポジション名を使う")
            break
    if all_text and not any(pos in all_text for pos in POSITION_TOKENS):
        violations.append("ポジション名（CO/BB/BTN等）が一度も登場しない")

    # opp_exploit の具体性
    opp = str(entry["opp_exploit"])
    if opp and not any(w in opp for w in ACTION_WORDS):
        violations.append("opp_exploit にアクション名（bet/raise/fold等）がない")

    return violations
