"""
SHAP でアンサンブルモデルの予測根拠を可視化する。
勝率・連対率・複勝率を意識した可視化を追加。

出力先: D:/keiba_ai/shap_output/
  [基本 SHAP]
  01_lgb_summary.png       - LightGBM beeswarm（1着クラス）
  02_lgb_bar.png           - LightGBM 特徴量重要度棒グラフ
  03_xgb_summary.png       - XGBoost beeswarm
  04_cb_summary.png        - CatBoost beeswarm
  05_ensemble_bar.png      - 3モデル加重平均 特徴量重要度
  06_waterfall_*.png       - 穴馬個別 SHAP ウォーターフォール
  [勝率・連対率・複勝率]
  07_metric_shap_bar.png   - 勝率/連対率/複勝率 別 SHAP重要度比較（横並び棒グラフ）
  08_rentan_summary.png    - 連対率（1〜2着）SHAP beeswarm
  09_fukusho_summary.png   - 複勝率（1〜3着）SHAP beeswarm
  10_metric_precision.png  - 実測ヒット率（勝率/連対率/複勝率）
  11_shap_hitrate.png      - 予測確率十分位別ヒット率
"""

import os
import pickle
import numpy as np
import pandas as pd
import shap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime

# ── 設定 ──────────────────────────────────────────────────────────────────────
MODEL_PATH   = "D:/keiba_ai/model_v8.pkl"
DATA_PATH    = "D:/keiba_ai/keiba_data_features.csv"
OUT_DIR      = "D:/keiba_ai/shap_output"
SAMPLE_N     = 3000   # SHAP計算用サンプル数
WATERFALL_N  = 5      # 穴馬個別説明の頭数
TARGET_YEAR  = 2025   # 評価・穴馬抽出対象年
MIN_ODDS     = 30.0   # 穴馬定義（単勝30倍以上）
TOP_FEATURES = 20     # 棒グラフに表示する特徴量数

# 着順クラス列インデックス（全モデル共通: column N-1 = N着）
WIN_COL     = 0   # 1着
RENTAN_COL  = 1   # 2着
FUKUSHO_COL = 2   # 3着

COLORS = {
    "勝率":   "#E06C75",
    "連対率": "#E5C07B",
    "複勝率": "#98C379",
}


def _find_jp_font():
    candidates = ["MS Gothic", "Yu Gothic", "Meiryo", "IPAGothic", "Noto Sans CJK JP"]
    available = {f.name for f in fm.fontManager.ttflist}
    for c in candidates:
        if c in available:
            return c
    return None


jp_font = _find_jp_font()
if jp_font:
    plt.rcParams["font.family"] = jp_font
plt.rcParams["figure.dpi"] = 120


# ── ユーティリティ ─────────────────────────────────────────────────────────────
def load_artifacts():
    print(f"[{datetime.now():%H:%M:%S}] モデル読み込み中 ...")
    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    return (saved["lgb_model"], saved["xgb_model"],
            saved["cb_model"], saved["le"], saved["features"])


def load_data(features):
    print(f"[{datetime.now():%H:%M:%S}] データ読み込み中 ...")
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    return df, df[features]


def compute_ensemble_probas(lgb_model, xgb_model, cb_model, X):
    """アンサンブル確率から勝率・連対率・複勝率の確率を算出する。"""
    lgb_p = lgb_model.predict_proba(X)
    xgb_p = xgb_model.predict_proba(X)
    cb_p  = cb_model.predict_proba(X)
    ens   = 0.5 * lgb_p + 0.3 * xgb_p + 0.2 * cb_p

    win_prob     = ens[:, WIN_COL]
    rentan_prob  = ens[:, WIN_COL] + ens[:, RENTAN_COL]
    fukusho_prob = ens[:, WIN_COL] + ens[:, RENTAN_COL] + ens[:, FUKUSHO_COL]
    return win_prob, rentan_prob, fukusho_prob


def compute_hit_rates(df_year, win_prob, rentan_prob, fukusho_prob):
    """
    レースごとに win_prob 最大馬を1頭選び、実際の着順でヒット率を計算する。
    穴馬フィルタは掛けず全馬が対象。
    """
    df = df_year.copy()
    df["_win_prob"]     = win_prob
    df["_rentan_prob"]  = rentan_prob
    df["_fukusho_prob"] = fukusho_prob

    records = []
    for _, race in df.groupby("race_code"):
        if len(race) < 3 or "kakutei_chakujun" not in race.columns:
            continue
        pick = race.nlargest(1, "_win_prob").iloc[0]
        pos  = pick["kakutei_chakujun"]
        records.append({
            "win":     int(pos == 1),
            "rentan":  int(pos <= 2),
            "fukusho": int(pos <= 3),
        })

    if not records:
        return None

    hits = pd.DataFrame(records)
    return {
        "勝率":    hits["win"].mean(),
        "連対率":  hits["rentan"].mean(),
        "複勝率":  hits["fukusho"].mean(),
        "n_races": len(hits),
    }


