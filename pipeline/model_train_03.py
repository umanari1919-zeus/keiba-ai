import pickle
from datetime import datetime

from pipeline.config import BASE_DIR, CSV_FEATURES, MODEL_FORBIDDEN_FEATURE_COLUMNS, MODEL_PATH
from pipeline.native_runtime import ensure_native_runtime

ensure_native_runtime()

try:
    import catboost as cb
except ImportError:
    cb = None
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

FEATURES = [
    'barei', 'seibetsu_code', 'kishu_code', 'chokyoshi_code',
    'futan_juryo', 'bataiju', 'zogen_sa', 'zogen_fugo',
    'kyakushitsu_hantei',
    'kyori', 'track_code', 'tenko_code',
    'shiba_babajotai_code', 'dirt_babajotai_code', 'shusso_tosu',
    'wakuban', 'umaban', 'kaisai_kai', 'kaisai_nichime',
    'past3_avg_chakujun',
    'total_races', 'win_count', 'win_rate',
    'prev_chakujun',
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
    # ニックス指数（父×母父の相性）
    'nick_index', 'nick_roi', 'nick_win_rate', 'nick_place_rate',
    # 高度特徴量 (feature_advanced_19)
    'post_win_rate', 'post_bias', 'inner_advantage',
    'tenko_apt', 'shiba_baba_apt', 'dirt_baba_apt',
    'ema3_chakujun', 'ema5_chakujun', 'ema10_chakujun',
    'weight_ema3', 'weight_up_trend', 'weight_down_trend',
    'weight_big_change', 'weight_stability',
    'futan_diff', 'age_futan_interaction', 'futan_increase',
    'interval_bucket', 'interval_age', 'long_rest', 'tight_schedule',
    'race_month', 'season', 'is_spring', 'is_summer', 'is_autumn', 'is_winter',
    'kaikai_inner_rate', 'kaikai_outer_rate',
    # ペース・調教 (pace_training_analysis_20)
    'training_score', 'wood_intensity', 'hanro_intensity',
    'dist_category', 'nige_dist_score', 'oikomi_dist_score',
    'pace_consistency', 'track_change',
    # 騎手・調教師・3代ニックス (jockey_trainer_analysis_21)
    'jt_win_rate', 'jt_place_rate', 'jt_roi',
    'jockey_course_dist_win_rate', 'trainer_course_win_rate',
    'nick3_index', 'nick3_roi', 'nick3_win_rate',
    # 統計特徴量 (statistical_tools_23)
    'horse_cluster', 'cluster_win_rate',
    'age_from_peak', 'is_peak_age', 'before_peak', 'past_peak', 'age_experience',
]


LEAKY_OR_RAW_COLUMNS = set(MODEL_FORBIDDEN_FEATURE_COLUMNS)


def _to_numeric_frame(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    X = df[cols].copy()
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]):
            converted = pd.to_numeric(X[col], errors="coerce")
            if converted.notna().sum() > 0:
                X[col] = converted
            else:
                X[col] = pd.factorize(X[col].astype(str).fillna(""))[0]
    return X.fillna(0)


def _detect_features(df: pd.DataFrame) -> list[str]:
    base = [f for f in FEATURES if f in df.columns and f not in LEAKY_OR_RAW_COLUMNS]
    extra = []
    for c in df.columns:
        normalized = c.lower()
        if c in base or c in LEAKY_OR_RAW_COLUMNS:
            continue
        if "odds" in normalized or "ninki" in normalized or "popular" in normalized:
            continue
        if df[c].dtype == "object":
            continue
        if c.endswith("_date"):
            continue
        extra.append(c)
    features = base + sorted(extra)
    return [f for f in features if f in df.columns]


