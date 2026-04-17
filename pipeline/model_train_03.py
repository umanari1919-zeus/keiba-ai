import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb
import xgboost as xgb
import catboost as cb
import pickle
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

def train_model():
    print(f"🤖 [{datetime.now()}] データリーケージ修正版 学習開始...")
    print("⚠️ オッズ・人気を除外した真の予測モデル")
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    
    features = [f for f in FEATURES if f in df.columns]
    print(f"📋 使用特徴量数：{len(features)}個")
    
    X = df[features]
    y = df['kakutei_chakujun']
    
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    X_train_enc, X_test_enc, y_train_enc, y_test_enc = train_test_split(
        X, y_encoded, test_size=0.2, random_state=42
    )
    
    print(f"📊 学習データ：{len(X_train):,}件")
    print(f"📊 テストデータ：{len(X_test):,}件")

    # ① LightGBM
    print("\n🔍 LightGBM学習中...")
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
    lgb_acc = accuracy_score(y_test, lgb_model.predict(X_test))
    print(f"🎯 LightGBM正解率：{lgb_acc:.2%}")

    # ② XGBoost
    print("\n🔍 XGBoost学習中...")
    xgb_model = xgb.XGBClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        eval_metric='mlogloss'
    )
    xgb_model.fit(X_train_enc, y_train_enc)
    xgb_pred = le.inverse_transform(xgb_model.predict(X_test_enc))
    xgb_acc = accuracy_score(y_test, xgb_pred)
    print(f"🎯 XGBoost正解率：{xgb_acc:.2%}")

    # ③ CatBoost
    print("\n🔍 CatBoost学習中...")
    cb_model = cb.CatBoostClassifier(
        iterations=300,
        learning_rate=0.05,
        depth=6,
        random_seed=42,
        verbose=0
    )
    cb_model.fit(X_train, y_train)
    cb_acc = accuracy_score(y_test, cb_model.predict(X_test))
    print(f"🎯 CatBoost正解率：{cb_acc:.2%}")

    # ④ 加重アンサンブル（LightGBM重視）
    print("\n🔀 加重アンサンブル予測中...")
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test_enc)
    cb_proba = cb_model.predict_proba(X_test)

    # LightGBM:0.5 XGBoost:0.3 CatBoost:0.2
    ensemble_proba = (
        0.5 * lgb_proba +
        0.3 * xgb_proba +
        0.2 * cb_proba
    )
    ensemble_pred = le.inverse_transform(ensemble_proba.argmax(axis=1))
    ensemble_acc = accuracy_score(y_test, ensemble_pred)

    print(f"\n{'='*40}")
    print(f"📊 モデル比較（オッズ・人気除外版）")
    print(f"{'='*40}")
    print(f"LightGBM : {lgb_acc:.2%}")
    print(f"XGBoost  : {xgb_acc:.2%}")
    print(f"CatBoost : {cb_acc:.2%}")
    print(f"Ensemble : {ensemble_acc:.2%}")
    print(f"{'='*40}")

    with open("D:\\keiba_ai\\model_v8.pkl", "wb") as f:
        pickle.dump({
            'lgb_model': lgb_model,
            'xgb_model': xgb_model,
            'cb_model': cb_model,
            'le': le,
            'features': features
        }, f)
    
    print("\n💾 model_v8.pkl に保存しました！")
    return lgb_model, xgb_model, cb_model, features

if __name__ == "__main__":
    train_model()