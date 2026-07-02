---
name: spec-update
description: SPECを実装前に書く（または更新する）ための手順とテンプレート。新機能の実装前・既存SPECが現実と乖離しているときに使う。「コードが先・SPECが後」を防ぐ。
argument-hint: "[spec-name] / new:[spec-name]（テンプレート生成）"
---

# /spec-update — SPEC更新・新機能設計

## いつSPECを書くか

| ケース | 対応 |
|---|---|
| 新しい計算ロジックを追加する | 実装前に `specs/` に新ファイルを作る |
| 既存の計算ロジックを変更する | 実装前に既存SPECを更新する |
| UIのみの変更 | `docs/features/` を更新（SPECは不要） |
| バグ修正（ロジック変更なし） | SPECの受入基準が間違っていた場合のみ更新 |
| インフラ変更 | `docs/infra.md` と **`.claude/skills/` の該当手順** を同時更新 |

## SPECを書くときの必須チェック

- [ ] 受入基準が `REQUIREMENTS.md` の Must / Must Not と矛盾していないか
      （矛盾したら受入基準の方がバグ。specs/INDEX.md の優先順位ルール参照）
- [ ] 受入基準の各行が `tests/PLAN.md` のテストケースに1:1で対応づくか
- [ ] 変更が他SPECに波及しないか（例: カテゴリ追加 → classify / gto_math / nice_plays / improve_chances）

---

## SPECファイルの形式テンプレート

```markdown
# specs/{name}.md — {機能名}

**Status: 📝 Draft** （→ 🔄 実装中 → ✅ 実装済み）
**実装ファイル:** `scripts/xxx.py`
**対応テスト:** `tests/test_xxx.py`

---

## 1. 設計意図（なぜこの機能が必要か）

## 2. INPUT / OUTPUT

INPUT:  hand: dict（フィールド名と型）
OUTPUT: float 0.0〜1.0

## 3. ルール・制約

## 4. 受入基準（= テストケース）

| 入力 | 期待出力 |
|---|---|

## 5. V2以降の拡張候補（オプション）

## 変更履歴
```

---

## SPEC更新フロー（実行順）

### Step 1: 影響範囲の確認
```bash
grep -rn "関数名" scripts/ routes/ html_pages/
```

### Step 2: SPECを更新
- `specs/INDEX.md` のステータスを `🔄 実装中` に変更
- 該当SPECの受入基準を更新
- 変更の理由を `## 変更履歴` セクションに追記

### Step 3: 実装

### Step 4: テストを書く
`tests/PLAN.md` の対象テストを実装する。

### Step 5: コミット
```
git commit -m "feat: {機能名} [spec:updated] test:✅"
```

### Step 6: SPECのステータスを `✅ 実装済み` に更新

---

## `specs/INDEX.md` の更新ルール

| 変更内容 | INDEX更新 |
|---|---|
| 新SPEC作成 | 行を追加 |
| 実装完了 | Status を ✅ に変更 |
| 廃止 | Status を ⚠️廃止 に変更し行を残す |

---

## $ARGUMENTS の使い方

引数なし → 現在のSPEC一覧とステータスを表示
`[spec-name]` → 既存SPECを読み込んで現状との乖離を確認
`new:[spec-name]` → 新SPECのテンプレートを生成
