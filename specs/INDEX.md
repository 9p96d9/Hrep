# specs/INDEX.md — SDD仕様インデックス

Claude が実装作業を始める前に、このファイルを読んで該当SPECに移動する。

## SPECの読み方

- **Status: ✅ 実装済み** → コードが存在し、テスト済み
- **Status: 🔄 実装中** → コードあり、テスト未完
- **Status: 📝 Draft** → SPECのみ、未実装
- **Status: ⚠️ 要更新** → コードとSPECが乖離している疑い

> HrepNextはコーディング前段階なので、全SPECのStatusは 📝 Draft から始まる。
> 旧Hrep/GTO-に実装があっても、このフォルダにコードが入るまでは ✅ にしない。

---

## SDD対象SPEC一覧

| ファイル | 対象領域 | Status | 対応テスト |
|---|---|---|---|
| `specs/gto_math.md` | α・MDF・難易度スコア・ナイスプレイ判定 | ✅ 実装済み（`scripts/hand_converter.py`） | `tests/test_gto_math.py` |
| `specs/classify.md` | 11カテゴリ定義・ライン分類ルール | ✅ 実装済み（`scripts/hand_converter.py`） | `tests/test_classify.py` |
| `specs/ai_analysis.md` | AIプロンプト仕様・`detail_street`出力・品質ルール | 🔄 実装中（`scripts/ai_prompt.py` / `scripts/ai_validator.py`。実AI出力の検証未） | `tests/test_ai_output.py` |

---

## SDD対象外（docs/ で管理）

| ファイル | 対象領域 | 理由 |
|---|---|---|
| `docs/features/classify_result.md` | 解析結果画面UI | 自動検証不可 |
| `docs/features/nice_plays.md` | 高難度正解セクションUX | 自動検証不可 |
| `docs/features/improve_chances.md` | 改善チャンスセクションUX | 自動検証不可 |
| `docs/features/cart.md` | AI解析カート | 自動検証不可 |
| `docs/features/extension.md` | Chrome拡張 | 自動検証不可 |
| `docs/infra.md` | Cloud Run・Firestore・CI/CD | 自動検証不可 |
| `docs/data_schema.md` | JSONスキーマ・Firestore | Emulatorが必要 |

---

## 受入基準の優先順位ルール

受入基準（テストケース）が `REQUIREMENTS.md` の Must / Must Not と矛盾したら、**受入基準の方を直す**。
矛盾に気づいたら実装を止めて、先にSPECを修正してからコミットする。

## コミット時のSPEC更新ルール

```
feat: 新機能  → spec更新必須 + test:✅
fix:  バグ修正 → spec確認必須（変更があれば更新）+ test:✅
docs: ドキュメント → spec更新は任意
```