def _build_time_group_split(df: pd.DataFrame):
    split_col = None
    if "race_date" in df.columns:
        dt = pd.to_datetime(df["race_date"], errors="coerce")
        if dt.notna().sum() > 1000:
            df = df.copy()
            df["_split_date"] = dt
            split_col = "_split_date"
    if split_col is None and "kaisai_gappi" in df.columns:
        dt = pd.to_datetime(df["kaisai_gappi"].astype(str), format="%Y%m%d", errors="coerce")
        if dt.notna().sum() > 1000:
            df = df.copy()
            df["_split_date"] = dt
            split_col = "_split_date"

    if split_col is None or "race_code" not in df.columns:
        return None

    races = (
        df[["race_code", split_col]]
        .dropna(subset=[split_col])
        .drop_duplicates(subset=["race_code"])
        .sort_values(split_col)
        .reset_index(drop=True)
    )
    if len(races) < 100:
        return None

    n = len(races)
    n_test = max(1, int(n * 0.2))
    n_val = max(1, int(n * 0.2))
    test_codes = set(races.iloc[-n_test:]["race_code"])
    val_codes = set(races.iloc[-(n_test + n_val):-n_test]["race_code"])
    train_codes = set(races.iloc[:-(n_test + n_val)]["race_code"])
    if not train_codes or not val_codes or not test_codes:
        return None

    idx_train = df[df["race_code"].isin(train_codes)].index
    idx_val = df[df["race_code"].isin(val_codes)].index
    idx_test = df[df["race_code"].isin(test_codes)].index
    if len(idx_train) == 0 or len(idx_val) == 0 or len(idx_test) == 0:
        return None
    return idx_train, idx_val, idx_test


def _safe_random_split(X, y_encoded):
    y_series = pd.Series(y_encoded, index=X.index)
    counts = y_series.value_counts().sort_index()
    rare_labels = counts[counts < 2].index.tolist()
    rare_mask = y_series.isin(rare_labels)

    X_rare = X.loc[rare_mask]
    y_rare = y_series.loc[rare_mask]
    X_rem = X.loc[~rare_mask]
    y_rem = y_series.loc[~rare_mask]

    if len(X_rem) == 0:
        return X_rare.copy(), X_rare.iloc[:0].copy(), X_rare.iloc[:0].copy(), y_rare.to_numpy(), y_rare.iloc[:0].to_numpy(), y_rare.iloc[:0].to_numpy()

    try:
        X_train_full, X_test, y_train_full, y_test = train_test_split(
            X_rem, y_rem, test_size=0.2, random_state=42, stratify=y_rem
        )
    except ValueError:
        X_train_full, X_test, y_train_full, y_test = train_test_split(
            X_rem, y_rem, test_size=0.2, random_state=42
        )
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_full, y_train_full, test_size=0.2, random_state=42, stratify=y_train_full
        )
    except ValueError:
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_full, y_train_full, test_size=0.2, random_state=42
        )

    if len(X_rare) > 0:
        X_train = pd.concat([X_train, X_rare], axis=0)
        y_train = pd.concat([pd.Series(y_train, index=X_train.index[:len(y_train)]), y_rare], axis=0)
        # y_train 上の index を X_train と合わせ直す
        y_train = pd.Series(y_train.to_numpy(), index=X_train.index)

    all_classes = set(counts.index.tolist())
    train_classes = set(pd.Series(y_train).unique().tolist())
    missing = sorted(all_classes - train_classes)
    if missing:
        for label in missing:
            pick = None
            for frame_x, frame_y in ((X_val, y_val), (X_test, y_test)):
                idx = np.where(np.asarray(frame_y) == label)[0]
                if len(idx):
                    pick = int(idx[0])
                    if frame_x is X_val:
                        X_train = pd.concat([X_train, frame_x.iloc[[pick]]], axis=0)
                        y_train = pd.concat([pd.Series(y_train), pd.Series([label], index=frame_x.iloc[[pick]].index)], axis=0)
                        X_val = frame_x.drop(frame_x.index[pick])
                        y_val = np.delete(np.asarray(frame_y), pick)
                    else:
                        X_train = pd.concat([X_train, frame_x.iloc[[pick]]], axis=0)
                        y_train = pd.concat([pd.Series(y_train), pd.Series([label], index=frame_x.iloc[[pick]].index)], axis=0)
                        X_test = frame_x.drop(frame_x.index[pick])
                        y_test = np.delete(np.asarray(frame_y), pick)
                    break
    y_train = pd.Series(np.asarray(y_train), index=X_train.index)
    return X_train, X_val, X_test, np.asarray(y_train), np.asarray(y_val), np.asarray(y_test)


