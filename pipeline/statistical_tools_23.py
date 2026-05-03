"""
統計・数理分析
- ベイズ最適化による特徴量選択（Optuna）
- PCA 次元削減・可視化
- K-Means クラスタリング（馬のタイプ分類）
- 生存分析（馬の能力ピーク予測）
- モンテカルロシミュレーション（リスク分析）
"""
import pandas as pd
import numpy as np
import pickle
import json
import os
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import optuna
import lightgbm as lgb
from sklearn.model_selection import cross_val_score

MODEL_FILE = "D:\\keiba_ai\\model_v8.pkl"
OUTPUT_DIR = "D:\\keiba_ai\\data"
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ──────────────────────────────────────────────
# ①ベイズ最適化による特徴量選択
# ──────────────────────────────────────────────

def bayesian_feature_selection(df: pd.DataFrame, features: list,
                                n_trials=50) -> list:
    """Optuna で最も精度に寄与する特徴量サブセットを探索"""
    X = df[[f for f in features if f in df.columns]].fillna(0)
    y = df['kakutei_chakujun'].fillna(0)

    def objective(trial):
        selected = [f for f in X.columns
                    if trial.suggest_categorical(f, [True, False])]
        if not selected:
            return 0.0
        model = lgb.LGBMClassifier(n_estimators=100, verbose=-1, n_jobs=1)
        scores = cross_val_score(model, X[selected], y, cv=3, scoring='accuracy', n_jobs=-1)
        return scores.mean()

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_features = [f for f in X.columns
                     if study.best_params.get(f, False)]
    print(f"  ✅ ベイズ最適化: {len(features)}個 → {len(best_features)}個")
    return best_features


# ──────────────────────────────────────────────
# ② PCA 次元削減・可視化
# ──────────────────────────────────────────────

def run_pca_analysis(df: pd.DataFrame, features: list, n_components=10) -> pd.DataFrame:
    X = df[[f for f in features if f in df.columns]].fillna(0).astype(float)
    scaler = StandardScaler()
    Xs     = scaler.fit_transform(X)

    pca = PCA(n_components=min(n_components, X.shape[1]))
    components = pca.fit_transform(Xs)

    explained = pca.explained_variance_ratio_.cumsum()
    print(f"  📊 PCA: {n_components}成分で分散 {explained[-1]*100:.1f}% を説明")

    pca_df = pd.DataFrame(
        components,
        columns=[f'pca_{i+1}' for i in range(components.shape[1])],
        index=df.index
    )

    # 寄与度の高い特徴量を報告
    loadings = pd.DataFrame(pca.components_.T,
                             index=[f for f in features if f in df.columns],
                             columns=[f'PC{i+1}' for i in range(pca.n_components_)])
    top = loadings['PC1'].abs().sort_values(ascending=False).head(10)
    print(f"  🔝 PC1への寄与度TOP5: {list(top.head(5).index)}")

    return pd.concat([df.reset_index(drop=True), pca_df], axis=1)


# ──────────────────────────────────────────────
# ③ K-Means クラスタリング（馬のタイプ分類）
# ──────────────────────────────────────────────

