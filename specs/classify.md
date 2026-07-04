# specs/classify.md — ハンド分類定義

**Status: ✅ 実装済み**（V1範囲。エクイティ判定はリバーのみ・フロップ/ターンは設計通りunknownに倒れる。ハンドJSON→分類入力の変換は `hand_converter` 相当として別途）
**実装:** `scripts/classify.py`（分類フロー・判定機構）+ `scripts/equity.py`（レンジ区間モデル）
**対応テスト:** `tests/test_classify.py`, `tests/test_equity.py`

---

## 0. 設計原則 — 判断と結果の分離はコール側にも適用する

旧体系（GTO-/Hrep）の欠陥: フォールドにはGTO判定（nice_fold/bad_fold）があるのに、
コールは**結果だけ**で分類していた（勝てばbluff_catch、負ければcall_lost）。
「必要エクイティを満たす正しいコールで負けた」は、収支グラフが嘘をつく典型スポットであり、
このプロダクトが「正解だ」と言うべき本丸である。

→ フォールド側と同一のGTO判定機構をコール敗北にも適用し、`nice_call` / `bad_call` を導入する。

---

## 1. ライン分類（5種）

`bluered_classification.line` フィールドに格納される値。

**ラインはUI上のグルーピングであり、ショーダウンの有無そのものではない。**
判定の正とするのはカテゴリ→ライン対応表（§4）である。

| line 値 | 定義 | UIフィルター |
|---|---|---|
| `blue` | ショーダウンでHeroが勝利したハンド | 「青線」フィルター対象 |
| `red` | 損失またはノーショーダウン勝利で、判断の検証が必要なハンド | 「赤線」フィルター対象 |
| `gray` | GTO的に正しい判断（`nice_fold` / `nice_call` 専用） | フィルター対象外（高難度正解セクションで別途表示） |
| `warn` | 正誤の判定が困難な判断（`fold_unknown` / `call_lost` 専用） | フィルター対象外 |
| `preflop_only` | プリフロップのみで終了 | フィルター対象外 |

> `gray` と `warn` は「赤線フィルター」に出ない。
> gray は高難度正解セクションで優先表示されるため、赤線フィルターからの除外は意図的。

---

## 2. カテゴリ定義（11種）

### Blue Line カテゴリ（ショーダウン勝利）

| カテゴリキー | 日本語ラベル | 定義 |
|---|---|---|
| `value_success` | バリュー成功 | Heroがバリューベットし、相手がコールした上でHeroが勝利 |
| `bluff_catch` | ブラフキャッチ | Heroが相手のベットに対してコールし、ショーダウンでHeroが勝利（相手がブラフだった） |

### Gray Line カテゴリ（GTO的に正しい判断・結果を問わない）

| カテゴリキー | 日本語ラベル | 定義 |
|---|---|---|
| `nice_fold` | ナイスフォールド | Heroが相手のベットにフォールドし、GTO的に正しいフォールドと判断されるスポット |
| `nice_call` | ナイスコール | **Heroが相手のベットにコールしてショーダウンで敗北したが、GTO的に正しいコールと判断されるスポット（損失は分散）** |

### Red Line カテゴリ（判断に問題がある、またはノーショーダウン勝利）

| カテゴリキー | 日本語ラベル | 定義 |
|---|---|---|
| `hero_aggression_won` | アグレッション勝利 | Heroがベット/レイズし、相手がフォールド（ノーショーダウン勝利） |
| `bluff_failed` | ブラフ失敗 | Heroがベット/レイズしたが相手にコールされ、ショーダウンでHeroが敗北 |
| `bad_call` | バッドコール | Heroが相手のベットにコールして敗北し、GTO的にフォールドが正解だったと判断されるスポット |
| `bad_fold` | バッドフォールド | Heroが相手のベットにフォールドしたが、GTO的にコールが正解だったと判断されるスポット |

### Warn / 中立カテゴリ

| カテゴリキー | 日本語ラベル | ライン | 定義 |
|---|---|---|---|
| `call_lost` | コール負け(要確認) | warn | コールして敗北したが、正誤の判定が困難なスポット |
| `fold_unknown` | フォールド(要確認) | warn | フォールドしたが、正誤の判定が困難なスポット |
| `preflop_only` | プリフロップのみ | preflop_only | ポストフロップアクションなし。フォールドまたはオールイン解決 |

---

## 3. 分類の判定フロー

