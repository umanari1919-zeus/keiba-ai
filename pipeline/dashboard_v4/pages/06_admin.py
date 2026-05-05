"""
👨‍💼 Admin — 管理画面

パイプライン制御・ジョブ実行・ログ監視・エージェント統計を表示。
"""
import streamlit as st
from datetime import datetime
from typing import Optional
from utils.api_client import APIClient
from utils.theme import apply_theme

# テーマ適用
apply_theme()

st.set_page_config(
    page_title="Admin",
    page_icon="👨‍💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("👨‍💼 Administration Console")
st.markdown("パイプライン制御・ジョブ管理・ログ監視・統計")

# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["🚀 Pipeline Control", "⏰ Jobs", "📜 Logs", "📊 Agent Stats"])

# ── TAB 1: Pipeline Control ────────────────────────────────────────
with tabs[0]:
    st.subheader("🚀 Pipeline Execution")

    # パイプラインパターン選択
    col1, col2 = st.columns([2, 1])
    with col1:
        pattern = st.selectbox(
            "Select Pipeline Pattern",
            ["v2", "morning", "weekly", "results"],
            help="v2: 日次DAG, morning: 朝モード, weekly: 週次, results: 夕方結果同期",
        )
    with col2:
        if st.button("▶️ Run Pipeline", use_container_width=True):
            try:
                with st.spinner(f"Starting pipeline ({pattern})..."):
                    trace_id = APIClient.run_pipeline(pattern=pattern)
                st.success(f"✅ Pipeline started")
                st.info(f"**Trace ID:** `{trace_id}`")
                st.session_state.last_trace_id = trace_id
            except RuntimeError as e:
                st.error(f"❌ Failed to start pipeline: {e}")

    st.markdown("---")

    # 実行中のパイプライン監視
    st.subheader("📊 Pipeline Monitoring")

    if "last_trace_id" in st.session_state:
        trace_id = st.session_state.last_trace_id
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.write(f"**Trace ID:** `{trace_id}`")

        try:
            status = APIClient.get_pipeline_status(trace_id)

            # ステータス表示
            if status["status"] == "running":
                st.info(f"🔄 **Status:** Running ({status['elapsed_seconds']:.1f}s elapsed)")
            elif status["status"] == "completed":
                st.success(
                    f"✅ **Status:** Completed ({status['elapsed_seconds']:.1f}s)"
                )
            elif status["status"] == "failed":
                st.error(
                    f"❌ **Status:** Failed (Exit Code: {status['exit_code']})"
                )
            else:
                st.warning(f"⚠️ **Status:** {status['status']}")

            # ログ表示
            if st.checkbox("Show logs", value=True):
                try:
                    logs = APIClient.get_pipeline_log(trace_id, tail=50)
                    if logs:
                        st.text_area(
                            "Logs (last 50 lines)",
                            value="\n".join(logs),
                            height=300,
                            disabled=True,
                        )
                    else:
                        st.info("No logs available yet")
                except RuntimeError as e:
                    st.warning(f"Failed to load logs: {e}")

            # キャンセルボタン
            with col2:
                if status["status"] == "running":
                    if st.button("⏹️ Cancel", use_container_width=True):
                        try:
                            result = APIClient.cancel_pipeline(trace_id)
                            st.success(f"✅ {result['message']}")
                            st.rerun()
                        except RuntimeError as e:
                            st.error(f"❌ Cancel failed: {e}")

        except RuntimeError as e:
            st.warning(f"Failed to load status: {e}")

    st.markdown("---")

    # 実行履歴
    st.subheader("📋 Execution History")
    try:
        history = APIClient.get_pipeline_history(limit=20)
        if history:
            # テーブル表示
            display_data = []
            for item in history:
                display_data.append({
                    "Trace ID": item["trace_id"][:20] + "..." if len(item["trace_id"]) > 20 else item["trace_id"],
                    "Pattern": item["pattern"],
                    "Status": item["status"],
                    "Duration (s)": f"{item['duration_seconds']:.1f}" if item["duration_seconds"] else "—",
                    "Exit Code": item["exit_code"] or "—",
                })
            st.dataframe(display_data, use_container_width=True)
        else:
            st.info("No execution history available")
    except RuntimeError as e:
        st.error(f"Failed to load history: {e}")


# ── TAB 2: Jobs ────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("⏰ Scheduler Jobs")

    try:
        jobs = APIClient.get_jobs()

        if jobs:
            # ジョブテーブル
            display_jobs = []
            for job in jobs:
                display_jobs.append({
                    "Name": job["name"],
                    "Next Run": job["next_run"][:19] if job["next_run"] else "—",
                    "Last Run": job["last_run"][:19] if job["last_run"] else "Never",
                    "Interval (h)": f"{job.get('interval_seconds', 0) // 3600}" if job.get("interval_seconds") else "—",
                })

            st.dataframe(display_jobs, use_container_width=True)

            st.markdown("---")
            st.subheader("🎯 Trigger Job Manually")

            selected_job = st.selectbox(
                "Select job to trigger",
                [j["name"] for j in jobs],
            )

            if st.button("▶️ Trigger Job", use_container_width=True):
                try:
                    with st.spinner(f"Triggering {selected_job}..."):
                        result = APIClient.trigger_job(selected_job)
                    st.success(f"✅ {result['message']}")
                except RuntimeError as e:
                    st.error(f"❌ Trigger failed: {e}")

        else:
            st.info("No scheduled jobs available")
    except RuntimeError as e:
        st.error(f"Failed to load jobs: {e}")


# ── TAB 3: Logs ────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("📜 Log Search")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_pattern = st.text_input(
            "Search pattern (trace_id or keyword)",
            placeholder="e.g., run_20260505, ERROR",
        )

    with col2:
        limit = st.number_input(
            "Limit",
            min_value=10,
            max_value=1000,
            value=100,
            step=10,
        )

    with col3:
        if st.button("🔍 Search", use_container_width=True):
            st.session_state.search_logs = True

    if st.session_state.get("search_logs"):
        try:
            with st.spinner("Searching logs..."):
                logs_result = APIClient.search_logs(
                    pattern=search_pattern if search_pattern else None,
                    limit=limit,
                )

            if logs_result["logs"]:
                st.success(f"Found {len(logs_result['logs'])} entries")

                # ログ表示
                log_text = "\n".join(
                    [f"[{log['file']}] {log['line']}" for log in logs_result["logs"]]
                )
                st.text_area(
                    "Search Results",
                    value=log_text,
                    height=400,
                    disabled=True,
                )
            else:
                st.info("No logs found")
        except RuntimeError as e:
            st.error(f"Search failed: {e}")


