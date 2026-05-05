"""
💰 Portfolio — 資金管理・Kelly基準・ベットサイジング

現在資金、ピーク、ドローダウン、月別推移、Kelly基準シミュレーション、リスク警告。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from pathlib import Path
import json
from utils.api_client import APIClient
from utils.data_loader import load_cached_data
from utils.theme import apply_theme

apply_theme()

st.set_page_config(
    page_title="Portfolio",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("💰 Portfolio Management")
st.markdown("資金推移、Kelly基準シミュレーション、ベットサイジング最適化")

# ── 資金データ読み込み ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_bankroll_data():
    """bankroll.json を読み込み"""
    try:
        bankroll_path = Path("data") / "bankroll.json"
        if bankroll_path.exists():
            with open(bankroll_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=300)
def load_roi_data():
    """ROI トラッカーを読み込み"""
    try:
        csv_path = Path("data") / "roi_tracker.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, on_bad_lines='skip')
        return pd.DataFrame()
    except:
        return pd.DataFrame()


# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["💰 Bankroll", "📊 Monthly Trend", "🎲 Kelly Criterion", "⚠️ Risk Analysis"])

# ── TAB 1: Bankroll Status ─────────────────────────────────────────────
with tabs[0]:
    st.subheader("💰 Bankroll Status")

    bankroll = load_bankroll_data()

    if bankroll:
        col1, col2, col3, col4 = st.columns(4)

        current = bankroll.get("current", 1000000)
        peak = bankroll.get("peak", 1000000)
        initial = bankroll.get("initial", 1000000)
        drawdown_percent = bankroll.get("drawdown_percent", 0)

        with col1:
            st.metric(
                "💵 Current Bankroll",
                f"¥{current:,.0f}",
                delta=f"¥{current - initial:,.0f}" if current != initial else "0",
            )

        with col2:
            st.metric(
                "📈 Peak Bankroll",
                f"¥{peak:,.0f}",
                delta=f"+{((peak - initial) / initial * 100):.1f}%" if initial > 0 else "0%",
            )

        with col3:
            st.metric(
                "⬇️ Max Drawdown",
                f"{drawdown_percent:.1f}%",
                delta_color="inverse",
            )

        with col4:
            roi = ((current - initial) / initial * 100) if initial > 0 else 0
            st.metric(
                "📊 Total ROI",
                f"{roi:.1f}%",
                delta="+" if roi > 0 else "",
            )

        st.markdown("---")

        # 資金推移グラフ
        roi_df = load_roi_data()
        if not roi_df.empty:
            date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)
            bankroll_col = next((col for col in roi_df.columns if "bankroll" in col.lower()), None)

            if date_col:
                # 月別資金推移
                roi_df['date'] = pd.to_datetime(roi_df[date_col], errors='coerce')
                roi_df['month'] = roi_df['date'].dt.to_period('M')

                if bankroll_col:
                    roi_df[bankroll_col] = pd.to_numeric(roi_df[bankroll_col], errors='coerce')
                    monthly = roi_df.groupby('month')[bankroll_col].agg(['first', 'last', 'min', 'max']).reset_index()
                    monthly.columns = ['Month', 'Opening', 'Closing', 'Low', 'High']
                else:
                    # bankroll 列がない場合、ROI から再構築
                    roi_col = next((col for col in roi_df.columns if "roi" in col.lower()), None)
                    if roi_col:
                        roi_df[roi_col] = pd.to_numeric(roi_df[roi_col], errors='coerce')
                        # ROI累積から bankroll を推定
                        roi_df['cumulative_net'] = roi_df[roi_col].cumsum()
                        roi_df['bankroll'] = initial + (roi_df['cumulative_net'] * initial / 100)
                        monthly = roi_df.groupby('month')['bankroll'].agg(['first', 'last', 'min', 'max']).reset_index()
                        monthly.columns = ['Month', 'Opening', 'Closing', 'Low', 'High']
                    else:
                        monthly = pd.DataFrame()

                if not monthly.empty:
                    fig = go.Figure()

                    # Candlestick 風グラフ
                    fig.add_trace(go.Scatter(
                        x=monthly['Month'].astype(str),
                        y=monthly['Closing'],
                        mode='lines+markers',
                        name='月末資金',
                        line=dict(color='#2E86AB', width=2),
                        marker=dict(size=8),
                    ))

                    # 帯グラフ（高値〜安値）
                    fig.add_trace(go.Scatter(
                        x=monthly['Month'].astype(str),
                        y=monthly['High'],
                        mode='lines',
                        name='月間高値',
                        line=dict(color='rgba(46, 134, 171, 0)'),
                        showlegend=False,
                    ))

                    fig.add_trace(go.Scatter(
                        x=monthly['Month'].astype(str),
                        y=monthly['Low'],
                        mode='lines',
                        name='月間安値',
                        line=dict(color='rgba(46, 134, 171, 0)'),
                        fill='tonexty',
                        fillcolor='rgba(46, 134, 171, 0.2)',
                        showlegend=False,
                    ))

                    fig.update_layout(
                        title="Monthly Bankroll Trend",
                        xaxis_title="Month",
                        yaxis_title="Bankroll (¥)",
                        hovermode='x unified',
                        template='plotly_dark',
                        height=400,
                    )

                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Bankroll data not available. Check data/bankroll.json")

# ── TAB 2: Monthly Trend ───────────────────────────────────────────────
with tabs[1]:
    st.subheader("📊 Monthly Net Profit Trend")

    roi_df = load_roi_data()

    if not roi_df.empty:
        date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)
        roi_col = next((col for col in roi_df.columns if "roi" in col.lower()), None)

        if date_col and roi_col:
            roi_df['date'] = pd.to_datetime(roi_df[date_col], errors='coerce')
            roi_df['month'] = roi_df['date'].dt.to_period('M')
            roi_df[roi_col] = pd.to_numeric(roi_df[roi_col], errors='coerce')

            # 月別集計
            monthly = roi_df.groupby('month')[roi_col].agg(['sum', 'mean', 'count', 'std']).reset_index()
            monthly.columns = ['Month', 'Total Net Profit', 'Avg Daily Profit', 'Days', 'Volatility']

            # 月別棒グラフ（色分け）
            colors = ['#2ecc71' if x > 0 else '#e74c3c' for x in monthly['Total Net Profit']]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=monthly['Month'].astype(str),
                y=monthly['Total Net Profit'],
                marker_color=colors,
                name='Net Profit',
                hovertemplate='<b>%{x}</b><br>Net Profit: ¥%{y:,.0f}<extra></extra>',
            ))

            fig.update_layout(
                title='Monthly Net Profit',
                xaxis_title='Month',
                yaxis_title='Net Profit (¥)',
                template='plotly_dark',
                height=400,
                showlegend=False,
            )

            st.plotly_chart(fig, use_container_width=True)

            # 月別統計テーブル
            st.dataframe(
                monthly.assign(**{'Total Net Profit': monthly['Total Net Profit'].apply(lambda x: f"¥{x:,.0f}"),
                                  'Avg Daily Profit': monthly['Avg Daily Profit'].apply(lambda x: f"¥{x:,.0f}"),
                                  'Volatility': monthly['Volatility'].apply(lambda x: f"{x:,.0f}")}),
                use_container_width=True
            )
        else:
            st.warning("Required columns not found")
    else:
        st.info("No data available")

# ── TAB 3: Kelly Criterion ─────────────────────────────────────────────
with tabs[2]:
    st.subheader("🎲 Kelly Criterion & Bet Sizing")

    st.markdown("""
    **Kelly 公式**: f* = (bp - q) / b
    - **b**: オッズ - 1 （例: 10倍オッズなら b=9）
    - **p**: 予想勝率
    - **q**: 1 - p （負ける確率）
    - **f***: 資金に対する最適ベット比率

    **推奨**: Kelly × 0.10 = **フラクショナルKelly（保守的）**
    """)

    # Kelly シミュレーター
    col1, col2, col3 = st.columns(3)

    with col1:
        bankroll_sim = st.number_input("資金", value=1000000, step=100000, min_value=100000)

    with col2:
        win_rate = st.slider("予想勝率 (%)", min_value=1, max_value=100, value=15, step=1)

    with col3:
        odds = st.number_input("オッズ (倍)", value=10.0, step=0.5, min_value=1.0)

    # Kelly 計算
    p = win_rate / 100.0
    q = 1 - p
    b = odds - 1

    kelly_fraction = (b * p - q) / b if b > 0 else 0
    fractional_kelly = kelly_fraction * 0.10  # フラクショナル Kelly

    optimal_bet = bankroll_sim * fractional_kelly
    expected_value = optimal_bet * ((odds - 1) * p - q)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Kelly %", f"{kelly_fraction*100:.2f}%")

    with col2:
        st.metric("Fractional Kelly (10%)", f"{fractional_kelly*100:.2f}%")

    with col3:
        st.metric("推奨ベット額", f"¥{optimal_bet:,.0f}")

    with col4:
        st.metric("期待値", f"¥{expected_value:,.0f}", delta=f"{(expected_value/bankroll_sim*100):.2f}%" if bankroll_sim > 0 else "0%")

    st.markdown("---")

    # Kelly カーブ
    win_rates = range(5, 101, 5)
    kelly_values = []

    for wr in win_rates:
        p_temp = wr / 100.0
        q_temp = 1 - p_temp
        kelly_temp = (b * p_temp - q_temp) / b if b > 0 else 0
        kelly_values.append(max(0, kelly_temp * 100))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(win_rates),
        y=kelly_values,
        mode='lines+markers',
        name='Kelly %',
        line=dict(color='#2E86AB', width=2),
        marker=dict(size=6),
    ))

    # Break-even line (勝率で Kelly が 0 になる点)
    breakeven_wr = int(q / (q + b) * 100) if (q + b) > 0 else 0
    fig.add_vline(x=breakeven_wr, line_dash="dash", line_color="red", annotation_text=f"Breakeven: {breakeven_wr}%")

    fig.update_layout(
        title=f"Kelly Criterion Curve (オッズ {odds}倍)",
        xaxis_title="Win Rate (%)",
        yaxis_title="Kelly % (Full)",
        hovermode='x unified',
        template='plotly_dark',
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: Risk Analysis ───────────────────────────────────────────────
with tabs[3]:
    st.subheader("⚠️ Risk Analysis & Drawdown Management")

    bankroll = load_bankroll_data()

    if bankroll:
        drawdown = bankroll.get("drawdown_percent", 0)
        current = bankroll.get("current", 1000000)
        peak = bankroll.get("peak", 1000000)

        # リスク表示
        if drawdown > 30:
            st.error(f"🔴 **CRITICAL**: Drawdown {drawdown:.1f}% 超過！即座に対応が必要です。")
        elif drawdown > 20:
            st.error(f"🔴 **SEVERE**: Drawdown {drawdown:.1f}%. ベット額を大幅削減してください。")
        elif drawdown > 10:
            st.warning(f"🟡 **WARNING**: Drawdown {drawdown:.1f}%. ベット額を削減してください。")
        else:
            st.success(f"✅ Safe: Drawdown {drawdown:.1f}% (安全圏)")

        st.markdown("---")

        # 回復目標
        col1, col2 = st.columns(2)

        with col1:
            st.metric("ピークから現在", f"¥{current - peak:,.0f}", delta=f"{((current-peak)/peak*100):.1f}%")

        with col2:
            recovery_needed = peak - current
            daily_roi = 0.01  # 1% daily gain assumption
            days_to_recover = recovery_needed / (current * daily_roi) if current > 0 and daily_roi > 0 else 999

            st.metric("回復予想日数", f"{int(days_to_recover)}", delta=f"日次ROI {daily_roi*100:.1f}% 仮定")

        st.markdown("---")

        # Drawdown 分布ヒストグラム
        roi_df = load_roi_data()

        if not roi_df.empty:
            date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)
            roi_col = next((col for col in roi_df.columns if "roi" in col.lower()), None)

            if date_col and roi_col:
                roi_df['date'] = pd.to_datetime(roi_df[date_col], errors='coerce')
                roi_df[roi_col] = pd.to_numeric(roi_df[roi_col], errors='coerce')
                roi_df = roi_df.sort_values(date_col)

                # Running Max を計算
                roi_df['running_max'] = roi_df[roi_col].expanding().max()
                roi_df['drawdown'] = ((roi_df[roi_col] - roi_df['running_max']) / roi_df['running_max'] * 100).clip(upper=0)

                fig = px.histogram(
                    roi_df,
                    x='drawdown',
                    nbins=30,
                    title='Drawdown Distribution',
                    labels={'drawdown': 'Drawdown (%)'},
                )

                st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

st.info("""
💡 **資金管理のポイント**

- **Kelly 基準**: 長期的な資金成長の理論値（慎重なら Kelly × 0.10）
- **ドローダウン管理**: 20% 超過で要対応、30% で危機的
- **月別追跡**: 赤字月の原因分析・改善が重要
- **リスク調整**: ボラティリティが高い場合は Kelly をさらに削減
""")
