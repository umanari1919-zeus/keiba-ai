"""
📈 Performance — 成績サマリー・ROI追跡

日次・週次・月次の ROI トレンド、的中率、レース別パフォーマンス、フィルタ機能。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from pathlib import Path
from utils.api_client import APIClient
from utils.data_loader import load_cached_data
from utils.theme import apply_theme

apply_theme()

st.set_page_config(
    page_title="Performance",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Performance Summary")
st.markdown("日次・週次・月次の成績推移、的中率、パフォーマンス分析")

# ── ROI データ読み込み ────────────────────────────────────────────────
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


@st.cache_data(ttl=600)
def get_roi_summary(year: int):
    """年別 ROI サマリーを取得"""
    try:
        return APIClient.get_roi(year=year)
    except:
        return {}


# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["📊 ROI Trend", "🎯 Hit Rate", "💹 Monthly", "🏆 Race Ranking"])

# ── TAB 1: ROI Trend ───────────────────────────────────────────────────
with tabs[0]:
    st.subheader("📈 ROI Trend (Daily/Weekly)")

    roi_df = load_roi_data()

    if not roi_df.empty:
        # 日付カラム特定
        date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)
        roi_col = next((col for col in roi_df.columns if "roi" in col.lower()), None)

        if date_col and roi_col:
            # 数値化
            roi_df[roi_col] = pd.to_numeric(roi_df[roi_col], errors='coerce')

            # 期間選択
            col1, col2 = st.columns([1, 3])
            with col1:
                period = st.selectbox("Period", ["30日", "3ヶ月", "6ヶ月", "全期間"])

            period_days = {"30日": 30, "3ヶ月": 90, "6ヶ月": 180, "全期間": 9999}
            cutoff_date = datetime.now() - timedelta(days=period_days[period])

            # フィルタ
            filtered_df = roi_df[pd.to_datetime(roi_df[date_col], errors='coerce') >= cutoff_date].copy()

            if not filtered_df.empty:
                # ROI 折れ線グラフ
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=filtered_df[date_col],
                    y=filtered_df[roi_col],
                    mode='lines+markers',
                    name='ROI (%)',
                    line=dict(color='#2E86AB', width=2),
                    marker=dict(size=6),
                ))

                # ゼロラインを追加
                fig.add_hline(y=0, line_dash="dash", line_color="red", opacity=0.5)

                fig.update_layout(
                    title=f"ROI Trend ({period})",
                    xaxis_title="Date",
                    yaxis_title="ROI (%)",
                    hovermode='x unified',
                    template='plotly_dark',
                    height=400,
                )

                st.plotly_chart(fig, use_container_width=True)

                # 統計
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    current_roi = filtered_df[roi_col].iloc[-1]
                    st.metric("Current ROI", f"{current_roi:.1f}%")

                with col2:
                    max_roi = filtered_df[roi_col].max()
                    st.metric("Max ROI", f"{max_roi:.1f}%")

                with col3:
                    avg_roi = filtered_df[roi_col].mean()
                    st.metric("Avg ROI", f"{avg_roi:.1f}%")

                with col4:
                    volatility = filtered_df[roi_col].std()
                    st.metric("Volatility (σ)", f"{volatility:.1f}%")
            else:
                st.info("No data for selected period")
        else:
            st.warning("Required columns not found")
    else:
        st.info("No ROI data available. Run the pipeline to generate data.")


# ── TAB 2: Hit Rate ────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("🎯 Hit Rate Analysis")

    roi_df = load_roi_data()

    if not roi_df.empty:
        # 的中率カラム特定
        hit_col = next((col for col in roi_df.columns if "hit" in col.lower() or "的中" in col), None)

        if hit_col:
            hit_df = roi_df.dropna(subset=[hit_col]).copy()
            hit_df[hit_col] = pd.to_numeric(hit_df[hit_col], errors='coerce')

            # 的中率の推移
            date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)

            if date_col:
                fig = px.bar(
                    hit_df,
                    x=date_col,
                    y=hit_col,
                    title="Hit Rate Trend",
                    labels={hit_col: "Hit Rate (%)"},
                )
                st.plotly_chart(fig, use_container_width=True)

                # 統計
                col1, col2, col3 = st.columns(3)
                with col1:
                    avg_hit = hit_df[hit_col].mean()
                    st.metric("Avg Hit Rate", f"{avg_hit:.1f}%")

                with col2:
                    max_hit = hit_df[hit_col].max()
                    st.metric("Best Hit Rate", f"{max_hit:.1f}%")

                with col3:
                    min_hit = hit_df[hit_col].min()
                    st.metric("Worst Hit Rate", f"{min_hit:.1f}%")
        else:
            st.info("Hit rate data not available")
    else:
        st.info("No data available")


# ── TAB 3: Monthly Performance ─────────────────────────────────────────
with tabs[2]:
    st.subheader("📅 Monthly Performance")

    roi_df = load_roi_data()

    if not roi_df.empty:
        date_col = next((col for col in roi_df.columns if "date" in col.lower() or "日付" in col), None)
        roi_col = next((col for col in roi_df.columns if "roi" in col.lower()), None)

        if date_col and roi_col:
            # 月別集計
            roi_df['date'] = pd.to_datetime(roi_df[date_col], errors='coerce')
            roi_df['month'] = roi_df['date'].dt.to_period('M')
            roi_df[roi_col] = pd.to_numeric(roi_df[roi_col], errors='coerce')

            monthly = roi_df.groupby('month')[roi_col].agg(['sum', 'mean', 'count']).reset_index()
            monthly.columns = ['Month', 'Total ROI', 'Avg ROI', 'Days']

            # 月別棒グラフ
            fig = px.bar(
                monthly,
                x='Month',
                y='Total ROI',
                title='Monthly ROI',
                color='Total ROI',
                color_continuous_scale='RdYlGn',
            )
            st.plotly_chart(fig, use_container_width=True)

            # テーブル
            st.dataframe(monthly, use_container_width=True)
        else:
            st.warning("Required columns not found")
    else:
        st.info("No data available")


# ── TAB 4: Race Ranking ────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🏆 Race Performance Ranking")

    try:
        # race_ranking_{year}.csv を読み込み
        year = st.selectbox("Year", [datetime.now().year, datetime.now().year - 1], key="race_year")
        limit = st.slider("Top N", min_value=5, max_value=50, value=20)

        ranking_data = APIClient.get_race_ranking(year=year, limit=limit)

        if "races" in ranking_data and ranking_data["races"]:
            race_df = pd.DataFrame(ranking_data["races"])

            # 主要カラムを抽出
            display_cols = [col for col in race_df.columns if col in [
                "race_code", "race_name", "roi", "hit_rate", "avg_odds", "profit"
            ]]

            if display_cols:
                st.dataframe(race_df[display_cols], use_container_width=True)
            else:
                st.dataframe(race_df.head(limit), use_container_width=True)

            # グラフ
            if "roi" in race_df.columns:
                fig = px.bar(
                    race_df.head(20),
                    x="race_code",
                    y="roi",
                    title="Top 20 Races by ROI",
                    labels={"roi": "ROI (%)"},
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No race ranking data for {year}")
    except RuntimeError as e:
        st.warning(f"Failed to load race ranking: {e}")

st.markdown("---")

st.info("""
💡 **Performance ページ使い方**

- **ROI Trend** — 長期的な成績推移を確認
- **Hit Rate** — 的中率の変化を監視
- **Monthly** — 月別成績で季節性を把握
- **Race Ranking** — どのレースが利益を出しているか分析
""")
