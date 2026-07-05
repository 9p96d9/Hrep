"""run_detail_street_gate — detail_street 受入ゲートのCLIランナー。

sample_hands → annotate_hand → detail_street プロンプト → AI(Groq/Gemini) →
parse_json_array → validate_detail_street_batch（specs/ai_analysis.md §8）を
1コマンドで回し、violation を出す。violation があれば exit 1。

使い方:
    GROQ_API_KEY=gsk_... python scripts/run_detail_street_gate.py
    GEMINI_API_KEY=... python scripts/run_detail_street_gate.py
    python scripts/run_detail_street_gate.py --dry-run   # AI呼び出しせずプロンプトだけ確認
    python scripts/run_detail_street_gate.py --hands path/to/hands.json

fixtures 形式: {"scenario_name": <hand>, ...} または [<hand>, ...]。
gto_math / bluered_classification が無いハンドは annotate_hand で自動付与する。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import ai_prompt  # noqa: E402
from scripts.ai_validator import validate_detail_street_batch  # noqa: E402
from scripts.hand_converter import annotate_hand  # noqa: E402

DEFAULT_HANDS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "sample_hands.json",
)


def load_hands(path: str):
    """(names, hands) を返す。names は表示用ラベル、hands は annotate 済みハンド列。"""
    raw = json.load(open(path, encoding="utf-8"))
    if isinstance(raw, dict):
        names, items = list(raw.keys()), list(raw.values())
    elif isinstance(raw, list):
        items = raw
        names = [f"hand[{i}]" for i in range(len(raw))]
    else:
        raise SystemExit(f"未知のfixture形式: {type(raw).__name__}")

    hands = []
    for h in items:
        if "gto_math" not in h or "bluered_classification" not in h:
            h = annotate_hand(h)
        hands.append(h)
    return names, hands


def main() -> int:
    ap = argparse.ArgumentParser(description="detail_street 受入ゲートランナー")
    ap.add_argument("--hands", default=DEFAULT_HANDS, help="ハンドfixtureのパス")
    ap.add_argument("--dry-run", action="store_true", help="AI呼び出しせずプロンプト/到達フラグのみ表示")
    args = ap.parse_args()

    names, hands = load_hands(args.hands)
    prompt = ai_prompt.build_detail_street_prompt(hands)

    print(f"# hands: {len(hands)} | est tokens: {ai_prompt.estimate_tokens(len(hands))}")
    for i, name in enumerate(names, 1):
        f = ai_prompt.streets_reached_flags(hands[i - 1])
        print(f"  id={i} {name}: turn={f['turn']} river={f['river']}")

    if args.dry_run:
        print("\n=== SYSTEM PROMPT ===\n" + prompt["system"])
        print("\n=== USER PROMPT ===\n" + prompt["user"])
        return 0

    # 遅延importでdry-runは requests 不要
    from services import ai_providers

    text = ai_providers.run_chat(prompt["system"], prompt["user"])
    items = ai_providers.parse_json_array(text)

    flags = [dict(id=i + 1, **ai_prompt.streets_reached_flags(h)) for i, h in enumerate(hands)]
    violations = validate_detail_street_batch(items, flags)
    total = sum(len(v) for v in violations.values())

    print(f"\n=== violations: {total} 件 / {len(hands)} hands ===")
    if violations:
        print(json.dumps(violations, ensure_ascii=False, indent=1))
        print("\n受入ゲート: FAIL（specs/ai_analysis.md §8）。ai_prompt.py のシステムプロンプトを調整して再実行。")
        return 1
    print("受入ゲート: PASS（violation 0）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
