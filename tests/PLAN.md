# tests/PLAN.md — テスト計画

---

## 原則

**テストするもの:** DB不要・外部API不要で動く純粋関数のみ
**テストしないもの:** UI（HTML/CSS/JS）・DB統合・AI API呼び出し・外部サービス

理由: Firebase Emulatorをセットアップしない。GitHub Actionsで確実に動く純粋関数テストだけ書く。

**受入基準の正:** 各テストの期待値は `specs/` の受入基準表と一致させる。
テストとSPECが食い違ったら、まず `REQUIREMENTS.md` に照らしてどちらが正か判断する。

---

## テスト対象関数（優先度順）

### 優先度 HIGH（実装と同時に書く）

#### `tests/test_gto_math.py`
対象: `_compute_difficulty`, `_compute_nice_play_score`
仕様参照: `specs/gto_math.md`

```
test_difficulty_bluff_catch_river      → ≥ 0.9
test_difficulty_bluff_catch_turn       → ≈ 0.72
test_difficulty_nice_fold_flop         → ≈ 0.51
test_difficulty_bluff_catch_preflop    → ≈ 0.36
test_difficulty_value_success          → ≈ 0.50
test_nice_play_score_bluff_catch_river → ≥ 0.5（表示対象）
test_nice_play_score_nice_call_river   → ≥ 0.5（損益マイナスでも表示対象）
test_nice_play_score_lucky_bluff_catch → 0.0（GTO判定=不正解の幸運コールは除外）
test_nice_play_score_bluff_catch_pf    → 0.0（閾値未満）
test_nice_play_score_value_success     → 0.0（対象外カテゴリ）
test_nice_play_score_hero_aggression   → 0.0（V1対象外）
test_alpha_adjustment_at_indifference  → +0.05補正が適用される
test_max_score_cap                     → 1.0を超えない
test_zero_candidates_returns_empty_list → 空リストを返す（UIは0件表示。非表示にしない）
```

対象: `_compute_gto_math` の出力形式

```
test_gto_math_defender_cat   → "必要エクイティ=XX%" を含む
test_gto_math_aggressor_cat  → "α=XX%" を含む
test_gto_math_fold_river     → "MDF基準=XX%" を含む
test_gto_math_fold_flop      → "MDF" を含まない（リバー以外）
test_gto_math_fold_turn      → "MDF" を含まない
```

---

### 優先度 HIGH（分類は骨格なので先に書く）

#### `tests/test_equity.py`
対象: リバーエクイティ推定（レンジ区間モデル）
仕様参照: `specs/classify.md` §3 V1アルゴリズム

```
test_quads_call_correct                  → correct（区間全体が必要エクイティの上）
test_top_pair_good_kicker_call_correct   → correct
test_mid_pair_straddles_falls_to_unknown → unknown（区間が跨ぐ）
test_trash_call_incorrect                → incorrect（楽観バウンドでも沈む）
test_non_river_board_falls_to_unknown    → unknown（V1はリバーのみ判定）
test_missing_required_equity_falls_to_unknown → unknown
test_interval_is_consistent              → 悲観 ≤ 楽観
test_equity_monotone_in_range_strength   → レンジが強いほどエクイティ低下
test_verdict_feeds_classification        → nice_call/bad_call/call_lost へ接続
```

注意: 全列挙（C(45,2)=990コンボ）・乱数なしなので決定的。treysは純Pythonで
DB・外部API不要の原則は維持される。

#### `tests/test_classify.py`
対象: 分類ロジック
仕様参照: `specs/classify.md`

```
test_showdown_hero_wins_after_call    → bluff_catch / blue
test_showdown_hero_wins_after_bet     → value_success / blue
test_showdown_hero_loses_after_bet    → bluff_failed / red
test_noshow_hero_bet_opp_fold         → hero_aggression_won / red
test_call_lose_gto_correct            → nice_call / gray
test_call_lose_gto_incorrect          → bad_call / red
test_call_lose_undecidable            → call_lost / warn
test_fold_gto_correct                 → nice_fold / gray
test_fold_gto_incorrect               → bad_fold / red
test_fold_undecidable                 → fold_unknown / warn
test_preflop_only                     → preflop_only / preflop_only
```

---

### 優先度 HIGH（パイプライン統合）

#### `tests/test_hand_converter.py`
対象: ハンドJSON→分類・スコア変換（`annotate_hand`）
仕様参照: `specs/hand_converter.md`

