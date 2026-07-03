"""specs/classify.md §5「GTOスコア判定（レンジ区間モデル）」受入基準のテスト。

全列挙・乱数なしなので期待値は決定的。treysが必要（CI: .github/workflows/test.yml）。
"""
import pytest

from scripts.classify import (
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    VERDICT_UNKNOWN,
    classify_hand,
)
from scripts.equity import (
    PESSIMISTIC_TOP_FRACTION,
    judge_call,
    river_equity_interval,
    river_equity_vs_top_fraction,
)

BOARD = ["Ks", "Qd", "9c", "8s", "2h"]


def test_quads_call_correct():
    verdict = judge_call(["Ah", "Ad"], ["As", "Ac", "7d", "5h", "2c"], required_equity=0.42)
    assert verdict == VERDICT_CORRECT


def test_top_pair_good_kicker_call_correct():
    assert judge_call(["Kd", "Jd"], BOARD, required_equity=0.42) == VERDICT_CORRECT


def test_mid_pair_straddles_falls_to_unknown():
    # 区間が必要エクイティを跨ぐ = 相手レンジの想定次第で答えが変わる → 断定しない
    pessimistic, optimistic = river_equity_interval(["8d", "7d"], BOARD)
    assert pessimistic < 0.35 < optimistic
    assert judge_call(["8d", "7d"], BOARD, required_equity=0.35) == VERDICT_UNKNOWN


def test_trash_call_incorrect():
    assert judge_call(["4d", "3h"], BOARD, required_equity=0.30) == VERDICT_INCORRECT


def test_non_river_board_falls_to_unknown():
    # V1はリバーのみ判定。フロップ/ターンは常に判定困難（保守側）
    flop = ["Ks", "Qd", "9c"]
    turn = ["Ks", "Qd", "9c", "8s"]
    assert judge_call(["Ah", "Ad"], flop, required_equity=0.30) == VERDICT_UNKNOWN
    assert judge_call(["Ah", "Ad"], turn, required_equity=0.30) == VERDICT_UNKNOWN


def test_missing_required_equity_falls_to_unknown():
    assert judge_call(["Ah", "Ad"], ["As", "Ac", "7d", "5h", "2c"], required_equity=None) == VERDICT_UNKNOWN


def test_interval_is_consistent():
    # 悲観バウンド ≤ 楽観バウンド（レンジを強くするとエクイティは下がる）
    for hero in (["Ah", "Ad"], ["Kd", "Jd"], ["8d", "7d"], ["4d", "3h"], ["Ah", "Td"]):
        board = BOARD if hero != ["Ah", "Ad"] else ["As", "Ac", "7d", "5h", "2c"]
        pessimistic, optimistic = river_equity_interval(hero, board)
        assert 0.0 <= pessimistic <= optimistic <= 1.0


def test_equity_monotone_in_range_strength():
    fractions = [PESSIMISTIC_TOP_FRACTION, 0.5, 0.75, 1.0]
    equities = [river_equity_vs_top_fraction(["Kd", "Jd"], BOARD, f) for f in fractions]
    assert equities == sorted(equities)


def test_verdict_feeds_classification():
    # 統合: リバーコール敗北 + レンジ区間判定 → nice_call / bad_call / call_lost
    correct = judge_call(["Kd", "Jd"], BOARD, required_equity=0.42)
    c = classify_hand(showdown=True, hero_won=False, call_verdict=correct)
    assert (c.category, c.line) == ("nice_call", "gray")

    incorrect = judge_call(["4d", "3h"], BOARD, required_equity=0.30)
    c = classify_hand(showdown=True, hero_won=False, call_verdict=incorrect)
    assert (c.category, c.line) == ("bad_call", "red")

    unknown = judge_call(["8d", "7d"], BOARD, required_equity=0.35)
    c = classify_hand(showdown=True, hero_won=False, call_verdict=unknown)
    assert (c.category, c.line) == ("call_lost", "warn")
