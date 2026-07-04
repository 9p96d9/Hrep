"""hand_converter — ハンドJSONへの分類・GTO数学・スコア注釈（純粋関数）

仕様: specs/classify.md（11カテゴリ・ライン）, specs/gto_math.md（α/MDF/難易度/ナイスプレイ）
入力形式: docs/data_schema.md のハンドJSON

DB・外部API・AI SDKをimportしない（tests/PLAN.md 原則）。
treys はGTO判定ヒューリスティックにのみ使い、未インストールでも動く（判定困難に倒す）。
"""

from __future__ import annotations

import copy
import re

# ---------------------------------------------------------------------------
# 定数（specs/classify.md §4 の対応表が正）
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "value_success": "バリュー成功",
    "bluff_catch": "ブラフキャッチ",
    "nice_call": "ナイスコール",
    "nice_fold": "ナイスフォールド",
    "hero_aggression_won": "アグレッション勝利",
    "bluff_failed": "ブラフ失敗",
    "bad_call": "バッドコール",
    "bad_fold": "バッドフォールド",
    "call_lost": "コール負け(要確認)",
    "fold_unknown": "フォールド(要確認)",
    "preflop_only": "プリフロップのみ",
}

CATEGORY_LINES = {
    "value_success": "blue",
    "bluff_catch": "blue",
    "nice_call": "gray",
    "nice_fold": "gray",
    "hero_aggression_won": "red",
    "bluff_failed": "red",
    "bad_call": "red",
    "bad_fold": "red",
    "call_lost": "warn",
    "fold_unknown": "warn",
    "preflop_only": "preflop_only",
}

CATEGORY_BASE_SCORES = {
    "value_success": 0.50,
    "bluff_catch": 0.90,
    "nice_call": 0.90,
    "nice_fold": 0.85,
    "hero_aggression_won": 0.70,
    "bluff_failed": 0.30,
    "bad_call": 0.30,
    "bad_fold": 0.30,
    "call_lost": 0.25,
    "fold_unknown": 0.25,
    "preflop_only": 0.20,
}

STREET_WEIGHTS = {"river": 1.0, "turn": 0.8, "flop": 0.6, "preflop": 0.4}

STREET_LABELS_JA = {
    "preflop": "プリフロップ",
    "flop": "フロップ",
    "turn": "ターン",
    "river": "リバー",
}

# ナイスプレイV1対象（specs/gto_math.md §4）
NICE_PLAY_CATEGORIES = {"bluff_catch", "nice_call", "nice_fold"}
NICE_PLAY_THRESHOLD = 0.5
NICE_PLAY_LIMIT = 3

# 改善チャンス対象（docs/features/improve_chances.md — 確定した不正解のみ）
IMPROVE_CATEGORIES = {"bad_fold", "bad_call"}
IMPROVE_LIMIT = 3

AGGRESSIVE_ACTIONS = {"bet", "raise", "allin"}

# GTO判定ヒューリスティックの保守マージン（specs/classify.md §3: 迷ったらwarn）
JUDGMENT_MARGIN = 0.15


# ---------------------------------------------------------------------------
# ストリート・アクション補助
# ---------------------------------------------------------------------------

def _street_actions(hand: dict, street: str) -> list:
    s = (hand.get("streets") or {}).get(street)
    if s is None:
        return []
    if isinstance(s, list):  # preflop はアクション配列そのもの
        return s
    return s.get("actions") or []


def _street_pot_bb(hand: dict, street: str):
    s = (hand.get("streets") or {}).get(street)
    if isinstance(s, dict):
        return s.get("pot_bb")
    if street == "preflop":
        return 1.5  # SB + BB
    return None


def decision_street(hand: dict) -> str:
    """ポストフロップでアクションがある最深ストリート。なければ preflop。"""
    for street in ("river", "turn", "flop"):
        if _street_actions(hand, street):
            return street
    return "preflop"


def street_reached(hand: dict) -> str:
    """ボードまたはアクションが存在する最深ストリート（AI出力の空文字判定に使う）。"""
    streets = hand.get("streets") or {}
    for street in ("river", "turn", "flop"):
        s = streets.get(street)
        if isinstance(s, dict) and (s.get("board") or s.get("actions")):
            return street
    return "preflop"


