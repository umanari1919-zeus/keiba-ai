"""
📊 Model Comparison — MLflow 実験比較・モデルバージョン追跡

MLflow のランデータまたは model_v8.meta.json からメトリクスを読み込み、
モデル間の精度比較・アンサンブル重み・特徴量数の推移を可視化する。
"""

import json
import os
import glob

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from pathlib import Path

try:
    from utils.theme import apply_theme
    apply_theme()
except ImportError:
    pass

st.set_page_config(
    page_title="Model Comparison",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 モデル比較")
st.markdown("MLflow 実験トラッキングによるモデルバージョン比較・メトリクス推移")

BASE_PATH = os.getenv("KEIBA_BASE", r"D:\keiba_ai")


# ── データ読み込み ──────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_mlflow_runs() -> pd.DataFrame:
    """MLflow のランデータを DataFrame で返す。"""
    try:
        import mlflow
        tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI",
            f"file:///{Path(BASE_PATH).as_posix()}/mlflow_tracking",
        )
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("umanari-ensemble")
        runs = mlflow.search_runs(max_results=50, order_by=["start_time DESC"])
        if not runs.empty:
            return runs
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=300)
def load_meta_files() -> list[dict]:
    """model_v8.meta.json 系のサイドカーファイルを読み込む。"""
    pattern = os.path.join(BASE_PATH, "*.meta.json")
    files = sorted(glob.glob(pattern), reverse=True)
    metas = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                metas.append(json.load(fp))
        except Exception:
            continue
    return metas


# ── メイン ──────────────────────────────────────────────────────────

runs_df = load_mlflow_runs()
meta_files = load_meta_files()

if runs_df.empty and not meta_files:
    st.warning("MLflow ランデータもメタファイルも見つかりません。モデルを学習してから確認してください。")
    st.info("""
    **データ生成方法:**
    ```bash
    python pipeline/model_train_03.py      # モデル学習 → 自動登録
    python mlflow_register.py model_v8.pkl  # 手動登録
    ```
    """)
    st.stop()

# ── MLflow ラン一覧テーブル ─────────────────────────────────────────

