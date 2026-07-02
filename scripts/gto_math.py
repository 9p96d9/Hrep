"""GTO数学・スコア計算 — specs/gto_math.md 準拠。

α・MDF・必要エクイティの文字列生成（_compute_gto_math）、
難易度スコア（_compute_difficulty）、ナイスプレイスコアV1（_compute_nice_play_score）。
MDFはリバーのみ言及する — REQUIREMENTS.md Must 準拠。
"""

import re

from scripts.classify import (
    CATEGORY_BASE_SCORE,
    GTO_INCORRECT,
    POSTFLOP_STREETS,
    _AGGRESSIVE_ACTIONS,
    _find_decision_spot,
    _name,
    judge_gto_decision,
)

DEFENDER_CATEGORIES = {"bluff_catch", "nice_call", "bad_call", "call_lost"}
AGGRESSOR_CATEGORIES = {"hero_aggression_won", "value_success", "bluff_failed"}
FOLD_CATEGORIES = {"fold_unknown", "nice_fold", "bad_fold"}

# specs/gto_math.md §4 ナイスプレイV1
NICE_PLAY_CATEGORIES = {"bluff_catch", "nice_call", "nice_fold"}
NICE_PLAY_THRESHOLD = 0.5
NICE_PLAY_MAX_COUNT = 3

STREET_WEIGHTS = {"river": 1.0, "turn": 0.8, "flop": 0.6, "preflop": 0.4}

STREET_LABELS = {
    "river": "リバー",
    "turn": "ターン",
    "flop": "フロップ",
    "preflop": "プリフロップ",
}

SPOT_NAMES = {
    "bluff_catch": "ブラフキャッチ",
    "nice_call": "ナイスコール",
    "bad_call": "バッドコール",
    "call_lost": "コール",
    "value_success": "バリュー",
    "hero_aggression_won": "アグレッション",
    "bluff_failed": "ブラフ",
    "nice_fold": "ナイスフォールド",
    "bad_fold": "バッドフォールド",
    "fold_unknown": "フォールド",
}

_ALPHA_RE = re.compile(r"α=(\d+(?:\.\d+)?)%")


def _compute_gto_math(hand):
    """カテゴリ別GTO数学コンテキスト文字列を返す — specs/gto_math.md §2。"""
    category = _category(hand)
    spot_name = SPOT_NAMES.get(category)
    if spot_name is None:
        return ""
    street = _decision_street(hand)
    head = f"[GTO数学] {spot_name}スポット | {STREET_LABELS[street]}"

    if category in DEFENDER_CATEGORIES:
        spot = _find_decision_spot(hand)
        if spot is None:
            return head
        pct = _pct(spot["required_equity"])
        return f"{head} | 必要エクイティ={pct}（α={pct}）"

    if category in AGGRESSOR_CATEGORIES:
        spot = _find_hero_bet_spot(hand)
        if spot is None:
            return head
        bet, pot = spot
        alpha = bet / (pot + bet)
        return f"{head} | ベット={bet:g}bb / ポット={pot:g}bb | α={_pct(alpha)}"

    if category in FOLD_CATEGORIES:
        spot = _find_decision_spot(hand)
        if spot is None:
            return head
        alpha = spot["required_equity"]
        if street == "river":
            return f"{head} | α={_pct(alpha)} | MDF基準={_pct(1 - alpha)}"
        return f"{head} | α={_pct(alpha)} | Heroがフォールド"

    return ""


def _compute_difficulty(hand):
    """難易度スコア = カテゴリ基礎スコア × ストリートウェイト ± α微補正（上限1.0）。

    結果（損益）は入力に含まない — REQUIREMENTS.md Must 準拠。
    αは gto_math 文字列から正規表現で抽出（specs/gto_math.md §3）。
    """
    base = CATEGORY_BASE_SCORE.get(_category(hand), 0.20)
    weight = STREET_WEIGHTS[_decision_street(hand)]
    score = base * weight

    match = _ALPHA_RE.search(hand.get("gto_math") or "")
    if match:
        alpha = float(match.group(1)) / 100
        indifference = 1.0 - abs(2 * alpha - 1.0)
        score += (indifference - 0.5) * 0.1

    return max(0.0, min(1.0, score))


def _compute_nice_play_score(hand, gto_verdict=None):
    """ナイスプレイスコアV1 — specs/gto_math.md §4。

    対象カテゴリ {bluff_catch, nice_call, nice_fold} のみ難易度スコアを返し、
    表示閾値（0.5）未満と対象外カテゴリは 0.0。
    bluff_catch はGTO判定=不正解（幸運なコール）なら除外。判定困難は
    ショーダウン勝利という追加証拠を考慮して対象に残す（specs/classify.md §4）。
    """
    category = _category(hand)
    if category not in NICE_PLAY_CATEGORIES:
        return 0.0
    if category == "bluff_catch":
        verdict = gto_verdict if gto_verdict is not None else judge_gto_decision(hand)
        if verdict == GTO_INCORRECT:
            return 0.0
    score = _compute_difficulty(hand)
    return score if score >= NICE_PLAY_THRESHOLD else 0.0


def _select_nice_plays(hands):
    """ナイスプレイ候補を難易度スコア降順で最大3件返す。

    0件なら空リスト（UIは「0件」を正直に表示する。セクションを非表示にしない）。
    """
    candidates = [(_compute_nice_play_score(h), h) for h in hands]
    candidates = [(score, h) for score, h in candidates if score > 0]
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [h for _, h in candidates[:NICE_PLAY_MAX_COUNT]]


def _category(hand):
    return (hand.get("bluered_classification") or {}).get("category")


def _decision_street(hand):
    """river → turn → flop → preflop の順で最初にアクションがある場所（specs/gto_math.md §2）。"""
    streets = hand.get("streets") or {}
    for street in reversed(POSTFLOP_STREETS):
        data = streets.get(street) or {}
        if data.get("actions"):
            return street
    return "preflop"


def _find_hero_bet_spot(hand):
    """Heroの最後のベット/レイズとその直前のポットを返す。(bet_bb, pot_bb) / None。"""
    streets = hand.get("streets") or {}
    hero_pos = hand.get("hero_position")
    found = None
    for street in POSTFLOP_STREETS:
        data = streets.get(street) or {}
        pot = data.get("pot_bb")
        if pot is None:
            continue
        invested = {}
        current_bet = 0
        for act in data.get("actions") or []:
            name = _name(act)
            pos = act.get("position")
            if name in _AGGRESSIVE_ACTIONS:
                amount = act.get("amount_bb") or 0
                if pos == hero_pos:
                    found = (amount, pot)
                pot += amount - invested.get(pos, 0)
                invested[pos] = amount
                current_bet = amount
            elif name == "call":
                net_call = current_bet - invested.get(pos, 0)
                if net_call > 0:
                    pot += net_call
                    invested[pos] = current_bet
    return found


def _pct(ratio):
    return f"{round(ratio * 100)}%"
