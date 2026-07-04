# specs/gto_math.md — GTO数学・スコア定義

**Status: ✅ 実装済み**（`scripts/hand_converter.py` — compute_gto_math / compute_difficulty / compute_nice_play_score）
**実装参考:** `GTO-/scripts/analyze2.py` (`_compute_gto_math`, `_compute_difficulty`, `_compute_nice_play_score`)
**対応テスト:** `tests/test_gto_math.py`

---

## 1. 基本用語定義

```
α (Alpha)  = Bet ÷ (Pot + Bet)
           = ブラフの損益分岐フォールド率
           = コールに必要な最低エクイティ

MDF        = 1 − α
           = 相手のブラフを防ぐための最低コール頻度
           ※「フォールドしてよい頻度」ではなく「コールしなければならない最低頻度」

必要エクイティ = コール額 ÷ (コール後の最終ポット)
```

**MDF適用ルール（厳守）:**
- リバーのみ言及する
- フロップ/ターンではMDFに触れない。エクイティ・ドロー・レンジ構成で論じる
- 理由: フロップ/ターンはエクイティが残るためMDFは純粋な上限にならない

---

## 2. カテゴリ別GTO数学コンテキスト

ストリートは river → turn → flop → preflop の順で最初にアクションがある場所を使用。

### DEFENDER系（bluff_catch / nice_call / bad_call / call_lost）
```
INPUT:  相手のbet/raise額、Heroの投資額、ポット
OUTPUT: 必要エクイティ = net_call ÷ (pot_before_call + net_call)
表示例: "[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=33%"
```

### AGGRESSOR系（hero_aggression_won / value_success / bluff_failed）
```
INPUT:  HeroのBet額、ポット
OUTPUT: α = Bet ÷ (Pot + Bet)
表示例: "[GTO数学] バリュースポット | ターン | ベット=12bb / ポット=24bb | α=33%"
```

### FOLD系（fold_unknown / nice_fold / bad_fold）
```
INPUT:  相手のBet額、ポット、ストリート
OUTPUT:
  - river: MDF基準 = 1 - α
  - flop/turn: α のみ（MDFは表示しない）
表示例(river): "[GTO数学] ナイスフォールドスポット | リバー | α=33% | MDF基準=67%"
表示例(flop):  "[GTO数学] フォールドスポット | フロップ | α=40% | Heroがフォールド"
```

---

## 3. 難易度スコア

### 設計哲学
αは相手が決める（ベットサイズ次第）。Heroの難しさを直接測れない。
→ **カテゴリ（プレイの文脈）を主軸に、ストリートで補正する。**

### 計算式
```
難易度スコア = カテゴリ基礎スコア × ストリートウェイト ± α微補正
（上限 1.0 でキャップ）
```

### カテゴリ基礎スコア
| カテゴリ | スコア | 理由 |
|---|---|---|
| bluff_catch | 0.90 | 定義上コール/フォールドが拮抗 |
| nice_call | 0.90 | bluff_catchと同一の判断。結果（敗北）で難易度は変わらない |
| nice_fold | 0.85 | 定義上フォールド判断が難しい |
| hero_aggression_won | 0.70 | ブラフ実行 = 混合戦略の実行 |
| value_success | 0.50 | 正解だが難易度は様々 |
| bluff_failed | 0.30 | |
| bad_call | 0.30 | |
| bad_fold | 0.30 | |
| call_lost | 0.25 | 判定困難（warn） |
| fold_unknown | 0.25 | |
| preflop_only / その他 | 0.20 | |

### ストリートウェイト
| ストリート | 重み | 理由 |
|---|---|---|
| river | 1.0 | エクイティ確定・判断が全て |
| turn | 0.8 | |
| flop | 0.6 | 後続ストリートで修正可能 |
| preflop | 0.4 | |

### α微補正（補助的）
```
indifference = 1.0 - |2α - 1|   # α=0.5のとき最大1.0
補正値 = (indifference - 0.5) × 0.1   # ±0.05以内
```
カテゴリ判断を覆さない範囲のみ。αはgto_mathの文字列から正規表現で抽出。