```
test_river_call_lose_gto_correct_is_nice_call   → nice_call / gray / スコア≥0.5
test_river_call_lose_undecidable_is_call_lost   → call_lost / warn
test_river_fold_call_incorrect_is_nice_fold     → nice_fold / gray / MDF基準あり
test_turn_fold_is_fold_unknown                  → fold_unknown / warn / MDFなし
test_river_hero_bet_opp_fold_is_hero_aggression_won → hero_aggression_won / red
test_river_hero_bet_called_and_wins_is_value_success → value_success / blue
test_river_call_and_win_is_bluff_catch          → bluff_catch / blue
test_preflop_only_hand                          → preflop_only / gto_math=""
test_checkdown_showdown_is_preflop_only         → preflop_only（判断スポットなし）
test_scores_match_gto_math_spec                 → specs/gto_math.md の式と一致
test_input_hand_is_not_mutated                  → 入力dict非破壊
```

---

### 優先度 MEDIUM（AI出力バリデーター）

#### `tests/test_ai_output.py`
対象: AI出力のバリデーション関数（`detail_street` を主対象）
仕様参照: `specs/ai_analysis.md` §8

```
test_no_mdf_on_flop_read        → flop_read に "MDF" が含まれない
test_no_mdf_on_turn_read        → turn_read に "MDF" が含まれない
test_river_reached_has_mdf      → river到達ハンドの river_analysis に "MDF" or "必要エクイティ"
test_river_not_reached_empty    → フロップ終了ハンドで turn_read="" / river_analysis=""
test_position_as_subject        → "ヒーロー" ではなくポジション名が主語
test_all_fields_present         → 6フィールド全て存在
test_opp_exploit_has_action     → "bet"/"raise"/"fold" 等のアクション名を含む
```

注意: このテストはAI APIを呼ばない。解析済みJSONを `tests/fixtures/` に置いて検証する。
このバリデーターは本番でもAI出力の受入ゲートとして再利用する（テスト専用にしない）。

#### `tests/test_ai_prompt.py`
対象: プロンプト生成・プロバイダー判定・応答パーサー（`scripts/ai_prompt.py`）
仕様参照: `specs/ai_analysis.md` §2・§3・§6・§7

```
test_provider_priority_env_groq_first     → GROQ_API_KEY が最優先
test_provider_env_gemini_second           → GEMINI_API_KEY が次点
test_provider_byok_format_detection       → gsk_=Groq / その他=Gemini
test_provider_none_when_undecidable       → None
test_system_prompt_contains_batch_instructions → §3の指示文を含む
test_system_prompt_contains_quality_rules → §6の品質ルールを含む
test_user_prompt_quotes_gto_math_verbatim → [GTO数学]をそのまま引用（§7）
test_user_prompt_numbers_hands_sequentially → id連番
test_user_prompt_flags_unreached_streets  → 未到達ストリートの明示
test_parse_* 3件                          → 応答JSON抽出（フェンス・前置き許容）
```

---

## fixturesの設計

### `tests/fixtures/sample_hands.json`

各カテゴリのサンプルハンドを最低1件ずつ用意する。

```json
{
  "bluff_catch_river": {
    "bluered_classification": {
      "category": "bluff_catch",
      "category_label": "ブラフキャッチ",
      "line": "blue"
    },
    "streets": {
      "river": {
        "board": ["7s"],
        "pot_bb": 28.0,
        "actions": [{"position": "BTN", "action": "bet", "amount_bb": 20.0}]
      }
    },
    "hero_position": "BB",
    "gto_math": "[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=42%（α=42%）"
  }
}
```

### `tests/fixtures/sample_ai_output_street.json`

`detail_street` 形式のAI出力サンプル（合格例と違反例の両方を用意し、バリデーターが違反を検出できることも確認する）。

---

## GitHub Actions 設定

`.github/workflows/test.yml`:

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pytest python-dotenv treys
      - run: pytest tests/ -v --tb=short
```

DBや外部APIは不要なので、secrets設定なしで動く。
（AIクライアントSDKはテストでimportしない設計にする。バリデーターは純粋関数として `scripts/` から分離してimportする。）

---

## コミットメッセージルール

```
feat: 機能名 test:✅        # テストを書いて通過した
fix:  バグ修正 test:✅       # テストで再現→修正→通過
feat: 機能名 test:skip+UI   # UIのみ変更でテスト不要
feat: 機能名 test:skip+DB   # DB統合テストは後回し
```
