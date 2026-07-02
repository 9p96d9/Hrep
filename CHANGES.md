# CHANGES.md — Hrep からの変更点（HrepNext 初版・2026-07-02）

コーディング開始前の全面見直し。原本: 旧Hrepフォルダ（仕様策定段階・2026-07に削除、必要分は `docs/legacy.md` と `experiments/` に退避）、実装参考: GitHub `9p96d9/GTO-`（本番稼働実績あり）。

---

## 1. 矛盾の修正（バグだったもの）

| 箇所 | Hrepの状態 | 修正 |
|---|---|---|
| `specs/gto_math.md` 受入基準 | 「候補が0件 → セクション非表示」— 本文とREQUIREMENTS.md Must（0件を正直に表示）に矛盾 | 受入基準を「0件を表示する」に訂正 |
| `specs/classify.md` ライン定義 | 「red = ショーダウンなし」なのに bluff_failed / call_lost（ショーダウン敗北）がred | カテゴリ→ライン対応表を唯一の正とし、ライン定義を書き直し |
| `.claude/settings.json` | `Bash(gh *)` 等の無効構文で許可ルールが全滅 | `Bash(gh:*)` 形式に修正 + deny追加 |
| スキル3本（deploy-check / error-diagnose / cost） | 削除済みのEC2・PostgreSQL・Cloudflare・AWS手順のまま。旧リポジトリURLも残存 | Cloud Run + Firestore + GCP手順に全面書き換え |

## 2. プロダクトの構造変更（採用された提案）

### ① `nice_call` / `bad_call` 導入 — 判断と結果の分離をコール側にも適用
旧体系はコールを結果だけで分類していた（勝てばbluff_catch、負ければcall_lost）。
「正しいコールで負けた」を検出する `nice_call`（gray・難易度0.90・ナイスプレイ対象）と
`bad_call`（red・改善チャンス対象）を新設。9 → **11カテゴリ**。
`call_lost` は「判定困難なコール負け（warn）」に再定義。
さらに `bluff_catch` に幸運コール除外条件を追加（勝っていてもGTO判定が不正解なら称えない）。
→ `specs/classify.md` §0・§4、`specs/gto_math.md` §4

### ③ 改善チャンスセクション新設
「ポジティブ先頭は硬い真実の配送手段」という哲学の**荷物側**が未設計だった。
GTO判定で不正解が確定した bad_fold / bad_call のみを、ナイスプレイと同じ客観トーンで
直後に表示するセクションを設計（誤指摘防止のためwarn系・bluff_failedは対象外）。
→ `docs/features/improve_chances.md`（新規）、REQUIREMENTS.md Must / Must Not に追記

### 見送り（V2候補としてREQUIREMENTS.mdに記録）
- ② KPIの担当機能（コンテンツ駆動の再オープン通知・週次成績曲線）
- ④ 3betポット難易度補正・誤称賛報告ボタン・preflop_rangesのデータ資産化

## 3. SPECの整理

- `detail_street` モードをDraft付録から**正式版**に昇格。旧 `detail` は移行期間のみ、`standard` は廃止
- AIプロバイダーは Groq/Gemini BYOK を維持（ユーザー判断）。Claude Fable 5 はSPEC外の品質実験と明記
- 全SPECのStatusを 📝 Draft に統一（このフォルダにコードが入るまで ✅ にしない）
- 受入基準の優先順位ルールを明文化: REQUIREMENTS.md の Must/Must Not > 受入基準

## 4. harness の再設計（docs/harness_design.md に判断記録）

- **原則1: 事実はdocs、手順はskills** — スキル腐敗の根本原因（事実の直書き）を構造で排除
- **原則2: 不変ルールのhooks強制** — 採否未決定（比較表は harness_design.md）。ベースラインで構築済み
- **原則3: 非対称permissions** — 参照系は自動許可 / 破壊系（強制push・サービス削除・.env読み取り）はdeny
- スキルを旧 `.claude/commands/*.md` から現行の `.claude/skills/<name>/SKILL.md`（frontmatter付き）へ移行
- `PYTHONUTF8=1` を環境変数に設定（GTO-時代のWindowsエンコーディング事故の根絶）

## 5. docs の整理

- `docs/infra.md` / `docs/data_schema.md` から [LEGACY] 実体を分離し、`docs/legacy.md` に集約（再作成防止の記録）
- `docs/features/cart.md` のA/B/Cデザインバリアントを廃止（開発実験の残骸）。右ドロワーに一本化
- Chrome Web Storeリリース準備をV1ゴールとして明記（extension.md）

## 未完了（次のステップ）

- [x] hooks採否の決定 → **採用・実装・動作テスト済み**（`.claude/hooks/` 2本）
- [ ] コーディング開始（specs/INDEX.md の Draft から着手順を決める）
- [ ] GCPプロジェクトのCLI初期設定（`docs/infra.md` の「コンソールレス運用方針」参照）