def compute_shap_metric(lgb_shap_vals):
    """
    LightGBM SHAP値から勝率/連対率/複勝率用の値を導出する。
    SHAP の加法性より P(A or B) の SHAP = SHAP(A) + SHAP(B)。
    返値: shape (n_samples, n_features) x 3メトリクス
    """
    win_shap     = lgb_shap_vals[:, :, WIN_COL]
    rentan_shap  = lgb_shap_vals[:, :, WIN_COL] + lgb_shap_vals[:, :, RENTAN_COL]
    fukusho_shap = (lgb_shap_vals[:, :, WIN_COL]
                    + lgb_shap_vals[:, :, RENTAN_COL]
                    + lgb_shap_vals[:, :, FUKUSHO_COL])
    return win_shap, rentan_shap, fukusho_shap


def shap_importance(shap_vals_2d, features):
    return pd.Series(np.abs(shap_vals_2d).mean(axis=0), index=features)


def sample_background(X, n):
    return X.sample(min(n, len(X)), random_state=42)


def save(fig, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  → 保存: {path}")


# ── 可視化関数（基本） ──────────────────────────────────────────────────────────
def plot_summary(shap_2d, X_sample, title, fname):
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.summary_plot(shap_2d, X_sample, show=False,
                      max_display=TOP_FEATURES, plot_size=None)
    plt.title(title, fontsize=13)
    save(fig, fname)


def plot_bar(importance: pd.Series, title: str, fname: str, color="#4C72B0"):
    top = importance.nlargest(TOP_FEATURES).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(top.index, top.values, color=color)
    ax.set_xlabel("平均 |SHAP値|")
    ax.set_title(title, fontsize=13)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    save(fig, fname)


def plot_waterfall(shap_explanation, horse_label, fname):
    fig, ax = plt.subplots(figsize=(10, 7))
    shap.plots.waterfall(shap_explanation, show=False, max_display=15)
    plt.title(f"SHAP 個別説明: {horse_label}", fontsize=12)
    save(fig, fname)


# ── 可視化関数（勝率・連対率・複勝率） ─────────────────────────────────────────
def plot_metric_shap_bar(imp_win, imp_rentan, imp_fukusho, features, fname):
    """3指標の SHAP重要度を横並び棒グラフで比較する。"""
    # 3指標の平均で上位特徴量を選択
    avg = (imp_win + imp_rentan + imp_fukusho) / 3
    top_feats = avg.nlargest(TOP_FEATURES).index.tolist()[::-1]

    x     = np.arange(len(top_feats))
    width = 0.25
    fig, ax = plt.subplots(figsize=(11, 8))

    for i, (label, imp) in enumerate(
        [("勝率", imp_win), ("連対率", imp_rentan), ("複勝率", imp_fukusho)]
    ):
        ax.barh(x + (i - 1) * width, imp[top_feats].values,
                width, label=label, color=COLORS[label], alpha=0.85)

    ax.set_yticks(x)
    ax.set_yticklabels(top_feats, fontsize=9)
    ax.set_xlabel("平均 |SHAP値|")
    ax.set_title("指標別 特徴量SHAP重要度（勝率 / 連対率 / 複勝率）", fontsize=13)
    ax.legend(loc="lower right")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    save(fig, fname)


def plot_metric_precision(hit_rates: dict, year: int, fname: str):
    """実測ヒット率を棒グラフで表示する。"""
    metrics = ["勝率", "連対率", "複勝率"]
    values  = [hit_rates[m] * 100 for m in metrics]
    n       = hit_rates["n_races"]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(metrics, values,
                  color=[COLORS[m] for m in metrics], width=0.5, alpha=0.85)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=12, fontweight="bold")

    ax.set_ylabel("ヒット率 (%)")
    ax.set_ylim(0, max(values) * 1.25)
    ax.set_title(
        f"{year}年 予測ヒット率（win_prob最大馬を1頭選択, {n}レース）", fontsize=12
    )
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    save(fig, fname)


