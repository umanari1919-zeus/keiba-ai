import pandas as pd
import numpy as np
import pickle
from datetime import datetime

def simulate_recovery(year):
    with open("D:\\keiba_ai\\model_v8.pkl", "rb") as f:
        saved = pickle.load(f)
    
    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model = saved['cb_model']
    le = saved['le']
    features = saved['features']
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    
    test_df = df[df['kaisai_nen'] == year].copy()
    if len(test_df) == 0:
        return None
    
    X_test = test_df[features]
    
    # 加重アンサンブル予測
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    cb_proba = cb_model.predict_proba(X_test)
    
    ensemble_proba = (
        0.5 * lgb_proba +
        0.3 * xgb_proba +
        0.2 * cb_proba
    )
    test_df['pred_chakujun'] = le.inverse_transform(
        ensemble_proba.argmax(axis=1)
    )
    
    results = []
    for race_code, race_df in test_df.groupby('race_code'):
        if len(race_df) < 3:
            continue
        
        # オッズ3倍以上の穴馬狙い
        race_df_filtered = race_df[race_df['tansho_odds'] >= 30]
        if len(race_df_filtered) == 0:
            continue
        
        honmei = race_df_filtered.loc[
            race_df_filtered['pred_chakujun'].idxmin()
        ]
        
        actual_chakujun = honmei['kakutei_chakujun']
        odds = honmei['tansho_odds'] / 10
        
        results.append({
            'race_code': race_code,
            'bamei': honmei['bamei'],
            'barei': honmei['barei'],
            'bataiju': honmei['bataiju'],
            'zogen_sa': honmei['zogen_sa'],
            'zogen_fugo': honmei['zogen_fugo'],
            'kishumei_ryakusho': honmei['kishumei_ryakusho'],
            'pred_chakujun': honmei['pred_chakujun'],
            'actual_chakujun': actual_chakujun,
            'odds': odds,
            'hit': 1 if actual_chakujun == 1 else 0
        })
    
    results_df = pd.DataFrame(results)
    total_races = len(results_df)
    total_bet = total_races * 100
    wins = results_df[results_df['hit'] == 1]
    total_return = (wins['odds'] * 100).sum()
    hit_rate = len(wins) / total_races * 100
    recovery_rate = total_return / total_bet * 100
    
    if year == 2025:
        results_df.to_csv("D:\\keiba_ai\\simulation_2025.csv",
                          index=False, encoding="utf-8-sig")
        print(f"💾 simulation_2025.csv に保存しました！")
    
    return {
        'year': year,
        'races': total_races,
        'hit_rate': hit_rate,
        'recovery_rate': recovery_rate,
        'profit': total_return - total_bet
    }

if __name__ == "__main__":
    print("📊 年別回収率シミュレーション（データリーケージ修正版）")
    print("="*50)
    
    total_profit = 0
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        result = simulate_recovery(year)
        if result:
            emoji = "🎉" if result['recovery_rate'] >= 100 else "📉"
            print(f"{emoji} {result['year']}年")
            print(f"   レース数：{result['races']:,}")
            print(f"   的中率　：{result['hit_rate']:.1f}%")
            print(f"   回収率　：{result['recovery_rate']:.1f}%")
            print(f"   損　益　：{result['profit']:+,.0f}円")
            print(f"   {'─'*30}")
            total_profit += result['profit']
    
    print(f"\n💰 6年間の総損益：{total_profit:+,.0f}円")
    print("="*50)