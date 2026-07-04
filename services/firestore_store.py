"""firestore_store — Firestore永続化層

スキーマ: docs/data_schema.md
  analyses/{analysis_id}                … uid / saved_at / hand_ids / meta
  analyses/{analysis_id}/hands/{hand_id} … hand_json / bb_size / pot_size_bb / street_reached

hand_json はサブコレクション側に置く（1MB上限回避）。classified_snapshot は復活させない。
"""

from __future__ import annotations

import json
import os
import uuid

from scripts.hand_converter import decision_street, street_reached, _street_pot_bb

_db = None
_init_error = None


def _client():
    global _db, _init_error
    if _db is not None:
        return _db
    if _init_error is not None:
        raise _init_error
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if raw:
                # JSON文字列で渡す（ファイルパスではない — docs/infra.md）
                cred = credentials.Certificate(json.loads(raw))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()  # Cloud Run上はADC
        _db = firestore.client()
        return _db
    except Exception as e:  # 認証情報なしのローカル起動でも /health は生かす
        _init_error = e
        raise


def available() -> bool:
    try:
        _client()
        return True
    except Exception:
        return False


def verify_uid(id_token: str) -> str | None:
    """Firebase ID tokenを検証してuidを返す。無効ならNone。"""
    try:
        from firebase_admin import auth

        _client()
        return auth.verify_id_token(id_token).get("uid")
    except Exception:
        return None


def save_analysis(uid: str, hands: list, meta: dict | None = None,
                  bb_size: float | None = None) -> str:
    from firebase_admin import firestore

    db = _client()
    analysis_id = uuid.uuid4().hex[:12]
    doc = db.collection("analyses").document(analysis_id)
    hand_ids = []
    batch = db.batch()
    for hand in hands:
        hand_id = f"h{hand.get('hand_number', len(hand_ids) + 1)}"
        hand_ids.append(hand_id)
        pot = _street_pot_bb(hand, decision_street(hand))
        batch.set(doc.collection("hands").document(hand_id), {
            "hand_json": hand,
            "bb_size": bb_size,
            "pot_size_bb": pot,
            "street_reached": street_reached(hand),
        })
    batch.set(doc, {
        "uid": uid,
        "saved_at": firestore.SERVER_TIMESTAMP,
        "hand_ids": hand_ids,
        "meta": meta or {},
    })
    batch.commit()
    return analysis_id


def list_analyses(uid: str, limit: int = 50) -> list:
    from firebase_admin import firestore

    db = _client()
    q = (db.collection("analyses")
         .where("uid", "==", uid)
         .order_by("saved_at", direction=firestore.Query.DESCENDING)  # captured_atは欠落あり
         .limit(limit))
    out = []
    for doc in q.stream():
        d = doc.to_dict() or {}
        out.append({
            "analysis_id": doc.id,
            "saved_at": str(d.get("saved_at") or ""),
            "hand_count": len(d.get("hand_ids") or []),
            "meta": d.get("meta") or {},
        })
    return out


def get_analysis(analysis_id: str) -> dict | None:
    db = _client()
    snap = db.collection("analyses").document(analysis_id).get()
    return (snap.to_dict() or {}) | {"analysis_id": snap.id} if snap.exists else None


def get_hands(analysis_id: str) -> list:
    db = _client()
    docs = db.collection("analyses").document(analysis_id).collection("hands").stream()
    # ネストを維持する（docs/data_schema.md「よくあるミス」参照）
    hands = [{"hand_id": doc.id, **(doc.to_dict() or {})} for doc in docs]
    hands.sort(key=lambda h: (h.get("hand_json") or {}).get("hand_number") or 0)
    return hands


def save_ai_result(analysis_id: str, hand_number, result: dict, mode: str) -> None:
    """AI解析結果をハンドに保存する。再解析は上書き（docs/features/cart.md）。"""
    db = _client()
    ref = (db.collection("analyses").document(analysis_id)
           .collection("hands").document(f"h{hand_number}"))
    ref.update({
        f"hand_json.ai_{mode}": result,
        "hand_json.analyzed": True,
    })
