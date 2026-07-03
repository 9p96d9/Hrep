# docs/infra.md — インフラ構成

**種別: 参考ドキュメント（テストなし）**
**オペレーション手順 → `/deploy-check` SKILLを使う**

---

## 構成（Cloud Run + Firestore）

```
[Chrome拡張]
    ↓ HTTPS POST（hrep.app / *.run.app）
[Google Cloud Run]
  └─ FastAPI + uvicorn（Docker）
       └─ Firebase Admin SDK → Firestore（ハンドストレージ）
```

| 項目 | 値 |
|---|---|
| ドメイン | hrep.app（Cloudflare DNS管理）+ Cloud Run URL |
| バックエンド | Google Cloud Run（Docker） |
| DB | Firebase Firestore |
| 認証 | Firebase Auth（Google） |
| CI/CD | GitHub Actions → Cloud Run deploy |

### コスト概算（月額）

| 項目 | 費用 |
|---|---|
| Cloud Run | 無料枠内（リクエスト200万/月、低負荷なら$0） |
| Firestore | 無料枠内（読み取り50k/日、書き込み20k/日、1GB保存） |
| Firebase Auth | 無料枠内（MAU 10,000まで） |
| Groq / Gemini API | $0（BYOK・ユーザー負担） |
| **合計** | **~$0/月** |

### 環境変数

| 変数名 | 用途 |
|---|---|
| `FIREBASE_API_KEY` | Firebase Auth用 |
| `FIREBASE_AUTH_DOMAIN` | Firebase Auth用 |
| `FIREBASE_PROJECT_ID` | Firebase Auth用 |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Firebase Admin SDK（**JSON文字列**でSecret Manager経由。ファイルパスではない） |
| `GROQ_API_KEY` | サーバー側デフォルトAI（オプション） |
| `GEMINI_API_KEY` | Geminiフォールバック（オプション） |

### Google Cloud プロジェクト

| 項目 | 値 |
|---|---|
| プロジェクト名 | HandReporter |
| プロジェクトID | `poker-gto`（変更不可・永久固定） |
| OAuth同意画面アプリ名 | HandReporter |

---

## デプロイフロー

```
git push origin main
  ↓
GitHub Actions (google-github-actions/deploy-cloudrun)
  ↓
Docker build → Cloud Run deploy
  ↓
完了 → curl https://hrep.app/health で確認
```

### テストCI（`.github/workflows/test.yml`）

全push/PRで `pytest tests/` を実行する（Python 3.11・依存は pytest + python-dotenv のみ）。
DB・外部API・secretsは不要（tests/PLAN.md の純粋関数テスト原則）。デプロイワークフローとは独立。

### Cloud Run 設定注意点

- SSEストリーミングのため `--timeout=3600` を明示設定（デフォルト60秒では切れる）
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` はファイルパスでなくJSON文字列として渡す
- Cloud Run は HTTPS URL 自動発行。Chrome拡張側のエンドポイントURLと一致しているか確認

---

## コンソールレス運用方針（CLI-first）

**原則: GCP/Firebaseの設定操作はVSCode内のClaude Codeから `gcloud` / `firebase` CLI で行う。**
MCPサーバーは不要——Claude Codeはターミナル経由でCLIを直接実行できるため、
CLIが対応している操作はすべて会話から実行可能。コンソールを開くのは下表の「コンソール必須」のみ。

### CLIで完結できる操作（＝Claude Codeに頼めばよい）

| 操作 | コマンド例 |
|---|---|
| デプロイ | `gcloud run deploy <SERVICE> --source .` |
| 環境変数の設定 | `gcloud run services update <SERVICE> --set-env-vars KEY=VALUE` |
| シークレット管理 | `gcloud secrets create / versions add` |
| タイムアウト等の設定変更 | `gcloud run services update <SERVICE> --timeout=3600` |
| カスタムドメイン割当 | `gcloud run domain-mappings create` |
| ログ閲覧 | `gcloud run services logs read`（`/deploy-check` 参照） |
| ロールバック | `gcloud run services update-traffic --to-revisions <REV>=100` |
| API有効化 | `gcloud services enable run.googleapis.com firestore.googleapis.com` |
| IAM・サービスアカウント | `gcloud iam service-accounts create / gcloud projects add-iam-policy-binding` |
| Firestoreルール・インデックス | `firebase deploy --only firestore:rules,firestore:indexes` |
| 予算アラート作成 | `gcloud billing budgets create` |
| GitHub Actions用の鍵発行 | `gcloud iam service-accounts keys create` → `gh secret set` |

### コンソール必須（CLI不可・初回のみ）

| 操作 | 理由 | 頻度 |
|---|---|---|
| 課金アカウント作成（クレカ登録） | 決済情報はコンソールのみ | 初回1回 |
| OAuth同意画面の設定 | 一部項目がコンソール限定 | 初回1回（設定済み） |
| Firebase Auth プロバイダー（Googleログイン）の有効化トグル | Firebaseコンソール限定 | 初回1回（設定済み） |
| Chrome Web Store への拡張公開 | 別ダッシュボード | リリース時 |

> 既存プロジェクト `poker-gto` はOAuth・Auth設定済みなので、実質コンソールを触る場面はほぼない。
> 新しい設定作業が出たら、まずCLIでできるか調べる → できなければこの表に追記してからコンソールへ。

---

## 旧構成の記録

AWS EC2 / PostgreSQL / Cloudflare Tunnel 構成（〜2026-05）と削除済みリソース一覧は
`docs/legacy.md` を参照。**再作成しない。**