if not runs_df.empty:
    st.subheader("🔬 MLflow 実験ラン一覧")

    display_cols = {
        "run_id": "Run ID",
        "start_time": "実行日時",
        "params.model_version": "バージョン",
        "params.n_features": "特徴量数",
        "params.git_hash": "Git Hash",
        "metrics.ensemble_acc": "アンサンブル精度",
        "metrics.ensemble_logloss": "Logloss",
        "metrics.lgb_acc": "LGB精度",
        "metrics.xgb_acc": "XGB精度",
        "metrics.cb_acc": "CB精度",
        "metrics.val_acc": "検証精度",
    }
    available = {k: v for k, v in display_cols.items() if k in runs_df.columns}
    df_display = runs_df[list(available.keys())].rename(columns=available)
    if "Run ID" in df_display.columns:
        df_display["Run ID"] = df_display["Run ID"].str[:12]
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── メトリクス推移グラフ ─────────────────────────────────────

    st.subheader("📈 精度推移")

    metric_cols = [c for c in runs_df.columns if c.startswith("metrics.") and "acc" in c]
    if metric_cols and "start_time" in runs_df.columns:
        df_plot = runs_df[["start_time"] + metric_cols].copy()
        df_plot["start_time"] = pd.to_datetime(df_plot["start_time"])
        df_plot = df_plot.sort_values("start_time")

        fig = go.Figure()
        color_map = {
            "metrics.lgb_acc": ("#3fb950", "LightGBM"),
            "metrics.xgb_acc": ("#58a6ff", "XGBoost"),
            "metrics.cb_acc": ("#f78166", "CatBoost"),
            "metrics.ensemble_acc": ("#d2a8ff", "アンサンブル"),
            "metrics.val_acc": ("#f0883e", "検証セット"),
        }
        for col in metric_cols:
            color, name = color_map.get(col, ("#8b949e", col.replace("metrics.", "")))
            fig.add_trace(go.Scatter(
                x=df_plot["start_time"],
                y=df_plot[col],
                mode="lines+markers",
                name=name,
                line=dict(color=color, width=2),
                marker=dict(size=8),
            ))
        fig.update_layout(
            yaxis_title="Accuracy",
            xaxis_title="学習日時",
            template="plotly_dark",
            height=400,
            legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Logloss 推移 ──────────────────────────────────────────

    logloss_cols = [c for c in runs_df.columns if "logloss" in c]
    if logloss_cols and "start_time" in runs_df.columns:
        st.subheader("📉 Logloss 推移")
        df_ll = runs_df[["start_time"] + logloss_cols].copy()
        df_ll["start_time"] = pd.to_datetime(df_ll["start_time"])
        df_ll = df_ll.sort_values("start_time")

        fig_ll = go.Figure()
        for col in logloss_cols:
            fig_ll.add_trace(go.Scatter(
                x=df_ll["start_time"],
                y=df_ll[col],
                mode="lines+markers",
                name=col.replace("metrics.", ""),
                marker=dict(size=8),
            ))
        fig_ll.update_layout(
            yaxis_title="Log Loss",
            xaxis_title="学習日時",
            template="plotly_dark",
            height=350,
        )
        st.plotly_chart(fig_ll, use_container_width=True)

    # ── アンサンブル重み比較 ──────────────────────────────────

    weight_cols = [c for c in runs_df.columns if "weight" in c]
    if weight_cols:
        st.subheader("⚖️ アンサンブル重み")
        latest = runs_df.iloc[0]
        weights = {}
        for col in weight_cols:
            label = col.replace("params.", "").replace("_weight", "").upper()
            val = latest.get(col)
            if val is not None:
                try:
                    weights[label] = float(val)
                except (ValueError, TypeError):
                    pass

        if weights:
            col1, col2 = st.columns([1, 2])
            with col1:
                for name, w in weights.items():
                    st.metric(name, f"{w:.0%}")
            with col2:
                fig_w = go.Figure(data=[go.Pie(
                    labels=list(weights.keys()),
                    values=list(weights.values()),
                    hole=0.4,
                    marker_colors=["#3fb950", "#58a6ff", "#f78166"],
                )])
                fig_w.update_layout(
                    template="plotly_dark",
                    height=250,
                    margin=dict(t=10, b=10),
                )
                st.plotly_chart(fig_w, use_container_width=True)

# ── メタファイル情報 ─────────────────────────────────────────────

if meta_files:
    st.subheader("📋 モデルメタデータ")
    for i, m in enumerate(meta_files[:5]):
        with st.expander(
            f"🏷️ {m.get('run_name', 'unknown')} — "
            f"精度 {m.get('metrics', {}).get('ensemble_acc', 'N/A')} — "
            f"{m.get('registered_at', '')[:10]}",
            expanded=(i == 0),
        ):
            c1, c2, c3, c4 = st.columns(4)
            metrics = m.get("metrics", {})
            c1.metric("アンサンブル精度", f"{metrics.get('ensemble_acc', 0):.4f}")
            c2.metric("Logloss", f"{metrics.get('ensemble_logloss', 0):.4f}")
            c3.metric("特徴量数", m.get("n_features", "?"))
            c4.metric("Git Hash", m.get("git_hash", "?"))

            st.markdown(f"**Run ID:** `{m.get('run_id', 'N/A')}`")
            st.markdown(f"**重み:** LGB={m.get('ensemble_weights', [0])[0]:.0%} "
                        f"XGB={m.get('ensemble_weights', [0, 0])[1]:.0%} "
                        f"CB={m.get('ensemble_weights', [0, 0, 0])[2]:.0%}")

            if m.get("features"):
                st.markdown(f"**特徴量 ({len(m['features'])}個):** "
                            f"`{'`, `'.join(m['features'][:10])}`"
                            f"{'...' if len(m['features']) > 10 else ''}")

# ── フッター ──────────────────────────────────────────────────────

st.markdown("---")
st.caption("💡 MLflow UI: `mlflow ui --backend-store-uri file:///D:/keiba_ai/mlflow_tracking`")
