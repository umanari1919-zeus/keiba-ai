"""
Page: Portfolio & Bankroll Management
"""
import streamlit as st
import pandas as pd
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    PLOTLY = False

from components import kpi_card
from utils.data_loader import load_bankroll, load_bankroll_simulation, load_monte_carlo
from utils.theme import plotly_theme


def render():
    """Render the portfolio/bankroll page."""
    st.markdown('<div class="page-title">💰 資金管理</div>', unsafe_allow_html=True)

    bk = load_bankroll()
    cur = bk['current']
    ini = bk['initial']
    peak = bk['peak']
    pnl = cur - ini
    dd_cur = (peak - cur) / peak * 100 if peak > 0 else 0
    kelly_mult = 1.0 if dd_cur < 10 else 0.5 if dd_cur < 20 else 0.25 if dd_cur < 30 else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("現在資金", f"{cur:,.0f}円",
                 "#3fb950" if pnl >= 0 else "#f85149")
    with c2:
        kpi_card("ピーク資金", f"{peak:,.0f}円", "#58a6ff")
    with c3:
        kpi_card("累計損益",
                 f"{'+'if pnl>=0 else ''}{pnl:,.0f}円",
                 "#3fb950" if pnl >= 0 else "#f85149")
    with c4:
        kpi_card("ドローダウン", f"{dd_cur:.1f}%",
                 "#3fb950" if dd_cur < 10 else "#e3b341" if dd_cur < 20 else "#f85149")
    with c5:
        kpi_card("ベット乗数", f"{kelly_mult:.2f}x",
                 "#3fb950" if kelly_mult == 1 else "#e3b341" if kelly_mult > 0 else "#f85149",
                 delta=f"Kelly実効: {0.10*kelly_mult:.3f}")

    col_l, col_r = st.columns([2, 1], gap="large")

    with col_l:
        hist = bk.get('history', [])
        if hist:
            st.markdown("<div class='sec-head'>資金推移</div>", unsafe_allow_html=True)
            hdf = pd.DataFrame(hist)
            date_col = 'date' if 'date' in hdf.columns else 'month'
            balance_col = 'bankroll_after' if 'bankroll_after' in hdf.columns else 'balance'
            hdf[date_col] = pd.to_datetime(hdf[date_col])
            hdf = hdf.sort_values(date_col)

            if PLOTLY:
                marker_color = (
                    hdf['hit'].map({1: '#3fb950', 0: '#f85149'})
                    if 'hit' in hdf.columns else '#58a6ff'
                )
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=hdf[date_col], y=hdf[balance_col],
                    mode='lines+markers', name='残高',
                    line=dict(color='#58a6ff', width=2),
                    marker=dict(color=marker_color, size=6),
                    fill='tozeroy', fillcolor='rgba(88,166,255,0.05)',
                    hovertemplate='%{x|%Y-%m}<br>%{y:,.0f}円<extra></extra>'
                ))
                fig.add_hline(y=ini, line_dash='dash', line_color='#8b949e', annotation_text='初期資金')
                fig.update_layout(**plotly_theme(), height=280, yaxis_title='残高(円)')
                st.plotly_chart(fig, use_container_width=True)

                peak_s = hdf[balance_col].cummax()
                dd_s = (hdf[balance_col] - peak_s) / peak_s * 100
                fig2 = px.area(x=hdf[date_col], y=dd_s,
                               title="ドローダウン推移(%)",
                               color_discrete_sequence=['#f85149'])
                fig2.update_layout(**plotly_theme(), height=180)
                st.plotly_chart(fig2, use_container_width=True)

    with col_r:
        bk_sim = load_bankroll_simulation()
        if bk_sim and bk_sim.get('history_sample'):
            st.markdown("<div class='sec-head'>500レース成長シミュレーション</div>",
                        unsafe_allow_html=True)
            st.metric("最終資金", f"{bk_sim['final']:,.0f}円", f"{bk_sim['growth_rate']:+.1f}%")
            st.metric("最大DD", f"{bk_sim['max_drawdown']*100:.1f}%")
            st.metric("ピーク", f"{bk_sim['peak']:,.0f}円")

        mc = load_monte_carlo()
        if mc:
            st.markdown("<div class='sec-head'>モンテカルロ リスク</div>",
                        unsafe_allow_html=True)
            rows = []
            for key, r in mc.items():
                frac = key.replace('frac_', '').replace('pct', '')
                rows.append({
                    'ベット率': f"{frac}%",
                    '破産確率': f"{r['ruin_rate']*100:.1f}%",
                    '利益確率': f"{r['profit_prob']*100:.1f}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
