"""specs/hand_converter.md §5 受入基準のテスト。

ハンドJSONは docs/data_schema.md 形式で構築する。エクイティ判定が絡むケースは
tests/test_equity.py と同じボード/ハンド（決定的な期待verdict）を使う。
"""
import copy

import pytest

from scripts.hand_converter import annotate_hand

# test_equity.py と同じキャリブレーション済みスポット
BOARD_FLOP = ["Ks", "Qd", "9c"]
BOARD_TURN = ["8s"]
BOARD_RIVER = ["2h"]


def _hand(river_actions, *, turn_actions=None, hero_cards=None, hero_result_bb=-20.0):
    """flop/turnチェックスルー・リバーに判断スポットがある基本形。"""
    return {
        "hand_number": 1,
        "hero_position": "BB",
        "hero_cards": hero_cards or ["Kd", "Jd"],
        "hero_result_bb": hero_result_bb,
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": "BB", "action": "call"},
            ],
            "flop": {"board": BOARD_FLOP, "pot_bb": 5.5, "actions": []},
            "turn": {"board": BOARD_TURN, "pot_bb": 5.5, "actions": turn_actions or []},
            "river": {"board": BOARD_RIVER, "pot_bb": 28.0, "actions": river_actions},
        },
    }


def test_river_call_lose_gto_correct_is_nice_call():
    # トップペア好キッカーで必要エクイティ42%のコール → correct（test_equity.py と同一スポット）
    hand = _hand([
        {"position": "BTN", "action": "bet", "amount_bb": 20.0},
        {"position": "BB", "action": "call", "amount_bb": 20.0},
    ])
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "nice_call"
    assert out["bluered_classification"]["line"] == "gray"
    assert "必要エクイティ=42%" in out["gto_math"]
    assert out["nice_play_score"] >= 0.5  # 損益マイナスのままナイスプレイに載る


def test_river_call_lose_undecidable_is_call_lost():
    # ミドルペア → 区間が跨ぐ → unknown（test_equity.py と同一スポット）
    hand = _hand(
        [
            {"position": "BTN", "action": "bet", "amount_bb": 20.0},
            {"position": "BB", "action": "call", "amount_bb": 20.0},
        ],
        hero_cards=["8d", "7d"],
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "call_lost"
    assert out["bluered_classification"]["line"] == "warn"


def test_river_fold_call_incorrect_is_nice_fold():
    # 4ハイでリバーの大きなベットにフォールド → コール不正解 → nice_fold
    hand = _hand(
        [
            {"position": "BTN", "action": "bet", "amount_bb": 20.0},
            {"position": "BB", "action": "fold"},
        ],
        hero_cards=["4d", "3h"],
        hero_result_bb=-5.5,
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "nice_fold"
    assert out["bluered_classification"]["line"] == "gray"
    assert "MDF基準=" in out["gto_math"]


def test_turn_fold_is_fold_unknown():
    # river以外は判定しない（未来のカードで裁かない） → fold_unknown / MDFなし
    hand = {
        "hero_position": "BB",
        "hero_cards": ["4d", "3h"],
        "hero_result_bb": -5.5,
        "streets": {
            "preflop": [{"position": "BTN", "action": "raise", "amount_bb": 2.5}],
            "flop": {"board": BOARD_FLOP, "pot_bb": 5.5, "actions": []},
            "turn": {
                "board": BOARD_TURN,
                "pot_bb": 5.5,
                "actions": [
                    {"position": "BTN", "action": "bet", "amount_bb": 4.0},
                    {"position": "BB", "action": "fold"},
                ],
            },
        },
    }
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "fold_unknown"
    assert out["bluered_classification"]["line"] == "warn"
    assert "MDF" not in out["gto_math"]
    assert "ターン" in out["gto_math"]


def test_river_hero_bet_opp_fold_is_hero_aggression_won():
    hand = _hand(
        [
            {"position": "BB", "action": "bet", "amount_bb": 14.0},
            {"position": "BTN", "action": "fold"},
        ],
        hero_result_bb=28.0,
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "hero_aggression_won"
    assert out["bluered_classification"]["line"] == "red"
    assert "α=33%" in out["gto_math"]


def test_river_hero_bet_called_and_wins_is_value_success():
    hand = _hand(
        [
            {"position": "BB", "action": "bet", "amount_bb": 14.0},
            {"position": "BTN", "action": "call", "amount_bb": 14.0},
        ],
        hero_result_bb=42.0,
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "value_success"
    assert out["bluered_classification"]["line"] == "blue"


def test_river_call_and_win_is_bluff_catch():
    hand = _hand(
        [
            {"position": "BTN", "action": "bet", "amount_bb": 20.0},
            {"position": "BB", "action": "call", "amount_bb": 20.0},
        ],
        hero_result_bb=48.0,
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "bluff_catch"
    assert out["bluered_classification"]["line"] == "blue"


def test_preflop_only_hand():
    hand = {
        "hero_position": "SB",
        "hero_result_bb": -0.5,
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": "SB", "action": "fold"},
            ],
        },
    }
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "preflop_only"
    assert out["gto_math"] == ""
    assert out["nice_play_score"] == 0.0


def test_checkdown_showdown_is_preflop_only():
    # ポストフロップに bet/raise が無いチェックダウン → 判断スポットなし
    hand = _hand(
        [
            {"position": "BB", "action": "check"},
            {"position": "BTN", "action": "check"},
        ],
        hero_result_bb=5.5,
    )
    out = annotate_hand(hand)
    assert out["bluered_classification"]["category"] == "preflop_only"


def test_scores_match_gto_math_spec():
    # nice_call × river: 0.90 × 1.0 + α微補正(α=42% → +0.034) ≈ 0.934
    hand = _hand([
        {"position": "BTN", "action": "bet", "amount_bb": 20.0},
        {"position": "BB", "action": "call", "amount_bb": 20.0},
    ])
    out = annotate_hand(hand)
    indifference = 1.0 - abs(2 * 0.42 - 1.0)
    expected = 0.90 * 1.0 + (indifference - 0.5) * 0.1
    assert out["difficulty_score"] == pytest.approx(expected, abs=1e-6)
    assert out["nice_play_score"] == pytest.approx(expected, abs=1e-6)


def test_input_hand_is_not_mutated():
    hand = _hand([
        {"position": "BTN", "action": "bet", "amount_bb": 20.0},
        {"position": "BB", "action": "call", "amount_bb": 20.0},
    ])
    snapshot = copy.deepcopy(hand)
    annotate_hand(hand)
    assert hand == snapshot