```
1. プリフロップのみで終了？ → preflop_only

2. ショーダウンあり？
   YES:
     - Heroが最後にベット/レイズし勝利 → value_success
     - 相手がベットしHeroがコールして勝利 → bluff_catch
     - Heroがベット/レイズし相手コールで敗北 → bluff_failed
     - 相手ベットにHeroがコールして敗北:
         - GTOスコア判定: 正解   → nice_call
         - GTOスコア判定: 不正解 → bad_call
         - 判定困難             → call_lost

   NO（フォールドで終了）:
     - Heroがベット/レイズし相手フォールド → hero_aggression_won
     - 相手ベットにHeroがフォールド:
         - GTOスコア判定: 正解   → nice_fold
         - GTOスコア判定: 不正解 → bad_fold
         - 判定困難             → fold_unknown
```

### GTOスコア判定（コール/フォールド共通機構）

- フォールド側・コール側とも同一機構（下記V1アルゴリズム）で「コールが正解か」を判定し、
  フォールド側は反転して解釈する（コール正解のフォールド = bad_fold）
- **判定困難への倒し方は保守的にする**: 誤って「正解」と言えばナイスプレイの信頼が壊れ、
  誤って「不正解」と言えば改善チャンスの信頼が壊れる。迷ったら warn

#### V1 アルゴリズム — レンジ区間モデル（`scripts/equity.py`）

**対象はリバーの判断のみ。** フロップ/ターンはエクイティが未確定で、静的ヒューリスティックは
誤判定リスクが高いため、V1では常に判定困難（unknown）を返す（`specs/gto_math.md` §1 の
「リバーのみエクイティ確定」と同じ思想）。

```
INPUT:  hero_cards（2枚）, board（5枚）, required_equity（specs/gto_math.md §2 DEFENDER系）
OUTPUT: verdict ∈ {correct, incorrect, unknown}

1. 残り45枚から相手の2枚コンボ C(45,2)=990 通りを列挙し、
   treys評価でボード上の強さ順にランクする（全列挙・乱数なし）
2. 相手のベットレンジは不明なので、単一の推定でなく「もっともらしいレンジ族」に対する
   エクイティ区間を計算する:
     - 楽観バウンド = 全コンボ均一レンジ（最大ブラフ想定）に対するエクイティ
     - 悲観バウンド = 強い順に上位1/3のレンジ（バリュー寄り想定）に対するエクイティ
     equity(range) = (勝ちコンボ数 + 0.5×引き分け) ÷ |range|
3. 区間全体が必要エクイティの同じ側にあるときだけ断定する（margin = 0.10）:
     - 悲観バウンド ≥ required + margin → correct
       （= 強いレンジを想定してもコールは浮く）
     - 楽観バウンド ≤ required − margin → incorrect
       （= 最大限ブラフを想定してもコールは沈む）
     - それ以外 → unknown（区間が跨ぐ = 相手レンジの想定次第で答えが変わる）
```

定数: `PESSIMISTIC_TOP_FRACTION = 1/3`, `JUDGE_MARGIN = 0.10`（`scripts/classify.py` と共有）。
依存: `treys`（純Python。CI: `.github/workflows/test.yml` でインストール）。

---

## 4. カテゴリとライン・難易度の対応（この表が正）

| カテゴリ | ライン | 難易度基礎スコア | ナイスプレイV1対象 |
|---|---|---|---|
| value_success | blue | 0.50 | ✗ |
| bluff_catch | blue | 0.90 | ✅（GTO判定=不正解なら除外） |
| nice_call | gray | 0.90 | ✅ |
| nice_fold | gray | 0.85 | ✅ |
| hero_aggression_won | red | 0.70 | ✗ |
| bluff_failed | red | 0.30 | ✗ |
| bad_call | red | 0.30 | ✗（改善チャンス対象） |
| bad_fold | red | 0.30 | ✗（改善チャンス対象） |
| call_lost | warn | 0.25 | ✗ |
| fold_unknown | warn | 0.25 | ✗ |
| preflop_only | preflop_only | 0.20 | ✗ |

> `nice_call` の基礎スコアが `bluff_catch` と同じ0.90である理由:
> 両者は**同一の判断**（相手のベットに対するコール）であり、違いは結果だけ。
> 難易度が結果で変わるなら、それは結果論であり哲学違反。

