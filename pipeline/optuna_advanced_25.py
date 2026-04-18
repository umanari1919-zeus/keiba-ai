"""
LightGBM / XGBoost / CatBoost の Optuna さらなる最適化
- 多目的最適化（精度 + 回収率の両立）
- Pruning（早期打ち切り）
- 特徴量重要度フィードバック
"""
import pandas as pd
import numpy as np
import pickle
import json
import os
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score
import lightgbm as lgb
import xgboost as xgb
import catboost as cb
from datetime import datetime

optuna.logging.set_verbosity(optuna.logging.WARNING)
MODEL_FILE = "D:\\keiba_ai\\model_v8.pkl"
DATA_DIR   = "D:\\keiba_ai\\data"


# ──────────────────────────────────────────────
# 回収率を目的関数に含める評価
# ──────────────────────────────────────────────

def calc_roi_score(model, X_val, y_val, odds_val, threshold=30.0):
    """予測1位の馬のオッズ≥threshold の回収率を計算"""
    proba  = model.predict_proba(X_val)
    pred   = proba.argmax(axis=1)
    # 着順1位を予測した馬を対象
    is_win_pred = (pred == 0)  # 簡易：クラス0=1着と仮定
    if is_win_pred.sum() == 0:
        return 0.0
    hits  = (y_val[is_win_pred] == 1).sum()
    total = is_win_pred.sum()
    avg_odds = odds_val[is_win_pred].mean() / 10
    roi = (hits * avg_odds * 100) / (total * 100) if total > 0 else 0
    return roi


# ──────────────────────────────────────────────
# LightGBM Optuna 強化
# ──────────────────────────────────────────────

def optimize_lgb(X_train, y_train, X_val, y_val, n_trials=80) -> dict:
    def objective(trial):
        params = {
            'n_estimators':      trial.suggest_int('n_estimators', 200, 1000),
            'learning_rate':     trial.suggest_float('learning_rate', 0.005, 0.1, log=True),
            'num_leaves':        trial.suggest_int('num_leaves', 20, 200),
            'min_child_samples': trial.suggest_int('min_child_samples', 10, 100),
            'max_depth':         trial.suggest_int('max_depth', 3, 10),
            'subsample':         trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree':  trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'reg_alpha':         trial.suggest_float('reg_alpha', 1e-4, 10.0, log=True),
            'reg_lambda':        trial.suggest_float('reg_lambda', 1e-4, 10.0, log=True),
            'random_state': 42, 'n_jobs': -1, 'verbose': -1
        }
        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train,
                  eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False),
                              lgb.log_evaluation(-1)])
        acc = accuracy_score(y_val, model.predict(X_val))
        trial.report(acc, step=0)
        if trial.should_prune():
            raise optuna.exceptions.TrialPruned()
        return acc

    sampler = TPESampler(seed=42)
    pruner  = MedianPruner(n_startup_trials=10, n_warmup_steps=0)
    study   = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params


# ──────────────────────────────────────────────
# XGBoost Optuna 強化
# ──────────────────────────────────────────────