def board_through(hand: dict, street: str) -> list:
    """flop から指定ストリートまでのボードカードを連結して返す。"""
    order = ["flop", "turn", "river"]
    if street not in order:
        return []
    cards = []
    streets = hand.get("streets") or {}
    for st in order[: order.index(street) + 1]:
        s = streets.get(st)
        if isinstance(s, dict):
            cards.extend(s.get("board") or [])
    return cards


def _is_hero(action: dict, hero_position: str) -> bool:
    return action.get("position") == hero_position


def _last_aggression(actions: list):
    """ストリート内の最後のbet/raiseを (index, action) で返す。なければ None。"""
    for i in range(len(actions) - 1, -1, -1):
        if actions[i].get("action") in AGGRESSIVE_ACTIONS:
            return i, actions[i]
    return None


def _facing_bet_context(hand: dict, street: str, hero_position: str):
    """Heroが直面した相手のbet/raiseと、その時点のポットを返す。

    Returns:
        (net_call_bb, pot_before_call_bb) — pot_before_call はその相手ベットを含む。
        情報不足なら (None, None)。
    """
    actions = _street_actions(hand, street)
    pot_start = _street_pot_bb(hand, street)
    if pot_start is None:
        return None, None
    la = _last_aggression(actions)
    if la is None or _is_hero(la[1], hero_position):
        return None, None
    idx, bet = la
    amount = bet.get("amount_bb")
    if not amount:
        return None, None
    invested_before = sum((a.get("amount_bb") or 0) for a in actions[:idx])
    return float(amount), float(pot_start) + invested_before + float(amount)


def _hero_bet_context(hand: dict, street: str, hero_position: str):
    """Heroの最後のbet/raiseと、その直前のポットを返す。情報不足なら (None, None)。"""
    actions = _street_actions(hand, street)
    pot_start = _street_pot_bb(hand, street)
    if pot_start is None:
        return None, None
    la = _last_aggression(actions)
    if la is None or not _is_hero(la[1], hero_position):
        return None, None
    idx, bet = la
    amount = bet.get("amount_bb")
    if not amount:
        return None, None
    invested_before = sum((a.get("amount_bb") or 0) for a in actions[:idx])
    return float(amount), float(pot_start) + invested_before


# ---------------------------------------------------------------------------
# GTO判定ヒューリスティック（specs/classify.md §3 — 保守的に判定困難へ倒す）
# ---------------------------------------------------------------------------

def _treys_strength(hero_cards: list, board: list):
    """treysによるボード上のハンド強度（0.0〜1.0、高いほど強い）。評価不能なら None。"""
    try:
        from treys import Card, Evaluator
    except ImportError:
        return None
    try:
        ev = Evaluator()
        b = [Card.new(c) for c in board]
        h = [Card.new(c) for c in hero_cards]
        rank = ev.evaluate(b, h)
        return 1.0 - ev.get_five_card_rank_percentage(rank)
    except Exception:
        return None


def judge_call_decision(hand: dict, street: str) -> str:
    """コールが正解だったかのV1判定: "correct" / "incorrect" / "undecidable"。

    必要エクイティ（specs/gto_math.md §2 DEFENDER系）と treys評価の強度を比較。
    マージン内・情報不足は "undecidable"（誤称賛・誤指摘の防止を優先）。
    """
    hero_position = hand.get("hero_position")
    hero_cards = hand.get("hero_cards")
    board = board_through(hand, street)
    if not hero_cards or len(hero_cards) != 2 or len(board) < 3:
        return "undecidable"
    net_call, pot_before_call = _facing_bet_context(hand, street, hero_position)
    if not net_call or not pot_before_call:
        return "undecidable"
    required_equity = net_call / (pot_before_call + net_call)
    strength = _treys_strength(hero_cards, board)
    if strength is None:
        return "undecidable"
    if strength >= required_equity + JUDGMENT_MARGIN:
        return "correct"
    if strength <= required_equity - JUDGMENT_MARGIN:
        return "incorrect"
    return "undecidable"


def _auto_judgment(hand: dict, street: str, hero_folded: bool) -> str:
    """Heroが取った行動（コール or フォールド）自体の正誤を返す。"""
    call = judge_call_decision(hand, street)
    if not hero_folded:
        return call
    if call == "correct":
        return "incorrect"  # コールが正解ならフォールドは不正解
    if call == "incorrect":
        return "correct"
    return "undecidable"


# ---------------------------------------------------------------------------
# 分類（specs/classify.md §3 判定フロー）
# ---------------------------------------------------------------------------

