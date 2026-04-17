import pandas as pd
import random
from datetime import datetime

def generate_comment(bamei, odds, kishumei, pred_chakujun, 
                     barei, bataiju, zogen_sa, zogen_fugo):
    """うまなり地蔵スタイルのコメントを自動生成"""
    
    # 体重増減のコメント
    if zogen_fugo == 1 and zogen_sa > 10:
        taiju_comment = f"馬体重+{int(zogen_sa)}kgと気配充実🔥"
    elif zogen_fugo == -1 and zogen_sa > 10:
        taiju_comment = f"馬体重-{int(zogen_sa)}kgと絞れた体つき✨"
    else:
        taiju_comment = f"馬体重{int(bataiju)}kgと安定した仕上がり👍"
    
    # オッズ別コメント
    if odds >= 10:
        odds_comment = "閻魔帳が示す大穴候補👹"
        emoji = "💥"
    elif odds >= 5:
        odds_comment = "地蔵のお告げによる中穴狙い🙏"
        emoji = "🎯"
    else:
        odds_comment = "AIが導き出した本命候補⭐"
        emoji = "👑"
    
    # 着順予測コメント
    if pred_chakujun <= 3:
        pred_comment = "AIは上位入線を確信している"
    elif pred_chakujun <= 6:
        pred_comment = "AIは好走圏内と判断"
    else:
        pred_comment = "AIが穴をあける可能性を示唆"
    
    # 騎手コメント
    kishu_comments = [
        f"{kishumei}騎手との相性も良好",
        f"{kishumei}騎手が手綱を握る",
        f"{kishumei}騎手の腕に期待",
    ]
    kishu_comment = random.choice(kishu_comments)
    
    # 締めのセリフパターン
    shime_patterns = [
        "閻魔大王の審判が下る時、この馬の名を刻め🔥",
        "地獄の業火で炙り出したこの一頭に注目せよ👹",
        "うまなり地蔵が閻魔帳に記したこの馬を見逃すな🙏",
        "賽の河原で積み上げた石の数だけ、この馬を信じよ🙏",
        "地蔵の数珠が示す運命、この馬に賭けてみよ✨",
    ]
    shime = random.choice(shime_patterns)
    
    comment = f"""{emoji} {odds_comment}

🐴 {bamei}（{int(barei)}歳）
👤 {kishu_comment}
⚖️ {taiju_comment}
🔮 {pred_comment}

{shime}"""
    
    return comment

def generate_todays_post():
    print(f"📝 [{datetime.now()}] 本日の予想コメント生成中...")
    
    # 予想データ読み込み
    try:
        df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                         encoding="utf-8-sig")
    except:
        print("❌ simulation_2025.csvが見つかりません")
        return
    
    # 列名確認
    print(f"列名：{list(df.columns)}")
    
    # 穴馬候補を抽出
    df_ana = df[df['odds'] >= 3].copy()
    
    if len(df_ana) == 0:
        print("❌ 穴馬候補がありません")
        return
    
    # ランダムに1頭選ぶ
    sample = df_ana.sample(1).iloc[0]
    print(f"選ばれた馬：{sample['bamei']}")
    print(f"列の値：{sample.to_dict()}")
    
    # コメント生成
    comment = generate_comment(
        bamei=sample['bamei'],
        odds=sample['odds'],
        kishumei=sample.get('kishumei_ryakusho', 'AI選定'),
        pred_chakujun=sample['pred_chakujun'],
        barei=sample.get('barei', 0),
        bataiju=sample.get('bataiju', 0),
        zogen_sa=sample.get('zogen_sa', 0),
        zogen_fugo=sample.get('zogen_fugo', 0)
    )
    
    # X投稿文を作成
    post_text = f"""🙏 うまなり地蔵のお告げ 🙏

📅 {datetime.now().strftime('%Y年%m月%d日')}

{comment}

💰 オッズ：{sample['odds']:.1f}倍

#競馬予想 #うまなり地蔵 #AI予想 #穴馬"""

    print("\n" + "="*40)
    print(post_text)
    print("="*40)
    
    # テキストファイルに保存
    with open("D:\\keiba_ai\\today_post.txt", "w", encoding="utf-8") as f:
        f.write(post_text)
    
    print("\n💾 today_post.txt に保存しました！")
    return post_text

if __name__ == "__main__":
    generate_todays_post()