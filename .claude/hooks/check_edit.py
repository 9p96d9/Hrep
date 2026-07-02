"""PostToolUse(Edit|Write) hook — 編集直後の即時チェック。

- .py: ast.parse で構文チェック（デプロイ前でなく編集時点でエラーを検出）
- static/*.js: キャッシュバスト（?v=YYYYMMDD）更新のリマインド（GTO-時代の頻出事故）
exit 2 = stderr が Claude にフィードバックされる（編集自体は完了済み）
"""
import ast
import json
import pathlib
import sys

data = json.load(sys.stdin)
fp = data.get("tool_input", {}).get("file_path", "")
norm = fp.replace("\\", "/")

if norm.endswith(".py"):
    try:
        src = pathlib.Path(fp).read_text(encoding="utf-8")
        ast.parse(src, filename=fp)
    except SyntaxError as e:
        print(f"構文エラー: {fp}:{e.lineno} — {e.msg}。修正してください。", file=sys.stderr)
        sys.exit(2)
    except OSError:
        pass  # 削除直後など読めないケースは無視

elif ("/static/" in norm or norm.startswith("static/")) and norm.endswith(".js"):
    print(
        "リマインド: static JS を編集しました。テンプレートの ?v=YYYYMMDD キャッシュバストを"
        "更新しないとブラウザが旧JSを使い続けます（docs/features/classify_result.md）。",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