### 計算例
| スポット | 計算 | スコア |
|---|---|---|
| bluff_catch × river | 0.9 × 1.0 | 0.90 |
| bluff_catch × turn | 0.9 × 0.8 | 0.72 |
| nice_fold × river | 0.85 × 1.0 | 0.85 |
| nice_fold × flop | 0.85 × 0.6 | 0.51 |
| bluff_catch × preflop | 0.9 × 0.4 | 0.36 |
| value_success × river | 0.5 × 1.0 | 0.50 |

---

## 4. ナイスプレイスコア（V1）

### 設計哲学
誤った「ベストプレイ」を一度称えたら信頼が壊れる。
→ **V1は定義上インディファレンスなカテゴリのみ対象にする。**

```
対象カテゴリ: {bluff_catch, nice_call, nice_fold} のみ
  ※ bluff_catch は GTO判定=不正解（幸運なコール）なら除外（specs/classify.md §4）
ナイスプレイスコア = 難易度スコア  （対象外カテゴリは 0.0）
表示閾値: 0.5以上
最大表示件数: 3件（難易度スコア降順）
0件の場合: 「今日のナイスプレイ: 0件」を正直に表示（セクションを非表示にしない）
```
※ REQUIREMENTS.md Must 準拠: おべっかでなく事実を出す。0件隠蔽は信頼を損なう。
※ `nice_call`（負けたが正しかったコール）は損益がマイナスのままナイスプレイに載る。
  これが「結果と判断の分離」の最も強い実演であり、このセクションの存在意義。

### V2以降の拡張候補（未実装）

#### `hero_aggression_won` リバー限定追加
```
条件:
  - category = "hero_aggression_won"
  - street = "river"
  - α ≥ 0.40（ベットサイズがポットの2/3以上。小さいブラフは難易度が低い）
  - nice_play_score 閾値: 0.70（bluff_catch/nice_fold より高く設定）

理由: リバーフォールド誘導ブラフの実行は技術的難易度が高いが、
「ベットして相手が折れた」だけでは称えられない。
α ≥ 0.40 & threshold 0.70 で誤称賛リスクを抑える。
```

#### 品質 × 難易度 × 意外性の三軸（将来）
- 意外性スコア = そのカテゴリ × ポジションの発生頻度の逆数
  （例: BTN-3betポット-OOPでの nice_fold は希少 → 意外性高）
- "そんなライン正解なの？"スポットをランク上位に押し上げる

---

## 5. 受入基準（= テストケース）

| 入力 | 期待値 |
|---|---|
| bluff_catch × river, α=0.45 | difficulty ≈ 0.90〜0.92, nice_play_score ≥ 0.5 |
| bluff_catch × turn | difficulty ≈ 0.72, nice_play_score ≥ 0.5 |
| **nice_call × river** | **difficulty ≈ 0.90, nice_play_score ≥ 0.5（損益マイナスでも対象）** |
| **bluff_catch × river（GTO判定=不正解）** | **nice_play_score = 0.0（幸運なコールは除外）** |
| nice_fold × flop | difficulty ≈ 0.51, nice_play_score ≥ 0.5 |
| bluff_catch × preflop | difficulty ≈ 0.36, nice_play_score = 0.0（閾値未満） |
| value_success × river | nice_play_score = 0.0（対象外カテゴリ） |
| hero_aggression_won × river | nice_play_score = 0.0（V1対象外） |
| 候補が4件以上 | 上位3件のみ表示 |
| 候補が0件 | **「0件」を表示する（セクションは表示されたまま）** |
| α=0.5（完全インディファレンス） | 微補正 +0.05 が適用される |
| bluff_catch × river, α=0.5 | 0.90 + 0.05 = 0.95 ≤ 1.0（キャップ確認） |

## 変更履歴

- **HrepNext初版:**
  1. Hrep版の受入基準「候補が0件 → セクション非表示」を修正。
     本文・REQUIREMENTS.md Must（0件を正直に表示）と矛盾していたため、受入基準側を訂正した。
  2. **`nice_call`（0.90）・`bad_call`（0.30）を追加**し、ナイスプレイ対象を
     {bluff_catch, nice_call, nice_fold} に拡張。bluff_catchに幸運コール除外条件を追加。
     `call_lost` は判定困難扱いに再定義し 0.30 → 0.25。
