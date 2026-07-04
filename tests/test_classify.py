"""specs/classify.md 受入基準（§5）/ tests/PLAN.md 対応テスト"""

from scripts.hand_converter import annotate_hand, classify_hand


def _hand(river_actions, hero_result_bb, hero_position="BB"):
    return {
        "hand_number": 1,
        "hero_position": hero_position,
        "hero_result_bb": hero_result_bb,
        "streets": {
            "preflop": [
                {"position": "BTN", "action": "raise", "amount_bb": 2.5},
                {"position": hero_position, "action": "call"},
            ],
            "river": {
                "board": ["7s"],
                "pot_bb": 20.0,
                "actions": river_actions,
            },
        },
    }


def _assert(cls, category, line):
    assert cls["category"] == category
    assert cls["line"] == line


def test_showdown_hero_wins_after_call():
    hand = _hand([{"position": "BTN", "action": "bet", "amount_bb": 10.0},
                  {"position": "BB", "action": "call"}], hero_result_bb=15.0)
    _assert(classify_hand(hand), "bluff_catch", "blue")


def test_showdown_hero_wins_after_bet():
    hand = _hand([{"position": "BB", "action": "bet", "amount_bb": 10.0},
                  {"position": "BTN", "action": "call"}], hero_result_bb=15.0)
    _assert(classify_hand(hand), "value_success", "blue")


def test_showdown_hero_loses_after_bet():
    hand = _hand([{"position": "BB", "action": "bet", "amount_bb": 10.0},
                  {"position": "BTN", "action": "call"}], hero_result_bb=-15.0)
    _assert(classify_hand(hand), "bluff_failed", "red")


def test_noshow_hero_bet_opp_fold():
    hand = _hand([{"position": "BB", "action": "bet", "amount_bb": 10.0},
                  {"position": "BTN", "action": "fold"}], hero_result_bb=10.0)
    _assert(classify_hand(hand), "hero_aggression_won", "red")


def _call_lose_hand():
    return _hand([{"position": "BTN", "action": "bet", "amount_bb": 10.0},
                  {"position": "BB", "action": "call"}], hero_result_bb=-15.0)


def test_call_lose_gto_correct():
    # 負けたが正しかったコール = nice_call / gray（結果と判断の分離の本丸）
    _assert(classify_hand(_call_lose_hand(), gto_judgment="correct"), "nice_call", "gray")


def test_call_lose_gto_incorrect():
    _assert(classify_hand(_call_lose_hand(), gto_judgment="incorrect"), "bad_call", "red")


def test_call_lose_undecidable():
    _assert(classify_hand(_call_lose_hand(), gto_judgment="undecidable"), "call_lost", "warn")


def _fold_hand():
    return _hand([{"position": "BTN", "action": "bet", "amount_bb": 10.0},
                  {"position": "BB", "action": "fold"}], hero_result_bb=-5.0)


def test_fold_gto_correct():
    _assert(classify_hand(_fold_hand(), gto_judgment="correct"), "nice_fold", "gray")


def test_fold_gto_incorrect():
    _assert(classify_hand(_fold_hand(), gto_judgment="incorrect"), "bad_fold", "red")


def test_fold_undecidable():
    _assert(classify_hand(_fold_hand(), gto_judgment="undecidable"), "fold_unknown", "warn")


def test_preflop_only():
    hand = {
        "hand_number": 1,
        "hero_position": "CO",
        "hero_result_bb": -1.0,
        "streets": {
            "preflop": [
                {"position": "CO", "action": "raise", "amount_bb": 2.5},
                {"position": "BTN", "action": "raise", "amount_bb": 8.0},
                {"position": "CO", "action": "fold"},
            ]
        },
    }
    _assert(classify_hand(hand), "preflop_only", "preflop_only")


def test_hero_cards_undecidable_falls_to_warn():
    # hero_cards なし → 内部ヒューリスティックは判定困難に倒す（迷ったらwarn）
    _assert(classify_hand(_call_lose_hand()), "call_lost", "warn")


def test_annotate_hand_adds_fields_without_mutating_input():
    hand = _call_lose_hand()
    before = str(hand)
    out = annotate_hand(hand, gto_judgment="correct")
    assert str(hand) == before  # 入力は変更しない（純粋関数）
    assert out["bluered_classification"]["category"] == "nice_call"
    assert out["gto_math"].startswith("[GTO数学]")
    assert out["difficulty_score"] >= 0.5
    assert out["nice_play_score"] >= 0.5  # 損益マイナスでもナイスプレイ対象
    assert out["analyzed"] is False
