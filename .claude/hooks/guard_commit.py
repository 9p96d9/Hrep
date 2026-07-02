"""PreToolUse(Bash) hook — git commit のガード。

CLAUDE.md 作業ルール2 の機械的強制:
- コミットメッセージに test:✅ または test:skip+理由 が必須
- --no-verify によるフック回避を遮断
exit 2 = ブロック（stderr が Claude にフィードバックされる）
"""
import json
import re
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")

# git commit 以外のコマンドは素通し
if not re.search(r"\bgit\b[^|&;]*\bcommit\b", cmd):
    sys.exit(0)

if "--no-verify" in cmd or "-n " in cmd:
    print("ブロック: --no-verify でのフック回避は禁止（CLAUDE.md 作業ルール）", file=sys.stderr)
    sys.exit(2)

# merge/revert 等メッセージを自動生成するコミットは素通し
if re.search(r"\bcommit\b[^|&;]*--(amend|no-edit)\b", cmd) and "-m" not in cmd:
    sys.exit(0)

if re.search(r"test:(✅|skip\+\S+)", cmd):
    sys.exit(0)

print(
    "ブロック: コミットメッセージに test:✅ または test:skip+理由 が必要です。\n"
    "テストを実行済みなら test:✅ を、不要なら test:skip+UI のように理由を付けてください。"
    "（CLAUDE.md 作業ルール2 / tests/PLAN.md コミットメッセージルール）",
    file=sys.stderr,
)
sys.exit(2)
