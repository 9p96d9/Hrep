"""specs/gto_math.md §5 受入基準のテスト。期待値はSPECの受入基準表と一致させる。"""
import pytest

from scripts.gto_math import (
    NICE_PLAY_THRESHOLD,
    alpha_adjustment,
    compute_difficulty,
    compute_gto_math,
    compute_nice_play_score,
    extract_alpha,
    select_improve_chances,
    select_nice_plays,
)

# ---------------------------------------------------------------------------
# 難易度スコア


def test_difficulty_bluff_catch_river():
    # 0.90 × 1.0 + α微補正(α=0.45 → +0.04) = 0.94
    score = compute_difficulty("bluff_catch", "river", alpha_value=0.45)
    assert score >= 0.9
    assert score == pytest.approx(0.94)


def test_difficulty_bluff_catch_turn():
    assert compute_difficulty("bluff_catch", "turn") == pytest.approx(0.72)


def test_difficulty_nice_fold_flop():
    assert compute_difficulty("nice_fold", "flop") == pytest.approx(0.51)


def test_difficulty_bluff_catch_preflop():
    assert compute_difficulty("bluff_catch", "preflop") == pytest.approx(0.36)


def test_difficulty_value_success():
    assert compute_difficulty("value_success", "river") == pytest.approx(0.50)


def test_alpha_adjustment_at_indifference():
    # α=0.5（完全インディファレンス）→ +0.05 が適用される
    assert alpha_adjustment(0.5) == pytest.approx(0.05)
    with_adj = compute_difficulty("bluff_catch", "river", alpha_value=0.5)
    without_adj = compute_difficulty("bluff_catch", "river")
    assert with_adj - without_adj == pytest.approx(0.05)


def test_max_score_cap():
    # bluff_catch × river, α=0.5 → 0.90 + 0.05 = 0.95 ≤ 1.0
    assert compute_difficulty("bluff_catch", "river", alpha_value=0.5) == pytest.approx(0.95)
    for category in ("bluff_catch", "nice_call", "nice_fold", "value_success"):
        for street in ("preflop", "flop", "turn", "river"):
            assert compute_difficulty(category, street, alpha_value=0.5) <= 1.0


# ---------------------------------------------------------------------------
# ナイスプレイスコア（V1: bluff_catch / nice_call / nice_fold のみ）


def test_nice_play_score_bluff_catch_river():
    d = compute_difficulty("bluff_catch", "river", alpha_value=0.45)
    assert compute_nice_play_score("bluff_catch", d) >= 0.5


def test_nice_play_score_nice_call_river():
    # 損益マイナスでも表示対象（結果と判断の分離の最も強い実演）
    d = compute_difficulty("nice_call", "river")
    assert d == pytest.approx(0.90)
    assert compute_nice_play_score("nice_call", d) >= 0.5


def test_nice_play_score_lucky_bluff_catch():
    # ショーダウン勝利でもGTO判定=不正解（幸運なコール）は除外
    d = compute_difficulty("bluff_catch", "river")
    assert compute_nice_play_score("bluff_catch", d, gto_verdict="incorrect") == 0.0


def test_nice_play_score_undecidable_bluff_catch_stays():
    # 判定困難はショーダウン勝利という追加証拠を考慮して対象に残す（specs/classify.md §4）
    d = compute_difficulty("bluff_catch", "river")
    assert compute_nice_play_score("bluff_catch", d, gto_verdict="unknown") >= 0.5


def test_nice_play_score_bluff_catch_pf():
    d = compute_difficulty("bluff_catch", "preflop")  # 0.36 < 閾値
    assert compute_nice_play_score("bluff_catch", d) == 0.0


def test_nice_play_score_value_success():
    d = compute_difficulty("value_success", "river")
    assert compute_nice_play_score("value_success", d) == 0.0


def test_nice_play_score_hero_aggression():
    # hero_aggression_won はV1対象外（V2でリバー限定追加を検討）
    d = compute_difficulty("hero_aggression_won", "river")
    assert compute_nice_play_score("hero_aggression_won", d) == 0.0