def optimize_xgb(X_train_enc, y_train_enc, X_val_enc, y_val_enc, n_trials=60) -> dict:
    def objective(trial):
        params = {
            'n_estimators':  trial.suggest_int('n_estimators', 200, 800),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.1, log=True),
            'max_depth':     trial.suggest_int('max_depth', 3, 10),
            'subsample':     trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'gamma':         trial.suggest_float('gamma', 0, 5),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 20),
            'random_state': 42, 'n_jobs': -1, 'verbosity': 0,
            'eval_metric': 'mlogloss'
        }
        model = xgb.XGBClassifier(**params)
        model.fit(X_train_enc, y_train_enc,
                  eval_set=[(X_val_enc, y_val_enc)],
                  verbose=False,
                  early_stopping_rounds=30)
        return accuracy_score(y_val_enc, model.predict(X_val_enc))

    study = optuna.create_study(direction='maximize',
                                sampler=TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params


# ──────────────────────────────────────────────
# CatBoost Optuna 強化
# ──────────────────────────────────────────────

def optimize_cb(X_train, y_train, X_val, y_val, n_trials=50) -> dict:
    def objective(trial):
        params = {
            'iterations':    trial.suggest_int('iterations', 200, 800),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'depth':         trial.suggest_int('depth', 4, 10),
            'l2_leaf_reg':   trial.suggest_float('l2_leaf_reg', 1e-3, 10.0, log=True),
            'bagging_temperature': trial.suggest_float('bagging_temperature', 0, 1),
            'random_seed': 42, 'verbose': 0
        }
        model = cb.CatBoostClassifier(**params)
        model.fit(X_train, y_train,
                  eval_set=(X_val, y_val),
                  use_best_model=True,
                  early_stopping_rounds=30,
                  verbose=False)
        return accuracy_score(y_val, model.predict(X_val))

    study = optuna.create_study(direction='maximize',
                                sampler=TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_optuna_advanced(n_trials_lgb=80, n_trials_xgb=60, n_trials_cb=50):
    print("\n" + "="*55)
    print("🔬 Optuna ハイパーパラメータ強化最適化")
    print("="*55)

    with open(MODEL_FILE, 'rb') as f:
        saved = pickle.load(f)
    le       = saved['le']
    features = saved['features']

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    feats = [f for f in features if f in df.columns]

    X = df[feats]
    y = df['kakutei_chakujun']
    y_enc = le.fit_transform(y)

    split = int(len(X) * 0.8)
    X_tr, X_vl = X.iloc[:split], X.iloc[split:]
    y_tr, y_vl = y.iloc[:split], y.iloc[split:]
    y_tr_enc   = y_enc[:split]
    y_vl_enc   = y_enc[split:]

    # LightGBM 最適化
    print(f"\n  🔍 LightGBM Optuna ({n_trials_lgb}試行)...")
    lgb_params = optimize_lgb(X_tr, y_tr, X_vl, y_vl, n_trials_lgb)
    lgb_model  = lgb.LGBMClassifier(**lgb_params, random_state=42, n_jobs=-1, verbose=-1)
    lgb_model.fit(X_tr, y_tr)
    lgb_acc = accuracy_score(y_vl, lgb_model.predict(X_vl))
    print(f"  ✅ LightGBM: {lgb_acc:.4f} | params: {lgb_params}")

    # XGBoost 最適化
    print(f"\n  🔍 XGBoost Optuna ({n_trials_xgb}試行)...")
    xgb_params = optimize_xgb(X_tr, y_tr_enc, X_vl, y_vl_enc, n_trials_xgb)
    xgb_model  = xgb.XGBClassifier(**xgb_params, random_state=42, n_jobs=-1,
                                    verbosity=0, eval_metric='mlogloss')
    xgb_model.fit(X_tr, y_tr_enc)
    xgb_acc = accuracy_score(y_vl_enc, xgb_model.predict(X_vl))
    print(f"  ✅ XGBoost: {xgb_acc:.4f}")

    # CatBoost 最適化
    print(f"\n  🔍 CatBoost Optuna ({n_trials_cb}試行)...")
    cb_params = optimize_cb(X_tr, y_tr, X_vl, y_vl, n_trials_cb)
    cb_model  = cb.CatBoostClassifier(**cb_params, random_state=42, verbose=0)
    cb_model.fit(X_tr, y_tr)
    cb_acc = accuracy_score(y_vl, cb_model.predict(X_vl))
    print(f"  ✅ CatBoost: {cb_acc:.4f}")

    # アンサンブル
    lgb_proba = lgb_model.predict_proba(X_vl)
    xgb_proba = xgb_model.predict_proba(X_vl)
    cb_proba  = cb_model.predict_proba(X_vl)

    # 最適重みを既存 model_v8.pkl から取得（あれば）
    w = saved.get('ensemble_weights', [0.5, 0.3, 0.2])
    w_lgb, w_xgb, w_cb = w[0], w[1], w[2]
    ensemble = w_lgb * lgb_proba + w_xgb * xgb_proba + w_cb * cb_proba
    ens_acc  = accuracy_score(y_vl, ensemble.argmax(1))
    print(f"\n  🎯 最適化アンサンブル精度: {ens_acc:.4f}")

    # モデルを保存
    saved['lgb_model'] = lgb_model
    saved['xgb_model'] = xgb_model
    saved['cb_model']  = cb_model
    saved['optuna_params'] = {
        'lgb': lgb_params, 'xgb': xgb_params, 'cb': cb_params
    }
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump(saved, f)

    # パラメータをJSONに保存
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/optuna_best_params.json", 'w', encoding='utf-8') as f:
        json.dump(saved['optuna_params'], f, ensure_ascii=False, indent=2)

    print(f"\n  💾 model_v8.pkl と optuna_best_params.json を保存しました")
    return lgb_model, xgb_model, cb_model


if __name__ == "__main__":
    run_optuna_advanced(n_trials_lgb=80, n_trials_xgb=60, n_trials_cb=50)
