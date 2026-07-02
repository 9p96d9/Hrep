"""
Fable 5 品質テスト — explain モード
specs/ai_analysis.md の品質ルールに準拠した出力を確認する
"""
import anthropic
import os

SAMPLE_HAND = """
ポジション: BTN (Hero) vs BB
スポット: SRP、リバー、ポットベット vs コール判断

ボード: Kh 9d 2c | 5s | 7h
プリフロップ: BTN RFI 2.5bb, BB call
フロップ: BBチェック、BTN CBet 1/3ポット、BBコール
ターン: BBチェック、BTNチェック
リバー: BBがポットベット (60bb into 60bb)

Heroハンド: JsTs (ストレートフィニッシュ)

[GTO数学] BTN vs BB | river | BB bet 100% pot
α (ベット比率) = 0.50 → 50%ポット = α/(1+α) = 33%
必要成功率 = 33%
MDF(Hero) = 1 - 0.50 = 50% （ポットベットに対してHeroは50%コールが均衡）
バリューターゲット: BTNがコールする場合、BBのブラフ:バリュー比率が鍵
"""

SYSTEM_PROMPT = """あなたはGTOポーカー分析の専門家です。
主語は必ずポジション名（BTN, BB, CO等）にしてください。
[GTO数学]ブロックの数値のみ引用し、AI独自の計算は禁止です。
MDF言及はリバーのみ許可。フロップ/ターンはエクイティ・ドロー・レンジで論じてください。
400〜1200文字で以下のセクションを段落で展開してください:
1. 均衡レンジとHeroのポジション
2. GTO数学的観点（MDF/必要成功率/バリューターゲット）
3. 相手レンジの変化と読み
4. 相手への搾取戦略
5. 代替ライン"""

def test_explain():
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    print("=== Fable 5 explain モード テスト ===\n")

    with client.messages.stream(
        model="claude-fable-5",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": SAMPLE_HAND}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

    print("\n\n=== 完了 ===")
    msg = stream.get_final_message()
    input_t = msg.usage.input_tokens
    output_t = msg.usage.output_tokens
    cost = (input_t / 1_000_000) * 10 + (output_t / 1_000_000) * 50
    print(f"tokens: in={input_t} out={output_t} | 推定コスト: ${cost:.4f}")

if __name__ == "__main__":
    test_explain()
