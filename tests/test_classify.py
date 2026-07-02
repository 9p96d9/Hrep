"""tests/test_classify.py — ハンド分類のテスト。

仕様参照: specs/classify.md §5 受入基準
テストケース一覧: tests/PLAN.md
GTOスコア判定は gto_verdict で注入する（純粋関数テスト・外部依存なし）。
"""

from scripts.classify import (
    GTO_CORRECT,
    GTO_INCORRECT,
    GTO_UNKNOWN,
    CATEGORY_LABELS,
    classify_hand,
)


def _hand(river_actions, hero_result_bb, hero_position="BB"):
    """リバーで解決するポストフロップハンドの最小形。"""
    return {
        "hero_position": hero_position,
        "hero_cards": ["Ah", "Kd"],
        "hero_result_bb": hero_result_bb,
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": "BB", "action": "call"},
            ],
            "flop": {
                "board": ["9h", "5d", "2c"],
                "pot_bb": 5.5,
                "actions": [
                    {"position": "BB", "action": "check"},
                    {"position": "BTN", "action": "check"},
                ],
            },
            "turn": {"board": ["Kh"], "pot_bb": 5.5, "actions": []},
            "river": {"board": ["7s"], "pot_bb": 5.5, "actions": river_actions},
        },
    }


def _assert_classified(result, category):
    assert result["category"] == category
    assert result["line"] == EXPECTED_LINES[category]
    assert result["category_label"] == CATEGORY_LABELS[category]


# specs/classify.md §5 受入基準の期待ライン
EXPECTED_LINES = {
    "bluff_catch": "blue",
    "value_success": "blue",
    "hero_aggression_won": "red",
    "bluff_failed": "red",
    "nice_call": "gray",
    "bad_call": "red",
    "call_lost": "warn",
    "nice_fold": "gray",
    "bad_fold": "red",
    "fold_unknown": "warn",
    "preflop_only": "preflop_only",
}


def test_showdown_hero_wins_after_call():
    hand = _hand(
        [
            {"position": "BB", "action": "check"},
            {"position": "BTN", "action": "bet", "amount_bb": 4.0},
            {"position": "BB", "action": "call"},
        ],
        hero_result_bb=6.75,
    )
    _assert_classified(classify_hand(hand), "bluff_catch")


def test_showdown_hero_wins_after_bet():
    hand = _hand(
        [
            {"position": "BB", "action": "bet", "amount_bb": 4.0},
            {"position": "BTN", "action": "call"},
        ],
        hero_result_bb=6.75,
    )
    _assert_classified(classify_hand(hand), "value_success")


def test_showdown_hero_loses_after_bet():
    hand = _hand(
        [
            {"position": "BB", "action": "bet", "amount_bb": 4.0},
            {"position": "BTN", "action": "call"},
        ],
        hero_result_bb=-6.75,
    )
    _assert_classified(classify_hand(hand), "bluff_failed")


def test_noshow_hero_bet_opp_fold():
    hand = _hand(
        [
            {"position": "BB", "action": "bet", "amount_bb": 4.0},
            {"position": "BTN", "action": "fold"},
        ],
        hero_result_bb=2.75,
    )
    _assert_classified(classify_hand(hand), "hero_aggression_won")


def _call_lose_hand():
    return _hand(
        [
            {"position": "BB", "action": "check"},
            {"position": "BTN", "action": "bet", "amount_bb": 4.0},
            {"position": "BB", "action": "call"},
        ],
        hero_result_bb=-6.75,
    )


def test_call_lose_gto_correct():
    _assert_classified(classify_hand(_call_lose_hand(), gto_verdict=GTO_CORRECT), "nice_call")


def test_call_lose_gto_incorrect():
    _assert_classified(classify_hand(_call_lose_hand(), gto_verdict=GTO_INCORRECT), "bad_call")


def test_call_lose_undecidable():
    _assert_classified(classify_hand(_call_lose_hand(), gto_verdict=GTO_UNKNOWN), "call_lost")


def _fold_hand():
    return _hand(
        [
            {"position": "BB", "action": "check"},
            {"position": "BTN", "action": "bet", "amount_bb": 4.0},
            {"position": "BB", "action": "fold"},
        ],
        hero_result_bb=-2.75,
    )


def test_fold_gto_correct():
    _assert_classified(classify_hand(_fold_hand(), gto_verdict=GTO_CORRECT), "nice_fold")


def test_fold_gto_incorrect():
    _assert_classified(classify_hand(_fold_hand(), gto_verdict=GTO_INCORRECT), "bad_fold")


def test_fold_undecidable():
    _assert_classified(classify_hand(_fold_hand(), gto_verdict=GTO_UNKNOWN), "fold_unknown")


def test_preflop_only():
    hand = {
        "hero_position": "BB",
        "hero_cards": ["Ah", "Kd"],
        "hero_result_bb": -2.5,
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": "BB", "action": "fold"},
            ],
        },
    }
    _assert_classified(classify_hand(hand), "preflop_only")
