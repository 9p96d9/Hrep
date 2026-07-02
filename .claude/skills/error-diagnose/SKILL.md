---
name: error-diagnose
description: 本番エラーの診断手順。ai / firestore / cloudrun / extension / python のカテゴリ別に診断コマンドと典型原因を提示する。本番でエラーが発生したとき・ログに異常が出たときに使う。
argument-hint: "[ai|firestore|cloudrun|extension|python]（省略時は症状から振り分け）"
---

# /error-diagnose — エラー診断

> 構成の事実は `docs/infra.md`・`docs/data_schema.md` が正。このスキルは診断手順のみを持つ。

---

## `ai` — AI API エラー

**症状:** `429 rate_limit` / `503 UNAVAILABLE` / JSON解析エラー

```
# レートリミット → リトライ間隔を確認（analyze2系の RETRY_WAIT）
# 503 → プロバイダー障害。Groq/Gemini の status ページを確認
# JSON解析エラー → AIがコードブロック記号を付けた可能性（_parse_json_response を確認）
# detail_street で未到達ストリートが空文字でない → バリデーター（tests/test_ai_output.py の関数）に通す
```

**切り替え:** `gsk_` で始まるキー → Groq / それ以外 → Gemini（`specs/ai_analysis.md` §2）

---

## `firestore` — Firestore エラー

**症状:** `PERMISSION_DENIED` / ドキュメントが見つからない / 1MB超過エラー

```
# 権限 → GOOGLE_APPLICATION_CREDENTIALS_JSON がJSON文字列で渡っているか（ファイルパスはNG）
# 見つからない → order_by("saved_at") を使っているか（captured_atは欠落あり）
# 1MB超過 → hand_json が hands サブコレクションに置かれているか（docs/data_schema.md）
```

典型ミス集は `docs/data_schema.md` の「よくあるミス」を参照。

---

## `cloudrun` — Cloud Run 起動・応答エラー

**症状:** 502/503 / コールドスタート後に落ちる / SSEが60秒で切れる

```bash
# 直近のエラーログ
gcloud run services logs read <SERVICE_NAME> --region asia-northeast1 --limit 100 | grep -i -E "error|traceback"

# リビジョン状態（直前のデプロイで壊れたか）
gcloud run revisions list --service <SERVICE_NAME> --region asia-northeast1
```

**よくある原因:**
- SSE切断 → `--timeout=3600` が設定されているか（`docs/infra.md` 注意点）
- 起動失敗 → 構文エラー（ログに `SyntaxError`）・環境変数不足
- 旧リビジョンに戻す: `gcloud run services update-traffic <SERVICE_NAME> --to-revisions <REV>=100`

---

## `extension` — Chrome拡張エラー

```
# background のログは chrome://extensions → Service Worker「検証」で見る（/sessionsのコンソールではない）
# ハンドが届かない → interceptor.js の傍受ON確認 → POST /api/hand-capture のレスポンスコード確認
# エンドポイントURL → インフラ移行後に拡張側の向き先が更新されているか（docs/features/extension.md）
```

---

## `python` — 構文・インポートエラー

```bash
python -c "
import ast, pathlib
for p in pathlib.Path('.').rglob('*.py'):
    if '_archive' in str(p) or '__pycache__' in str(p): continue
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError as e:
        print(f'ERROR: {p} - {e}')
"
```

---

## $ARGUMENTS の使い方

引数なし → エラーの症状を聞いて適切なカテゴリに振り分け
`ai` / `firestore` / `cloudrun` / `extension` / `python` → 直接そのカテゴリの診断を実行
