"""
SNS自動投稿ボット
- X (Twitter) 自動投稿
- Discord Bot 予想配信
- LINE Bot 通知
- Telegram Bot 通知
APIキーは .env ファイルに設定してください。
"""
import os
import json
import asyncio
import pandas as pd
from datetime import datetime

# ─── .env 読み込み ─────────────────────────────
def _load_env():
    env_path = "D:\\keiba_ai\\.env"
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()


# ──────────────────────────────────────────────
# 投稿文生成（共通）
# ──────────────────────────────────────────────

def generate_post_text(max_chars=270) -> str:
    """prediction_results から投稿文を生成"""
    try:
        picks_files = [f for f in os.listdir("D:\\keiba_ai")
                       if f.startswith("agent_picks_") and f.endswith(".json")]
        if picks_files:
            latest = sorted(picks_files)[-1]
            with open(f"D:\\keiba_ai\\{latest}", 'r', encoding='utf-8') as f:
                data = json.load(f)
            picks = data.get('approved_races', [])
        else:
            picks = []
    except Exception:
        picks = []

    today = datetime.now().strftime('%m/%d')
    lines = [f"【うまなり地蔵AI {today} 本日の予想】"]

    for p in picks[:3]:
        race   = p.get('race_code', '')[-4:]
        bamei  = p.get('bamei', '')
        odds   = p.get('odds', 0)
        ev     = p.get('ev', 0)
        if bamei:
            lines.append(f"R{race} ★{bamei} {odds:.1f}倍 EV={ev:.0%}")

    lines.append("#競馬予想 #AI予想 #うまなり地蔵 #穴馬")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars-3] + "..."
    return text


# ──────────────────────────────────────────────
# X (Twitter) 自動投稿
# ──────────────────────────────────────────────

def post_to_x(text: str) -> bool:
    """
    必要な環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, X_BEARER_TOKEN
    """
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=os.environ.get('X_API_KEY'),
            consumer_secret=os.environ.get('X_API_SECRET'),
            access_token=os.environ.get('X_ACCESS_TOKEN'),
            access_token_secret=os.environ.get('X_ACCESS_TOKEN_SECRET'),
        )
        response = client.create_tweet(text=text)
        print(f"  ✅ X投稿完了: tweet_id={response.data['id']}")
        return True
    except ImportError:
        print("  ⚠️ tweepy が未インストール: pip install tweepy")
    except Exception as e:
        print(f"  ⚠️ X投稿エラー: {e}")
    return False


# ──────────────────────────────────────────────
# Discord Bot
# ──────────────────────────────────────────────

def post_to_discord(text: str) -> bool:
    """
    必要な環境変数: DISCORD_WEBHOOK_URL
    Discord の Webhook URL を使って投稿（Bot不要）
    """
    try:
        import urllib.request
        import urllib.parse
        webhook_url = os.environ.get('DISCORD_WEBHOOK_URL', '')
        if not webhook_url:
            print("  ⚠️ DISCORD_WEBHOOK_URL が未設定")
            return False
        payload = json.dumps({'content': text, 'username': 'うまなり地蔵AI'}).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  ✅ Discord投稿完了: status={resp.status}")
            return True
    except Exception as e:
        print(f"  ⚠️ Discord投稿エラー: {e}")
    return False


# ──────────────────────────────────────────────
# Telegram Bot
# ──────────────────────────────────────────────

def post_to_telegram(text: str) -> bool:
    """
    必要な環境変数: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    """
    try:
        import telegram
        bot = telegram.Bot(token=os.environ.get('TELEGRAM_BOT_TOKEN', ''))
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        if not chat_id:
            print("  ⚠️ TELEGRAM_CHAT_ID が未設定")
            return False

        async def _send():
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text,
                                       parse_mode='HTML')

        asyncio.run(_send())
        print("  ✅ Telegram送信完了")
        return True
    except ImportError:
        print("  ⚠️ python-telegram-bot が未インストール")
    except Exception as e:
        print(f"  ⚠️ Telegram送信エラー: {e}")
    return False


