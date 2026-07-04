"""ハンド分類 — 11カテゴリ・5ライン（specs/classify.md）。

設計原則（§0）: 判断と結果の分離はコール側にも適用する。
コール敗北・フォールドとも GTO判定（correct/incorrect/unknown）で3分割する。
"""
from __future__ import annotations

from dataclasses import dataclass

VERDICT_CORRECT = "correct"
VERDICT_INCORRECT = "incorrect"
VERDICT_UNKNOWN = "unknown"

# §4 カテゴリとライン・日本語ラベルの対応（この表が正）
CATEGORIES: dict[str, tuple[str, str]] = {
    # category: (日本語ラベル, line)
    "value_success": ("バリュー成功", "blue"),
    "bluff_catch": ("ブラフキャッチ", "blue"),
    "nice_call": ("ナイスコール", "gray"),
    "nice_fold": ("ナイスフォールド", "gray"),
    "hero_aggression_won": ("アグレッション勝利", "red"),
    "bluff_failed": ("ブラフ失敗", "red"),
    "bad_call": ("バッドコール", "red"),
    "bad_fold": ("バッドフォールド", "red"),
    "call_lost": ("コール負け(要確認)", "warn"),
    "fold_unknown": ("フォールド(要確認)", "warn"),
    "preflop_only": ("プリフロップのみ", "preflop_only"),
}

# 赤線フィルター対象外ライン（gray は高難度正解セクションで別途表示）
NON_FILTER_LINES = frozenset({"gray", "warn", "preflop_only"})


@dataclass(frozen=True)
class Classification:
    category: str
    category_label: str
    line: str

    def as_dict(self) -> dict:
        """bluered_classification フィールド形式（docs/data_schema.md）。"""
        return {
            "category": self.category,
            "category_label": self.category_label,
            "line": self.line,
        }


def _make(category: str) -> Classification:
    label, line = CATEGORIES[category]
    return Classification(category, label, line)


# ---------------------------------------------------------------------------
# §3 GTOスコア判定（コール/フォールド共通機構）

# 判定困難に倒す中間帯の幅。誤って「正解/不正解」と言えば信頼が壊れるため、
# 迷ったら warn（specs/classify.md §3・REQUIREMENTS.md Must Not）。
JUDGE_MARGIN = 0.10


def judge_call_correctness(
    hero_equity: float | None,
    required_equity: float | None,
    margin: float = JUDGE_MARGIN,
) -> str:
    """「コールが正解か」を判定する。フォールド判定にも同一機構を使う。

    hero_equity: Heroハンドのボード上の強さ（treys評価ベースの推定。V1では
    上流で算出して渡す）。required_equity: specs/gto_math.md §2 DEFENDER系。
    確信が持てない中間帯（±margin）は VERDICT_UNKNOWN に倒す。
    """
    if hero_equity is None or required_equity is None:
        return VERDICT_UNKNOWN
    if hero_equity >= required_equity + margin:
        return VERDICT_CORRECT
    if hero_equity <= required_equity - margin:
        return VERDICT_INCORRECT
    return VERDICT_UNKNOWN


# ---------------------------------------------------------------------------
# §3 分類の判定フロー

def classify_hand(
    *,
    preflop_only: bool = False,
    showdown: bool = False,
    hero_won: bool = False,
    hero_last_aggressor: bool = False,
    call_verdict: str = VERDICT_UNKNOWN,
) -> Classification:
    """ハンドを11カテゴリのいずれかに分類する。

    call_verdict は judge_call_correctness() の結果（「コールが正解か」）。
    フォールド側では反転して解釈する（コール正解のフォールド = bad_fold）。
    """
    if preflop_only:
        return _make("preflop_only")

    if showdown:
        if hero_last_aggressor:
            return _make("value_success" if hero_won else "bluff_failed")
        if hero_won:
            return _make("bluff_catch")
        # 相手ベットにHeroがコールして敗北
        if call_verdict == VERDICT_CORRECT:
            return _make("nice_call")
        if call_verdict == VERDICT_INCORRECT:
            return _make("bad_call")
        return _make("call_lost")

    # ショーダウンなし（フォールドで終了）
    if hero_last_aggressor:
        return _make("hero_aggression_won")
    # 相手ベットにHeroがフォールド
    if call_verdict == VERDICT_CORRECT:  # コールが正解だった → 悪いフォールド
        return _make("bad_fold")
    if call_verdict == VERDICT_INCORRECT:  # コールは不正解 → 正しいフォールド
        return _make("nice_fold")
    return _make("fold_unknown")
