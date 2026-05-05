"""
🧪 Backtest — ウォークフォワード検証・パラメータグリッド・条件別分析

時系列OOS検証結果、EV グリッドサーチ、会場×距離×季節 係数分析。
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
    page_title="Backtest",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧪 Walk-Forward Validation")
st.markdown("時系列OOS検証、パラメータグリッド分析、条件別係数最適化")

# ── データ読み込み ────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_backtest_results():
    """バックテスト結果を読み込み"""
    try:
        backtest_path = Path("data") / "backtest_summary.json"
        if backtest_path.exists():
            with open(backtest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=600)
def load_walkforward_results():
    """ウォークフォワード検証結果を読み込み"""
    try:
        wf_path = Path("data") / "walkforward_result.json"
        if wf_path.exists():
            with open(wf_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


@st.cache_data(ttl=600)
def load_condition_coefficients():
    """条件別係数を読み込み"""
    try:
        cond_path = Path("data") / "condition_coefficients.json"
        if cond_path.exists():
            with open(cond_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except:
        return {}


# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["📊 Walk-Forward Results", "🔍 Parameter Grid", "🎯 Condition Analysis", "📈 Backtest Metrics"])

# ── TAB 1: Walk-Forward Results ────────────────────────────────────────
with tabs[0]:
    st.subheader("📊 Walk-Forward Validation (Time-Series OOS)")

    wf_results = load_walkforward_results()

    if wf_results:
        st.markdown("""
        **ウォークフォワード検証**: 時系列データで、過去データで学習 → 未来データで検証を繰り返す。
        - **Purge Width**: 学習期間と検証期間の間隔（データリーク防止）
        - **OOS Performance**: Out-of-Sample 検証セット上での成績（最も信頼性が高い）
        """)

        # 年別成績集計
        yearly_results = wf_results.get("yearly", [])

        if yearly_results:
            yearly_df = pd.DataFrame(yearly_results)

            # ROI 推移グラフ
            if "year" in yearly_df.columns and "roi" in yearly_df.columns:
                fig = go.Figure()

                fig.add_trace(go.Scatter(
                    x=yearly_df["year"],
                    y=yearly_df["roi"],
                    mode='lines+markers',
                    name='ROI (%)',
                    line=dict(color='#2E86AB', width=2),
                    marker=dict(size=10),
                    fill='tozeroy',
                    fillcolor='rgba(46, 134, 171, 0.2)',
                ))

                fig.update_layout(
                    title='Walk-Forward ROI by Year',
                    xaxis_title='Year',
                    yaxis_title='ROI (%)',
                    hovermode='x unified',
                    template='plotly_dark',
                    height=400,
                )

                st.plotly_chart(fig, use_container_width=True)

            # 年別統計テーブル
            display_cols = ['year', 'roi', 'hit_rate', 'max_dd', 'sharpe', 'profit_factor']
            available_cols = [col for col in display_cols if col in yearly_df.columns]

            if available_cols:
                display_df = yearly_df[available_cols].copy()

                # フォーマッティング
                if 'roi' in display_df.columns:
                    display_df['roi'] = display_df['roi'].apply(lambda x: f"{x:.1f}%")
                if 'hit_rate' in display_df.columns:
                    display_df['hit_rate'] = display_df['hit_rate'].apply(lambda x: f"{x:.1f}%")
                if 'max_dd' in display_df.columns:
                    display_df['max_dd'] = display_df['max_dd'].apply(lambda x: f"{x:.1f}%")
                if 'sharpe' in display_df.columns:
                    display_df['sharpe'] = display_df['sharpe'].apply(lambda x: f"{x:.2f}")
                if 'profit_factor' in display_df.columns:
                    display_df['profit_factor'] = display_df['profit_factor'].apply(lambda x: f"{x:.2f}")

                st.dataframe(display_df, use_container_width=True)

                # サマリー統計
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    avg_roi = yearly_df.get('roi', [0]).mean() if 'roi' in yearly_df.columns else 0
                    st.metric("平均 ROI", f"{avg_roi:.1f}%")

                with col2:
                    avg_hit = yearly_df.get('hit_rate', [0]).mean() if 'hit_rate' in yearly_df.columns else 0
                    st.metric("平均的中率", f"{avg_hit:.1f}%")

                with col3:
                    max_dd = yearly_df.get('max_dd', [0]).max() if 'max_dd' in yearly_df.columns else 0
                    st.metric("最大DD", f"{max_dd:.1f}%", delta_color="inverse")

                with col4:
                    profit_factor = yearly_df.get('profit_factor', [0]).mean() if 'profit_factor' in yearly_df.columns else 0
                    st.metric("Profit Factor", f"{profit_factor:.2f}")

        else:
            st.info("Walk-forward results not available")

    else:
        st.info("Backtest data not available. Run backtest_walkforward_35.py to generate results.")

# ── TAB 2: Parameter Grid Search ───────────────────────────────────────
with tabs[1]:
    st.subheader("🔍 Parameter Grid Search Heatmap")

    st.markdown("""
    **EV Threshold × Kelly Fraction**: グリッドサーチで各パラメータ組み合わせの ROI を可視化。
    最適値は赤いホットスポット（高ROI）の位置。
    """)

    backtest_results = load_backtest_results()

    if backtest_results:
        grid_search = backtest_results.get("parameter_grid", {})

        if grid_search:
            # EV Threshold と Kelly Fraction のグリッド作成
            ev_thresholds = sorted(set(float(key.split("_")[0]) for key in grid_search.keys() if "_" in key))
            kelly_fractions = sorted(set(float(key.split("_")[1]) for key in grid_search.keys() if "_" in key))

            # ROI マトリックス
            roi_matrix = np.zeros((len(kelly_fractions), len(ev_thresholds)))

            for i, kf in enumerate(kelly_fractions):
                for j, ev in enumerate(ev_thresholds):
                    key = f"{ev}_{kf}"
                    roi_matrix[i, j] = grid_search.get(key, {}).get("roi", 0)

            # ヒートマップ
            fig = go.Figure(data=go.Heatmap(
                z=roi_matrix,
                x=ev_thresholds,
                y=kelly_fractions,
                colorscale='RdYlGn',
                hovertemplate='<b>EV: %{x:.2f} | Kelly: %{y:.2f}</b><br>ROI: %{z:.1f}%<extra></extra>',
            ))

            fig.update_layout(
                title='Parameter Grid Search (ROI %)',
                xaxis_title='EV Threshold',
                yaxis_title='Kelly Fraction',
                height=500,
                template='plotly_dark',
            )

            st.plotly_chart(fig, use_container_width=True)

            # ベストパラメータ表示
            best_key = max(grid_search.items(), key=lambda x: x[1].get("roi", 0))[0]
            best_result = grid_search[best_key]

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Best EV Threshold", f"{best_result.get('ev_threshold', 0):.2f}")

            with col2:
                st.metric("Best Kelly Fraction", f"{best_result.get('kelly_fraction', 0):.3f}")

            with col3:
                st.metric("Best ROI", f"{best_result.get('roi', 0):.1f}%")

        else:
            st.info("Parameter grid search results not available")

    else:
        st.info("Backtest results not available")

# ── TAB 3: Condition Analysis ──────────────────────────────────────────
with tabs[2]:
    st.subheader("🎯 Performance by Condition (Venue × Distance × Season)")

    cond_coeff = load_condition_coefficients()

    if cond_coeff:
        # 会場別分析
        st.markdown("**会場別ROI係数** (基準=1.0):")

        venue_data = cond_coeff.get("venue", {})

        if venue_data:
            venue_df = pd.DataFrame(list(venue_data.items()), columns=['Venue', 'Coefficient'])
            venue_df = venue_df.sort_values('Coefficient', ascending=False)

            fig_venue = px.bar(
                venue_df,
                x='Venue',
                y='Coefficient',
                title='ROI Coefficient by Venue',
                color='Coefficient',
                color_continuous_scale='RdYlGn',
                range_color=[0.5, 1.5],
            )

            st.plotly_chart(fig_venue, use_container_width=True)

        # 距離別分析
        st.markdown("**距離別ROI係数** (基準=1.0):")

        distance_data = cond_coeff.get("distance", {})

        if distance_data:
            distance_df = pd.DataFrame(list(distance_data.items()), columns=['Distance (m)', 'Coefficient'])
            distance_df['Distance (m)'] = distance_df['Distance (m)'].astype(int)
            distance_df = distance_df.sort_values('Distance (m)')

            fig_distance = px.line(
                distance_df,
                x='Distance (m)',
                y='Coefficient',
                title='ROI Coefficient by Distance',
                markers=True,
            )

            st.plotly_chart(fig_distance, use_container_width=True)

        # 季節別分析
        st.markdown("**季節別ROI係数** (基準=1.0):")

        season_data = cond_coeff.get("season", {})

        if season_data:
            season_df = pd.DataFrame(list(season_data.items()), columns=['Season', 'Coefficient'])
            season_order = ['Spring', 'Summer', 'Autumn', 'Winter']
            season_df['Season'] = pd.Categorical(season_df['Season'], categories=season_order, ordered=True)
            season_df = season_df.sort_values('Season')

            fig_season = px.bar(
                season_df,
                x='Season',
                y='Coefficient',
                title='ROI Coefficient by Season',
                color='Coefficient',
                color_continuous_scale='RdYlGn',
                range_color=[0.5, 1.5],
            )

            st.plotly_chart(fig_season, use_container_width=True)

    else:
        st.info("Condition coefficient data not available. Run condition_adjuster_34.py to generate.")

# ── TAB 4: Backtest Metrics ────────────────────────────────────────────
with tabs[3]:
    st.subheader("📈 Comprehensive Backtest Metrics")

    backtest_results = load_backtest_results()

    if backtest_results:
        metrics = backtest_results.get("overall_metrics", {})

        if metrics:
            # KPI メトリクス
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "Total Trades",
                    metrics.get("total_trades", 0),
                    delta=f"{metrics.get('winning_trades', 0)} wins"
                )

            with col2:
                hit_rate = metrics.get("hit_rate", 0)
                st.metric("Hit Rate", f"{hit_rate:.1f}%")

            with col3:
                avg_win = metrics.get("avg_win", 0)
                avg_loss = metrics.get("avg_loss", 0)
                profit_factor = avg_win / abs(avg_loss) if avg_loss != 0 else 0
                st.metric("Profit Factor", f"{profit_factor:.2f}", delta="ベター: >1.5")

            with col4:
                sharpe = metrics.get("sharpe_ratio", 0)
                st.metric("Sharpe Ratio", f"{sharpe:.2f}", delta="ベター: >1.0")

            st.markdown("---")

            # リスク指標
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                max_dd = metrics.get("max_drawdown", 0)
                st.metric("Max Drawdown", f"{max_dd:.1f}%", delta_color="inverse")

            with col2:
                avg_dd = metrics.get("avg_drawdown", 0)
                st.metric("Avg Drawdown", f"{avg_dd:.1f}%", delta_color="inverse")

            with col3:
                dd_recovery = metrics.get("drawdown_recovery_days", 0)
                st.metric("Avg DD Recovery", f"{dd_recovery:.0f} days")

            with col4:
                calmar = metrics.get("calmar_ratio", 0)
                st.metric("Calmar Ratio", f"{calmar:.2f}", delta="ベター: >1.0")

            st.markdown("---")

            # バックテスト結果サマリー
            st.subheader("Backtest Summary")

            summary_text = f"""
            ### 期間
            - 開始日: {metrics.get('start_date', 'N/A')}
            - 終了日: {metrics.get('end_date', 'N/A')}
            - 期間: {metrics.get('total_days', 0)} days

            ### 成績
            - 総勝数: {metrics.get('winning_trades', 0)} / {metrics.get('total_trades', 0)}
            - 平均利益: ¥{metrics.get('avg_win', 0):,.0f}
            - 平均損失: ¥{metrics.get('avg_loss', 0):,.0f}
            - 期待値: ¥{metrics.get('expected_value', 0):,.0f}

            ### リスク
            - 最大ドローダウン: {metrics.get('max_drawdown', 0):.1f}%
            - バックテスト通過: {"✅ Pass" if metrics.get('pass_backtest', False) else "❌ Fail"}
            """

            st.markdown(summary_text)

        else:
            st.info("Backtest metrics not available")

    else:
        st.info("Backtest results not available")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    if st.button("📥 Download Backtest Report", use_container_width=True):
        backtest_results = load_backtest_results()
        if backtest_results:
            st.download_button(
                label="Download JSON",
                data=json.dumps(backtest_results, indent=2, ensure_ascii=False),
                file_name=f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

with col2:
    if st.button("🔄 Run New Backtest", use_container_width=True):
        st.info("Triggering backtest pipeline...")
        try:
            trace_id = APIClient.run_pipeline(pattern="v2-weekly")
            st.success(f"✅ Backtest started: `{trace_id}`")
        except Exception as e:
            st.error(f"❌ Error: {e}")

st.info("""
💡 **バックテスト解釈ポイント**

- **ウォークフォワード**: OOS 検証が最も信頼性高い（過度なフィッティング防止）
- **パラメータグリッド**: 赤いホットスポットが最適パラメータ（通常グローバル最適値）
- **条件別係数**: 会場・距離・季節ごとの成績ばらつきを定量化
- **Sharpe/Calmar**: リスク調整後リターンの指標（高いほど良い）
- **Profit Factor**: >1.5 なら汎化性能良好、>2.0 なら非常に優秀
""")
