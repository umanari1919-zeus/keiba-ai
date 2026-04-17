import tweepy
import pandas as pd
import pickle
from dotenv import load_dotenv
import os
from datetime import datetime

# .envファイルからAPIキーを読み込む
load_dotenv("D:\\keiba_ai\\.env")

def create_post_text(race_code, bamei, odds, kishumei):
    """うまなり地蔵スタイルの投稿文を生成"""
    
    now = datetime.now()
    
    text = f"""🙏 うまなり地蔵のお告げ 🙏

📅 {now.strftime('%Y年%m月%d日')}

🔥 本日の閻魔帳に記された一頭

🐴 馬名：{bamei}
👤 騎手：{kishumei}
💰 オッズ：{odds:.1f}倍

📊 AIが導き出した穴馬候補
データと閻魔大王の御加護を信じよ🔥

#競馬予想 #うまなり地蔵 #AI予想 #穴馬"""
    
    return text

def post_to_x(text):
    """Xに投稿する"""
    
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
    
    # APIキーが設定されているか確認
    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("⚠️ APIキーが設定されていません！")
        print("📝 投稿予定テキスト：")
        print("="*40)
        print(text)
        print("="*40)
        return False
    
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        client.create_tweet(text=text)
        print("✅ X投稿完了！")
        return True
    except Exception as e:
        print(f"❌ 投稿失敗：{e}")
        return False

def generate_and_post():
    print(f"📱 [{datetime.now()}] X投稿生成開始...")
    
    # 予想結果を読み込む
    try:
        df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv", 
                         encoding="utf-8-sig")
    except:
        print("❌ simulation_2025.csvが見つかりません")
        return
    
    # 今日の予想（的中率が高い穴馬を選ぶ）
    df_hits = df[df['odds'] >= 3].copy()
    
    if len(df_hits) == 0:
        print("❌ 該当する予想がありません")
        return
    
    # サンプルとして最初の1件を投稿
    sample = df_hits.iloc[0]
    
    text = create_post_text(
        race_code=sample['race_code'],
        bamei=sample['bamei'],
        odds=sample['odds'],
        kishumei="AI選定"
    )
    
    print("\n📝 投稿予定テキスト：")
    print("="*40)
    print(text)
    print("="*40)
    
    post_to_x(text)

if __name__ == "__main__":
    generate_and_post()