"""specs/classify.md §5 受入基準のテスト。カテゴリ→ライン対応表（§4）が正。"""
import json
import pathlib

import pytest

from scripts.classify import (
    CATEGORIES,
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    VERDICT_UNKNOWN,
    classify_hand,
    judge_call_correctness,
)
from scripts.gto_math import CATEGORY_BASE_SCORES

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# §5 受入基準（分類フロー）


def test_showdown_hero_wins_after_call():
    c = classify_hand(showdown=True, hero_won=True, hero_last_aggressor=False)
    assert (c.category, c.line) == ("bluff_catch", "blue")


def test_showdown_hero_wins_after_bet():
    c = classify_hand(showdown=True, hero_won=True, hero_last_aggressor=True)
    assert (c.category, c.line) == ("value_success", "blue")


def test_showdown_hero_loses_after_bet():
    c = classify_hand(showdown=True, hero_won=False, hero_last_aggressor=True)
    assert (c.category, c.line) == ("bluff_failed", "red")


def test_noshow_hero_bet_opp_fold():
    c = classify_hand(showdown=False, hero_last_aggressor=True)
    assert (c.category, c.line) == ("hero_aggression_won", "red")


def test_call_lose_gto_correct():
    # 負けたが正しかったコール → gray（損失は分散。ナイスプレイ候補）
    c = classify_hand(showdown=True, hero_won=False, call_verdict=VERDICT_CORRECT)
    assert (c.category, c.line) == ("nice_call", "gray")


def test_call_lose_gto_incorrect():
    c = classify_hand(showdown=True, hero_won=False, call_verdict=VERDICT_INCORRECT)
    assert (c.category, c.line) == ("bad_call", "red")


def test_call_lose_undecidable():
    c = classify_hand(showdown=True, hero_won=False, call_verdict=VERDICT_UNKNOWN)
    assert (c.category, c.line) == ("call_lost", "warn")


def test_fold_gto_correct():
    # コールが不正解 = フォールドが正解 → nice_fold
    c = classify_hand(showdown=False, call_verdict=VERDICT_INCORRECT)
    assert (c.category, c.line) == ("nice_fold", "gray")


def test_fold_gto_incorrect():
    # コールが正解だったのにフォールド → bad_fold
    c = classify_hand(showdown=False, call_verdict=VERDICT_CORRECT)
    assert (c.category, c.line) == ("bad_fold", "red")


def test_fold_undecidable():
    c = classify_hand(showdown=False, call_verdict=VERDICT_UNKNOWN)
    assert (c.category, c.line) == ("fold_unknown", "warn")


def test_preflop_only():
    c = classify_hand(preflop_only=True)
    assert (c.category, c.line) == ("preflop_only", "preflop_only")


# ---------------------------------------------------------------------------
# GTOスコア判定（コール/フォールド共通機構）


def test_judge_clear_correct():
    assert judge_call_correctness(0.60, 0.40) == VERDICT_CORRECT


def test_judge_clear_incorrect():
    assert judge_call_correctness(0.20, 0.40) == VERDICT_INCORRECT


def test_judge_middle_band_falls_to_unknown():
    # 確信が持てない中間帯は判定困難に倒す（迷ったらwarn — REQUIREMENTS.md Must Not）
    assert judge_call_correctness(0.42, 0.40) == VERDICT_UNKNOWN
    assert judge_call_correctness(0.38, 0.40) == VERDICT_UNKNOWN


def test_judge_missing_inputs_fall_to_unknown():
    assert judge_call_correctness(None, 0.40) == VERDICT_UNKNOWN
    assert judge_call_correctness(0.60, None) == VERDICT_UNKNOWN


# ---------------------------------------------------------------------------
# カテゴリ表の整合性


def test_category_table_matches_difficulty_table():
    # §4 の11カテゴリ全てに難易度基礎スコアが定義されている（specs/gto_math.md §3）
    assert set(CATEGORIES) == set(CATEGORY_BASE_SCORES)


def test_fixtures_match_category_table():
    # fixtureの bluered_classification が §4 対応表（category→label/line）と一致する
    hands = json.loads((FIXTURES / "sample_hands.json").read_text(encoding="utf-8"))
    assert len(hands) >= len(CATEGORIES)  # 各カテゴリ最低1件
    seen = set()
    for name, hand in hands.items():
        bc = hand["bluered_classification"]
        label, line = CATEGORIES[bc["category"]]
        assert bc["category_label"] == label, name
        assert bc["line"] == line, name
        seen.add(bc["category"])
    assert seen == set(CATEGORIES)
