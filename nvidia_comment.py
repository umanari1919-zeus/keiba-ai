"""
うまなり地蔵AI — NVIDIA API コメント生成ツール
実際の馬名・オッズ・騎手などを入力してX投稿用コメントを生成する。

使い方:
  python nvidia_comment.py                        # 対話モード
  python nvidia_comment.py --bamei テスト馬 --odds 25.5 --kishu 武豊
"""
import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv("D:\\keiba_ai\\.env")

SYSTEM_PERSONA = """あなたは「うまなり地蔵」です。
競馬予想AIとして、閻魔大王・地蔵・賽の河原などの仏教的世界観でコメントを書きます。

ルール：
- 100文字以内で1つのコメントだけ出力する
- 馬名・騎手名・オッズを必ず含める
- 必ず絵文字を2〜3個使う（🙏👹🔥💥🎯✨のどれか）
- 「地蔵」「閻魔」「業火」などの言葉を1つ使う
- 余分な説明・前置きは不要。コメント本文のみ出力する"""


def generate_comment(bamei: str, odds: float, kishu: str,
                     barei: int = 4, bataiju: int = 480,
                     zogen: str = "前走同重") -> str:
    """NVIDIA APIでうまなり地蔵コメントを生成"""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("❌ NVIDIA_API_KEY が .env に設定されていません")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("❌ openai パッケージが未インストールです: pip install openai")
        sys.exit(1)

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    prompt = (
        f"馬名：{bamei}（{barei}歳）\n"
        f"騎手：{kishu}\n"
        f"オッズ：{odds:.1f}倍\n"
        f"馬体重：{bataiju}kg（{zogen}）\n\n"
        f"上記のデータをもとに、うまなり地蔵のペルソナで"
        f"100文字以内のX投稿コメントを1つだけ書いてください。"
    )

    print(f"\n⏳ {bamei}（{odds:.1f}倍）のコメント生成中...")

    response = client.chat.completions.create(
        model="meta/llama-3.1-70b-instruct",
        messages=[
            {"role": "system", "content": SYSTEM_PERSONA},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.8,
        max_tokens=200
    )

    comment = response.choices[0].message.content.strip()

    # X投稿用テキスト整形
    post = (
        f"🙏 うまなり地蔵のお告げ 🙏\n\n"
        f"{comment}\n\n"
        f"💰 オッズ：{odds:.1f}倍\n\n"
        f"#競馬予想 #うまなり地蔵 #AI予想 #穴馬"
    )
    return post


def interactive_mode():
    """対話モード：入力を促してコメント生成"""
    print("=" * 50)
    print("  うまなり地蔵AI — コメント生成ツール")
    print("=" * 50)
    print("※ 空Enterでデフォルト値を使用\n")

    bamei  = input("馬名　　: ").strip() or "テスト馬"
    odds   = float(input("オッズ　: ").strip() or "25.5")
    kishu  = input("騎手名　: ").strip() or "AI選定"
    barei  = int(input("馬齢　　: ").strip() or "4")
    bataiju = int(input("馬体重　: ").strip() or "480")
    zogen  = input("体重変化: ").strip() or "前走同重"

    post = generate_comment(bamei, odds, kishu, barei, bataiju, zogen)

    print("\n" + "=" * 50)
    print(post)
    print("=" * 50)

    # ファイルに保存
    out = f"D:\\keiba_ai\\nvidia_comment_output.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(post)
    print(f"\n💾 {out} に保存しました")


def main():
    parser = argparse.ArgumentParser(description="うまなり地蔵 NVIDIA コメント生成")
    parser.add_argument("--bamei",  default="", help="馬名")
    parser.add_argument("--odds",   type=float, default=0.0, help="オッズ")
    parser.add_argument("--kishu",  default="AI選定", help="騎手名")
    parser.add_argument("--barei",  type=int, default=4, help="馬齢")
    parser.add_argument("--bataiju", type=int, default=480, help="馬体重")
    parser.add_argument("--zogen",  default="前走同重", help="体重変化")
    args = parser.parse_args()

    if args.bamei and args.odds > 0:
        # 引数モード
        post = generate_comment(
            args.bamei, args.odds, args.kishu,
            args.barei, args.bataiju, args.zogen
        )
        print("\n" + "=" * 50)
        print(post)
        print("=" * 50)
    else:
        # 対話モード
        interactive_mode()


if __name__ == "__main__":
    main()