def classify_hand(hand: dict, gto_judgment: str | None = None) -> dict:
    """ハンドを11カテゴリに分類する。

    Args:
        hand: docs/data_schema.md 形式のハンドJSON
        gto_judgment: Heroが取った行動の正誤を外部から与える場合に
            "correct" / "incorrect" / "undecidable"。None なら内部ヒューリスティックで判定。

    Returns:
        {"category", "category_label", "line", "gto_evaluation"}
        gto_evaluation はGTO判定を使った場合のみ判定値、それ以外は None。
    """
    hero_position = hand.get("hero_position")
    street = decision_street(hand)

    if street == "preflop":
        return _result("preflop_only", None)

    actions = _street_actions(hand, street)
    last = actions[-1]
    won = (hand.get("hero_result_bb") or 0) > 0

    if last.get("action") == "fold":
        if _is_hero(last, hero_position):
            judgment = gto_judgment or _auto_judgment(hand, street, hero_folded=True)
            if judgment == "correct":
                return _result("nice_fold", judgment)
            if judgment == "incorrect":
                return _result("bad_fold", judgment)
            return _result("fold_unknown", judgment)
        return _result("hero_aggression_won", None)

    # ショーダウン到達
    la = None
    for st in ("river", "turn", "flop"):
        la = _last_aggression(_street_actions(hand, st))
        if la:
            break
    if la is None:
        # チェックダウン: specs/classify.md の判定フロー対象外。勝ちはバリュー扱い、
        # 負けは判定困難（warn）に倒す
        return _result("value_success", None) if won else _result("call_lost", "undecidable")

    hero_was_aggressor = _is_hero(la[1], hero_position)
    if hero_was_aggressor:
        return _result("value_success" if won else "bluff_failed", None)

    # 相手のベットにHeroがコール
    judgment = gto_judgment or _auto_judgment(hand, street, hero_folded=False)
    if won:
        return _result("bluff_catch", judgment)
    if judgment == "correct":
        return _result("nice_call", judgment)
    if judgment == "incorrect":
        return _result("bad_call", judgment)
    return _result("call_lost", judgment)


def _result(category: str, gto_evaluation: str | None) -> dict:
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "line": CATEGORY_LINES[category],
        "gto_evaluation": gto_evaluation,
    }


# ---------------------------------------------------------------------------
# GTO数学ブロック（specs/gto_math.md §2）
# ---------------------------------------------------------------------------

DEFENDER_CATEGORIES = {"bluff_catch", "nice_call", "bad_call", "call_lost"}
AGGRESSOR_CATEGORIES = {"hero_aggression_won", "value_success", "bluff_failed"}
FOLD_CATEGORIES = {"nice_fold", "bad_fold", "fold_unknown"}

_SPOT_LABELS = {
    "bluff_catch": "ブラフキャッチ",
    "nice_call": "コール",
    "bad_call": "コール",
    "call_lost": "コール",
    "value_success": "バリュー",
    "bluff_failed": "ブラフ",
    "hero_aggression_won": "アグレッション",
    "nice_fold": "ナイスフォールド",
    "bad_fold": "フォールド",
    "fold_unknown": "フォールド",
}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _bb(x: float) -> str:
    return f"{x:g}bb"


def compute_gto_math(hand: dict, category: str) -> str:
    """[GTO数学] コンテキスト文字列を生成する。MDFはリバーのみ言及（厳守）。"""
    if category == "preflop_only":
        return ""
    street = decision_street(hand)
    street_ja = STREET_LABELS_JA[street]
    spot = _SPOT_LABELS.get(category, category)
    hero_position = hand.get("hero_position")
    head = f"[GTO数学] {spot}スポット | {street_ja}"

    if category in DEFENDER_CATEGORIES:
        net_call, pot_before_call = _facing_bet_context(hand, street, hero_position)
        if not net_call or not pot_before_call:
            return head
        required = net_call / (pot_before_call + net_call)
        alpha = net_call / pot_before_call  # bet ÷ (pot + bet) — pot_before_call はベット込み
        return f"{head} | 必要エクイティ={_pct(required)}（α={_pct(alpha)}）"

    if category in AGGRESSOR_CATEGORIES:
        bet, pot = _hero_bet_context(hand, street, hero_position)
        if not bet or not pot:
            return head
        alpha = bet / (pot + bet)
        return f"{head} | ベット={_bb(bet)} / ポット={_bb(pot)} | α={_pct(alpha)}"

    if category in FOLD_CATEGORIES:
        net_call, pot_before_call = _facing_bet_context(hand, street, hero_position)
        if not net_call or not pot_before_call:
            return head
        alpha = net_call / pot_before_call
        if street == "river":
            return f"{head} | α={_pct(alpha)} | MDF基準={_pct(1 - alpha)}"
        return f"{head} | α={_pct(alpha)} | Heroがフォールド"

    return head


