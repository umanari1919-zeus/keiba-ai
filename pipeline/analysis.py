import pandas as pd
import numpy as np

def detailed_analysis():
    df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                     encoding="utf-8-sig", on_bad_lines="skip")
    
    print("="*50)
    print("📊 2025年 詳細分析レポート")
    print("="*50)

    # ① オッズ帯別
    print("\n【① オッズ帯別成績】")
    df['odds_band'] = pd.cut(df['odds'], 
        bins=[0,3,5,10,20,50,999],
        labels=['〜3倍','3〜5倍','5〜10倍',
                '10〜20倍','20〜50倍','50倍〜'])
    for band, g in df.groupby('odds_band', observed=True):
        total = len(g)
        hits = g['hit'].sum()
        ret = (g[g['hit']==1]['odds']*100).sum()
        bet = total * 100
        print(f"  {band}：{total}R "
              f"的中{hits}回({hits/total*100:.1f}%) "
              f"回収率{ret/bet*100:.1f}% "
              f"損益{ret-bet:+,.0f}円")

    # ② 的中率別損益
    print("\n【② 月別成績】")
    df['month'] = df['race_code'].astype(str).str[4:6]
    for month, g in df.groupby('month'):
        total = len(g)
        hits = g['hit'].sum()
        ret = (g[g['hit']==1]['odds']*100).sum()
        bet = total * 100
        print(f"  {month}月：{total}R "
              f"的中{hits}回({hits/total*100:.1f}%) "
              f"回収率{ret/bet*100:.1f}% "
              f"損益{ret-bet:+,.0f}円")

    # ③ 高配当的中TOP10
    print("\n【③ 高配当的中TOP10】")
    hit_df = df[df['hit']==1].sort_values('odds', ascending=False).head(10)
    for _, row in hit_df.iterrows():
        print(f"  🏆 {row['bamei']} "
              f"{row['odds']:.1f}倍 "
              f"（{row['kishumei_ryakusho']}騎手）")

    # ④ 騎手別成績TOP10
    print("\n【④ 騎手別成績TOP10（回収率順）】")
    kishu_stats = df.groupby('kishumei_ryakusho').apply(
        lambda g: pd.Series({
            'races': len(g),
            'hits': g['hit'].sum(),
            'return': (g[g['hit']==1]['odds']*100).sum(),
            'bet': len(g)*100
        })
    )
    kishu_stats['hit_rate'] = kishu_stats['hits']/kishu_stats['races']*100
    kishu_stats['recovery'] = kishu_stats['return']/kishu_stats['bet']*100
    kishu_stats = kishu_stats[kishu_stats['races'] >= 10]
    kishu_stats = kishu_stats.sort_values('recovery', ascending=False).head(10)
    for kishu, row in kishu_stats.iterrows():
        print(f"  {kishu}：{int(row['races'])}R "
              f"的中率{row['hit_rate']:.1f}% "
              f"回収率{row['recovery']:.1f}%")

    # ⑤ 馬齢別成績
    print("\n【⑤ 馬齢別成績】")
    for barei, g in df.groupby('barei'):
        total = len(g)
        if total < 50:
            continue
        hits = g['hit'].sum()
        ret = (g[g['hit']==1]['odds']*100).sum()
        bet = total * 100
        print(f"  {int(barei)}歳：{total}R "
              f"的中{hits}回({hits/total*100:.1f}%) "
              f"回収率{ret/bet*100:.1f}% "
              f"損益{ret-bet:+,.0f}円")

    # ⑥ 総合サマリー
    total = len(df)
    hits = df['hit'].sum()
    ret = (df[df['hit']==1]['odds']*100).sum()
    bet = total * 100
    print(f"\n{'='*50}")
    print(f"📈 総合サマリー")
    print(f"{'='*50}")
    print(f"対象レース：{total:,}R")
    print(f"的中数　　：{hits:,}回")
    print(f"的中率　　：{hits/total*100:.1f}%")
    print(f"総投資額　：{bet:,}円")
    print(f"総回収額　：{ret:,.0f}円")
    print(f"回収率　　：{ret/bet*100:.1f}%")
    print(f"純利益　　：{ret-bet:+,.0f}円")
    print(f"{'='*50}")

if __name__ == "__main__":
    detailed_analysis()