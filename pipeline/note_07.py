import pandas as pd
from datetime import datetime
import random

def generate_note_article():
    print(f"📝 [{datetime.now()}] note記事生成中...")
    
    # 予想データ読み込み
    df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                     encoding="utf-8-sig")
    
    # 今週の成績集計
    total = len(df)
    hits = len(df[df['hit'] == 1])
    hit_rate = hits / total * 100
    recovery = (df[df['hit']==1]['odds'] * 100).sum() / (total * 100) * 100
    
    # 的中馬TOP5
    hit_df = df[df['hit'] == 1].copy()
    hit_df = hit_df.sort_values('odds', ascending=False).head(5)
    
    # 的中馬リスト
    hit_list = ""
    for _, row in hit_df.iterrows():
        hit_list += f"🏆 {row['bamei']}（{row['odds']:.1f}倍）\n"
    
    # note記事本文
    article = f"""# 🙏 うまなり地蔵AI予想レポート
## {datetime.now().strftime('%Y年%m月')}の成績

---

## 📊 今月の成績サマリー

| 項目 | 結果 |
|------|------|
| 対象レース数 | {total:,}レース |
| 的中数 | {hits:,}回 |
| 的中率 | {hit_rate:.1f}% |
| 回収率 | {recovery:.1f}% |

---

## 🔥 高配当的中TOP5

{hit_list}

---

## 🤖 AIシステムについて

うまなり地蔵AIは以下の技術で構築されています。

- **データソース**：JRA-VAN DataLab（1954年〜現在）
- **学習データ**：約45万件のレースデータ
- **アルゴリズム**：LightGBM
- **特徴量**：馬体重・過去成績・騎手成績・調教師成績など

---

## 🙏 地蔵からひとこと

データと閻魔大王の御加護により、
穴馬を炙り出す修行を続けております。

回収率{recovery:.1f}%という結果は、
AIの力と競馬の神秘が融合した証。

引き続き閻魔帳に記された馬たちを
皆様にお届けしてまいります🔥

---

*※本記事は競馬予想AIの研究・記録目的で作成しています。
馬券購入は自己責任でお願いします。*

#競馬予想AI #うまなり地蔵 #機械学習 #穴馬予想
"""
    
    # ファイルに保存
    filename = f"D:\\keiba_ai\\note_{datetime.now().strftime('%Y%m')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(article)
    
    print(f"✅ note記事生成完了！")
    print(f"💾 {filename} に保存しました！")
    print("\n" + "="*40)
    print(article[:500] + "...")
    print("="*40)
    
    return article

if __name__ == "__main__":
    generate_note_article()