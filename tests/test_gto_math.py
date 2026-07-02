"""tests/test_gto_math.py — GTO数学・スコア計算のテスト。

仕様参照: specs/gto_math.md §5 受入基準
テストケース一覧: tests/PLAN.md
"""

import pytest

from scripts.classify import GTO_CORRECT, GTO_INCORRECT
from scripts.gto_math import (
    _compute_difficulty,
    _compute_gto_math,
    _compute_nice_play_score,
    _select_nice_plays,
)


def _hand(category, street=None, actions=None, pot_bb=None, gto_math=None):
    """指定ストリートで解決するハンドの最小形。"""
    boards = {"flop": ["9h", "5d", "2c"], "turn": ["Kh"], "river": ["7s"]}
    hand = {
        "hero_position": "BB",
        "hero_cards": ["Ah", "Kd"],
        "bluered_classification": {"category": category},
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": "BB", "action": "call"},
            ],
        },
    }
    if street:
        hand["streets"][street] = {
            "board": boards[street],
            "pot_bb": pot_bb,
            "actions": actions,
        }
    if gto_math is not None:
        hand["gto_math"] = gto_math
    return hand


def _facing_bet_actions(hero_response, bet_bb=20.0):
    return [
        {"position": "BB", "action": "check"},
        {"position": "BTN", "action": "bet", "amount_bb": bet_bb},
        {"position": "BB", "action": hero_response},
    ]


def _hero_bet_actions(bet_bb=12.0):
    return [
        {"position": "BB", "action": "bet", "amount_bb": bet_bb},
        {"position": "BTN", "action": "call"},
    ]


# ---- 難易度スコア（specs/gto_math.md §3） ----


def test_difficulty_bluff_catch_river():
    hand = _hand(
        "bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0,
        gto_math="[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=45%（α=45%）",
    )
    assert _compute_difficulty(hand) >= 0.9


def test_difficulty_bluff_catch_turn():
    hand = _hand("bluff_catch", "turn", _facing_bet_actions("call"), pot_bb=14.0)
    assert _compute_difficulty(hand) == pytest.approx(0.72)


def test_difficulty_nice_fold_flop():
    hand = _hand("nice_fold", "flop", _facing_bet_actions("fold", bet_bb=4.0), pot_bb=6.0)
    assert _compute_difficulty(hand) == pytest.approx(0.51)


def test_difficulty_bluff_catch_preflop():
    hand = _hand("bluff_catch")
    assert _compute_difficulty(hand) == pytest.approx(0.36)


def test_difficulty_value_success():
    hand = _hand("value_success", "river", _hero_bet_actions(), pot_bb=24.0)
    assert _compute_difficulty(hand) == pytest.approx(0.50)


# ---- ナイスプレイスコアV1（specs/gto_math.md §4） ----


def test_nice_play_score_bluff_catch_river():
    hand = _hand("bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0)
    assert _compute_nice_play_score(hand, gto_verdict=GTO_CORRECT) >= 0.5


def test_nice_play_score_nice_call_river():
    # 損益マイナス（コール敗北）でも表示対象 — 結果と判断の分離
    hand = _hand("nice_call", "river", _facing_bet_actions("call"), pot_bb=28.0)
    hand["hero_result_bb"] = -22.5
    assert _compute_nice_play_score(hand) >= 0.5


def test_nice_play_score_lucky_bluff_catch():
    # ショーダウン勝利でもGTO判定=不正解の幸運コールは除外（誤称賛防止）
    hand = _hand("bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0)
    assert _compute_nice_play_score(hand, gto_verdict=GTO_INCORRECT) == 0.0


def test_nice_play_score_bluff_catch_pf():
    hand = _hand("bluff_catch")
    assert _compute_nice_play_score(hand, gto_verdict=GTO_CORRECT) == 0.0


def test_nice_play_score_value_success():
    hand = _hand("value_success", "river", _hero_bet_actions(), pot_bb=24.0)
    assert _compute_nice_play_score(hand) == 0.0


def test_nice_play_score_hero_aggression():
    hand = _hand(
        "hero_aggression_won", "river",
        [
            {"position": "BB", "action": "bet", "amount_bb": 12.0},
            {"position": "BTN", "action": "fold"},
        ],
        pot_bb=24.0,
    )
    assert _compute_nice_play_score(hand) == 0.0


def test_alpha_adjustment_at_indifference():
    # α=0.5（完全インディファレンス）→ +0.05 補正: 0.90 + 0.05 = 0.95
    hand = _hand(
        "bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0,
        gto_math="[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=50%（α=50%）",
    )
    assert _compute_difficulty(hand) == pytest.approx(0.95)


def test_max_score_cap():
    hand = _hand(
        "bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0,
        gto_math="[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=50%（α=50%）",
    )
    assert _compute_difficulty(hand) <= 1.0


def test_zero_candidates_returns_empty_list():
    # 空リストを返す（UIは0件表示。セクションを非表示にしない）
    hands = [
        _hand("value_success", "river", _hero_bet_actions(), pot_bb=24.0),
        _hand("bluff_failed", "river", _hero_bet_actions(), pot_bb=24.0),
    ]
    assert _select_nice_plays(hands) == []


# ---- _compute_gto_math の出力形式（specs/gto_math.md §2） ----


def test_gto_math_defender_cat():
    hand = _hand("bluff_catch", "river", _facing_bet_actions("call"), pot_bb=28.0)
    output = _compute_gto_math(hand)
    assert "必要エクイティ=42%" in output


def test_gto_math_aggressor_cat():
    hand = _hand("value_success", "turn", _hero_bet_actions(bet_bb=12.0), pot_bb=24.0)
    output = _compute_gto_math(hand)
    assert "α=33%" in output


def test_gto_math_fold_river():
    hand = _hand("nice_fold", "river", _facing_bet_actions("fold"), pot_bb=28.0)
    output = _compute_gto_math(hand)
    assert "MDF基準=58%" in output


def test_gto_math_fold_flop():
    hand = _hand("nice_fold", "flop", _facing_bet_actions("fold", bet_bb=4.0), pot_bb=6.0)
    assert "MDF" not in _compute_gto_math(hand)


def test_gto_math_fold_turn():
    hand = _hand("fold_unknown", "turn", _facing_bet_actions("fold"), pot_bb=14.0)
    assert "MDF" not in _compute_gto_math(hand)
