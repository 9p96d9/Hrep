"""ハンド分類ロジック — specs/classify.md 準拠。

11カテゴリ・5ライン。判定の正は specs/classify.md §4 のカテゴリ→ライン対応表。
GTO判定（コール/フォールド共通機構）は §3 のV1ヒューリスティック。
迷ったら warn（判定困難）に倒す — REQUIREMENTS.md Must Not 準拠。
"""

# GTOスコア判定の3値（Heroが実際に取ったアクションに対する判定）
GTO_CORRECT = "correct"
GTO_INCORRECT = "incorrect"
GTO_UNKNOWN = "unknown"

CATEGORY_LABELS = {
    "value_success": "バリュー成功",
    "bluff_catch": "ブラフキャッチ",
    "nice_fold": "ナイスフォールド",
    "nice_call": "ナイスコール",
    "hero_aggression_won": "アグレッション勝利",
    "bluff_failed": "ブラフ失敗",
    "bad_call": "バッドコール",
    "bad_fold": "バッドフォールド",
    "call_lost": "コール負け(要確認)",
    "fold_unknown": "フォールド(要確認)",
    "preflop_only": "プリフロップのみ",
}

# specs/classify.md §4 — この表が正
CATEGORY_LINE = {
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

# specs/classify.md §4 — 難易度基礎スコア
CATEGORY_BASE_SCORE = {
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

POSTFLOP_STREETS = ("flop", "turn", "river")

_AGGRESSIVE_ACTIONS = {"bet", "raise", "allin", "all-in", "all_in"}

# GTO判定V1: 必要エクイティに対するハンド強度の中間帯（±この幅は判定困難に倒す）
GTO_JUDGE_MARGIN = 0.15


def classify_hand(hand, gto_verdict=None):
    """ハンドJSONを分類し bluered_classification 形式のdictを返す。

    gto_verdict: GTO_CORRECT / GTO_INCORRECT / GTO_UNKNOWN。
    Noneの場合は judge_gto_decision() で判定する（データ不足時は判定困難）。
    """
    postflop = _postflop_actions(hand)
    if not postflop:
        return _result("preflop_only")

    hero_pos = hand.get("hero_position")
    hero_won = (hand.get("hero_result_bb") or 0) >= 0
    last_action = postflop[-1]

    if _name(last_action) == "fold":
        if last_action.get("position") == hero_pos:
            verdict = gto_verdict if gto_verdict is not None else judge_gto_decision(hand)
            return _result(_fold_category(verdict))
        return _result("hero_aggression_won")

    # ショーダウン
    hero_is_last_aggressor = _last_aggressor(postflop) == hero_pos
    hero_called = _last_action_of(postflop, hero_pos) == "call"

    if hero_is_last_aggressor:
        return _result("value_success" if hero_won else "bluff_failed")
    if hero_called:
        if hero_won:
            return _result("bluff_catch")
        verdict = gto_verdict if gto_verdict is not None else judge_gto_decision(hand)
        return _result(_call_loss_category(verdict))

    # チェックダウン等、§3のフローが定義しないショーダウン。
    # ライン定義（blue=ショーダウン勝利）を優先し、敗北側は判定困難に倒す
    return _result("value_success" if hero_won else "call_lost")


def judge_gto_decision(hand):
    """GTOスコア判定（コール/フォールド共通機構）— specs/classify.md §3 V1ヒューリスティック。

    必要エクイティ（specs/gto_math.md §2 DEFENDER系）に対して、Heroハンドの
    ボード上の強さ（treys評価）が GTO_JUDGE_MARGIN を超えて上回れば「コールが正解」、
    下回れば「フォールドが正解」。中間帯・データ不足・treys未導入は判定困難に倒す。

    返り値はHeroが実際に取ったアクション（call/fold）に対する判定。
    """
    spot = _find_decision_spot(hand)
    if spot is None:
        return GTO_UNKNOWN
    hero_action, required_equity, board = spot

    strength = _hero_strength(hand.get("hero_cards"), board)
    if strength is None:
        return GTO_UNKNOWN

    if strength >= required_equity + GTO_JUDGE_MARGIN:
        call_is_correct = True
    elif strength <= required_equity - GTO_JUDGE_MARGIN:
        call_is_correct = False
    else:
        return GTO_UNKNOWN

    hero_did_call = hero_action == "call"
    return GTO_CORRECT if hero_did_call == call_is_correct else GTO_INCORRECT


def _result(category):
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "line": CATEGORY_LINE[category],
    }


def _name(action):
    return (action.get("action") or "").lower()


def _postflop_actions(hand):
    """フロップ以降の全アクションをストリート順に返す。"""
    streets = hand.get("streets") or {}
    actions = []
    for street in POSTFLOP_STREETS:
        data = streets.get(street) or {}
        for act in data.get("actions") or []:
            actions.append(act)
    return actions

def _last_aggressor(actions):
    for act in reversed(actions):
        if _name(act) in _AGGRESSIVE_ACTIONS:
            return act.get("position")
    return None


def _last_action_of(actions, position):
    for act in reversed(actions):
        if act.get("position") == position:
            return _name(act)
    return None


def _find_decision_spot(hand):
    """Heroが相手のベット/レイズに応答（call/fold）した最終スポットを探す。

    返り値: (hero_action, 必要エクイティ, その時点のボード) / 見つからなければ None
    """
    streets = hand.get("streets") or {}
    hero_pos = hand.get("hero_position")
    board = []
    found = None
    for street in POSTFLOP_STREETS:
        data = streets.get(street) or {}
        board = board + list(data.get("board") or [])
        pot = data.get("pot_bb")
        if pot is None:
            continue
        invested = {}  # このストリートの投入額（amount_bb はストリート内累計額とみなす）
        current_bet = 0
        aggressor = None
        for act in data.get("actions") or []:
            name = _name(act)
            pos = act.get("position")
            if name in _AGGRESSIVE_ACTIONS:
                amount = act.get("amount_bb") or 0
                pot += amount - invested.get(pos, 0)
                invested[pos] = amount
                current_bet = amount
                aggressor = pos
            elif name in ("call", "fold"):
                net_call = current_bet - invested.get(pos, 0)
                if pos == hero_pos and aggressor not in (None, hero_pos) and net_call > 0:
                    required = net_call / (pot + net_call)
                    found = (name, required, list(board))
                if name == "call" and net_call > 0:
                    pot += net_call
                    invested[pos] = current_bet
    return found


def _hero_strength(hero_cards, board):
    """ボード上のHeroハンド強度（全ヴィランコンボに対する勝率近似）。treys未導入なら None。"""
    if not hero_cards or len(hero_cards) != 2 or len(board) < 3:
        return None
    try:
        from treys import Card, Deck, Evaluator
    except ImportError:
        return None
    try:
        hero = [Card.new(c) for c in hero_cards]
        board_c = [Card.new(c) for c in board[:5]]
    except (KeyError, ValueError):
        return None
    evaluator = Evaluator()
    hero_rank = evaluator.evaluate(board_c, hero)
    dead = set(hero + board_c)
    remaining = [c for c in Deck.GetFullDeck() if c not in dead]
    wins = ties = total = 0
    for i in range(len(remaining)):
        for j in range(i + 1, len(remaining)):
            villain_rank = evaluator.evaluate(board_c, [remaining[i], remaining[j]])
            total += 1
            if hero_rank < villain_rank:
                wins += 1
            elif hero_rank == villain_rank:
                ties += 1
    if total == 0:
        return None
    return (wins + ties * 0.5) / total


def _fold_category(verdict):
    if verdict == GTO_CORRECT:
        return "nice_fold"
    if verdict == GTO_INCORRECT:
        return "bad_fold"
    return "fold_unknown"


def _call_loss_category(verdict):
    if verdict == GTO_CORRECT:
        return "nice_call"
    if verdict == GTO_INCORRECT:
        return "bad_call"
    return "call_lost"
