"""specs/ai_analysis.md §8 受入基準のテスト（detail_street）。

AI APIは呼ばない。tests/fixtures/ の解析済みJSONをバリデーターに通して検証する。
バリデーター自身が違反を検出できることも fixture の違反例で確認する。
"""
import json
import pathlib

import pytest

from scripts.ai_output_validator import validate_detail_street

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load():
    return json.loads(
        (FIXTURES / "sample_ai_output_street.json").read_text(encoding="utf-8")
    )


def _validate(case: dict) -> list[str]:
    return validate_detail_street(
        case["entry"],
        reached_turn=case["reached_turn"],
        reached_river=case["reached_river"],
    )


def test_valid_samples_pass():
    cases = _load()
    for name, case in cases.items():
        if case["expect_valid"]:
            assert _validate(case) == [], name


def test_violation_samples_are_detected():
    cases = _load()
    for name, case in cases.items():
        if not case["expect_valid"]:
            assert _validate(case) != [], name


def test_no_mdf_on_flop_read():
    case = _load()["violation_mdf_on_flop"]
    violations = _validate(case)
    assert any("flop_read" in v and "MDF" in v for v in violations)


def test_no_mdf_on_turn_read():
    case = _load()["valid_river_hand"]
    entry = dict(case["entry"], turn_read="Turn KhでBBはMDF基準67%までコールする。")
    violations = validate_detail_street(entry, reached_turn=True, reached_river=True)
    assert any("turn_read" in v and "MDF" in v for v in violations)


def test_river_reached_has_mdf():
    case = _load()["valid_river_hand"]
    river = case["entry"]["river_analysis"]
    assert "MDF" in river or "必要エクイティ" in river
    # river到達なのにMDF/必要エクイティの引用がなければ違反
    entry = dict(case["entry"], river_analysis="River 7sでBBはコールが均衡。")
    violations = validate_detail_street(entry, reached_turn=True, reached_river=True)
    assert any("river_analysis" in v for v in violations)


def test_river_not_reached_empty():
    case = _load()["valid_flop_end_hand"]
    assert case["entry"]["turn_read"] == ""
    assert case["entry"]["river_analysis"] == ""
    assert _validate(case) == []
    # 未到達なのに非空なら違反
    entry = dict(case["entry"], river_analysis="River 7sでコール。")
    violations = validate_detail_street(entry, reached_turn=False, reached_river=False)
    assert any("river未到達" in v for v in violations)


def test_position_as_subject():
    case = _load()["violation_hero_subject"]
    violations = _validate(case)
    assert any("主語" in v or "ポジション" in v for v in violations)


def test_all_fields_present():
    case = _load()["violation_missing_field"]
    violations = _validate(case)
    assert any("kaizen" in v for v in violations)


def test_opp_exploit_has_action():
    case = _load()["valid_river_hand"]
    entry = dict(case["entry"], opp_exploit="相手はGTOから逸脱している。")
    violations = validate_detail_street(entry, reached_turn=True, reached_river=True)
    assert any("opp_exploit" in v and "アクション" in v for v in violations)
