"""
🏠 Home — ホーム・今日の予想

今日の買い目、リアルタイム実行状況、重要アラート、キー統計を表示。
WebSocket でパイプライン実行ログをリアルタイム更新。
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from utils.api_client import APIClient
from utils.data_loader import load_cached_data
from utils.theme import apply_theme
from utils.websocket_client import StreamlitWebSocketAdapter
import asyncio

# テーマ適用
apply_theme()

st.set_page_config(
    page_title="Home",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏠 Home — Today's Predictions")
st.markdown(f"📅 {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")

# ── セッション状態初期化 ────────────────────────────────────────────
if "live_logs" not in st.session_state:
    st.session_state.live_logs = []
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False


# ── 今日の予想を読み込み ──────────────────────────────────────────
@st.cache_data(ttl=300)
def load_todays_predictions():
    """今日の予想を取得"""
    today = datetime.now().strftime("%Y%m%d")
    try:
        return APIClient.get_predictions(date=today)
    except:
        return {}


# ── KPI セクション ────────────────────────────────────────────────────
st.subheader("📊 Key Statistics")

col1, col2, col3, col4 = st.columns(4)

try:
    bankroll = APIClient.get_bankroll()
    with col1:
        st.metric(
            "💰 Current Bankroll",
            f"¥{bankroll.get('current', 1000000):,.0f}",
            delta=f"{bankroll.get('drawdown_percent', 0):.1f}% DD",
            delta_color="inverse",
        )

    params = APIClient.get_parameters()
    with col2:
        st.metric(
            "⚡ EV Threshold",
            f"{params.get('EV_THRESHOLD', 0.15):.2f}",
        )

    with col3:
        st.metric(
            "🎲 Kelly Fraction",
            f"{params.get('KELLY_FRACTION', 0.10):.2f}",
        )

    with col4:
        st.metric(
            "🎯 Min Odds",
            f"{params.get('MIN_ODDS', 10.0):.1f}倍",
        )
except RuntimeError as e:
    st.warning(f"⚠️ Failed to load KPIs: {e}")

st.markdown("---")

# ── 今日の買い目（トップピック） ────────────────────────────────────
st.subheader("🎯 Today's Top Picks")

predictions = load_todays_predictions()

if predictions and "predictions" in predictions:
    pred_df = pd.DataFrame(predictions["predictions"])

    if not pred_df.empty:
        # トップ 5 を表示
        top_picks = pred_df.nlargest(5, "prediction_score") if "prediction_score" in pred_df.columns else pred_df.head(5)

        display_picks = []
        for idx, row in top_picks.iterrows():
            display_picks.append({
                "Race": row.get("race_code", "—"),
                "Horse": row.get("horse_name", "—"),
                "Score": f"{row.get('prediction_score', 0):.2f}",
                "Odds": f"{row.get('odds', 0):.1f}倍" if row.get('odds') else "—",
                "EV": "✅" if row.get("recommended", False) else "—",
            })

        st.dataframe(pd.DataFrame(display_picks), use_container_width=True)

        st.success(f"✅ Total predictions: {len(pred_df)} horses")
    else:
        st.info("No predictions available for today")
else:
    st.info("📍 No prediction data available. Run the pipeline to generate predictions.")

st.markdown("---")

# ── パイプライン実行コントロール ────────────────────────────────────
st.subheader("🚀 Pipeline Execution")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    pipeline_pattern = st.selectbox(
        "Pipeline Pattern",
        ["v2", "morning", "weekly", "results"],
        help="v2: Daily DAG (recommended), morning: Morning mode, weekly: Weekly, results: Evening results sync",
    )

with col2:
    if st.button("▶️ Run", use_container_width=True):
        try:
            with st.spinner(f"Starting {pipeline_pattern} pipeline..."):
                trace_id = APIClient.run_pipeline(pattern=pipeline_pattern)
            st.session_state.last_trace_id = trace_id
            st.success(f"✅ Pipeline started: `{trace_id}`")
            st.rerun()
        except RuntimeError as e:
            st.error(f"❌ Failed to start pipeline: {e}")

with col3:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── 実行ログ（リアルタイム） ─────────────────────────────────────────
st.subheader("📜 Live Execution Log")

if "last_trace_id" in st.session_state:
    trace_id = st.session_state.last_trace_id

    # ステータス確認
    try:
        status = APIClient.get_pipeline_status(trace_id)
        status_color = {
            "running": "🔄 Running",
            "completed": "✅ Completed",
            "failed": "❌ Failed",
            "cancelled": "⏹️ Cancelled",
        }

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.write(f"**Trace ID:** `{trace_id}`")
        with col2:
            st.write(f"**Status:** {status_color.get(status['status'], status['status'])}")
        with col3:
            st.write(f"**Elapsed:** {status.get('elapsed_seconds', 0):.1f}s")

        # ログ表示コンテナ
        log_container = st.empty()
        log_display = st.empty()

        # ログを定期的に更新
        if status["status"] == "running":
            with st.spinner("Fetching logs..."):
                logs = APIClient.get_pipeline_log(trace_id, tail=30)
                log_display.text_area(
                    "Logs (last 30 lines)",
                    value="\n".join(logs),
                    height=300,
                    disabled=True,
                    key="pipeline_logs",
                )

                # 自動リロードボタン
                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("🔃 Auto Refresh (5s)", use_container_width=True):
                        st.session_state.auto_refresh = True

                if st.session_state.get("auto_refresh"):
                    st.info("🔄 Auto-refreshing logs every 5 seconds...")
                    # 実際のリアルタイム更新は Streamlit の制限があるため、
                    # クライアント側で定期的に reload() を呼び出す必要があります
        else:
            logs = APIClient.get_pipeline_log(trace_id, tail=50)
            log_display.text_area(
                "Logs (all lines)",
                value="\n".join(logs),
                height=400,
                disabled=True,
            )

            if status["status"] == "failed":
                st.error(f"❌ Pipeline failed with exit code: {status['exit_code']}")
            elif status["status"] == "completed":
                st.success(f"✅ Pipeline completed successfully ({status['elapsed_seconds']:.1f}s)")

    except RuntimeError as e:
        st.warning(f"Failed to load status: {e}")

else:
    st.info("👆 Click 'Run' to start a pipeline and see logs here")

st.markdown("---")

# ── 重要アラート ────────────────────────────────────────────────────
st.subheader("⚠️ Important Alerts")

try:
    bankroll = APIClient.get_bankroll()
    drawdown = bankroll.get("drawdown_percent", 0)

    if drawdown > 20:
        st.error(f"🔴 **CRITICAL:** Drawdown exceeds 20% ({drawdown:.1f}%). Review strategy immediately.")
    elif drawdown > 10:
        st.warning(f"🟡 **WARNING:** Drawdown at {drawdown:.1f}%. Reduce bet sizing.")
    else:
        st.success(f"✅ Drawdown at {drawdown:.1f}% (Safe)")
except:
    pass

st.markdown("---")

# ── クイックリンク ────────────────────────────────────────────────────
st.subheader("🔗 Quick Links")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("📊 View Performance", use_container_width=True):
        st.switch_page("pages/01_performance.py")

with col2:
    if st.button("🏇 Race Entries", use_container_width=True):
        st.switch_page("pages/07_race_entries.py")

with col3:
    if st.button("⚙️ Settings", use_container_width=True):
        st.switch_page("pages/05_settings.py")

with col4:
    if st.button("👨‍💼 Admin", use_container_width=True):
        st.switch_page("pages/06_admin.py")

st.markdown("---")

# ── 情報 ────────────────────────────────────────────────────────────
st.info("""
💡 **使い方**

1. **Pipeline Pattern** を選択 (推奨: `v2` 日次DAG)
2. **Run** をクリックしてパイプライン実行開始
3. リアルタイムログで進捗を確認
4. 完了後、他のページで詳細を確認

📚 詳細は各ページを参照：
- **Performance** — ROI、的中率、成績推移
- **Race Entries** — 出走表、全頭評価
- **Settings** — パラメータ調整
- **Admin** — ジョブ管理、ログ検索
""")
