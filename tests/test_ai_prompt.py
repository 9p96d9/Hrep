"""specs/ai_analysis.md §2（プロバイダー）・§3（detail_streetプロンプト）・§7（[GTO数学]引用）のテスト。

AI APIは呼ばない。プロンプト文字列と応答パーサーのみ検証する。
"""
import pytest

from scripts.ai_prompt import (
    DETAIL_STREET_SYSTEM_PROMPT,
    GEMINI_MODEL,
    GROQ_MODEL,
    build_detail_street_prompt,
    detect_provider,
    parse_detail_street_response,
    street_reached,
)

RIVER_HAND = {
    "hero_position": "BB",
    "hero_cards": ["Kd", "Jd"],
    "bluered_classification": {"category_label": "ナイスコール"},
    "gto_math": "[GTO数学] ナイスコールスポット | リバー | 必要エクイティ=42%（α=42%）",
    "streets": {
        "preflop": [{"position": "BTN", "action": "raise", "amount_bb": 2.5}],
        "flop": {"board": ["Ks", "Qd", "9c"], "pot_bb": 5.5, "actions": []},
        "turn": {"board": ["8s"], "pot_bb": 5.5, "actions": []},
        "river": {
            "board": ["2h"],
            "pot_bb": 28.0,
            "actions": [{"position": "BTN", "action": "bet", "amount_bb": 20.0}],
        },
    },
}

FLOP_END_HAND = {
    "hero_position": "BTN",
    "hero_cards": ["Ah", "Qh"],
    "bluered_classification": {"category_label": "フォールド(要確認)"},
    "gto_math": "[GTO数学] フォールドスポット | フロップ | α=40% | Heroがフォールド",
    "streets": {
        "preflop": [{"position": "BTN", "action": "raise", "amount_bb": 2.5}],
        "flop": {
            "board": ["9h", "5d", "2c"],
            "pot_bb": 5.5,
            "actions": [
                {"position": "BB", "action": "bet", "amount_bb": 4.0},
                {"position": "BTN", "action": "fold"},
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# §2 プロバイダー判定


def test_provider_priority_env_groq_first():
    provider, model, key = detect_provider(
        byok_key="other_key", env={"GROQ_API_KEY": "gsk_env", "GEMINI_API_KEY": "gem_env"}
    )
    assert (provider, model, key) == ("groq", GROQ_MODEL, "gsk_env")


def test_provider_env_gemini_second():
    provider, model, key = detect_provider(byok_key="gsk_byok", env={"GEMINI_API_KEY": "gem_env"})
    assert (provider, model, key) == ("gemini", GEMINI_MODEL, "gem_env")


def test_provider_byok_format_detection():
    assert detect_provider(byok_key="gsk_abc")[0] == "groq"
    assert detect_provider(byok_key="AIzaSyExample")[0] == "gemini"


def test_provider_none_when_undecidable():
    assert detect_provider() is None


# ---------------------------------------------------------------------------
# §3 detail_street プロンプト


def test_system_prompt_contains_batch_instructions():
    # §3「バッチプロンプト指示」の4文がシステムプロンプトに含まれる
    assert "各フィールドは該当ストリートの話のみ書いてください" in DETAIL_STREET_SYSTEM_PROMPT
    assert "到達していない場合は空文字を返してください" in DETAIL_STREET_SYSTEM_PROMPT
    assert "MDF は river_analysis フィールドのみで言及してください" in DETAIL_STREET_SYSTEM_PROMPT


def test_system_prompt_contains_quality_rules():
    # §6 主語・数値出典・レンジ表記・評価軸
    assert "主語は必ずポジション名" in DETAIL_STREET_SYSTEM_PROMPT
    assert "[GTO数学]ブロックに記載の数値のみ引用可" in DETAIL_STREET_SYSTEM_PROMPT
    assert "ATo+" in DETAIL_STREET_SYSTEM_PROMPT
    assert "結果論的評価を出さない" in DETAIL_STREET_SYSTEM_PROMPT


def test_user_prompt_quotes_gto_math_verbatim():
    # §7: [GTO数学]ブロックは再計算せずそのまま引用させる
    _, user = build_detail_street_prompt([RIVER_HAND])
    assert RIVER_HAND["gto_math"] in user


def test_user_prompt_numbers_hands_sequentially():
    _, user = build_detail_street_prompt([RIVER_HAND, FLOP_END_HAND])
    assert "### ハンド 1" in user
    assert "### ハンド 2" in user
    assert "id 1〜2" in user


def test_user_prompt_flags_unreached_streets():
    _, user = build_detail_street_prompt([FLOP_END_HAND])
    assert "flop で終了" in user
    assert "空文字" in user


def test_street_reached():
    assert street_reached(RIVER_HAND) == "river"
    assert street_reached(FLOP_END_HAND) == "flop"
    assert street_reached({"streets": {"preflop": []}}) == "preflop"


# ---------------------------------------------------------------------------
# 応答パーサー


def test_parse_plain_json_array():
    assert parse_detail_street_response('[{"id": 1}]') == [{"id": 1}]


def test_parse_fenced_json_with_preamble():
    text = '解析結果です。\n```json\n[{"id": 1, "kaizen": "このラインで十分"}]\n```\nご確認ください。'
    assert parse_detail_street_response(text) == [{"id": 1, "kaizen": "このラインで十分"}]


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_detail_street_response("JSONがありません")