def plot_shap_hitrate(df_year, win_prob, rentan_prob, fukusho_prob, year, fname):
    """
    予測確率の十分位（デシル）ごとに実際のヒット率を折れ線で示す。
    モデルの識別能力と単調性を確認できる。
    """
    df = df_year.copy()
    df["_win_prob"]     = win_prob
    df["_rentan_prob"]  = rentan_prob
    df["_fukusho_prob"] = fukusho_prob

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    fig.suptitle(
        f"{year}年 予測確率デシル別 実測ヒット率（デシル10が最高確率群）",
        fontsize=12
    )

    specs = [
        ("勝率",   "_win_prob",     "kakutei_chakujun", lambda s: s == 1),
        ("連対率", "_rentan_prob",  "kakutei_chakujun", lambda s: s <= 2),
        ("複勝率", "_fukusho_prob", "kakutei_chakujun", lambda s: s <= 3),
    ]

    for ax, (label, prob_col, result_col, hit_fn) in zip(axes, specs):
        if result_col not in df.columns:
            ax.set_title(f"{label}（データなし）")
            continue

        df["_decile"] = pd.qcut(df[prob_col], q=10,
                                labels=False, duplicates="drop") + 1
        grp = df.groupby("_decile")[result_col].apply(
            lambda s: hit_fn(s).mean() * 100
        )

        ax.bar(grp.index, grp.values, color=COLORS[label], alpha=0.75, width=0.7)
        ax.plot(grp.index, grp.values, "o-", color=COLORS[label],
                linewidth=2, markersize=6)
        ax.set_xlabel("確率デシル（1=低・10=高）")
        ax.set_ylabel("実測ヒット率 (%)")
        ax.set_title(label, fontsize=12)
        ax.set_xticks(grp.index)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

        # 全体平均を点線で表示
        overall = hit_fn(df[result_col]).mean() * 100
        ax.axhline(overall, color="gray", linestyle="--", linewidth=1,
                   label=f"全体平均 {overall:.1f}%")
        ax.legend(fontsize=8)

    plt.tight_layout()
    save(fig, fname)


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    lgb_model, xgb_model, cb_model, le, features = load_artifacts()
    df, X = load_data(features)

    X_sample = sample_background(X, SAMPLE_N)

    # ── LightGBM SHAP（全クラス分計算） ─────────────────────────────────────
    print(f"\n[{datetime.now():%H:%M:%S}] LightGBM SHAP 計算中 ...")
    lgb_exp  = shap.TreeExplainer(lgb_model)
    lgb_shap = lgb_exp(X_sample)   # Explanation: (n, features, classes)

    win_shap, rentan_shap, fukusho_shap = compute_shap_metric(lgb_shap.values)

    imp_win     = shap_importance(win_shap,     features)
    imp_rentan  = shap_importance(rentan_shap,  features)
    imp_fukusho = shap_importance(fukusho_shap, features)

    # 01: LightGBM beeswarm（勝率）
    plot_summary(win_shap, X_sample,
                 "LightGBM: 勝率への特徴量の影響度", "01_lgb_summary.png")
    # 02: LightGBM 棒グラフ
    plot_bar(imp_win, "LightGBM 特徴量重要度（勝率 |SHAP|平均）", "02_lgb_bar.png",
             color=COLORS["勝率"])

    # ── XGBoost SHAP ─────────────────────────────────────────────────────────
    print(f"[{datetime.now():%H:%M:%S}] XGBoost SHAP 計算中 ...")
    xgb_exp  = shap.TreeExplainer(xgb_model)
    xgb_shap = xgb_exp(X_sample)
    xgb_win  = xgb_shap.values[:, :, WIN_COL]
    imp_xgb_win = shap_importance(xgb_win, features)

    # 03: XGBoost beeswarm
    plot_summary(xgb_win, X_sample,
                 "XGBoost: 勝率への特徴量の影響度", "03_xgb_summary.png")

    # ── CatBoost SHAP ────────────────────────────────────────────────────────
    print(f"[{datetime.now():%H:%M:%S}] CatBoost SHAP 計算中 ...")
    cb_exp  = shap.TreeExplainer(cb_model)
    cb_shap = cb_exp(X_sample)
    cb_win  = cb_shap.values[:, :, WIN_COL]
    imp_cb_win = shap_importance(cb_win, features)

    # 04: CatBoost beeswarm
    plot_summary(cb_win, X_sample,
                 "CatBoost: 勝率への特徴量の影響度", "04_cb_summary.png")

    # 05: アンサンブル平均 棒グラフ
    ens_imp = 0.5 * imp_win + 0.3 * imp_xgb_win + 0.2 * imp_cb_win
    plot_bar(ens_imp, "アンサンブル 特徴量重要度（加重 |SHAP|平均・勝率）",
             "05_ensemble_bar.png")

    # ── 穴馬の個別ウォーターフォール ─────────────────────────────────────────
    print(f"\n[{datetime.now():%H:%M:%S}] 穴馬個別説明 生成中 ...")
    target = df[
        (df["kaisai_nen"] == TARGET_YEAR) &
        (df.get("tansho_odds", pd.Series(0, index=df.index)) >= MIN_ODDS)
    ].copy()

    if len(target) == 0:
        print(f"  ⚠ {TARGET_YEAR}年の穴馬データが見つかりません。スキップします。")
    else:
        X_target  = target[features]
        wp, _, _  = compute_ensemble_probas(lgb_model, xgb_model, cb_model, X_target)
        target["win_prob"] = wp
        top_horses = target.nlargest(WATERFALL_N, "win_prob")

        for i, (idx, row) in enumerate(top_horses.iterrows(), 1):
            shap_row = lgb_exp(X_target.loc[[idx]]).values[:, :, WIN_COL]
            # Explanation オブジェクトを再構築
            base_val = lgb_exp.expected_value[WIN_COL]
            exp = shap.Explanation(
                values=shap_row[0],
                base_values=base_val,
                data=X_target.loc[idx].values,
                feature_names=features,
            )
            label = (f"umaban={int(row.get('umaban', 0))} "
                     f"odds={row.get('tansho_odds', '?')}倍 "
                     f"win_prob={row['win_prob']:.3f}")
            plot_waterfall(exp, label, f"06_waterfall_{i:02d}.png")

    # ━━━ 勝率・連対率・複勝率 可視化 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # 07: 3指標の SHAP重要度 横並び比較
    print(f"\n[{datetime.now():%H:%M:%S}] 指標別 SHAP重要度 比較グラフ生成中 ...")
    plot_metric_shap_bar(imp_win, imp_rentan, imp_fukusho, features,
                         "07_metric_shap_bar.png")

    # 08: 連対率 beeswarm
    plot_summary(rentan_shap, X_sample,
                 "LightGBM: 連対率（1〜2着）への特徴量の影響度",
                 "08_rentan_summary.png")

    # 09: 複勝率 beeswarm
    plot_summary(fukusho_shap, X_sample,
                 "LightGBM: 複勝率（1〜3着）への特徴量の影響度",
                 "09_fukusho_summary.png")

    # 10 & 11: 対象年データで実測ヒット率を計算
    print(f"\n[{datetime.now():%H:%M:%S}] {TARGET_YEAR}年 ヒット率計算中 ...")
    df_year = df[df["kaisai_nen"] == TARGET_YEAR].copy()

    if len(df_year) == 0:
        print(f"  ⚠ {TARGET_YEAR}年データなし。スキップします。")
    else:
        X_year = df_year[features]
        wp, rp, fp = compute_ensemble_probas(lgb_model, xgb_model, cb_model, X_year)

        # 10: 実測ヒット率棒グラフ
        hit_rates = compute_hit_rates(df_year, wp, rp, fp)
        if hit_rates:
            print(f"  勝率={hit_rates['勝率']:.1%}  連対率={hit_rates['連対率']:.1%}"
                  f"  複勝率={hit_rates['複勝率']:.1%}  ({hit_rates['n_races']}レース)")
            plot_metric_precision(hit_rates, TARGET_YEAR, "10_metric_precision.png")

        # 11: デシル別ヒット率
        plot_shap_hitrate(df_year, wp, rp, fp, TARGET_YEAR, "11_shap_hitrate.png")

    # ── サマリ出力 ────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  指標別 SHAP重要度 トップ{TOP_FEATURES}（LightGBM）")
    print(f"{'─'*55}")
    print(f"  {'特徴量':<33} {'勝率':>8} {'連対率':>8} {'複勝率':>8}")
    print(f"{'─'*55}")
    top_feats = (imp_win + imp_rentan + imp_fukusho).nlargest(TOP_FEATURES).index
    for feat in top_feats:
        print(f"  {feat:<33} {imp_win[feat]:>8.4f} "
              f"{imp_rentan[feat]:>8.4f} {imp_fukusho[feat]:>8.4f}")
    print(f"{'='*55}")
    print(f"\n✅ 全出力を {OUT_DIR} に保存しました。")


if __name__ == "__main__":
    main()
