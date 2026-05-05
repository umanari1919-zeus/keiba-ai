"""
Page: Detailed Analysis
"""
import streamlit as st
import pandas as pd
import numpy as np
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    PLOTLY = False

from components import kpi_card
from utils.data_loader import (
    load_roi_tracker, load_model_performance, load_pedigree_nicks,
    load_shap_summary, load_condition_roi, load_knowledge_base
)
from utils.theme import plotly_theme


def render():
    """Render the detailed analysis page."""
    st.markdown('<div class="page-title">🔬 詳細分析</div>', unsafe_allow_html=True)

    # ── Model Performance ──────────────────────────────
    st.markdown("<div class='sec-head'>モデル精度推移</div>", unsafe_allow_html=True)
    perf = load_model_performance()
    if perf and not perf.empty:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            latest_acc = perf['accuracy'].iloc[-1] if 'accuracy' in perf.columns else 0
            kpi_card("現在精度", f"{latest_acc:.1f}%", "#3fb950")
        with col_b:
            avg_roc = perf['roc_auc'].mean() if 'roc_auc' in perf.columns else 0
            kpi_card("平均 ROC-AUC", f"{avg_roc:.3f}", "#58a6ff")
        with col_c:
            latest_f1 = perf['f1_score'].iloc[-1] if 'f1_score' in perf.columns else 0
            kpi_card("F1 Score", f"{latest_f1:.3f}", "#e3b341")

        if PLOTLY and 'date' in perf.columns:
            perf['date'] = pd.to_datetime(perf['date'])
            fig = go.Figure()
            if 'accuracy' in perf.columns:
                fig.add_trace(go.Scatter(
                    x=perf['date'], y=perf['accuracy'],
                    name='精度', line=dict(color='#3fb950', width=2),
                    mode='lines+markers'
                ))
            if 'roc_auc' in perf.columns:
                fig.add_trace(go.Scatter(
                    x=perf['date'], y=perf['roc_auc'] * 100,
                    name='ROC-AUC (%)', line=dict(color='#58a6ff', width=2, dash='dash'),
                    mode='lines+markers'
                ))
            fig.update_layout(**plotly_theme(), height=250, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("モデル性能データなし")

    # ── SHAP Feature Importance ────────────────────────
    st.markdown("<div class='sec-head'>特徴量重要度 (SHAP)</div>", unsafe_allow_html=True)
    shap_data = load_shap_summary()
    if shap_data and not shap_data.empty:
        col_lgb, col_xgb = st.columns(2)
        with col_lgb:
            st.markdown("**LightGBM**", unsafe_allow_html=True)
            if 'lgb_shap' in shap_data.columns:
                lgb_top = shap_data.nlargest(10, 'lgb_shap')[['feature', 'lgb_shap']].copy()
                if PLOTLY and not lgb_top.empty:
                    fig = px.barh(lgb_top, x='lgb_shap', y='feature',
                                 color='lgb_shap', color_continuous_scale='Viridis',
                                 labels={'lgb_shap': 'SHAP値'})
                    fig.update_layout(**plotly_theme(), height=300, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(lgb_top, use_container_width=True, hide_index=True)

        with col_xgb:
            st.markdown("**XGBoost**", unsafe_allow_html=True)
            if 'xgb_shap' in shap_data.columns:
                xgb_top = shap_data.nlargest(10, 'xgb_shap')[['feature', 'xgb_shap']].copy()
                if PLOTLY and not xgb_top.empty:
                    fig = px.barh(xgb_top, x='xgb_shap', y='feature',
                                 color='xgb_shap', color_continuous_scale='Plasma',
                                 labels={'xgb_shap': 'SHAP値'})
                    fig.update_layout(**plotly_theme(), height=300, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(xgb_top, use_container_width=True, hide_index=True)
    else:
        st.info("SHAP分析データなし — `model_train_03.py` を実行してください")

    # ── Pedigree Nicks Analysis ────────────────────────
    st.markdown("<div class='sec-head'>血統ニックス分析</div>", unsafe_allow_html=True)
    nicks = load_pedigree_nicks()
    if nicks and not nicks.empty:
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.markdown("**ニックス指数分布**", unsafe_allow_html=True)
            if 'nicks_score' in nicks.columns:
                if PLOTLY:
                    fig = px.histogram(nicks, x='nicks_score', nbins=30,
                                      color_discrete_sequence=['#58a6ff'],
                                      labels={'nicks_score': 'ニックス指数', 'count': '件数'})
                    fig.update_layout(**plotly_theme(), height=250, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.bar_chart(nicks['nicks_score'].value_counts().head(20), height=250)

        with col_n2:
            st.markdown("**父系別平均ニックス**", unsafe_allow_html=True)
            if 'sire' in nicks.columns and 'nicks_score' in nicks.columns:
                sire_avg = nicks.groupby('sire')['nicks_score'].agg(['mean', 'count']).reset_index()
                sire_avg = sire_avg[sire_avg['count'] >= 5].sort_values('mean', ascending=False).head(12)
                if PLOTLY and not sire_avg.empty:
                    fig = px.bar(sire_avg, x='mean', y='sire', orientation='h',
                                color='mean', color_continuous_scale='RdYlGn',
                                labels={'mean': 'ニックス指数', 'count': '件数'})
                    fig.update_layout(**plotly_theme(), height=280, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(sire_avg, use_container_width=True, hide_index=True)
    else:
        st.info("血統データなし")

    # ── Condition-Adjusted ROI ─────────────────────────
    st.markdown("<div class='sec-head'>条件別ROI係数</div>", unsafe_allow_html=True)
    cond_roi = load_condition_roi()
    if cond_roi and not cond_roi.empty:
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown("**競馬場別**", unsafe_allow_html=True)
            if 'venue' in cond_roi.columns and 'roi_coeff' in cond_roi.columns:
                venue_roi = cond_roi[['venue', 'roi_coeff']].drop_duplicates().sort_values('roi_coeff', ascending=False)
                if PLOTLY and not venue_roi.empty:
                    fig = px.bar(venue_roi, x='roi_coeff', y='venue', orientation='h',
                                color='roi_coeff',
                                color_continuous_scale=['#f85149', '#e3b341', '#3fb950'])
                    fig.update_layout(**plotly_theme(), height=280, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(venue_roi, use_container_width=True, hide_index=True)

        with col_v2:
            st.markdown("**距離帯別**", unsafe_allow_html=True)
            if 'distance_band' in cond_roi.columns and 'roi_coeff' in cond_roi.columns:
                dist_roi = cond_roi[['distance_band', 'roi_coeff']].drop_duplicates().sort_values('distance_band')
                if PLOTLY and not dist_roi.empty:
                    fig = px.bar(dist_roi, x='distance_band', y='roi_coeff',
                                color='roi_coeff',
                                color_continuous_scale=['#f85149', '#e3b341', '#3fb950'],
                                labels={'distance_band': '距離帯', 'roi_coeff': 'ROI係数'})
                    fig.update_layout(**plotly_theme(), height=280, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(dist_roi, use_container_width=True, hide_index=True)
    else:
        st.info("条件別ROIデータなし")

    # ── Knowledge Base ─────────────────────────────────
    st.markdown("<div class='sec-head'>知識ベース</div>", unsafe_allow_html=True)
    kb = load_knowledge_base()
    if kb and not kb.empty:
        col_kb = st.columns([1, 2, 1])
        with col_kb[0]:
            cat_filter = st.multiselect(
                "カテゴリ",
                kb['category'].unique() if 'category' in kb.columns else [],
                default=kb['category'].unique().tolist()[:3] if 'category' in kb.columns else []
            )
        with col_kb[1]:
            conf_slider = st.slider("信頼度", 0.0, 1.0, (0.5, 1.0))
        with col_kb[2]:
            st.write("")

        filtered_kb = kb.copy()
        if 'category' in filtered_kb.columns and cat_filter:
            filtered_kb = filtered_kb[filtered_kb['category'].isin(cat_filter)]
        if 'confidence' in filtered_kb.columns:
            filtered_kb = filtered_kb[
                (filtered_kb['confidence'] >= conf_slider[0]) &
                (filtered_kb['confidence'] <= conf_slider[1])
            ]

        if not filtered_kb.empty:
            show_cols = [c for c in ['insight', 'category', 'confidence', 'last_updated', 'frequency']
                        if c in filtered_kb.columns]
            st.dataframe(
                filtered_kb[show_cols].sort_values('confidence', ascending=False),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("該当する知識なし")
    else:
        st.info("知識ベースなし — `knowledge_curator_41.py` を実行してください")

    # ── ROI Trend by Category ──────────────────────────
    tracker = load_roi_tracker()
    if not tracker.empty and 'category' in tracker.columns:
        st.markdown("<div class='sec-head'>カテゴリ別 ROI推移</div>", unsafe_allow_html=True)
        tracker_copy = tracker.copy()
        if 'date' in tracker_copy.columns:
            tracker_copy['date'] = pd.to_datetime(tracker_copy['date'])
            tracker_copy['month'] = tracker_copy['date'].dt.to_period('M')
            monthly = tracker_copy.groupby(['month', 'category']).apply(lambda g: pd.Series({
                'roi': g['return_amount'].sum() / g['bet_amount'].sum() * 100
                if g['bet_amount'].sum() > 0 else 0,
                'count': len(g)
            })).reset_index()

            if PLOTLY and not monthly.empty:
                fig = px.line(monthly, x='month', y='roi', color='category',
                             markers=True, title="カテゴリ別月次ROI推移")
                fig.add_hline(y=100, line_dash='dash', line_color='#8b949e')
                fig.update_layout(**plotly_theme(), height=280)
                st.plotly_chart(fig, use_container_width=True)
