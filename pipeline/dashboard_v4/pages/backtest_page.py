"""
Page: Backtest & Walk-Forward Validation
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
    load_walkforward, load_walkforward_folds, load_backtest_grid,
    load_ticket_recommendations, load_race_ranking
)
from utils.formatters import fmt_race
from utils.theme import plotly_theme


def render():
    """Render the backtest page."""
    st.markdown('<div class="page-title">🔄 バックテスト</div>', unsafe_allow_html=True)

    wf = load_walkforward()
    folds_df = load_walkforward_folds()
    grid_df = load_backtest_grid()

    if wf:
        v = wf.get('verdict', '')
        cls = 'box-ok' if '良好' in v else 'box-warn' if '普通' in v else 'box-err'
        st.markdown(f"<div class='{cls}' style='margin-bottom:16px'>{v}</div>",
                    unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("平均ROI", f"{wf.get('avg_roi', 0):+.1f}%", "#3fb950")
        with c2:
            kpi_card("平均的中率", f"{wf.get('avg_hit_rate', 0):.1f}%", "#e3b341")
        with c3:
            avg_dd = wf.get('avg_max_dd', 0)
            kpi_card("平均最大DD", f"{avg_dd:.1f}%",
                     "#3fb950" if avg_dd < 30 else "#e3b341" if avg_dd < 50 else "#f85149")
        with c4:
            n_folds = len(wf.get('folds', []))
            n_pos = wf.get('n_positive', 0)
            kpi_card("プラス期間", f"{n_pos}/{n_folds}", "#58a6ff")

        col_l, col_r = st.columns([2, 1], gap="large")

        with col_l:
            if not folds_df.empty:
                st.markdown("<div class='sec-head'>検証期間の成績</div>", unsafe_allow_html=True)
                show = [c for c in ['test_year', 'roi', 'hit_rate', 'max_dd', 'n_bets']
                        if c in folds_df.columns]
                st.dataframe(
                    folds_df[show].style.format({
                        'roi': '{:+.1f}%', 'hit_rate': '{:.1f}%',
                        'max_dd': '{:.1f}%', 'n_bets': '{:,}'
                    }),
                    use_container_width=True, hide_index=True
                )
                if PLOTLY and 'roi' in folds_df.columns:
                    fig = px.bar(folds_df, x='test_year', y='roi',
                                 title="年別 ROI（検証期間）",
                                 color='roi',
                                 color_continuous_scale=['#f85149', '#3fb950'])
                    fig.add_hline(y=0, line_dash='dash', line_color='#8b949e')
                    fig.update_layout(**plotly_theme(), height=280, coloraxis_showscale=False)
                    st.plotly_chart(fig, use_container_width=True)

        with col_r:
            if not grid_df.empty:
                st.markdown("<div class='sec-head'>パラメータ最適解</div>",
                            unsafe_allow_html=True)
                top_grid = (grid_df
                            .replace([np.inf, -np.inf], np.nan)
                            .dropna()
                            .head(8))
                show = [c for c in ['ev_threshold', 'kelly_fraction', 'roi']
                        if c in top_grid.columns]
                st.dataframe(top_grid[show], use_container_width=True, hide_index=True)

            rs_df = load_race_ranking()
            if not rs_df.empty:
                st.markdown("<div class='sec-head'>推奨レースフィルタ</div>",
                            unsafe_allow_html=True)
                grade_filter = st.multiselect("グレード", ['S', 'A', 'B', 'C'],
                                              default=['S', 'A'])
                filtered = rs_df[rs_df['grade'].isin(grade_filter)].head(20).copy()
                if 'race_code' in filtered.columns:
                    filtered.insert(0, 'レース', filtered['race_code'].apply(fmt_race))
                    filtered = filtered.drop(columns=['race_code'])
                st.dataframe(filtered, use_container_width=True, hide_index=True)

        # ヒートマップ
        if not grid_df.empty and PLOTLY and all(c in grid_df.columns for c in ['ev_threshold', 'kelly_fraction', 'roi']):
            st.markdown("<div class='sec-head'>パラメータ最適化ヒートマップ</div>",
                        unsafe_allow_html=True)
            pivot = (grid_df
                     .pivot_table(values='roi', index='kelly_fraction', columns='ev_threshold')
                     .replace([np.inf, -np.inf], np.nan).fillna(0).clip(-200, 2000))
            fig = go.Figure(go.Heatmap(
                z=pivot.values,
                x=[f"EV {v:.0%}" for v in pivot.columns],
                y=[f"Kelly {v:.0%}" for v in pivot.index],
                colorscale='RdYlGn', zmid=0,
                text=[[f"{v:+.0f}%" for v in row] for row in pivot.values],
                texttemplate="%{text}"
            ))
            fig.update_layout(**plotly_theme(), height=320,
                              title="ROI ヒートマップ (EV閾値 × Kelly係数)")
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("`python pipeline/backtest_walkforward_35.py` を実行してください。")

    # 馬券戦略
    st.markdown("<div class='sec-head'>馬券種別分布 (ticket_optimizer)</div>",
                unsafe_allow_html=True)
    tk_df = load_ticket_recommendations()
    if not tk_df.empty and 'ticket_type' in tk_df.columns:
        col_l2, col_r2 = st.columns([1, 2], gap="large")
        with col_l2:
            dist = tk_df['ticket_type'].value_counts().reset_index()
            dist.columns = ['馬券種', '件数']
            if PLOTLY:
                fig = px.pie(dist, values='件数', names='馬券種',
                             hole=0.45,
                             color_discrete_sequence=['#58a6ff', '#3fb950', '#e3b341', '#f85149', '#bc8cff'])
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(**plotly_theme(), height=260, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
