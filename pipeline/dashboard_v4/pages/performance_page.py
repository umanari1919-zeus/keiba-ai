"""
Page: Performance Summary
"""
import streamlit as st
import pandas as pd
import numpy as np
try:
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    PLOTLY = False

from components import kpi_card
from utils.data_loader import load_roi_tracker, load_bankroll
from utils.theme import plotly_theme


def render():
    """Render the performance summary page."""
    st.markdown('<div class="page-title">📊 成績サマリー</div>', unsafe_allow_html=True)

    tracker = load_roi_tracker()
    bk = load_bankroll()
    cur = bk['current']
    ini = bk['initial']
    pnl = cur - ini
    roi_all = cur / ini * 100 if ini > 0 else 100

    now_dt = pd.Timestamp.now()
    if not tracker.empty:
        m_df = tracker[(tracker['date'].dt.year == now_dt.year) &
                       (tracker['date'].dt.month == now_dt.month)]
        m_bet = m_df['bet_amount'].sum()
        m_ret = m_df['return_amount'].sum()
        m_roi = m_ret / m_bet * 100 if m_bet > 0 else 0
        hits = int(tracker['hit'].sum())
        n = len(tracker)
        hr = hits / n * 100 if n > 0 else 0
    else:
        m_roi = hr = 0
        n = hits = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("累計損益",
                 f"{'+'if pnl>=0 else ''}{pnl:,.0f}円",
                 "#3fb950" if pnl >= 0 else "#f85149")
    with c2:
        kpi_card("累計回収率", f"{roi_all:.1f}%",
                 "#3fb950" if roi_all >= 100 else "#f85149",
                 delta=f"初期 {ini:,.0f}円")
    with c3:
        kpi_card(f"{now_dt.month}月 回収率", f"{m_roi:.1f}%",
                 "#3fb950" if m_roi >= 100 else "#f85149")
    with c4:
        kpi_card("累計的中率", f"{hr:.1f}%", "#e3b341",
                 delta=f"{hits}/{n}件")

    if not tracker.empty:
        col_l, col_r = st.columns([2, 1], gap="large")

        with col_l:
            st.markdown("<div class='sec-head'>週次回収率推移</div>", unsafe_allow_html=True)
            tracker_copy = tracker.copy()
            tracker_copy['week'] = tracker_copy['date'].dt.to_period('W').apply(lambda x: x.start_time)
            wkly = tracker_copy.groupby('week').apply(lambda g: pd.Series({
                'roi': g['return_amount'].sum() / g['bet_amount'].sum() * 100
                if g['bet_amount'].sum() > 0 else 0,
                'hits': int(g['hit'].sum()),
                'count': len(g)
            })).reset_index()

            if PLOTLY and not wkly.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=wkly['week'].astype(str), y=wkly['roi'],
                    marker_color=wkly['roi'].apply(lambda r: '#3fb950' if r >= 100 else '#f85149'),
                ))
                fig.add_hline(y=100, line_dash='dash', line_color='#8b949e', annotation_text='100%')
                fig.add_hline(y=115, line_dash='dot', line_color='#3fb950', annotation_text='目標115%')
                fig.update_layout(**plotly_theme(), height=300, showlegend=False, yaxis_title='回収率(%)')
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown("<div class='sec-head'>オッズ帯別成績</div>", unsafe_allow_html=True)
            tc = tracker.copy()
            tc['band'] = pd.cut(tc['odds'],
                                bins=[0, 5, 10, 20, 50, 9999],
                                labels=['〜5倍', '5〜10倍', '10〜20倍', '20〜50倍', '50倍〜'])
            rows = []
            for band, g in tc.groupby('band', observed=True):
                bet = g['bet_amount'].sum()
                ret = g['return_amount'].sum()
                rows.append({
                    'オッズ帯': str(band), '件数': len(g),
                    '的中率': f"{g['hit'].mean()*100:.1f}%",
                    '回収率': f"{ret/bet*100:.1f}%" if bet > 0 else '-',
                    '損益': f"{ret-bet:+,.0f}円",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("記録なし — `roi_tracker_12.py` でベットを記録してください。")
