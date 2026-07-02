# docs/legacy.md — 旧構成の記録（再作成しない）

**種別: アーカイブ。旧Hrepフォルダ削除（2026-07）に伴い、参照されていたLEGACY記録をここに退避。**
初代の実装コード・全履歴は GitHub `9p96d9/GTO-` に現存する。

---

## [LEGACY] AWS構成（2026-05まで・削除済み）

```
[Chrome拡張]
    ↓ HTTPS POST
[Cloudflare Tunnel]
    ↓
[AWS EC2 t3.small]
  └─ Docker
       ├─ gto-app       (FastAPI + uvicorn, port 8000)
       └─ gto-postgres  (postgres:18-alpine, port 5432)
```

| 項目 | 値 |
|---|---|
| EC2 | t3.small, Amazon Linux 2, ap-northeast-1 |
| DB | PostgreSQL 18 (コンテナ名: gto-postgres, DB名: postgres) |
| DBユーザー | gto_user |
| コンテナレジストリ | AWS ECR |
| 月額コスト | ~$20（EC2 $17 + EBS $2 + ECR $0.5） |

### 削除済みリソース

| リソース | 削除日 |
|---|---|
| Railway | 2026-05-15 |
| AWS ECS Fargate / ALB | 2026-05-18 |
| AWS RDS (PostgreSQL) | 2026-05-20 |
| EC2 + gto-postgres コンテナ | 2026-06（Firebase/Cloud Run移行） |

### [LEGACY] 環境変数

| 変数名 | 用途 |
|---|---|
| `USE_POSTGRES` | `true` で PostgreSQL使用 |
| `DATABASE_URL` | PostgreSQL接続文字列 |

---

## [LEGACY] PostgreSQL テーブル定義（AWS時代・削除済み）

### `analyses` テーブル

| カラム | 型 | 説明 |
|---|---|---|
| `id` | VARCHAR(100) PK | job_id（UUID） |
| `uid` | VARCHAR(100) | Firebase Auth UID |
| `saved_at` | TIMESTAMP | 保存日時（ソートキー） |
| `hand_ids` | JSONB | 含まれるhand_idのリスト |
| `meta` | JSONB | セッションメタデータ |

### `analysis_hands` テーブル

| カラム | 型 | 説明 |
|---|---|---|
| `id` | SERIAL PK | |
| `analysis_id` | VARCHAR(100) FK | analyses.id |
| `hand_id` | VARCHAR(200) | ハンド識別子 |
| `hand_json` | JSONB | ハンドデータ全体 |
| `bb_size` | NUMERIC | ビッグブラインド額 |
| `pot_size_bb` | NUMERIC | 最終ポットサイズ |
| `street_reached` | VARCHAR(10) | 最深ストリート |

### [LEGACY] SQLAlchemy の注意点

```python
# NG: SQLAlchemy が :param: と誤解析
text("SET col = :param::jsonb")

# OK: CAST() 形式を使う
text("SET col = CAST(:param AS jsonb)")
```
