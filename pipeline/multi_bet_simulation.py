import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from pipeline.config import BASE_DIR, CSV_FEATURES, DB_URL
from pipeline.native_runtime import ensure_native_runtime

def multi_bet_simulation(year=2025):
    print(f"🎯 [{datetime.now()}] 全馬券種シミュレーション開始...")
    ensure_native_runtime()

    with open(os.path.join(BASE_DIR, "model_v8.pkl"), "rb") as f:
        saved = pickle.load(f)
    
    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model = saved['cb_model']
    le = saved['le']
    features = saved['features']
    
    df = pd.read_csv(CSV_FEATURES,
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    test_df = df[df['kaisai_nen'] == year].copy()
    
    # アンサンブル予測
    X_test = test_df[features]
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    cb_proba = (cb_model.predict_proba(X_test) if cb_model is not None else 0)
    ensemble_proba = 0.5*lgb_proba + 0.3*xgb_proba + 0.2*cb_proba
    test_df['pred_chakujun'] = le.inverse_transform(
        ensemble_proba.argmax(axis=1)
    )

    engine = create_engine(DB_URL)
    
    print("💰 オッズデータ取得中...")
    with engine.connect() as conn:
        fukusho = pd.read_sql(text(f"""
            SELECT race_code, umaban, odds_saitei
            FROM odds1_fukusho
            WHERE kaisai_nen = '{year}'
        """), conn)
        
        umaren = pd.read_sql(text(f"""
            SELECT race_code, kumiban, odds
            FROM odds2_umaren
            WHERE kaisai_nen = '{year}'
        """), conn)
        
        wide = pd.read_sql(text(f"""
            SELECT race_code, kumiban, odds_saitei
            FROM odds3_wide
            WHERE kaisai_nen = '{year}'
        """), conn)
        
        umatan = pd.read_sql(text(f"""
            SELECT race_code, kumiban, odds
            FROM odds4_umatan
            WHERE kaisai_nen = '{year}'
        """), conn)
        
        sanrenpuku = pd.read_sql(text(f"""
            SELECT race_code, kumiban, odds
            FROM odds5_sanrenpuku
            WHERE kaisai_nen = '{year}'
        """), conn)

    # 全オッズを数値に変換
    fukusho['odds_saitei'] = pd.to_numeric(fukusho['odds_saitei'], errors='coerce').fillna(0)
    umaren['odds'] = pd.to_numeric(umaren['odds'], errors='coerce').fillna(0)
    wide['odds_saitei'] = pd.to_numeric(wide['odds_saitei'], errors='coerce').fillna(0)
    umatan['odds'] = pd.to_numeric(umatan['odds'], errors='coerce').fillna(0)
    sanrenpuku['odds'] = pd.to_numeric(sanrenpuku['odds'], errors='coerce').fillna(0)

    def make_kumiban_2(u1, u2):
        return f"{int(u1):02d}{int(u2):02d}"
    
    def make_kumiban_3(u1, u2, u3):
        return f"{int(u1):02d}{int(u2):02d}{int(u3):02d}"

    results = {
        'tansho': [], 'fukusho': [], 'umaren': [],
        'umatan': [], 'wide': [], 'sanrenpuku': []
    }

    print("🏇 レースごとに集計中...")
    for race_code, race_df in test_df.groupby('race_code'):
        if len(race_df) < 3:
            continue

        race_df = race_df.sort_values('pred_chakujun')
        honmei = race_df.iloc[0]
        taiko = race_df.iloc[1]
        sanban = race_df.iloc[2]

        honmei_uma = int(honmei['umaban'])
        taiko_uma = int(taiko['umaban'])
        sanban_uma = int(sanban['umaban'])
        honmei_jun = honmei['kakutei_chakujun']
        taiko_jun = taiko['kakutei_chakujun']
        sanban_jun = sanban['kakutei_chakujun']

        # 馬番を文字列形式に変換
        honmei_uma_str = f"{honmei_uma:02d}"

        # 単勝
        tansho_odds = honmei['tansho_odds'] / 10
        results['tansho'].append({
            'bamei': honmei['bamei'],
            'odds': tansho_odds,
            'hit': 1 if honmei_jun == 1 else 0,
            'return': tansho_odds * 100 if honmei_jun == 1 else 0
        })

        # 複勝
        fuku = fukusho[
            (fukusho['race_code'] == race_code) &
            (fukusho['umaban'] == honmei_uma_str)
        ]
        if len(fuku) > 0:
            fuku_odds = fuku.iloc[0]['odds_saitei'] / 10
            hit = 1 if honmei_jun <= 3 else 0
            results['fukusho'].append({
                'bamei': honmei['bamei'],
                'odds': fuku_odds,
                'hit': hit,
                'return': fuku_odds * 100 if hit else 0
            })

        # 馬連
        uma1 = min(honmei_uma, taiko_uma)
        uma2 = max(honmei_uma, taiko_uma)
        kb_umaren = make_kumiban_2(uma1, uma2)
        ur = umaren[
            (umaren['race_code'] == race_code) &
            (umaren['kumiban'] == kb_umaren)
        ]
        if len(ur) > 0:
            ur_odds = ur.iloc[0]['odds'] / 10
            hit = 1 if (honmei_jun <= 2 and taiko_jun <= 2) else 0
            results['umaren'].append({
                'odds': ur_odds,
                'hit': hit,
                'return': ur_odds * 100 if hit else 0
            })

        # 馬単
        kb_umatan = make_kumiban_2(honmei_uma, taiko_uma)
        ut = umatan[
            (umatan['race_code'] == race_code) &
            (umatan['kumiban'] == kb_umatan)
        ]
        if len(ut) > 0:
            ut_odds = ut.iloc[0]['odds'] / 10
            hit = 1 if (honmei_jun == 1 and taiko_jun == 2) else 0
            results['umatan'].append({
                'odds': ut_odds,
                'hit': hit,
                'return': ut_odds * 100 if hit else 0
            })

        # ワイド
        kb_wide = make_kumiban_2(uma1, uma2)
        wd = wide[
            (wide['race_code'] == race_code) &
            (wide['kumiban'] == kb_wide)
        ]
        if len(wd) > 0:
            wd_odds = wd.iloc[0]['odds_saitei'] / 10
            hit = 1 if (honmei_jun <= 3 and taiko_jun <= 3) else 0
            results['wide'].append({
                'odds': wd_odds,
                'hit': hit,
                'return': wd_odds * 100 if hit else 0
            })

        # 三連複
        uma_list = sorted([honmei_uma, taiko_uma, sanban_uma])
        kb_san = make_kumiban_3(uma_list[0], uma_list[1], uma_list[2])
        sr = sanrenpuku[
            (sanrenpuku['race_code'] == race_code) &
            (sanrenpuku['kumiban'] == kb_san)
        ]
        if len(sr) > 0:
            sr_odds = sr.iloc[0]['odds'] / 10
            hit = 1 if (honmei_jun <= 3 and
                       taiko_jun <= 3 and
                       sanban_jun <= 3) else 0
            results['sanrenpuku'].append({
                'odds': sr_odds,
                'hit': hit,
                'return': sr_odds * 100 if hit else 0
            })

    # 結果表示
    bet_names = {
        'tansho': '単勝',
        'fukusho': '複勝',
        'umaren': '馬連',
        'umatan': '馬単',
        'wide': 'ワイド',
        'sanrenpuku': '三連複'
    }

    print(f"\n{'='*60}")
    print(f"📊 {year}年 全馬券種シミュレーション結果")
    print(f"{'='*60}")
    
    total_profit_all = 0
    for key, name in bet_names.items():
        r = pd.DataFrame(results[key])
        if len(r) == 0:
            continue
        total = len(r)
        hits = r['hit'].sum()
        total_return = r['return'].sum()
        total_bet = total * 100
        hit_rate = hits / total * 100
        recovery = total_return / total_bet * 100
        profit = total_return - total_bet
        total_profit_all += profit
        
        emoji = "🎉" if recovery >= 100 else "📉"
        print(f"\n{emoji} 【{name}】")
        print(f"   レース数：{total:,}R")
        print(f"   的中数　：{int(hits):,}回")
        print(f"   的中率　：{hit_rate:.1f}%")
        print(f"   回収率　：{recovery:.1f}%")
        print(f"   損　益　：{profit:+,.0f}円")
    
    print(f"\n{'='*60}")
    print(f"💰 全馬券種合計損益：{total_profit_all:+,.0f}円")
    print(f"{'='*60}")

if __name__ == "__main__":
    multi_bet_simulation(2025)
