"""ai_providers — Groq / Gemini 呼び出し（BYOK対応）

仕様: specs/ai_analysis.md §2
  gsk_...  → Groq   (llama-3.3-70b-versatile)
  その他   → Gemini (gemini-2.5-flash)
優先順位: 環境変数 GROQ_API_KEY → GEMINI_API_KEY → BYOKキーの形式判定
"""

from __future__ import annotations

import json
import os

import requests

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
TIMEOUT_SEC = 180


class AIProviderError(RuntimeError):
    pass


def resolve_provider(byok_key: str | None = None) -> tuple[str, str]:
    """(provider, api_key) を返す。provider は "groq" / "gemini"。"""
    if os.environ.get("GROQ_API_KEY"):
        return "groq", os.environ["GROQ_API_KEY"]
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini", os.environ["GEMINI_API_KEY"]
    if not byok_key:
        raise AIProviderError("APIキーが指定されていません（BYOK）")
    if byok_key.startswith("gsk_"):
        return "groq", byok_key
    return "gemini", byok_key


def run_chat(system: str, user: str, byok_key: str | None = None) -> str:
    """プロンプトを実行してテキスト応答を返す。"""
    provider, api_key = resolve_provider(byok_key)
    if provider == "groq":
        return _run_groq(system, user, api_key)
    return _run_gemini(system, user, api_key)


def _run_groq(system: str, user: str, api_key: str) -> str:
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
        },
        timeout=TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        raise AIProviderError(f"Groq API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _run_gemini(system: str, user: str, api_key: str) -> str:
    resp = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.4},
        },
        timeout=TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        raise AIProviderError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise AIProviderError(f"Gemini応答の形式が不正: {json.dumps(data)[:300]}") from e


def parse_json_array(text: str) -> list:
    """AI応答からJSON配列を取り出す（コードフェンス・前後の説明文を許容）。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            raise AIProviderError(f"AI応答をJSON配列として解釈できません: {text[:200]}")
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, list):
        raise AIProviderError("AI応答がJSON配列ではありません")
    return parsed