def test_select_nice_plays_top3_by_score_desc():
    hands = [
        {"id": 1, "nice_play_score": 0.72},
        {"id": 2, "nice_play_score": 0.95},
        {"id": 3, "nice_play_score": 0.85},
        {"id": 4, "nice_play_score": 0.90},
    ]
    selected = select_nice_plays(hands)
    assert [h["id"] for h in selected] == [2, 4, 3]  # 上位3件のみ


def test_zero_candidates_returns_empty_list():
    # 空リストを返す（UIは「0件」を正直に表示。セクションを非表示にしない）
    assert select_nice_plays([]) == []
    below = [{"id": 1, "nice_play_score": 0.0}, {"id": 2, "nice_play_score": 0.36}]
    assert select_nice_plays(below) == []
    assert NICE_PLAY_THRESHOLD == 0.5


# ---------------------------------------------------------------------------
# §4b 改善チャンス選定


def _ic_hand(hand_id, category, street, pot):
    return {
        "id": hand_id,
        "bluered_classification": {"category": category},
        "decision_street": street,
        "decision_pot_bb": pot,
    }


def test_improve_chances_street_priority_over_pot():
    # river が turn より先（ポットが小さくても）
    hands = [
        _ic_hand(1, "bad_fold", "turn", 40.0),
        _ic_hand(2, "bad_call", "river", 10.0),
    ]
    assert [h["id"] for h in select_improve_chances(hands)] == [2, 1]


def test_improve_chances_pot_desc_within_street():
    hands = [
        _ic_hand(1, "bad_call", "river", 12.0),
        _ic_hand(2, "bad_call", "river", 30.0),
    ]
    assert [h["id"] for h in select_improve_chances(hands)] == [2, 1]


def test_improve_chances_excludes_non_target_categories():
    # bluff_failed（均衡上の失敗）・warn系（判定未確定）・gray は指摘しない
    hands = [
        _ic_hand(1, "bluff_failed", "river", 50.0),
        _ic_hand(2, "call_lost", "river", 50.0),
        _ic_hand(3, "fold_unknown", "river", 50.0),
        _ic_hand(4, "nice_fold", "river", 50.0),
    ]
    assert select_improve_chances(hands) == []


def test_improve_chances_max_three():
    hands = [_ic_hand(i, "bad_call", "river", float(i)) for i in range(1, 6)]
    selected = select_improve_chances(hands)
    assert len(selected) == 3
    assert [h["id"] for h in selected] == [5, 4, 3]


def test_improve_chances_zero_candidates_returns_empty_list():
    assert select_improve_chances([]) == []


# ---------------------------------------------------------------------------
# _compute_gto_math の出力形式


def test_gto_math_defender_cat():
    # tests/PLAN.md fixture例: pot=28, bet=20 → 必要エクイティ=42%
    text = compute_gto_math("bluff_catch", "river", pot_bb=28.0, bet_bb=20.0)
    assert "必要エクイティ=42%" in text
    assert text.startswith("[GTO数学]")
    assert "リバー" in text


def test_gto_math_aggressor_cat():
    # specs/gto_math.md §2 表示例: ベット=12bb / ポット=24bb | α=33%
    text = compute_gto_math("value_success", "turn", pot_bb=24.0, bet_bb=12.0)
    assert "α=33%" in text
    assert "ベット=12bb" in text
    assert "ポット=24bb" in text


def test_gto_math_fold_river():
    text = compute_gto_math("nice_fold", "river", pot_bb=24.0, bet_bb=12.0)
    assert "α=33%" in text
    assert "MDF基準=67%" in text


def test_gto_math_fold_flop():
    # リバー以外ではMDFに言及しない
    text = compute_gto_math("fold_unknown", "flop", pot_bb=15.0, bet_bb=10.0)
    assert "α=40%" in text
    assert "MDF" not in text


def test_gto_math_fold_turn():
    text = compute_gto_math("bad_fold", "turn", pot_bb=24.0, bet_bb=12.0)
    assert "MDF" not in text


def test_extract_alpha():
    assert extract_alpha("[GTO数学] バリュースポット | ターン | α=33%") == pytest.approx(0.33)
    assert extract_alpha("[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=42%") is None
    assert extract_alpha("") is None
