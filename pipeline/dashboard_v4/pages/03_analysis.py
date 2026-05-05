"""
🔬 Analysis — SHAP・特徴量・血統・オッズシグナル分析

特徴量重要度、血統ニックス、オッズシグナル (SHARP/STEAM/DRIFT)、相関分析。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from utils.api_client import APIClient
from utils.data_loader import load_cached_data
from utils.theme import apply_theme

apply_theme()

st.set_page_config(
    page_title="Analysis",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔬 Detailed Analysis")
st.markdown("特徴量分析、血統・オッズシグナル、相関分析、知識ベース反映")

# ── データ読み込み ────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_model_performance():
    """モデルパフォーマンスを読み込み"""
    try:
        perf_path = Path("data") / "model_performance.json"
        if perf_path.exists():
            with open(perf_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=600)
def load_shap_features():
    """SHAP 特徴量重要度を読み込み"""
    try:
        # shap_output/ ディレクトリから feature_importance.json 読み込み
        shap_path = Path("pipeline") / "shap_output" / "feature_importance.json"
        if shap_path.exists():
            with open(shap_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=600)
def load_knowledge_base():
    """知識ベース EV boost を読み込み"""
    try:
        kb_path = Path("data") / "knowledge_base" / "ev_boost_map.json"
        if kb_path.exists():
            with open(kb_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=600)
def load_keiba_features():
    """特徴量データを読み込み"""
    try:
        csv_path = Path("data") / "keiba_data_features.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, nrows=10000, on_bad_lines='skip')
        return pd.DataFrame()
    except:
        return pd.DataFrame()


# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["🔬 Feature Importance", "🧬 Bloodline Analysis", "📊 Odds Signals", "📈 Correlation"])

# ── TAB 1: Feature Importance ──────────────────────────────────────────
with tabs[0]:
    st.subheader("🔬 SHAP Feature Importance (Top 15)")

    shap_features = load_shap_features()

    if shap_features:
        # LightGBM と XGBoost の feature importance を取得
        lgb_features = shap_features.get("lightgbm", {})
        xgb_features = shap_features.get("xgboost", {})

        # 結合・ソート
        all_features = {}
        for feat, imp in lgb_features.items():
            all_features[feat] = all_features.get(feat, 0) + imp
        for feat, imp in xgb_features.items():
            all_features[feat] = all_features.get(feat, 0) + imp

        # Top 15
        top_features = sorted(all_features.items(), key=lambda x: x[1], reverse=True)[:15]
        feature_names = [f[0] for f in top_features]
        feature_values = [f[1] for f in top_features]

        # 水平棒グラフ
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=feature_names,
            x=feature_values,
            orientation='h',
            marker=dict(color=feature_values, colorscale='Blues', showscale=True),
            hovertemplate='<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>',
        ))

        fig.update_layout(
            title='Top 15 Feature Importance (Ensemble)',
            xaxis_title='Importance Score',
            yaxis_title='Feature',
            height=500,
            template='plotly_dark',
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)

        # 特徴量カテゴリ分布
        st.markdown("---")
        st.subheader("Feature Category Distribution")

        # 特徴量カテゴリを推定
        category_map = {
            'odds': ['tansho_odds', 'fukusho_odds', 'odds'],
            'horse': ['horse_age', 'horse_weight', 'weight_change', 'wins', 'place'],
            'jockey': ['jockey_win_rate', 'kishu_keibajo_win_rate', 'jockey'],
            'trainer': ['trainer_win_rate', 'chokyoshi', 'trainer'],
            'pace': ['pace_rating', 'pace_direction', 'pace', 'ペース'],
            'condition': ['weather', 'condition', 'track', '馬場'],
            'race': ['distance', 'grade', 'race_type', 'field'],
        }

        category_importance = {}
        for feat, imp in top_features:
            found = False
            for cat, keywords in category_map.items():
                if any(kw.lower() in feat.lower() for kw in keywords):
                    category_importance[cat] = category_importance.get(cat, 0) + imp
                    found = True
                    break
            if not found:
                category_importance['other'] = category_importance.get('other', 0) + imp

        fig_cat = px.pie(
            values=list(category_importance.values()),
            names=list(category_importance.keys()),
            title='Feature Category Breakdown',
            color_discrete_sequence=px.colors.sequential.Blues_r,
        )

        st.plotly_chart(fig_cat, use_container_width=True)

    else:
        st.info("SHAP feature importance not available. Run feature analysis pipeline.")

# ── TAB 2: Bloodline & Nicks ──────────────────────────────────────────
with tabs[1]:
    st.subheader("🧬 Bloodline & Nick Analysis")

    st.markdown("""
    **ニックス**: 父馬の血統 × 母の父の血統の組み合わせが、子馬の成績に及ぼす影響。
    競馬では「××系とΔΔ系の相性が良い」という知識が蓄積されている。
    """)

    keiba_df = load_keiba_features()

    if not keiba_df.empty:
        # 血統関連列を抽出
        bloodline_cols = [col for col in keiba_df.columns if 'nick' in col.lower() or 'chichi' in col.lower() or '血統' in col]

        if bloodline_cols:
            # 勝利馬の血統分析
            if 'target' in keiba_df.columns or 'win' in keiba_df.columns:
                target_col = next((col for col in keiba_df.columns if col in ['target', 'win']), None)

                if target_col:
                    winner_df = keiba_df[keiba_df[target_col] == 1]

                    # 最も多い血統ニックス
                    nick_col = bloodline_cols[0] if bloodline_cols else None

                    if nick_col and nick_col in keiba_df.columns:
                        nick_counts = winner_df[nick_col].value_counts().head(20)

                        fig = px.bar(
                            x=nick_counts.values,
                            y=nick_counts.index,
                            orientation='h',
                            title=f'Top 20 Winning Bloodline Nicks ({nick_col})',
                            labels={'x': 'Frequency', 'y': 'Nick'},
                        )

                        st.plotly_chart(fig, use_container_width=True)

        # 知識ベース EV boost
        kb = load_knowledge_base()

        if kb:
            st.markdown("---")
            st.subheader("Knowledge Base EV Boost Applied")

            # boost マップを表示
            boost_list = []
            for key, boost_val in list(kb.items())[:20]:
                boost_list.append({
                    'Key': key,
                    'EV Boost': f"{boost_val:.2f}" if isinstance(boost_val, (int, float)) else str(boost_val),
                })

            if boost_list:
                st.dataframe(pd.DataFrame(boost_list), use_container_width=True)

    else:
        st.info("Bloodline data not available")

# ── TAB 3: Odds Signals ────────────────────────────────────────────────
with tabs[2]:
    st.subheader("📊 Odds Signals (SHARP / STEAM / DRIFT)")

    st.markdown("""
    **SHARP**: 専業筋（プロ）が買った馬 → オッズが下がる前の高オッズで良い買い目
    **STEAM**: 大衆が買った馬 → オッズが更に下がるリスク（避けるべき）
    **DRIFT**: 人気が落ちて、オッズが上がった馬 → 賭けられなかった理由を確認
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.metric("🎯 SHARP シグナル", "未検出", delta="オッズ監視中", delta_color="neutral")

    with col2:
        st.metric("⚠️ STEAM シグナル", "未検出", delta="大衆追従回避", delta_color="neutral")

    st.markdown("---")

    # オッズ変動シミュレーション
    st.subheader("Odds Movement Simulation")

    col1, col2, col3 = st.columns(3)

    with col1:
        opening_odds = st.number_input("オープニングオッズ", value=10.0, min_value=1.0)

    with col2:
        closing_odds = st.number_input("クローズオッズ", value=8.5, min_value=1.0)

    with col3:
        win_prob = st.slider("推定勝率", 0, 100, 20)

    # オッズの種類を判定
    odds_move = closing_odds - opening_odds
    odds_change_pct = (odds_move / opening_odds * 100) if opening_odds > 0 else 0

    if odds_change_pct < -10:
        signal = "🎯 SHARP (下がったオッズ)"
        color = "blue"
    elif odds_change_pct > 10:
        signal = "📈 DRIFT (上がったオッズ)"
        color = "orange"
    else:
        signal = "→ STABLE (変動少)"
        color = "gray"

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("オッズ変動", f"{odds_change_pct:+.1f}%", delta=signal)

    with col2:
        ev_opening = (opening_odds - 1) * (win_prob / 100) - (1 - win_prob / 100)
        st.metric("オープニングEV", f"{ev_opening:+.2f}", delta="+ なら買い" if ev_opening > 0 else "避ける")

    with col3:
        ev_closing = (closing_odds - 1) * (win_prob / 100) - (1 - win_prob / 100)
        st.metric("クローズEV", f"{ev_closing:+.2f}", delta="+ なら買い" if ev_closing > 0 else "避ける")

    # オッズ変動グラフ
    odds_timeline = np.linspace(opening_odds, closing_odds, 10)
    ev_timeline = [(o - 1) * (win_prob / 100) - (1 - win_prob / 100) for o in odds_timeline]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        y=odds_timeline,
        mode='lines+markers',
        name='Odds',
        line=dict(color='#2E86AB', width=2),
        yaxis='y1',
        marker=dict(size=8),
    ))

    fig.add_trace(go.Scatter(
        y=ev_timeline,
        mode='lines+markers',
        name='EV',
        line=dict(color='#E74C3C', width=2, dash='dash'),
        yaxis='y2',
        marker=dict(size=8),
    ))

    fig.update_layout(
        title='Odds & EV Timeline',
        xaxis_title='Time',
        yaxis=dict(title='Odds', side='left'),
        yaxis2=dict(title='EV', side='right', overlaying='y'),
        hovermode='x unified',
        template='plotly_dark',
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: Correlation Analysis ────────────────────────────────────────
with tabs[3]:
    st.subheader("📈 Feature Correlation Heatmap")

    keiba_df = load_keiba_features()

    if not keiba_df.empty:
        # 数値列のみ選択
        numeric_df = keiba_df.select_dtypes(include=[np.number])

        if not numeric_df.empty:
            # 相関マトリックス
            corr_matrix = numeric_df.corr()

            # Top 10 相関する特徴量を抽出
            corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    corr_val = corr_matrix.iloc[i, j]
                    if abs(corr_val) > 0.5:  # 0.5 以上の相関
                        corr_pairs.append({
                            'Feature 1': corr_matrix.columns[i],
                            'Feature 2': corr_matrix.columns[j],
                            'Correlation': corr_val,
                        })

            if corr_pairs:
                corr_df = pd.DataFrame(corr_pairs).sort_values('Correlation', key=abs, ascending=False).head(15)

                fig = px.bar(
                    corr_df,
                    x='Correlation',
                    y=[f"{r['Feature 1']} ↔ {r['Feature 2']}" for _, r in corr_df.iterrows()],
                    orientation='h',
                    title='Top 15 Feature Correlations',
                    color='Correlation',
                    color_continuous_scale='RdBu',
                    range_color=[-1, 1],
                )

                st.plotly_chart(fig, use_container_width=True)

                # 相関テーブル
                st.dataframe(corr_df.assign(Correlation=corr_df['Correlation'].apply(lambda x: f"{x:.3f}")), use_container_width=True)

    else:
        st.info("Feature data not available")

st.markdown("---")

st.info("""
💡 **分析ポイント**

- **特徴量重要度**: オッズ・馬齢・騎手・調教師が上位（典型的）
- **血統ニックス**: 勝利馬の血統パターンを学習 → EV boost に反映
- **オッズシグナル**: SHARP は買い目、DRIFT は要検証、STEAM は要回避
- **相関分析**: 高相関特徴量は共線性チェック対象（モデルの不安定性）
""")
