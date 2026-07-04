"""specs/gto_math.md 受入基準（§5）/ tests/PLAN.md 対応テスト"""

import pytest

from scripts.hand_converter import (
    compute_difficulty,
    compute_gto_math,
    compute_nice_play_score,
    select_nice_plays,
)


# ---------------------------------------------------------------------------
# 難易度スコア = カテゴリ基礎スコア × ストリートウェイト ± α微補正
# ---------------------------------------------------------------------------

def test_difficulty_bluff_catch_river():
    assert compute_difficulty("bluff_catch", "river") >= 0.9


def test_difficulty_bluff_catch_turn():
    assert compute_difficulty("bluff_catch", "turn") == pytest.approx(0.72)


def test_difficulty_nice_fold_flop():
    assert compute_difficulty("nice_fold", "flop") == pytest.approx(0.51)


def test_difficulty_bluff_catch_preflop():
    assert compute_difficulty("bluff_catch", "preflop") == pytest.approx(0.36)


def test_difficulty_value_success():
    assert compute_difficulty("value_success", "river") == pytest.approx(0.50)


def test_alpha_adjustment_at_indifference():
    # α=0.5（完全インディファレンス）→ +0.05 補正
    base = compute_difficulty("bluff_catch", "river")
    adjusted = compute_difficulty("bluff_catch", "river", "[GTO数学] | α=50%")
    assert adjusted == pytest.approx(base + 0.05)
    assert adjusted == pytest.approx(0.95)


def test_max_score_cap():
    assert compute_difficulty("bluff_catch", "river", "[GTO数学] | α=50%") <= 1.0


# ---------------------------------------------------------------------------
# ナイスプレイスコア（V1: bluff_catch / nice_call / nice_fold のみ）
# ---------------------------------------------------------------------------

def test_nice_play_score_bluff_catch_river():
    d = compute_difficulty("bluff_catch", "river")
    assert compute_nice_play_score("bluff_catch", d) >= 0.5


def test_nice_play_score_nice_call_river():
    # 損益マイナスでも表示対象（結果と判断の分離）
    d = compute_difficulty("nice_call", "river")
    assert compute_nice_play_score("nice_call", d, "correct") >= 0.5


def test_nice_play_score_lucky_bluff_catch():
    # GTO判定=不正解の幸運コールは除外（誤称賛防止）
    d = compute_difficulty("bluff_catch", "river")
    assert compute_nice_play_score("bluff_catch", d, "incorrect") == 0.0


def test_nice_play_score_bluff_catch_pf():
    d = compute_difficulty("bluff_catch", "preflop")
    assert compute_nice_play_score("bluff_catch", d) < 0.5  # 閾値未満で非表示


def test_nice_play_score_value_success():
    d = compute_difficulty("value_success", "river")
    assert compute_nice_play_score("value_success", d) == 0.0


def test_nice_play_score_hero_aggression():
    d = compute_difficulty("hero_aggression_won", "river")
    assert compute_nice_play_score("hero_aggression_won", d) == 0.0


def _np_hand(hnum, category, score):
    return {
        "hand_number": hnum,
        "nice_play_score": score,
        "bluered_classification": {"category": category},
    }


def test_top3_selection():
    hands = [_np_hand(i, "bluff_catch", 0.6 + i * 0.05) for i in range(5)]
    selected = select_nice_plays(hands)
    assert len(selected) == 3
    assert [h["hand_number"] for h in selected] == [4, 3, 2]  # スコア降順


def test_zero_candidates_returns_empty_list():
    # UIは0件を正直に表示する。セクション非表示にしない（REQUIREMENTS.md Must）
    assert select_nice_plays([]) == []
    assert select_nice_plays([_np_hand(1, "value_success", 0.9)]) == []
    assert select_nice_plays([_np_hand(1, "bluff_catch", 0.36)]) == []  # 閾値未満


# ---------------------------------------------------------------------------
# [GTO数学]ブロック出力形式（specs/gto_math.md §2）
# ---------------------------------------------------------------------------

def _river_facing_bet_hand(hero_action):
    return {
        "hero_position": "BB",
        "streets": {
            "river": {
                "board": ["7s"],
                "pot_bb": 28.0,
                "actions": [
                    {"position": "BTN", "action": "bet", "amount_bb": 20.0},
                    {"position": "BB", "action": hero_action},
                ],
            }
        },
    }


def test_gto_math_defender_cat():
    text = compute_gto_math(_river_facing_bet_hand("call"), "bluff_catch")
    assert "必要エクイティ=" in text
    assert "%" in text


def test_gto_math_aggressor_cat():
    hand = {
        "hero_position": "CO",
        "streets": {
            "turn": {
                "board": ["Kh"],
                "pot_bb": 24.0,
                "actions": [
                    {"position": "CO", "action": "bet", "amount_bb": 12.0},
                    {"position": "BTN", "action": "call"},
                ],
            }
        },
    }
    text = compute_gto_math(hand, "value_success")
    assert "α=33%" in text
    assert "MDF" not in text  # リバー以外でMDFに触れない


def test_gto_math_fold_river():
    text = compute_gto_math(_river_facing_bet_hand("fold"), "nice_fold")
    assert "MDF基準=" in text


def _flop_fold_hand(street="flop"):
    return {
        "hero_position": "BB",
        "streets": {
            street: {
                "board": ["9h", "5d", "2c"] if street == "flop" else ["Kh"],
                "pot_bb": 6.0,
                "actions": [
                    {"position": "BTN", "action": "bet", "amount_bb": 4.0},
                    {"position": "BB", "action": "fold"},
                ],
            }
        },
    }


def test_gto_math_fold_flop():
    text = compute_gto_math(_flop_fold_hand("flop"), "fold_unknown")
    assert "MDF" not in text
    assert "α=" in text


def test_gto_math_fold_turn():
    text = compute_gto_math(_flop_fold_hand("turn"), "fold_unknown")
    assert "MDF" not in text
