"""tests/test_ai_output.py — AI出力（detail_street）バリデーターのテスト。

仕様参照: specs/ai_analysis.md §8 受入基準
テストケース一覧: tests/PLAN.md
AI APIは呼ばない。解析済みJSON（tests/fixtures/）で、合格例が通ることと
バリデーターが違反を検出できることの両方を確認する。
"""

import json
from pathlib import Path

from scripts.ai_output_validator import validate_detail_street

_FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_ai_output_street.json").read_text(
        encoding="utf-8"
    )
)


def _validate(fixture_name):
    fixture = _FIXTURES[fixture_name]
    return validate_detail_street(fixture["output"], fixture["street_reached"])


def test_no_mdf_on_flop_read():
    assert not any("flop_read" in v for v in _validate("valid_river"))
    assert any("flop_read" in v and "MDF" in v for v in _validate("violation_mdf_on_flop"))


def test_no_mdf_on_turn_read():
    assert not any("turn_read" in v for v in _validate("valid_river"))
    assert any("turn_read" in v and "MDF" in v for v in _validate("violation_mdf_on_turn"))


def test_river_reached_has_mdf():
    # 合格例のriver_analysisは [GTO数学] のMDF/必要エクイティを引用している
    assert _validate("valid_river") == []
    assert any("river_analysis" in v for v in _validate("violation_river_no_mdf"))


def test_river_not_reached_empty():
    # フロップ終了ハンドは turn_read="" / river_analysis="" で合格
    assert _validate("valid_flop_only") == []
    assert any("turn_read" in v for v in _validate("violation_unreached_nonempty"))


def test_position_as_subject():
    violations = _validate("violation_hero_subject")
    assert any("ヒーロー" in v for v in violations)
    assert not any("ヒーロー" in v for v in _validate("valid_river"))


def test_all_fields_present():
    assert _validate("valid_river") == []
    assert _validate("valid_flop_only") == []
    assert any("kaizen" in v and "存在しない" in v for v in _validate("violation_missing_field"))


def test_opp_exploit_has_action():
    assert not any("opp_exploit" in v for v in _validate("valid_river"))
    assert any("opp_exploit" in v for v in _validate("violation_opp_exploit_vague"))
