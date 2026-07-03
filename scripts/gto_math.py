"""GTO数学・難易度スコア・ナイスプレイスコア（specs/gto_math.md）。

純粋関数のみ。DB・外部API・AI SDKに依存しない（tests/PLAN.md 原則）。
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# §1 基本用語

def alpha(bet_bb: float, pot_bb: float) -> float:
    """α = Bet ÷ (Pot + Bet)。ブラフの損益分岐フォールド率。"""
    return bet_bb / (pot_bb + bet_bb)


def mdf(bet_bb: float, pot_bb: float) -> float:
    """MDF = 1 − α。相手のブラフを防ぐための最低コール頻度。リバーのみ言及可。"""
    return 1.0 - alpha(bet_bb, pot_bb)


def required_equity(call_bb: float, pot_before_call_bb: float) -> float:
    """必要エクイティ = コール額 ÷ (コール後の最終ポット)。"""
    return call_bb / (pot_before_call_bb + call_bb)


def extract_alpha(gto_math_text: str) -> float | None:
    """gto_math 文字列から α を抽出する（§3 α微補正はここから取る）。"""
    m = re.search(r"α=(\d+(?:\.\d+)?)%", gto_math_text or "")
    return float(m.group(1)) / 100.0 if m else None


# ---------------------------------------------------------------------------
# §2 カテゴリ別GTO数学コンテキスト

DEFENDER_CATEGORIES = frozenset({"bluff_catch", "nice_call", "bad_call", "call_lost"})
AGGRESSOR_CATEGORIES = frozenset({"hero_aggression_won", "value_success", "bluff_failed"})
FOLD_CATEGORIES = frozenset({"fold_unknown", "nice_fold", "bad_fold"})

_SPOT_LABELS = {
    "bluff_catch": "ブラフキャッチ",
    "nice_call": "ナイスコール",
    "bad_call": "バッドコール",
    "call_lost": "コール",
    "hero_aggression_won": "アグレッション",
    "value_success": "バリュー",
    "bluff_failed": "ブラフ",
    "nice_fold": "ナイスフォールド",
    "bad_fold": "バッドフォールド",
    "fold_unknown": "フォールド",
}

_STREET_JP = {"preflop": "プリフロップ", "flop": "フロップ", "turn": "ターン", "river": "リバー"}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _bb(x: float) -> str:
    return f"{x:g}bb"


def compute_gto_math(
    category: str,
    street: str,
    pot_bb: float,
    bet_bb: float,
    call_bb: float | None = None,
) -> str:
    """[GTO数学]ブロック文字列を生成する。

    pot_bb は bet を含まないポット。DEFENDER系の net_call は省略時 bet_bb と同額。
    MDFはリバーのFOLD系のみ出力する（§1 MDF適用ルール）。
    """
    spot = _SPOT_LABELS.get(category, category)
    street_jp = _STREET_JP.get(street, street)
    head = f"[GTO数学] {spot}スポット | {street_jp}"

    if category in DEFENDER_CATEGORIES:
        # tests/PLAN.md fixture例: pot=28, bet=20 → 必要エクイティ=42%（= 20÷48）
        net_call = bet_bb if call_bb is None else call_bb
        req = required_equity(net_call, pot_bb)
        return f"{head} | 必要エクイティ={_pct(req)}"

    if category in AGGRESSOR_CATEGORIES:
        a = alpha(bet_bb, pot_bb)
        return f"{head} | ベット={_bb(bet_bb)} / ポット={_bb(pot_bb)} | α={_pct(a)}"

    if category in FOLD_CATEGORIES:
        a = alpha(bet_bb, pot_bb)
        if street == "river":
            return f"{head} | α={_pct(a)} | MDF基準={_pct(1.0 - a)}"
        return f"{head} | α={_pct(a)} | Heroがフォールド"

    return head


# ---------------------------------------------------------------------------
# §3 難易度スコア

CATEGORY_BASE_SCORES = {
    "bluff_catch": 0.90,
    "nice_call": 0.90,
    "nice_fold": 0.85,
    "hero_aggression_won": 0.70,
    "value_success": 0.50,
    "bluff_failed": 0.30,
    "bad_call": 0.30,
    "bad_fold": 0.30,
    "call_lost": 0.25,
    "fold_unknown": 0.25,
    "preflop_only": 0.20,
}
DEFAULT_BASE_SCORE = 0.20

STREET_WEIGHTS = {"river": 1.0, "turn": 0.8, "flop": 0.6, "preflop": 0.4}
DEFAULT_STREET_WEIGHT = 0.4


def alpha_adjustment(a: float) -> float:
    """α微補正（±0.05以内）。α=0.5（完全インディファレンス）で最大 +0.05。"""
    indifference = 1.0 - abs(2.0 * a - 1.0)
    return (indifference - 0.5) * 0.1


def compute_difficulty(category: str, street: str, alpha_value: float | None = None) -> float:
    """難易度スコア = カテゴリ基礎スコア × ストリートウェイト ± α微補正（上限1.0）。

    結果（損益）は入力に含めない（REQUIREMENTS.md Must）。
    """
    base = CATEGORY_BASE_SCORES.get(category, DEFAULT_BASE_SCORE)
    score = base * STREET_WEIGHTS.get(street, DEFAULT_STREET_WEIGHT)
    if alpha_value is not None:
        score += alpha_adjustment(alpha_value)
    return max(0.0, min(score, 1.0))


# ---------------------------------------------------------------------------
# §4 ナイスプレイスコア（V1）

NICE_PLAY_CATEGORIES = frozenset({"bluff_catch", "nice_call", "nice_fold"})
NICE_PLAY_THRESHOLD = 0.5
NICE_PLAY_MAX_COUNT = 3


def compute_nice_play_score(
    category: str,
    difficulty: float,
    gto_verdict: str | None = None,
) -> float:
    """ナイスプレイスコア。対象外カテゴリ・閾値未満は 0.0。

    bluff_catch は GTO判定=不正解（幸運なコール）なら除外する（誤称賛防止）。
    判定困難（unknown/None）はショーダウン勝利という追加証拠を考慮して対象に残す。
    """
    if category not in NICE_PLAY_CATEGORIES:
        return 0.0
    if category == "bluff_catch" and gto_verdict == "incorrect":
        return 0.0
    if difficulty < NICE_PLAY_THRESHOLD:
        return 0.0
    return difficulty


def select_nice_plays(hands: list[dict], score_key: str = "nice_play_score") -> list[dict]:
    """表示対象のナイスプレイを難易度スコア降順で最大3件返す。

    0件なら空リストを返す。UIは「今日のナイスプレイ: 0件」を正直に表示する
    （セクションを非表示にしない — REQUIREMENTS.md Must）。
    """
    candidates = [h for h in hands if h.get(score_key, 0.0) >= NICE_PLAY_THRESHOLD]
    candidates.sort(key=lambda h: h[score_key], reverse=True)
    return candidates[:NICE_PLAY_MAX_COUNT]
