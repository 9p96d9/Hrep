# HrepNext

> 勝ったか？ではなく、上手かったか？を答える装置。

多くのポーカーツールは結果を説明する。HrepNextは結果から切り離された実力を証明する。
収支グラフが決して教えてくれない真実——分散と切り離した「お前は本当に良い判断をしたか」——を、
裁きではなく成長として届ける。（詳細: [`REQUIREMENTS.md`](REQUIREMENTS.md)）

## 構成

```
[Chrome拡張 (extension/)]
    ↓ HTTPS POST /api/hand-capture
[Google Cloud Run]
  └─ Flask + gunicorn (main.py)
       └─ Firebase Admin SDK → Firestore（ハンドストレージ）
```

- バックエンド: Google Cloud Run（Docker, Flask + gunicorn）/ リージョン `asia-northeast1`
- DB: Firebase Firestore ／ 認証: Firebase Auth（Google）
- CI/CD: GitHub Actions → Cloud Run deploy
- ドメイン: hrep.app（Cloudflare DNS）+ Cloud Run URL

詳細は [`docs/infra.md`](docs/infra.md)。

## ディレクトリ構成

| パス | 内容 |
|---|---|
| `main.py` | Flaskサーバー（エントリポイント・APIルート） |
| `scripts/` | ハンド整形・分類・GTO数学（`hand_converter.py` ほか） |
| `services/` | Firestore など外部サービス連携 |
| `templates/` `static/` | WebアプリのUI |
| `extension/` | Chrome拡張（MV3・ハンドキャプチャ） |
| `specs/` | SDD対象仕様（テストと直結） |
| `docs/` | インフラ・データ・機能仕様のドキュメント |
| `tests/` | テスト（pytest） |

## ローカル起動

```bash
pip install -r requirements.txt
python main.py
```

Firestore未設定のローカル開発では認証は `dev-local` にフォールバックする（`main.py` current_uid）。

## テスト

```bash
pytest tests/
```

## Chrome拡張

`extension/` を `chrome://extensions`（デベロッパーモード）から「パッケージ化されていない拡張機能を読み込む」で読み込む。
仕様と実装状況は [`docs/features/extension.md`](docs/features/extension.md) を参照。

## 詳細ドキュメント

| 目的 | ファイル |
|---|---|
| プロダクト要件・禁止事項 | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| SDD対象仕様（テストと直結） | [`specs/INDEX.md`](specs/INDEX.md) |
| UI・機能の振る舞い | [`docs/features/`](docs/features/) |
| インフラ構成（Cloud Run + Firestore） | [`docs/infra.md`](docs/infra.md) |
| データ形式・Firestoreスキーマ | [`docs/data_schema.md`](docs/data_schema.md) |
| テスト計画 | [`tests/PLAN.md`](tests/PLAN.md) |
| harness設計の判断記録 | [`docs/harness_design.md`](docs/harness_design.md) |
| Hrepからの変更点 | [`CHANGES.md`](CHANGES.md) |
| 開発ガイド（Claude Code） | [`CLAUDE.md`](CLAUDE.md) |
