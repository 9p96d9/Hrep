"""リバーエクイティ推定 — レンジ区間モデル（specs/classify.md §3 V1アルゴリズム）。

相手のベットレンジは不明なので、単一の推定値でなく「もっともらしいレンジ族」に
対するエクイティ区間を計算し、区間全体が必要エクイティの同じ側にあるときだけ
correct / incorrect を断定する。跨いだら判定困難（unknown）に倒す。

対象はリバーのみ（全列挙・乱数なし・決定的）。フロップ/ターンは常に unknown。
依存: treys（純Python）。classify.py はこのモジュールに依存しない。
"""
from __future__ import annotations

import itertools

from treys import Card, Evaluator

from scripts.classify import JUDGE_MARGIN, VERDICT_UNKNOWN, judge_call_correctness

# 悲観バウンドのレンジ幅: 強い順に上位1/3（バリュー寄りのベットレンジ想定）
PESSIMISTIC_TOP_FRACTION = 1 / 3

_RANKS = "23456789TJQKA"
_SUITS = "shdc"
_DECK = tuple(r + s for r in _RANKS for s in _SUITS)

_evaluator = Evaluator()


def _villain_scores(hero_cards: list[str], board: list[str]) -> tuple[int, list[int]]:
    """Heroのtreysスコアと、残り45枚からなる全相手コンボ990通りのスコア（強い順）。"""
    used = set(hero_cards) | set(board)
    board_ints = [Card.new(c) for c in board]
    hero_score = _evaluator.evaluate(board_ints, [Card.new(c) for c in hero_cards])
    remaining = [c for c in _DECK if c not in used]
    scores = [
        _evaluator.evaluate(board_ints, [Card.new(c1), Card.new(c2)])
        for c1, c2 in itertools.combinations(remaining, 2)
    ]
    scores.sort()  # treysはスコアが小さいほど強い
    return hero_score, scores


def river_equity_vs_top_fraction(
    hero_cards: list[str],
    board: list[str],
    top_fraction: float = 1.0,
) -> float:
    """強い順に上位 top_fraction のレンジに対するHeroのリバーエクイティ（引き分けは0.5）。"""
    hero_score, scores = _villain_scores(hero_cards, board)
    n = max(1, round(len(scores) * top_fraction))
    in_range = scores[:n]
    wins = sum(1 for s in in_range if hero_score < s)
    ties = sum(1 for s in in_range if hero_score == s)
    return (wins + 0.5 * ties) / n


def river_equity_interval(hero_cards: list[str], board: list[str]) -> tuple[float, float]:
    """(悲観バウンド, 楽観バウンド) を返す。悲観=上位1/3レンジ、楽観=均一レンジ。"""
    hero_score, scores = _villain_scores(hero_cards, board)

    def equity(top_fraction: float) -> float:
        n = max(1, round(len(scores) * top_fraction))
        in_range = scores[:n]
        wins = sum(1 for s in in_range if hero_score < s)
        ties = sum(1 for s in in_range if hero_score == s)
        return (wins + 0.5 * ties) / n

    return equity(PESSIMISTIC_TOP_FRACTION), equity(1.0)


def judge_call(
    hero_cards: list[str],
    board: list[str],
    required_equity: float | None,
    margin: float = JUDGE_MARGIN,
) -> str:
    """「コールが正解か」のverdict。フォールド側も同じ結果を反転して解釈する。

    - 悲観バウンド ≥ required + margin → correct（強いレンジ想定でもコールは浮く）
    - 楽観バウンド ≤ required − margin → incorrect（最大ブラフ想定でもコールは沈む）
    - それ以外・リバー未到達・入力不足 → unknown（迷ったらwarn）
    """
    if required_equity is None or len(board) != 5 or len(hero_cards) != 2:
        return VERDICT_UNKNOWN
    pessimistic, optimistic = river_equity_interval(hero_cards, board)

    correct_side = judge_call_correctness(pessimistic, required_equity, margin)
    if correct_side == "correct":
        return correct_side
    incorrect_side = judge_call_correctness(optimistic, required_equity, margin)
    if incorrect_side == "incorrect":
        return incorrect_side
    return VERDICT_UNKNOWN
