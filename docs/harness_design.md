# docs/harness_design.md — 開発harness設計の判断記録

**種別: 設計判断ドキュメント（Claude Code環境の構成）**
**Status: hooksあり採用・実装済み（2026-07-02）**

---

## 背景 — Hrep時代のharnessが腐敗した原因

1. **スキルに「事実」を埋め込んだ**: `/cost` にAWSコスト表、`/deploy-check` にEC2手順を直書き。
   インフラがCloud Runに移行した後もスキルは旧世界のまま残り、docs/infra.mdと矛盾した
2. **ルールが「お願い」だった**: 「コミットに `test:✅` を含める」はCLAUDE.mdの記述だけで、
   忘れれば素通り。強制する仕組みがなかった
3. **permissionsが無効構文だった**: `Bash(gh *)` は正しくは `Bash(gh:*)`。
   実質すべての許可ルールが機能していなかった

---

## 設計3原則

### 原則1: 事実はdocs、手順はskills
スキルは**実行する手順（コマンド列）だけ**を持ち、事実（コスト・構成値・URL）は `docs/` を読みに行く。
事実は必ず古くなるが、手順は事実より寿命が長い。腐敗経路を構造で断つ。

### 原則2: 不変ルールはhooksで機械的に強制（採否検討中 → 下の比較）
毎コミットに適用される不変ルール（test表記・構文チェック）はモデルの記憶でなくharnessに持たせる。

### 原則3: 許可は非対称（読み取りは自由・破壊は遮断）
参照系コマンドは自動許可、デプロイ・削除系は毎回確認、`.env` 読み取りと強制pushはdeny。

---

## hooks あり/なし 比較

### hooksなし（CLAUDE.mdの記述だけ）で起きること

- 長いセッションの終盤でコンテキストが圧縮されるとルールが忘れられ、`test:✅` なしコミットが通る
- 構文エラーの発見が遅い: 編集 → commit → push → GitHub Actionsで失敗、で初めて気づく
  （GTO-時代の実例: Dockerfileの `COPY templates/` 忘れで本番500エラーが継続）
- 防げるのは「善意のミス」だけ。忘れたら素通り

### hooksあり（harnessがツール実行の前後に必ずスクリプトを走らせる）

| シナリオ | hooksなし | hooksあり |
|---|---|---|
| `test:✅` なしで `git commit` | そのまま通る | **コミット自体がブロック**。修正指示がClaudeに返り、その場で修正 |
| `.py` 編集で構文エラー | push後にActionsで発覚（〜数分後） | **編集した瞬間**にエラーが返り、即修正 |
| `static/*.js` 編集 | キャッシュバスト忘れ → 本番で旧JS | 編集直後に `?v=` 更新のリマインド |
| `git commit --no-verify` で回避 | 可能 | ブロック |

### hooksのコスト

- `.claude/hooks/` にPythonスクリプト2本（各20行程度）が増え、ルール変更時はスクリプトも直す
- 意図的なWIPコミットでも `test:skip+wip` と書く必要がある（厳密さの裏返し）
- hook誤動作時の切り分けが1手間増える
- Windows環境では `python` がPATHにあることが前提

### 判断の軸

- **頻繁に変わるルール** → CLAUDE.md向き（文章を直すだけ）
- **毎コミット適用の不変ルール** → hooks向き（忘却に耐性）
- このプロジェクトの「SPECとテストがコミットの門番」ルールは後者

---

## 構成案（hooks採用時の全体像）

```
.claude/
├── settings.json          # permissions(allow/deny) + env + hooks登録
├── hooks/
│   ├── guard_commit.py    # PreToolUse(Bash): git commitのtest表記チェック・--no-verify遮断
│   └── check_edit.py      # PostToolUse(Edit|Write): .py構文チェック / static/*.js キャッシュバスト注意
└── skills/
    ├── poker-brain-pre/   # スポット分析手順（レンジ表のみ内包・事実はspecs参照）
    ├── poker-brain-post/  # AI出力レビュー手順（ルールはspecs/ai_analysis.md参照）
    ├── deploy-check/      # Cloud Runデプロイ確認手順（構成値はdocs/infra.md参照）
    ├── error-diagnose/    # エラー分類と診断手順
    ├── cost/              # GCP無料枠確認手順（コスト表は持たない）
    └── spec-update/       # SPEC作成・更新フロー
```

### settings.json（hooksなし版 = ベースライン）

```json
{
  "permissions": {
    "allow": [
      "Bash(git:*)", "Bash(gh:*)", "Bash(python:*)", "Bash(pytest:*)",
      "Bash(gcloud run services describe:*)", "Bash(gcloud run services logs:*)",
      "Bash(curl:*)", "WebSearch",
      "WebFetch(domain:github.com)", "WebFetch(domain:hrep.app)"
    ],
    "deny": [
      "Read(./.env)", "Read(./.env.*)",
      "Bash(git push --force:*)",
      "Bash(gcloud run services delete:*)",
      "Bash(gcloud firestore databases delete:*)"
    ]
  },
  "env": { "PYTHONUTF8": "1" }
}
```

hooks採用時は上記に `"hooks"` セクションを追加する（guard_commit.py / check_edit.py を登録）。

---

## 決定

- [x] **hooksあり（全部入り）— 2026-07-02 採用決定**
- [ ] ~~hooksなし~~

実装済み・動作テスト済み:
- `.claude/hooks/guard_commit.py` — test表記なしコミットのブロック / `--no-verify` 遮断（3ケース確認）
- `.claude/hooks/check_edit.py` — .py構文即時チェック / static JSキャッシュバストリマインド（3ケース確認）
- `settings.json` に PreToolUse(Bash) / PostToolUse(Edit|Write) として登録済み

**Status: 決定済み・実装済み**