> `bluff_catch` の除外条件: ショーダウンで勝っていても、GTO判定が「不正解のコール」なら
> それは幸運なコールでありナイスプレイに出さない（誤称賛防止）。判定困難の場合は
> ショーダウン勝利という追加証拠を考慮して対象に残す。

---

## 5. 受入基準（= テストケース）

| 入力ハンド | 期待カテゴリ | 期待ライン |
|---|---|---|
| ポストフロップ、Heroコール、ショーダウン勝利 | bluff_catch | blue |
| ポストフロップ、Heroベット、相手コール、Hero勝利 | value_success | blue |
| ポストフロップ、Heroベット、相手フォールド | hero_aggression_won | red |
| ポストフロップ、Heroベット、相手コール、Hero敗北 | bluff_failed | red |
| コール敗北・GTO判定=正解 | **nice_call** | **gray** |
| コール敗北・GTO判定=不正解 | **bad_call** | **red** |
| コール敗北・判定困難 | call_lost | warn |
| フォールド・GTO判定=正解 | nice_fold | gray |
| フォールド・GTO判定=不正解 | bad_fold | red |
| フォールド・判定困難 | fold_unknown | warn |
| プリフロップのみ | preflop_only | preflop_only |

### GTOスコア判定（レンジ区間モデル・`tests/test_equity.py`）

| 入力（リバー・required=必要エクイティ） | 期待verdict |
|---|---|
| クワッズ（AhAd / As Ac 7d 5h 2c）, required=0.42 | correct |
| トップペア好キッカー（KdJd / Ks Qd 9c 8s 2h）, required=0.42 | correct |
| ミドルペア（8d7d / Ks Qd 9c 8s 2h）, required=0.35 | unknown（区間が跨ぐ） |
| 4ハイ（4d3h / Ks Qd 9c 8s 2h）, required=0.30 | incorrect |
| ボードが5枚未満（リバー未到達） | unknown（V1はリバーのみ判定） |
| 任意の入力 | 悲観バウンド ≤ 楽観バウンド（区間の整合性） |
| required が None | unknown |

## 変更履歴

- **HrepNext初版:**
  1. Hrep版のライン定義「blue = ショーダウンに至った / red = ショーダウンなし」を廃止
     （カテゴリ表と矛盾していた）。カテゴリ→ライン対応表（§4）を唯一の正とした。
  2. **`nice_call` / `bad_call` を新設**。コール敗北を結果でなくGTO判定で3分割し、
     「負けたが正しかったコール」をナイスプレイ候補に昇格（§0の設計原則）。
     `call_lost` は「判定困難なコール負け（warn）」に再定義。
  3. `bluff_catch` のナイスプレイ対象に「GTO判定=不正解なら除外」条件を追加（幸運なコールの誤称賛防止）。
- **2026-07-03 実装（`scripts/classify.py`）:**
  1. §3の分類フローと GTOスコア判定機構（`judge_call_correctness`: 必要エクイティ±0.10の
     中間帯は判定困難に倒す）を実装。§5受入基準は全件テスト済み。
  2. treys評価によるHeroハンド強度（`hero_equity`）の算出は未実装。実装までは
     verdict=unknown（warn）に倒れるため、誤称賛・誤指摘は発生しない（保守的側に安全）。
- **2026-07-03 実装（`scripts/equity.py`）— GTOスコア判定のV1アルゴリズムを具体化:**
  1. 単一の `hero_equity` 点推定でなく**レンジ区間モデル**を採用。相手のベットレンジは
     不明なので、悲観バウンド（上位1/3レンジ）と楽観バウンド（均一レンジ）の区間を計算し、
     区間全体が必要エクイティの同じ側にあるときだけ断定する。跨いだらunknown。
     旧SPECの「閾値を上回るか下回るか」より保守的で、誤称賛・誤指摘の両方を構造的に防ぐ。
  2. **V1はリバーのみ判定**とした。フロップ/ターンはエクイティ未確定で静的判定の
     誤りリスクが高いため常にunknown（`specs/gto_math.md` §1「リバーのみエクイティ確定」と同思想）。
     結果: nice_fold/bad_fold/nice_call/bad_call はV1ではリバーの判断にのみ付与される。
  3. 全列挙（C(45,2)=990コンボ・乱数なし）で決定的。依存に treys を追加
     （純Python・CI変更は `.github/workflows/test.yml` と `tests/PLAN.md` に反映済み）。