def _normalize_proba(proba, n_classes: int) -> np.ndarray:
    p = np.asarray(proba, dtype=float)
    if p.ndim == 1:
        p = p.reshape(-1, 1)
    if p.shape[1] < n_classes:
        p = np.pad(p, ((0, 0), (0, n_classes - p.shape[1])), constant_values=0.0)
    elif p.shape[1] > n_classes:
        p = p[:, :n_classes]
    p = np.nan_to_num(p, nan=0.0, posinf=0.0, neginf=0.0)
    p = np.clip(p, 0.0, None)
    row_sum = p.sum(axis=1, keepdims=True)
    bad_rows = row_sum[:, 0] <= 0
    if np.any(bad_rows):
        p[bad_rows, :] = 1.0 / n_classes
        row_sum = p.sum(axis=1, keepdims=True)
    return p / row_sum


def _optimize_ensemble_weights(lgb_p, xgb_p, cb_p, y_true):
    n_classes = max(np.asarray(lgb_p).shape[1], np.asarray(xgb_p).shape[1], np.asarray(cb_p).shape[1] if cb_p is not None else 0)
    lgb_p = _normalize_proba(lgb_p, n_classes)
    xgb_p = _normalize_proba(xgb_p, n_classes)
    cb_p = _normalize_proba(cb_p, n_classes) if cb_p is not None else None
    candidates = np.arange(0.05, 0.96, 0.05)
    best = None
    best_score = float("inf")
    best_acc = -1.0
    if cb_p is None:
        for w1 in candidates:
            w2 = 1.0 - w1
            if w2 < 0.05:
                continue
            p = _normalize_proba(w1 * lgb_p + w2 * xgb_p, n_classes)
            score = log_loss(y_true, p, labels=list(range(p.shape[1])))
            acc = accuracy_score(y_true, p.argmax(axis=1))
            if score < best_score or (np.isclose(score, best_score) and acc > best_acc):
                best_score = score
                best_acc = acc
                best = [float(w1), float(w2), 0.0]
        return best or [0.5, 0.5, 0.0], best_score, best_acc

    for w1 in candidates:
        for w2 in candidates:
            w3 = 1.0 - w1 - w2
            if w3 < 0.05:
                continue
            p = _normalize_proba(w1 * lgb_p + w2 * xgb_p + w3 * cb_p, n_classes)
            score = log_loss(y_true, p, labels=list(range(p.shape[1])))
            acc = accuracy_score(y_true, p.argmax(axis=1))
            if score < best_score or (np.isclose(score, best_score) and acc > best_acc):
                best_score = score
                best_acc = acc
                best = [float(w1), float(w2), float(w3)]
    return best or [0.5, 0.3, 0.2], best_score, best_acc