def horse_type_clustering(df: pd.DataFrame, n_clusters=8) -> pd.DataFrame:
    cluster_features = [
        'barei', 'sogo_win_rate', 'shiba_win_rate', 'dirt_win_rate',
        'short_win_rate', 'middle_win_rate', 'long_win_rate',
        'kyakushitsu_keiko_nige', 'kyakushitsu_keiko_senko',
        'kyakushitsu_keiko_sashi', 'kyakushitsu_keiko_oikomi',
        'win_rate', 'total_races', 'bataiju'
    ]
    feats = [f for f in cluster_features if f in df.columns]
    X = df[feats].fillna(0).astype(float)

    scaler = StandardScaler()
    Xs     = scaler.fit_transform(X)

    # シルエットスコアで最適クラスタ数を選択
    best_k, best_score = n_clusters, -1
    for k in range(4, min(12, len(df) // 1000 + 4)):
        km = KMeans(n_clusters=k, random_state=42, n_init=5)
        labels = km.fit_predict(Xs)
        if len(set(labels)) > 1:
            score = silhouette_score(Xs, labels, sample_size=min(5000, len(Xs)))
            if score > best_score:
                best_score, best_k = score, k

    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    df['horse_cluster'] = km.fit_predict(Xs)

    # クラスタ別勝率を計算
    cluster_stats = df.groupby('horse_cluster').apply(lambda g: pd.Series({
        'cluster_win_rate':   (g['kakutei_chakujun'] == 1).mean(),
        'cluster_avg_odds':   g['tansho_odds'].mean() / 10,
        'cluster_size':       len(g)
    }), include_groups=False)
    print(f"  🏇 馬タイプ分類: {best_k}クラスタ (silhouette={best_score:.3f})")
    for idx, row in cluster_stats.iterrows():
        print(f"    Cluster {idx}: 勝率{row['cluster_win_rate']*100:.1f}% "
              f"平均オッズ{row['cluster_avg_odds']:.1f}x N={int(row['cluster_size'])}")

    df = df.merge(cluster_stats.reset_index(), on='horse_cluster', how='left')
    return df


# ──────────────────────────────────────────────
# ④ 生存分析（馬の能力ピーク予測）
# ──────────────────────────────────────────────

def survival_analysis_peak(df: pd.DataFrame) -> pd.DataFrame:
    """
    各馬の勝利確率のピーク年齢を推定し、
    現在年齢とピーク年齢の乖離を特徴量にする。
    """
    # 年齢別の勝率計算
    age_win = df[df['kakutei_chakujun'] == 1].groupby('barei').size()
    age_total = df.groupby('barei').size()
    age_win_rate = (age_win / age_total).fillna(0)

    # 最もピークに近い年齢（勝率最大の年齢）
    peak_age = age_win_rate.idxmax() if len(age_win_rate) > 0 else 4

    # ピーク年齢からの距離（絶対値）
    df['age_from_peak'] = (df['barei'] - peak_age).abs()

    # ピーク前 or ピーク後のフラグ
    df['is_peak_age']      = (df['barei'] == peak_age).astype(int)
    df['before_peak']      = (df['barei'] < peak_age).astype(int)
    df['past_peak']        = (df['barei'] > peak_age + 1).astype(int)

    # 年齢×出走数（経験豊富さ）
    df['age_experience'] = df['barei'] * df['total_races']

    print(f"  ⏳ 能力ピーク年齢: {peak_age}歳")
    return df


# ──────────────────────────────────────────────
# ⑤ モンテカルロシミュレーション（リスク分析）
# ──────────────────────────────────────────────

def monte_carlo_risk_analysis(bankroll=100000, n_simulations=10000,
                               n_races=100, hit_rate=0.388,
                               avg_odds=4.78, bet_fraction=0.05) -> dict:
    """
    モンテカルロシミュレーションでバンクロールのリスクを分析する。
    """
    rng = np.random.default_rng(42)
    final_bankrolls = []
    max_drawdowns   = []
    ruin_count      = 0

    for _ in range(n_simulations):
        balance = bankroll
        peak    = bankroll
        max_dd  = 0.0

        for _ in range(n_races):
            bet = balance * bet_fraction
            if rng.random() < hit_rate:
                balance += bet * (avg_odds - 1)
            else:
                balance -= bet

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > max_dd:
                max_dd = dd
            if balance <= 0:
                ruin_count += 1
                balance = 0
                break

        final_bankrolls.append(balance)
        max_drawdowns.append(max_dd)

    finals = np.array(final_bankrolls)
    dds    = np.array(max_drawdowns)

    result = {
        'n_simulations': n_simulations,
        'n_races':       n_races,
        'hit_rate':      hit_rate,
        'avg_odds':      avg_odds,
        'bet_fraction':  bet_fraction,
        'initial_bankroll': bankroll,
        'median_final':  float(np.median(finals)),
        'mean_final':    float(np.mean(finals)),
        'p5_final':      float(np.percentile(finals, 5)),
        'p95_final':     float(np.percentile(finals, 95)),
        'ruin_rate':     float(ruin_count / n_simulations),
        'median_maxdd':  float(np.median(dds)),
        'p95_maxdd':     float(np.percentile(dds, 95)),
        'profit_prob':   float((finals > bankroll).mean()),
        'analyzed_at':   datetime.now().isoformat()
    }
    return result


def run_monte_carlo(bankroll=100000, hit_rate=0.388, avg_odds=4.78):
    print("\n" + "="*55)
    print("🎲 モンテカルロリスクシミュレーション")
    print("="*55)

    results = {}
    for frac in [0.02, 0.05, 0.10]:
        r = monte_carlo_risk_analysis(bankroll, n_simulations=5000,
                                      n_races=100, hit_rate=hit_rate,
                                      avg_odds=avg_odds, bet_fraction=frac)
        results[f'frac_{int(frac*100)}pct'] = r
        emoji = "✅" if r['ruin_rate'] < 0.1 else "⚠️"
        print(f"\n  {emoji} ベット率 {frac*100:.0f}%:")
        print(f"    中央値最終資金: {r['median_final']:,.0f}円 "
              f"(+{(r['median_final']/bankroll-1)*100:.1f}%)")
        print(f"    破産確率: {r['ruin_rate']*100:.1f}%")
        print(f"    最大ドローダウン中央値: {r['median_maxdd']*100:.1f}%")
        print(f"    利益確率(100レース): {r['profit_prob']*100:.1f}%")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(f"{OUTPUT_DIR}/monte_carlo_result.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 保存: {OUTPUT_DIR}/monte_carlo_result.json")
    return results


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_statistical_analysis():
    print("\n" + "="*55)
    print("📐 統計・数理分析")
    print("="*55)

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')

    with open(MODEL_FILE, 'rb') as f:
        saved = pickle.load(f)
    features = saved['features']

    # ③ クラスタリング
    print("\n🏇 馬タイプクラスタリング...")
    df = horse_type_clustering(df)

    # ④ 生存分析
    print("\n⏳ 能力ピーク分析...")
    df = survival_analysis_peak(df)

    # ② PCA（分析のみ、特徴量には追加しない）
    print("\n📊 PCA分析...")
    run_pca_analysis(df, features, n_components=5)

    df = df.fillna(0)
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")
    print(f"\n  ✅ 統計特徴量追加完了: {len(df.columns)}列")

    # ⑤ モンテカルロ
    run_monte_carlo()

    return df


STATISTICAL_FEATURES = [
    'horse_cluster', 'cluster_win_rate', 'cluster_avg_odds',
    'age_from_peak', 'is_peak_age', 'before_peak', 'past_peak', 'age_experience',
]


if __name__ == "__main__":
    run_statistical_analysis()