# ---------------------------------------------------------------------------
# 難易度スコア・ナイスプレイスコア（specs/gto_math.md §3-4）
# ---------------------------------------------------------------------------

def compute_difficulty(category: str, street: str, gto_math: str = "") -> float:
    """難易度 = カテゴリ基礎スコア × ストリートウェイト ± α微補正（上限1.0）。"""
    base = CATEGORY_BASE_SCORES.get(category, 0.20)
    weight = STREET_WEIGHTS.get(street, 0.4)
    score = base * weight
    m = re.search(r"α=(\d+(?:\.\d+)?)%", gto_math or "")
    if m:
        alpha = float(m.group(1)) / 100.0
        indifference = 1.0 - abs(2 * alpha - 1.0)
        score += (indifference - 0.5) * 0.1
    return max(0.0, min(score, 1.0))


def compute_nice_play_score(category: str, difficulty: float,
                            gto_evaluation: str | None = None) -> float:
    """対象カテゴリのみ難易度をそのまま返す。幸運なbluff_catchは0.0（誤称賛防止）。"""
    if category not in NICE_PLAY_CATEGORIES:
        return 0.0
    if category == "bluff_catch" and gto_evaluation == "incorrect":
        return 0.0
    return difficulty


# ---------------------------------------------------------------------------
# セクション選定（docs/features/nice_plays.md / improve_chances.md）
# ---------------------------------------------------------------------------

def select_nice_plays(hands: list, limit: int = NICE_PLAY_LIMIT,
                      threshold: float = NICE_PLAY_THRESHOLD) -> list:
    """高難度正解: nice_play_score ≥ 閾値をスコア降順で最大limit件。0件なら空リスト。"""
    candidates = [
        h for h in hands
        if (h.get("nice_play_score") or 0.0) >= threshold
        and (h.get("bluered_classification") or {}).get("category") in NICE_PLAY_CATEGORIES
    ]
    candidates.sort(key=lambda h: h.get("nice_play_score") or 0.0, reverse=True)
    return candidates[:limit]


def select_improve_chances(hands: list, limit: int = IMPROVE_LIMIT) -> list:
    """改善チャンス: bad_fold/bad_call のみ。ストリートウェイト降順→ポット額降順。"""
    candidates = [
        h for h in hands
        if (h.get("bluered_classification") or {}).get("category") in IMPROVE_CATEGORIES
    ]

    def key(h):
        street = decision_street(h)
        pot = _street_pot_bb(h, street) or 0.0
        return (STREET_WEIGHTS.get(street, 0.0), pot)

    candidates.sort(key=key, reverse=True)
    return candidates[:limit]


# ---------------------------------------------------------------------------
# 注釈エントリポイント
# ---------------------------------------------------------------------------

def annotate_hand(hand: dict, gto_judgment: str | None = None) -> dict:
    """ハンドJSONに分類・GTO数学・スコアを注釈した新しいdictを返す（入力は変更しない）。

    付与フィールド: bluered_classification / gto_math / difficulty_score /
    nice_play_score / gto_evaluation / analyzed（未設定時のみ False）
    """
    out = copy.deepcopy(hand)
    cls = classify_hand(out, gto_judgment)
    street = decision_street(out)
    gto_math = compute_gto_math(out, cls["category"])
    difficulty = compute_difficulty(cls["category"], street, gto_math)
    nice = compute_nice_play_score(cls["category"], difficulty, cls["gto_evaluation"])

    out["bluered_classification"] = {
        "category": cls["category"],
        "category_label": cls["category_label"],
        "line": cls["line"],
    }
    out["gto_math"] = gto_math
    out["difficulty_score"] = round(difficulty, 4)
    out["nice_play_score"] = round(nice, 4)
    out["gto_evaluation"] = cls["gto_evaluation"]
    out.setdefault("analyzed", False)
    return out
