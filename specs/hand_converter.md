# specs/hand_converter.md — ハンドJSON→分類・スコア変換パイプライン

**Status: ✅ 実装済み**
**実装ファイル:** `scripts/hand_converter.py`（`annotate_hand`）
**対応テスト:** `tests/test_hand_converter.py`

---

## 1. 設計意図

`docs/data_schema.md` のハンドJSONから、判断スポットの事実（誰が最後に攻撃したか・
Heroの応答・ショーダウン結果）を抽出し、`classify` → `equity` → `gto_math` の
純粋関数群を正しい順序で束ねる。**このモジュール自体は判断ロジックを持たない。**
判断はすべて `specs/classify.md` / `specs/gto_math.md` に委譲する。

---

## 2. INPUT / OUTPUT

```
INPUT:  hand: dict（docs/data_schema.md のハンドJSON形式）
        必須: hero_position, streets
        任意: hero_cards, hero_result_bb（欠落時は保守側に倒す）

OUTPUT: dict
  {
    "bluered_classification": {"category", "category_label", "line"},
    "gto_math": str,              # [GTO数学]ブロック。preflop_onlyは ""
    "difficulty_score": float,    # 0.0〜1.0
    "nice_play_score": float,     # 0.0〜1.0
    "decision_street": str,       # 攻撃ストリート（判断スポット）。preflop_onlyは "preflop"
    "decision_pot_bb": float      # 判断スポットのポット。preflop_onlyは 0.0
  }
（入力handは変更しない。呼び出し側がマージする。
 decision_street / decision_pot_bb は改善チャンス選定＝specs/gto_math.md §4b が使用）
```

---

## 3. 抽出ルール

### 判断スポットの特定

- **攻撃ストリート** = river → turn → flop の順で最初に bet/raise（アグレッシブアクション）
  が存在するストリート。`[GTO数学]` と分類の対象はこのストリートの**最後の**アグレッシブアクション
- アグレッシブアクション = `action ∈ {bet, raise, allin}`（`check/call/fold` は非攻撃）
- **preflop_only 判定**: ポストフロップに bet/raise が1つも存在しない場合は `preflop_only`
  とする。アクションが物理的に無い場合（プリフロップ・フォールド/オールイン解決）に加え、
  **チェックダウンのショーダウンも含む**（判断スポットが存在しないため。V1の設計判断）

### 事実の判定

| 事実 | 判定方法 |
|---|---|
| showdown | アクションが存在する最深ストリートの最後のアクションが `fold` でない |
| hero_won | `hero_result_bb > 0`（勝者の特定のみに使用。判断の正誤には使わない） |
| hero_last_aggressor | 攻撃ストリートの最後のアグレッシブアクションの position == hero_position |
| ポット | 攻撃ストリートの `pot_bb` + そのストリートで最終アグレッションより前のアクションの `amount_bb` 合計 |
| ベット額 | 最終アグレッシブアクションの `amount_bb` |

### GTOスコア判定（結果論の防止）

- `equity.judge_call` を呼ぶのは**攻撃ストリートが river のときのみ**。
  turn のコール/フォールドを5枚ボードで判定すると「未来のカードで過去の判断を裁く」
  結果論になるため、river 以外は常に unknown を渡す（`specs/classify.md` §3 V1と同一の制約）
- `hero_cards` 欠落時も unknown（equity側で保守的に処理）

### スコア計算の順序

```
事実抽出 → verdict（equityレンジ区間モデル）→ category/line（classify）
  → gto_math文字列 → difficulty（αは gto_math から extract_alpha で抽出）
  → nice_play_score（categoryとverdictで幸運コール除外）
```

---

## 4. V1の制約（明記）

- ヘッズアップの判断スポットを想定。マルチウェイの複雑な絡みは攻撃ストリートの
  最終アグレッションとHeroの応答のみで単純化する
- 同一ストリートの bet→raise 合戦は最後のアグレッションだけを見る
- `hero_result_bb == 0`（チョップ等）は hero_won = False 側に倒す
  （bluff_catch/value_success の誤付与を防ぐ保守側）

---

## 5. 受入基準（= テストケース）

| 入力ハンド | 期待出力 |
|---|---|
| リバーで相手ベット→Heroコール→敗北（強ハンド・判定correct） | nice_call / gray、gto_mathに「必要エクイティ」 |
| リバーで相手ベット→Heroコール→敗北（判定unknown） | call_lost / warn |
| リバーで相手ベット→Heroフォールド（判定: コール不正解） | nice_fold / gray、gto_mathに「MDF基準」 |
| ターンで相手ベット→Heroフォールド | fold_unknown / warn（river以外は判定しない）、gto_mathに「MDF」なし |
| リバーでHeroベット→相手フォールド | hero_aggression_won / red、gto_mathに「α=」 |
| リバーでHeroベット→相手コール→Hero勝利 | value_success / blue |
| リバーで相手ベット→Heroコール→勝利 | bluff_catch / blue |
| プリフロップのみで終了 | preflop_only、gto_math = "" |
| チェックダウンのショーダウン | preflop_only（判断スポットなし） |
| difficulty / nice_play_score | `specs/gto_math.md` の式と一致（例: nice_call×river×α補正） |
| 入力handの非破壊 | 呼び出し後も入力dictが変化しない |

## 変更履歴

- **2026-07-03 新規作成:** GTO-の `hand_converter.py` 相当をSPEC化。チェックダウン→preflop_only、
  river以外は判定しない（結果論防止）、hero_result_bb=0は非勝利側、の3点をV1設計判断として明記。
- **2026-07-04:** OUTPUT に `decision_street` / `decision_pot_bb` を追加
  （改善チャンス選定 `select_improve_chances` = specs/gto_math.md §4b が使用）。