def train_model():
    print(f"🤖 [{datetime.now()}] 世界最強版 学習開始...")
    print("⚠️ オッズ・人気は除外、時系列で学習/検証/評価")

    df = pd.read_csv(CSV_FEATURES,
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)

    if "kakutei_chakujun" not in df.columns:
        raise ValueError("kakutei_chakujun 列が見つかりません")

    y_raw = pd.to_numeric(df["kakutei_chakujun"], errors="coerce")
    df = df[y_raw.notna()].copy()
    y = y_raw[y_raw.notna()].astype(int)
    df["kakutei_chakujun"] = y

    if len(df) > 8_000:
        print("⚡ 学習高速化: クラスごと上限付きサンプリングを適用")
        cap_per_class = 1000
        sampled_idx = []
        for cls, grp in df.groupby("kakutei_chakujun", sort=False):
            if len(grp) > cap_per_class:
                grp = grp.sample(n=cap_per_class, random_state=42)
            sampled_idx.extend(grp.index.tolist())
        df = df.loc[sorted(sampled_idx)].copy().reset_index(drop=True)
        y = pd.to_numeric(df["kakutei_chakujun"], errors="coerce").astype(int)
        print(f"   サンプル後: {len(df):,}件")

    features = _detect_features(df)
    print(f"📋 使用特徴量数：{len(features)}個")

    X = _to_numeric_frame(df, features)

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    split_idx = _build_time_group_split(df)
    if split_idx:
        idx_train, idx_val, idx_test = split_idx
        X_train, X_val, X_test = X.loc[idx_train], X.loc[idx_val], X.loc[idx_test]
        y_train, y_val, y_test = y_encoded[idx_train], y_encoded[idx_val], y_encoded[idx_test]
        print("🕒 時系列レース分割を適用")
    else:
        X_train, X_val, X_test, y_train, y_val, y_test = _safe_random_split(X, y_encoded)
        print("🧪 ランダム分割を適用（時系列列不足）")

    all_classes = set(np.unique(y_encoded).tolist())
    train_classes = set(np.unique(y_train).tolist())
    if train_classes != all_classes:
        missing = sorted(all_classes - train_classes)
        print(f"⚠️ train に未出現クラスあり → ランダム分割へ切替 ({missing[:5]}{'...' if len(missing) > 5 else ''})")
        X_train, X_val, X_test, y_train, y_val, y_test = _safe_random_split(X, y_encoded)

    print(f"📊 Train: {len(X_train):,}件")
    print(f"📊 Valid: {len(X_val):,}件")
    print(f"📊 Test : {len(X_test):,}件")

    cb_available = cb is not None
    if not cb_available:
        print("\n⚠️ CatBoost が未インストールのため、LGBM + XGBoost の2モデルで学習します")

    # ① LightGBM
    print("\n🔍 LightGBM 学習中...")
    lgb_model = lgb.LGBMClassifier(
        n_estimators=800,
        learning_rate=0.02,
        num_leaves=127,
        min_child_samples=20,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.75,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        objective="multiclass",
        verbose=-1,
    )
    lgb_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_metric="multi_logloss",
        callbacks=[lgb.early_stopping(150, verbose=False),
                   lgb.log_evaluation(period=100)],
    )
    lgb_pred = lgb_model.predict(X_test)
    lgb_acc = accuracy_score(y_test, lgb_pred)
    print(f"🎯 LightGBM 正解率: {lgb_acc:.2%}  (best iter={lgb_model.best_iteration_})")

    # ② XGBoost
    print("\n🔍 XGBoost 学習中...")
    xgb_model = xgb.XGBClassifier(
        n_estimators=800,
        learning_rate=0.02,
        max_depth=7,
        min_child_weight=3,
        subsample=0.8,
        colsample_bytree=0.75,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        eval_metric="mlogloss",
        objective="multi:softprob",
        tree_method="hist",
        early_stopping_rounds=150,
    )
    xgb_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    xgb_pred = xgb_model.predict(X_test)
    xgb_acc = accuracy_score(y_test, xgb_pred)
    print(f"🎯 XGBoost 正解率: {xgb_acc:.2%}  (best iter={xgb_model.best_iteration})")

    # ③ CatBoost
    cb_model = None
    cb_acc = float("nan")
    if cb_available:
        print("\n🔍 CatBoost 学習中...")
        try:
            cb_model = cb.CatBoostClassifier(
                iterations=800,
                learning_rate=0.02,
                depth=8,
                l2_leaf_reg=3.0,
                bagging_temperature=0.5,
                random_strength=1.0,
                border_count=128,
                random_seed=42,
                loss_function="MultiClass",
                eval_metric="MultiClass",
                early_stopping_rounds=150,
                verbose=100,
                thread_count=-1,
            )
            cb_model.fit(
                X_train, y_train,
                eval_set=(X_val, y_val),
                use_best_model=True,
            )
            cb_pred = cb_model.predict(X_test).ravel()
            cb_pred = np.array(cb_pred, dtype=int)
            cb_acc = accuracy_score(y_test, cb_pred)
            print(f"🎯 CatBoost 正解率: {cb_acc:.2%}  (best iter={cb_model.get_best_iteration()})")
        except Exception as exc:
            print(f"⚠️ CatBoost 学習失敗: {exc}")
            print("   → LGB + XGB の2モデルでアンサンブルします")
            cb_model = None
            cb_acc = float("nan")

    # ④ 検証データで重み最適化
    print("\n⚖️ アンサンブル重み最適化中...")
    n_classes = len(le.classes_)
    lgb_val_p = _normalize_proba(lgb_model.predict_proba(X_val), n_classes)
    xgb_val_p = _normalize_proba(xgb_model.predict_proba(X_val), n_classes)
    cb_val_p = _normalize_proba(cb_model.predict_proba(X_val), n_classes) if cb_model is not None else None
    weights, val_logloss, val_acc = _optimize_ensemble_weights(
        lgb_val_p, xgb_val_p, cb_val_p, y_val
    )
    if cb_model is not None:
        print(
            f"   最適重み: LGB={weights[0]:.2f} XGB={weights[1]:.2f} CB={weights[2]:.2f} "
            f"(valid acc={val_acc:.2%}, logloss={val_logloss:.5f})"
        )
    else:
        print(
            f"   最適重み: LGB={weights[0]:.2f} XGB={weights[1]:.2f} "
            f"(valid acc={val_acc:.2%}, logloss={val_logloss:.5f})"
        )

    # ⑤ テストデータ評価
    print("\n🔀 テスト評価...")
    lgb_test_p = _normalize_proba(lgb_model.predict_proba(X_test), n_classes)
    xgb_test_p = _normalize_proba(xgb_model.predict_proba(X_test), n_classes)
    if cb_model is not None:
        cb_test_p = _normalize_proba(cb_model.predict_proba(X_test), n_classes)
        ensemble_proba = _normalize_proba(
            weights[0] * lgb_test_p
            + weights[1] * xgb_test_p
            + weights[2] * cb_test_p,
            n_classes,
        )
    else:
        ensemble_proba = _normalize_proba(
            weights[0] * lgb_test_p
            + weights[1] * xgb_test_p,
            n_classes,
        )
    ensemble_pred = ensemble_proba.argmax(axis=1)
    ensemble_acc = accuracy_score(y_test, ensemble_pred)
    ensemble_logloss = log_loss(y_test, ensemble_proba, labels=list(range(ensemble_proba.shape[1])))

    print(f"\n{'='*40}")
    print("📊 モデル比較（テスト）")
    print(f"{'='*40}")
    print(f"LightGBM : {lgb_acc:.2%}")
    print(f"XGBoost  : {xgb_acc:.2%}")
    if cb_model is not None:
        print(f"CatBoost : {cb_acc:.2%}")
    print(f"Ensemble : {ensemble_acc:.2%} (logloss={ensemble_logloss:.5f})")
    print(f"{'='*40}")

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            'lgb_model': lgb_model,
            'xgb_model': xgb_model,
            'cb_model': cb_model,
            'le': le,
            'features': features,
            'ensemble_weights': weights,
            'metrics': {
                'lgb_acc': float(lgb_acc),
                'xgb_acc': float(xgb_acc),
                'cb_acc': float(cb_acc) if cb_model is not None else None,
                'ensemble_acc': float(ensemble_acc),
                'ensemble_logloss': float(ensemble_logloss),
                'val_acc': float(val_acc),
                'val_logloss': float(val_logloss),
                'trained_at': datetime.now().isoformat(timespec='seconds'),
            }
        }, f)

    print(f"\n💾 {MODEL_PATH} に保存しました（最適重み込み）")

    try:
        import sys as _sys
        _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
        from mlflow_register import register_model
        meta = register_model(str(MODEL_PATH))
        print(f"📊 MLflow 登録完了: run_id={meta['run_id']}")
    except Exception as e:
        print(f"⚠️ MLflow 登録スキップ: {e}")

    return lgb_model, xgb_model, cb_model, features

if __name__ == "__main__":
    train_model()