# ── TAB 4: Agent Stats ─────────────────────────────────────────────
with tabs[3]:
    st.subheader("📊 Agent Execution Statistics")

    try:
        agents = APIClient.get_agent_stats()

        if agents:
            display_agents = []
            for agent in agents:
                display_agents.append({
                    "Agent": agent["agent_name"],
                    "Total Runs": agent["total_runs"],
                    "Success": agent["success_count"],
                    "Errors": agent["error_count"],
                    "Avg Duration (s)": f"{agent['avg_duration_seconds']:.1f}",
                    "Last Run": agent["last_run"][:19] if agent["last_run"] else "Never",
                })

            st.dataframe(display_agents, use_container_width=True)

            # エージェント詳細
            st.markdown("---")
            st.subheader("🔍 Agent Details")

            selected_agent = st.selectbox(
                "Select agent",
                [a["agent_name"] for a in agents],
            )

            try:
                detail_stats = APIClient.get_agent_detail_stats(selected_agent)
                st.json(detail_stats)
            except RuntimeError as e:
                st.warning(f"Failed to load details: {e}")

        else:
            st.info("No agent statistics available")
    except RuntimeError as e:
        st.error(f"Failed to load agent stats: {e}")

st.markdown("---")

# ── APIサーバーステータス ──────────────────────────────────────────
st.subheader("🔗 API Server Status")

try:
    response = APIClient._make_request("GET", "/health")
    if response.get("status") == "ok":
        st.success("✅ FastAPI server is running (http://localhost:8000)")
except:
    st.error("❌ FastAPI server is not responding. Start with: `uvicorn api.main:app --reload`")
