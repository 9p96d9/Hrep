"""ハンドJSON→分類・スコア変換パイプライン（specs/hand_converter.md）。

docs/data_schema.md のハンドJSONから判断スポットの事実を抽出し、
classify → equity → gto_math を正しい順序で束ねる。
このモジュール自体は判断ロジックを持たない（すべて各SPECのモジュールに委譲）。
"""
from __future__ import annotations

from scripts import equity
from scripts.classify import VERDICT_UNKNOWN, classify_hand
from scripts.gto_math import (
    compute_difficulty,
    compute_gto_math,
    compute_nice_play_score,
    extract_alpha,
    required_equity,
)

AGGRESSIVE_ACTIONS = frozenset({"bet", "raise", "allin"})
POSTFLOP_STREETS = ("flop", "turn", "river")


def _street_actions(streets: dict, name: str) -> list[dict]:
    street = streets.get(name) or {}
    if isinstance(street, list):  # preflop はアクションのリスト
        return street
    return street.get("actions") or []


def _full_board(streets: dict) -> list[str]:
    board: list[str] = []
    for name in POSTFLOP_STREETS:
        street = streets.get(name) or {}
        if isinstance(street, dict):
            board.extend(street.get("board") or [])
    return board


def _find_aggression_street(streets: dict) -> tuple[str, int] | None:
    """river → turn → flop の順で最初に bet/raise があるストリートと、
    その最後のアグレッシブアクションのindexを返す。無ければ None（= preflop_only）。"""
    for name in reversed(POSTFLOP_STREETS):
        actions = _street_actions(streets, name)
        agg_indices = [
            i for i, a in enumerate(actions)
            if a.get("action") in AGGRESSIVE_ACTIONS
        ]
        if agg_indices:
            return name, agg_indices[-1]
    return None


def _is_showdown(streets: dict) -> bool:
    """アクションが存在する最深ストリートの最後のアクションが fold でない。"""
    for name in reversed(POSTFLOP_STREETS):
        actions = _street_actions(streets, name)
        if actions:
            return actions[-1].get("action") != "fold"
    return False


def annotate_hand(hand: dict) -> dict:
    """分類・[GTO数学]・難易度・ナイスプレイスコアを計算して返す。入力は変更しない。

    OUTPUT: {"bluered_classification", "gto_math", "difficulty_score", "nice_play_score"}
    """
    hero_position = hand.get("hero_position")
    streets = hand.get("streets") or {}
    aggression = _find_aggression_street(streets)

    # ポストフロップに判断スポット（bet/raise）が無い → preflop_only
    # （プリフロップ解決だけでなくチェックダウンも含む — specs/hand_converter.md §3）
    if aggression is None:
        classification = classify_hand(preflop_only=True)
        difficulty = compute_difficulty("preflop_only", "preflop")
        return {
            "bluered_classification": classification.as_dict(),
            "gto_math": "",
            "difficulty_score": difficulty,
            "nice_play_score": 0.0,
        }

    street_name, agg_index = aggression
    actions = _street_actions(streets, street_name)
    agg_action = actions[agg_index]
    hero_last_aggressor = agg_action.get("position") == hero_position

    showdown = _is_showdown(streets)
    hero_won = (hand.get("hero_result_bb") or 0) > 0  # チョップは非勝利側に倒す

    # ポット = ストリート開始時 pot_bb + 最終アグレッションより前の同ストリート投入額
    street_data = streets.get(street_name) or {}
    pot_bb = (street_data.get("pot_bb") or 0.0) + sum(
        a.get("amount_bb") or 0.0 for a in actions[:agg_index]
    )
    bet_bb = agg_action.get("amount_bb") or 0.0

    # GTOスコア判定は攻撃ストリートが river のときのみ（未来のカードで裁かない）
    call_verdict = VERDICT_UNKNOWN
    if not hero_last_aggressor and street_name == "river" and pot_bb > 0:
        req = required_equity(bet_bb, pot_bb)
        call_verdict = equity.judge_call(
            hand.get("hero_cards") or [], _full_board(streets), req
        )

    classification = classify_hand(
        showdown=showdown,
        hero_won=hero_won,
        hero_last_aggressor=hero_last_aggressor,
        call_verdict=call_verdict,
    )

    gto_math_text = compute_gto_math(
        classification.category, street_name, pot_bb=pot_bb, bet_bb=bet_bb
    )
    difficulty = compute_difficulty(
        classification.category, street_name, alpha_value=extract_alpha(gto_math_text)
    )
    nice_play = compute_nice_play_score(
        classification.category, difficulty, gto_verdict=call_verdict
    )

    return {
        "bluered_classification": classification.as_dict(),
        "gto_math": gto_math_text,
        "difficulty_score": difficulty,
        "nice_play_score": nice_play,
    }
