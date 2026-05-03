"""
うまなり地蔵コメント生成
Claude Haiku 4.5 + prompt caching + ローカルキャッシュで低コスト運用する。

APIキーなし時はテンプレートにフォールバック。
"""
import os
import json
import random
import hashlib
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("D:\\keiba_ai\\.env")

CACHE_FILE = "D:\\keiba_ai\\data\\comment_cache.json"
MODEL      = "claude-haiku-4-5-20251001"   # 最安モデル
MAX_TOKENS = 150                            # 必要最小限

# ──────────────────────────────────────────────────────────────
# うまなり地蔵ペルソナ（prompt caching の対象：変化しない部分）
# ──────────────────────────────────────────────────────────────

SYSTEM_PERSONA = """あなたは「うまなり地蔵」です。
競馬予想AIとして、閻魔大王・地蔵・賽の河原などの仏教的世界観でコメントを書きます。

ルール：
- 100文字以内で1つのコメントだけ出力する
- 馬名・騎手名・オッズを必ず含める
- 必ず絵文字を2〜3個使う（🙏👹🔥💥🎯✨のどれか）
- 「地蔵」「閻魔」「業火」などの言葉を1つ使う
- 余分な説明・前置きは不要。コメント本文のみ出力する"""


# ──────────────────────────────────────────────────────────────
# ローカルキャッシュ
# ──────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        return {}
    with open(CACHE_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_cache(cache: dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _cache_key(bamei: str, odds: float) -> str:
    raw = f"{bamei}_{odds:.1f}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ──────────────────────────────────────────────────────────────
# Claude API 呼び出し（Haiku + prompt caching）
# ──────────────────────────────────────────────────────────────

def _call_ollama(bamei: str, odds: float, kishumei: str,
                 barei: int, bataiju: int,
                 zogen_sa: int, zogen_fugo: int) -> str:
    """
    Ollama (local LLM) でコメントを生成。Claude API より優先（無料）。
    Ollama が起動していない場合は空文字を返す。
    """
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return ""
        model = get_model_for_task("japanese")  # X投稿コメントは日本語プロファイル
        if not model:
            return ""

        weight_str = (f"+{zogen_sa}kg増" if zogen_fugo == 1 and zogen_sa > 0
                      else f"-{zogen_sa}kg減" if zogen_fugo == -1 and zogen_sa > 0
                      else "前走同重")

        prompt = (
            f"馬名：{bamei}（{barei}歳）\n"
            f"騎手：{kishumei}\n"
            f"オッズ：{odds:.1f}倍\n"
            f"馬体重：{bataiju}kg（{weight_str}）\n\n"
            f"上記のデータをもとに、うまなり地蔵のペルソナで"
            f"100文字以内のX投稿コメントを1つだけ書いてください。"
        )
        result = _generate(prompt, system=SYSTEM_PERSONA, model=model, temperature=0.8)
        if result:
            print(f"  🤖 Ollama生成: {len(result)}文字")
        return result or ""
    except Exception as e:
        print(f"  [ollama] comment skip: {e}")
        return ""


def _call_claude(bamei: str, odds: float, kishumei: str,
                 barei: int, bataiju: int,
                 zogen_sa: int, zogen_fugo: int) -> str:
    """
    Claude Haiku に1コメントを生成させる。
    SYSTEM_PERSONA を cache_control でキャッシュし、
    2回目以降の入力トークンコストを約90%削減する。
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        weight_str = (f"+{zogen_sa}kg増" if zogen_fugo == 1 and zogen_sa > 0
                      else f"-{zogen_sa}kg減" if zogen_fugo == -1 and zogen_sa > 0
                      else "前走同重")

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {
                        # ペルソナ部分をキャッシュ（TTL 5分、変化しない）
                        "type": "text",
                        "text": SYSTEM_PERSONA,
                        "cache_control": {"type": "ephemeral"}
                    },
                    {
                        # レースごとに変わる情報（キャッシュ対象外）
                        "type": "text",
                        "text": (f"馬名：{bamei}（{barei}歳）\n"
                                 f"騎手：{kishumei}\n"
                                 f"オッズ：{odds:.1f}倍\n"
                                 f"馬体重：{bataiju}kg（{weight_str}）")
                    }
                ]
            }]
        )

        # usage ログ（キャッシュ効果を確認できる）
        usage = response.usage
        cache_hit = getattr(usage, 'cache_read_input_tokens', 0)
        cache_write = getattr(usage, 'cache_creation_input_tokens', 0)
        if cache_hit > 0:
            print(f"  💾 キャッシュヒット: {cache_hit}トークン節約")
        elif cache_write > 0:
            print(f"  📝 キャッシュ書込: {cache_write}トークン（次回から節約）")

        return response.content[0].text.strip()

    except ImportError:
        return ""   # APIなし → フォールバックへ
    except Exception as e:
        print(f"  ⚠️ Claude API エラー（テンプレートで代替）: {e}")
        return ""


# ──────────────────────────────────────────────────────────────
# テンプレートフォールバック（APIなし・エラー時）
# ──────────────────────────────────────────────────────────────

def _template_comment(bamei: str, odds: float, kishumei: str,
                      pred_chakujun: int, barei: int,
                      bataiju: int, zogen_sa: int, zogen_fugo: int) -> str:
    if zogen_fugo == 1 and zogen_sa > 10:
        taiju = f"馬体重+{zogen_sa}kgと気配充実🔥"
    elif zogen_fugo == -1 and zogen_sa > 10:
        taiju = f"馬体重-{zogen_sa}kgと絞れた体つき✨"
    else:
        taiju = f"馬体重{bataiju}kgと安定した仕上がり👍"

    odds_line = "閻魔帳が示す大穴候補👹" if odds >= 10 else "地蔵のお告げによる中穴🙏"
    kishu_line = random.choice([
        f"{kishumei}騎手との相性も良好",
        f"{kishumei}騎手が手綱を握る",
    ])
    shime = random.choice([
        "閻魔大王の審判が下る時、この馬の名を刻め🔥",
        "うまなり地蔵が閻魔帳に記したこの馬を見逃すな🙏",
        "地獄の業火で炙り出したこの一頭に注目せよ👹",
    ])

    return (f"💥 {odds_line}\n"
            f"🐴 {bamei}（{barei}歳）/ {kishu_line}\n"
            f"⚖️ {taiju}\n{shime}")


# ──────────────────────────────────────────────────────────────
# メイン生成関数
# ──────────────────────────────────────────────────────────────

def generate_comment(bamei: str, odds: float, kishumei: str,
                     pred_chakujun: int, barei: int,
                     bataiju: int, zogen_sa: int, zogen_fugo: int) -> str:
    """
    1. ローカルキャッシュを確認（同一馬+オッズが存在すれば API 呼び出しなし）
    2. Anthropic APIキーがあれば Haiku + prompt caching で生成
    3. APIなし・エラー時はテンプレートにフォールバック
    """
    key   = _cache_key(bamei, odds)
    cache = _load_cache()

    if key in cache:
        print(f"  ✅ ローカルキャッシュヒット: {bamei}")
        return cache[key]

    # 優先順位: Ollama（無料・ローカル）→ Claude API（有料）→ テンプレート
    comment = _call_ollama(bamei, odds, kishumei, barei, bataiju, zogen_sa, zogen_fugo)

    if not comment:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            comment = _call_claude(bamei, odds, kishumei,
                                   barei, bataiju, zogen_sa, zogen_fugo)
        else:
            comment = ""

    if not comment:
        comment = _template_comment(bamei, odds, kishumei, pred_chakujun,
                                    barei, bataiju, zogen_sa, zogen_fugo)

    # キャッシュ保存（最大500件）
    cache[key] = comment
    if len(cache) > 500:
        oldest = list(cache.keys())[0]
        del cache[oldest]
    _save_cache(cache)

    return comment


def generate_todays_post() -> str:
    print(f"📝 [{datetime.now()}] 本日の予想コメント生成中...")

    try:
        df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                         encoding="utf-8-sig", on_bad_lines="skip")
    except FileNotFoundError:
        print("❌ simulation_2025.csv が見つかりません")
        return ""

    df_ana = df[df['odds'] >= 3].copy()
    if len(df_ana) == 0:
        print("❌ 穴馬候補がありません")
        return ""

    sample = df_ana.sample(1).iloc[0]
    print(f"  選択: {sample['bamei']} ({sample['odds']:.1f}倍)")

    comment = generate_comment(
        bamei=str(sample['bamei']),
        odds=float(sample['odds']),
        kishumei=str(sample.get('kishumei_ryakusho', 'AI選定')),
        pred_chakujun=int(sample.get('pred_chakujun', 5)),
        barei=int(sample.get('barei', 0)),
        bataiju=int(sample.get('bataiju', 0)),
        zogen_sa=int(sample.get('zogen_sa', 0)),
        zogen_fugo=int(sample.get('zogen_fugo', 0)),
    )

    post_text = (f"🙏 うまなり地蔵のお告げ 🙏\n\n"
                 f"📅 {datetime.now().strftime('%Y年%m月%d日')}\n\n"
                 f"{comment}\n\n"
                 f"💰 オッズ：{sample['odds']:.1f}倍\n\n"
                 f"#競馬予想 #うまなり地蔵 #AI予想 #穴馬")

    print("\n" + "="*40)
    print(post_text)
    print("="*40)

    with open("D:\\keiba_ai\\today_post.txt", "w", encoding="utf-8") as f:
        f.write(post_text)
    print("💾 today_post.txt に保存しました")

    return post_text


if __name__ == "__main__":
    generate_todays_post()
