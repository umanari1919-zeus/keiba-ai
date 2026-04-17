import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb
import xgboost as xgb
import catboost as cb
from datetime import datetime

FEATURES = [
    'barei', 'seibetsu_code', 'kishu_code', 'chokyoshi_code',
    'futan_juryo', 'bataiju', 'zogen_sa', 'zogen_fugo',
    'kyakushitsu_hantei',
    'kyori', 'track_code', 'tenko_code',
    'shiba_babajotai_code', 'dirt_babajotai_code', 'shusso_tosu',
    'wakuban', 'umaban', 'kaisai_kai', 'kaisai_nichime',
    'past3_avg_chakujun', 'past3_avg_odds',
    'total_races', 'win_count', 'win_rate',
    'prev_chakujun', 'prev_odds',
    'weeks_since_last_race', 'futan_henka',
    'kishu_win_rate', 'chokyoshi_win_rate', 'kishu_keibajo_win_rate',
    'chichi_code', 'haha_code', 'chichi_chichi_code',
    'shiba_win_rate', 'dirt_win_rate',
    'short_win_rate', 'middle_win_rate', 'long_win_rate',
    'kyakushitsu_keiko_nige', 'kyakushitsu_keiko_senko',
    'kyakushitsu_keiko_sashi', 'kyakushitsu_keiko_oikomi',
    'sogo_win_rate', 'sogo_total',
    'chokyo_3f', 'chokyo_lap_3f', 'chokyo_lap_1f', 'chokyo_4f',
    'chichi_kyori', 'haha_kyori', 'chichi_track', 'haha_track',
    'kishu_kyori', 'kishu_track', 'barei_kyori', 'bataiju_kyori',
    'weeks_barei', 'kaishi_nige', 'kaishi_senko', 'futan_barei',
]

def simulate_recovery_wf(test_df, lgb_model, xgb_model, cb_model, le, features):
    X_test = test_df[features]
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    cb_proba = cb_model.predict_proba(X_test)
    
    # probsの列数を揃える
    min_cols = min(lgb_proba.shape[1], xgb_proba.shape[1], cb_proba.shape[1])
    lgb_proba = lgb_proba[:, :min_cols]
    xgb_proba = xgb_proba[:, :min_cols]
    cb_proba = cb_proba[:, :min_cols]
    
    ensemble_proba = 0.5*lgb_proba + 0.3*xgb_proba + 0.2*cb_proba
    test_df = test_df.copy()
    test_df['pred_chakujun'] = le.inverse_transform(
        ensemble_proba.argmax(axis=1)
    )

    results = []
    for race_code, race_df in test_df.groupby('race_code'):
        if len(race_df) < 3:
            continue
        race_df = race_df.sort_values('pred_chakujun')
        honmei = race_df.iloc[0]
        honmei_jun = honmei['kakutei_chakujun']
        odds = honmei['tansho_odds'] / 10
        results.append({
            'odds': odds,
            'hit': 1 if honmei_jun == 1 else 0,
            'return': odds * 100 if honmei_jun == 1 else 0
        })

    r = pd.DataFrame(results)
    total = len(r)
    hits = r['hit'].sum()
    total_return = r['return'].sum()
    recovery = total_return / (total * 100) * 100
    profit = total_return - (total * 100)
    return {
        'total': total,
        'hit_rate': hits/total*100,
        'recovery': recovery,
        'profit': profit
    }

def walk_forward_validation():
    print(f"🔍 [{datetime.now()}] ウォークフォワード検証開始...")
    print("⚠️ オッズ・人気除外の真のモデルで検証")
    print("="*50)
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    
    features = [f for f in FEATURES if f in df.columns]

    # 全データでLabelEncoderをfit
    le = LabelEncoder()
    le.fit(df['kakutei_chakujun'])

    results = []
    train_years = [2020, 2021, 2022]

    for test_year in [2023, 2024, 2025]:
        print(f"\n📅 学習：{min(train_years)}〜{max(train_years)}年")
        print(f"📅 検証：{test_year}年")

        train_df = df[df['kaisai_nen'].isin(train_years)]
        test_df = df[df['kaisai_nen'] == test_year]

        X_train = train_df[features]
        y_train = train_df['kakutei_chakujun']
        X_test = test_df[features]
        y_test = test_df['kakutei_chakujun']

        # XGBoost用：学習データのみで再エンコード
        le_xgb = LabelEncoder()
        y_train_enc = le_xgb.fit_transform(y_train)

        # LightGBM
        lgb_model = lgb.LGBMClassifier(
            n_estimators=423,
            learning_rate=0.011269932671424674,
            num_leaves=69,
            min_child_samples=49,
            random_state=42,
            n_jobs=-1,
            verbose=-1
        )
        lgb_model.fit(X_train, y_train)

        # XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
            eval_metric='mlogloss'
        )
        xgb_model.fit(X_train, y_train_enc)

        # CatBoost
        cb_model = cb.CatBoostClassifier(
            iterations=300,
            learning_rate=0.05,
            depth=6,
            random_seed=42,
            verbose=0
        )
        cb_model.fit(X_train, y_train)

        # 精度確認
        lgb_pred = lgb_model.predict(X_test)
        accuracy = accuracy_score(y_test, lgb_pred)

        # 回収率シミュレーション
        sim = simulate_recovery_wf(
            test_df, lgb_model, xgb_model, cb_model, le, features
        )

        print(f"🎯 正解率　：{accuracy:.2%}")
        print(f"📈 回収率　：{sim['recovery']:.1f}%")
        print(f"🎯 的中率　：{sim['hit_rate']:.1f}%")
        print(f"💰 損　益　：{sim['profit']:+,.0f}円")

        results.append({
            'test_year': test_year,
            'accuracy': accuracy,
            'recovery': sim['recovery'],
            'profit': sim['profit']
        })

        train_years.append(test_year)

    print("\n" + "="*50)
    print("📊 ウォークフォワード検証まとめ")
    print("="*50)
    total_profit = sum(r['profit'] for r in results)
    avg_recovery = sum(r['recovery'] for r in results) / len(results)
    print(f"平均回収率：{avg_recovery:.1f}%")
    print(f"総損益　　：{total_profit:+,.0f}円")

    if avg_recovery >= 100:
        print("✅ 過学習なし！実戦投入可能レベル！")
    else:
        print("⚠️ 過学習の可能性あり。要改善！")

if __name__ == "__main__":
    walk_forward_validation()