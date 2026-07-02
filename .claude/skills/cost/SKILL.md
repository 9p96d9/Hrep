---
name: cost
description: GCP無料枠の消費状況確認と、設計変更のコスト影響判断の手順。月次コスト確認・「この設計は無料枠に収まるか」を判断するときに使う。
argument-hint: "引数なし=無料枠の考え方 / --check=実測コマンド実行"
---

# /cost — GCPコスト確認・無料枠管理

> コストの事実（何が無料枠か・概算額）は `docs/infra.md` が正。このスキルは確認手順と判断軸のみを持つ。
> **AWS時代のコスト情報は使わない**（削除済み。`../Hrep/docs/infra.md` [LEGACY]参照）。

---

## 前提: 現行構成は「無料枠内 ~$0/月」が設計目標

守るべきは金額ではなく**無料枠の天井との距離**。確認すべき3つ:

| サービス | 無料枠の天井（docs/infra.md参照） | 超えやすい操作 |
|---|---|---|
| Cloud Run | リクエスト200万/月・CPU/メモリ枠 | SSE長時間接続の張りっぱなし |
| Firestore | 読み取り50k/日・書き込み20k/日 | 全件読み込みの集計・N+1読み取り |
| Firebase Auth | MAU 10,000 | （当面問題なし） |

---

## 実測コマンド（--check）

```bash
# 課金アカウントと予算アラートの確認
gcloud billing accounts list

# Cloud Run リクエスト数・課金対象時間（直近の目安はコンソール推奨）
gcloud monitoring time-series list \
  --filter 'metric.type="run.googleapis.com/request_count"' \
  --interval-end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) 2>/dev/null || \
  echo "→ コンソール: console.cloud.google.com/run → メトリクス"

# Firestore使用量はコンソールで確認
echo "→ console.firebase.google.com → Firestore → 使用量"
```

CLIで取りにくい値はコンソールURLを提示して誘導する（無理にCLIで完結させない）。

---

## 設計変更のコスト判断軸

1. **読み取り回数が増える変更か？** — Firestoreは読み取り課金。一覧画面のN+1・ポーリングは要注意
2. **接続時間が延びる変更か？** — Cloud RunはCPU割当時間課金。SSEのkeep-alive設計を確認
3. **保存量が増える変更か？** — 1GBまで無料。ハンドJSONの重複保存を避ける
4. 判断に迷ったら: 無料枠の50%を超える試算が出た時点でユーザーに設計相談する

---

## $ARGUMENTS の使い方

引数なし → 無料枠の考え方と判断軸を表示し、docs/infra.mdの現状を読む
`--check` → 実測コマンドを実行して現在の消費を確認
