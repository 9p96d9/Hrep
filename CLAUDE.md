# HrepNext — Claude Code 開発ガイド

## ⚠️ 現在の開発状況 — セッション間の引き継ぎ（2026-07-04）

開発は2セッションに分岐している:

1. **純粋関数レイヤー**（`scripts/` 一式 + `tests/` 81件 + CI）→ **PR #2**
   （ブランチ `claude/continuation-development-sio204`）で実装済み・マージ待ち。
   分類→スコア→AIプロンプト→出力検証まで実装済み（`specs/INDEX.md` 参照）。
2. **Cloud Runアプリ本体**（スキャフォールド）→ 別セッションで開発中。

**アプリ側セッションへの注意:** `scripts/`（`hand_converter.annotate_hand`・`ai_prompt`）は
**PR #2 がマージされるまで main に存在しない**。PR #2 マージ後の main から作業するか、
`claude/continuation-development-sio204` から分岐すること。純粋関数レイヤーの重複実装は禁止。

> この節は両ブランチが main に合流したら削除する。

## プロダクト哲学

収支グラフが決して教えてくれない真実——分散と切り離した「お前は本当に良い判断をしたか」——を、裁きではなく成長として届ける装置。

良い気分は必ず「難しさ × 正しさ」で稼がせる。活動量・ストリーク・セッション数では稼がせない。

## 作業ルール（3行）

1. 実装前に `specs/` の該当SPECを読む（なければ `/spec-update` で先に書く）
2. 実装後にSPECのStatusを更新してからコミット — メッセージに `test:✅` or `test:skip+理由` を含める
3. UI・インフラの変更は `docs/` も更新する。**スキルが参照するインフラが変わったら `.claude/skills/` も同じコミットで更新する**（Hrep時代の最大の負債はスキルの腐敗だった）

## SKILLインデックス

| コマンド | 起動タイミング |
|---|---|
| `/poker-brain-pre` | AI解析実行前・スポット読みが必要なとき |
| `/poker-brain-post` | AI解析出力のレビュー・品質確認をするとき |
| `/deploy-check` | デプロイ後の確認・Cloud Run状態・Actionsログを見るとき |
| `/error-diagnose` | 本番でエラーが発生したとき |
| `/cost` | GCP無料枠の消費確認・設計のコスト影響を判断するとき |
| `/spec-update` | 新機能のSPEC作成・既存SPECの更新をするとき |

## 詳細参照先

| 目的 | ファイル |
|---|---|
| プロダクト要件・禁止事項 | `REQUIREMENTS.md` |
| SDD対象仕様（テストと直結） | `specs/INDEX.md` |
| UI・機能の振る舞い | `docs/features/` |
| インフラ構成（Cloud Run + Firestore） | `docs/infra.md` |
| データ形式・Firestoreスキーマ | `docs/data_schema.md` |
| テスト計画 | `tests/PLAN.md` |
| harness設計の判断記録（hooks比較含む） | `docs/harness_design.md` |
| Hrepからの変更点 | `CHANGES.md` |

## 旧バージョンの場所（参照のみ・変更しない）

| 場所 | 内容 |
|---|---|
| GitHub `9p96d9/GTO-`（ローカル: `../GTO-/`） | コーディング済み・本番稼働実績のある初代。実装の参考コードはここ |
| `docs/legacy.md` | 旧AWS構成・PostgreSQLスキーマの記録（再作成しない） |

> 仕様策定段階の旧Hrepフォルダは2026-07に削除済み。必要な内容は本リポジトリに退避済み
> （LEGACY記録 → `docs/legacy.md`、Fable 5実験 → `experiments/test_fable5.py`）。