# ──────────────────────────────────────────────
# LINE Bot (Messaging API)
# ──────────────────────────────────────────────

def post_to_line(text: str) -> bool:
    """
    必要な環境変数: LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID
    """
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', ''))
        user_id = os.environ.get('LINE_USER_ID', '')
        if not user_id:
            print("  ⚠️ LINE_USER_ID が未設定")
            return False
        api.push_message(user_id, TextSendMessage(text=text))
        print("  ✅ LINE送信完了")
        return True
    except ImportError:
        print("  ⚠️ line-bot-sdk が未インストール")
    except Exception as e:
        print(f"  ⚠️ LINE送信エラー: {e}")
    return False


# ──────────────────────────────────────────────
# 一括投稿
# ──────────────────────────────────────────────

def broadcast_picks(custom_text: str = None) -> dict:
    print("\n" + "="*55)
    print("📢 SNS一括配信")
    print("="*55)

    text = custom_text or generate_post_text()
    print(f"\n投稿内容:\n{text}\n")
    print(f"文字数: {len(text)}字")

    results = {
        'text':     text,
        'x':        False,
        'discord':  False,
        'telegram': False,
        'line':     False,
        'sent_at':  datetime.now().isoformat()
    }

    # 各プラットフォームに投稿
    if os.environ.get('X_API_KEY'):
        results['x'] = post_to_x(text)
    else:
        print("  ⏩ X: X_API_KEY 未設定（スキップ）")

    if os.environ.get('DISCORD_WEBHOOK_URL'):
        results['discord'] = post_to_discord(text)
    else:
        print("  ⏩ Discord: DISCORD_WEBHOOK_URL 未設定（スキップ）")

    if os.environ.get('TELEGRAM_BOT_TOKEN'):
        results['telegram'] = post_to_telegram(text)
    else:
        print("  ⏩ Telegram: TELEGRAM_BOT_TOKEN 未設定（スキップ）")

    if os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'):
        results['line'] = post_to_line(text)
    else:
        print("  ⏩ LINE: LINE_CHANNEL_ACCESS_TOKEN 未設定（スキップ）")

    print(f"\n  {'─'*40}")
    print(f"  X: {'✅' if results['x'] else '⏩'}  "
          f"Discord: {'✅' if results['discord'] else '⏩'}  "
          f"Telegram: {'✅' if results['telegram'] else '⏩'}  "
          f"LINE: {'✅' if results['line'] else '⏩'}")

    return results


# ──────────────────────────────────────────────
# .env テンプレート生成
# ──────────────────────────────────────────────

def create_env_template():
    template = """# うまなり地蔵AI 環境変数設定ファイル
# このファイルを D:\\keiba_ai\\.env として保存してください

# X (Twitter) API
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_BEARER_TOKEN=

# Discord Webhook URL
# サーバー設定 → テキストチャンネル → ウェブフック → 新しいウェブフック
DISCORD_WEBHOOK_URL=

# Telegram Bot
# @BotFather で作成したトークン
TELEGRAM_BOT_TOKEN=
# あなたのチャットID（@userinfobot で確認）
TELEGRAM_CHAT_ID=

# LINE Messaging API
# LINE Developers で作成したチャンネルアクセストークン
LINE_CHANNEL_ACCESS_TOKEN=
# 送信先のユーザーID
LINE_USER_ID=

# Anthropic API（claude_comment_06.py用）
ANTHROPIC_API_KEY=
"""
    env_path = "D:\\keiba_ai\\.env.template"
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(template)
    print(f"  📝 .env テンプレート生成: {env_path}")
    print("  → .env.template を .env にコピーして各APIキーを設定してください")


if __name__ == "__main__":
    create_env_template()
    broadcast_picks()
