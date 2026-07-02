# docs/data_schema.md — データスキーマ定義

**種別: 参考ドキュメント（DBテストはFirestore Emulator推奨・V1ではテスト対象外）**

---

## ハンドJSON形式（主要フィールド）

```json
{
  "hand_number": 42,
  "hero_position": "CO",
  "hero_cards": ["Ah", "Kd"],
  "hero_result_bb": -12.5,
  "is_3bet_pot": false,
  "players": [
    {
      "name": "PlayerA",
      "position": "BTN",
      "is_hero": false,
      "hole_cards": ["Qh", "Qs"],
      "result_bb": 12.5
    }
  ],
  "streets": {
    "preflop": [
      {"position": "CO", "action": "raise", "amount_bb": 2.5},
      {"position": "BTN", "action": "call"}
    ],
    "flop": {
      "board": ["9h", "5d", "2c"],
      "pot_bb": 6.0,
      "actions": [
        {"position": "CO", "action": "bet", "amount_bb": 4.0},
        {"position": "BTN", "action": "call"}
      ]
    },
    "turn": { "board": ["Kh"], "pot_bb": 14.0, "actions": [] },
    "river": { "board": ["7s"], "pot_bb": 28.0, "actions": [] }
  },
  "bluered_classification": {
    "category": "bluff_catch",
    "category_label": "ブラフキャッチ",
    "line": "blue"
  },
  "gto_math": "[GTO数学] ブラフキャッチスポット | リバー | 必要エクイティ=33%",
  "difficulty_score": 0.90,
  "nice_play_score": 0.90,
  "result": {
    "allin_ev": {"PlayerA": 15.2}
  },
  "analyzed": false,
  "gto_evaluation": null
}
```

フィールドの意味論（カテゴリ・ライン・スコア）は `specs/classify.md` と `specs/gto_math.md` が正。

---

## Firestore コレクション設計

### `analyses/{analysis_id}` ドキュメント

| フィールド | 型 | 説明 |
|---|---|---|
| `uid` | string | Firebase Auth UID |
| `saved_at` | timestamp | 保存日時（ソートキー） |
| `hand_ids` | array\<string\> | 含まれるhand_idのリスト |
| `meta` | map | セッションメタデータ |

### `analyses/{analysis_id}/hands/{hand_id}` サブコレクション

| フィールド | 型 | 説明 |
|---|---|---|
| `hand_json` | map | ハンドデータ全体 |
| `bb_size` | number | ビッグブラインド額 |
| `pot_size_bb` | number | 最終ポットサイズ |
| `street_reached` | string | 最深ストリート |

### クエリパターン

```python
# ユーザーの解析一覧（新しい順）
db.collection("analyses")
  .where("uid", "==", uid)
  .order_by("saved_at", direction=firestore.Query.DESCENDING)

# 特定解析のハンド一覧
db.collection("analyses").document(analysis_id).collection("hands").stream()
```

### ドキュメントサイズ注意

- Firestoreの上限は **1ドキュメント1MB**
- `hand_json` は `analyses` 直下でなく `hands` サブコレクションに置くことで回避
- 100ハンド超のセッションでも問題なし
- `classified_snapshot`（gzip+base64圧縮の一括保存）はこの設計により**廃止**。復活させない

---

## よくあるミス

```python
# NG: Firestore の doc.to_dict() の中身がトップレベルに展開される
d = {"hand_id": doc.id, **doc.to_dict(), ...}

# OK: ネストを維持する
d = {"hand_id": doc.id, "hand_json": doc.to_dict(), ...}
```

```python
# NG: value が null だと [] にならない
hand_results = hand_json.get("handResults", [])

# OK
hand_results = hand_json.get("handResults") or []
```

```python
# NG: captured_at は一部ドキュメントに欠落（ソートで落ちる）
order_by("captured_at")

# OK
order_by("saved_at")
```

---

## 旧スキーマの記録

PostgreSQLテーブル定義（AWS時代・削除済み）は `docs/legacy.md` を参照。**再作成しない。**
