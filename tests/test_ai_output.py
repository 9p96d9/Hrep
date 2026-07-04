"""specs/ai_analysis.md §8 受入基準 / tests/PLAN.md 対応テスト

AI APIは呼ばない。tests/fixtures/ の解析済みJSONでバリデーターを検証する。
バリデーターは本番の受入ゲート（scripts/ai_validator.py）そのものをimportする。
"""

import json
from pathlib import Path

import pytest

from scripts.ai_validator import validate_detail_street_item

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_ai_output_street.json").read_text(
        encoding="utf-8"
    )
)


def test_no_mdf_on_flop_read():
    errors = validate_detail_street_item(
        FIXTURES["violation_mdf_on_flop"], turn_reached=False, river_reached=False
    )
    assert any("flop_read" in e for e in errors)


def test_no_mdf_on_turn_read():
    item = dict(FIXTURES["valid_river_hand"], turn_read="ターンではMDF基準67%を満たす必要がある。")
    errors = validate_detail_street_item(item, turn_reached=True, river_reached=True)
    assert any("turn_read" in e for e in errors)


def test_river_reached_has_mdf():
    # 合格例: river到達 & river_analysis に MDF 引用あり → 違反なし
    assert validate_detail_street_item(
        FIXTURES["valid_river_hand"], turn_reached=True, river_reached=True
    ) == []
    # 違反例: river到達なのに river_analysis が空
    errors = validate_detail_street_item(
        FIXTURES["violation_river_reached_but_empty"], turn_reached=True, river_reached=True
    )
    assert any("river_analysis" in e for e in errors)


def test_river_not_reached_empty():
    # フロップ終了ハンド: turn_read="" / river_analysis="" で合格
    assert validate_detail_street_item(
        FIXTURES["valid_flop_end_hand"], turn_reached=False, river_reached=False
    ) == []
    # 非空だと違反
    item = dict(FIXTURES["valid_flop_end_hand"], river_analysis="リバーの話をしてしまう。")
    errors = validate_detail_street_item(item, turn_reached=False, river_reached=False)
    assert any("river" in e for e in errors)


def test_position_as_subject():
    errors = validate_detail_street_item(
        FIXTURES["violation_hero_subject"], turn_reached=False, river_reached=False
    )
    assert any("主語" in e for e in errors)


def test_all_fields_present():
    errors = validate_detail_street_item(
        FIXTURES["violation_missing_field"], turn_reached=False, river_reached=False
    )
    assert any("欠落" in e for e in errors)


def test_opp_exploit_has_action():
    item = dict(FIXTURES["valid_flop_end_hand"], opp_exploit="相手は弱いので攻めるとよい。")
    errors = validate_detail_street_item(item, turn_reached=False, river_reached=False)
    assert any("opp_exploit" in e for e in errors)


@pytest.mark.parametrize("key", ["valid_river_hand", "valid_flop_end_hand"])
def test_valid_fixtures_pass(key):
    river = key == "valid_river_hand"
    assert validate_detail_street_item(
        FIXTURES[key], turn_reached=river, river_reached=river
    ) == []
