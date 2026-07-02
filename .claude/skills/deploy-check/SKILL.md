---
name: deploy-check
description: デプロイ確認の手順。git push後のGitHub Actions進捗・Cloud Runの状態・本番ヘルスチェックを一連で実行する。デプロイ前チェック(--pre)も含む。
argument-hint: "引数なし=Actions+ヘルスチェック / --cloudrun=サービス詳細 / --pre=デプロイ前チェック"
---

# /deploy-check — デプロイ確認・Cloud Run状態確認

> 構成の事実（URL・環境変数・設定値）は `docs/infra.md` が正。このスキルは手順のみを持つ。
> **手順と docs/infra.md が食い違ったら、このスキルを直してからコミットする。**

---

## Step 1: GitHub Actions 確認

```bash
gh run list --limit 5
```

実行中のrunがある場合:
```bash
gh run view --log
```

失敗している場合 → `/error-diagnose` に切り替える。

---

## Step 2: 本番ヘルスチェック

```bash
curl -s https://hrep.app/health
# → {"status": "ok"} が返れば正常
```

---

## Step 3: Cloud Run サービス状態（--cloudrun）

```bash
# サービス概要（リビジョン・トラフィック・環境変数名）
gcloud run services describe <SERVICE_NAME> --region asia-northeast1

# 直近ログ
gcloud run services logs read <SERVICE_NAME> --region asia-northeast1 --limit 50

# エラーのみ
gcloud run services logs read <SERVICE_NAME> --region asia-northeast1 --limit 200 | grep -i error
```

SERVICE_NAME・リージョンは `docs/infra.md` で確認する（このスキルに直書きしない）。

---

## デプロイ前の必須チェック（--pre）

```bash
# 1. テスト
pytest tests/ -v --tb=short

# 2. 全Pythonファイル構文チェック
python -c "
import ast, pathlib
for p in pathlib.Path('.').rglob('*.py'):
    if '_archive' in str(p) or '__pycache__' in str(p): continue
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError as e:
        print(f'ERROR: {p} - {e}')
"

# 3. static/*.js を変更した場合 → テンプレートの ?v=YYYYMMDD 更新を確認
git diff --name-only HEAD | grep -q "static/" && echo "⚠️ キャッシュバスト ?v= の更新を確認"
```

---

## コミット・プッシュの手順

```bash
git add <files>
git commit -m "feat/fix: 変更内容 test:✅"   # または test:skip+理由
git push origin main
gh run list --limit 3
```

---

## $ARGUMENTS の使い方

引数なし → Step 1-2（Actions確認 + ヘルスチェック）
`--cloudrun` → Step 3（Cloud Run詳細）
`--pre` → デプロイ前チェックを実行
