"""
Page: Home / Today's Predictions
"""
import os
import streamlit as st
import subprocess
from datetime import datetime
from components import kpi_card
from utils.data_loader import (
    load_picks, load_race_ranking, load_odds_snapshot
)
from utils.formatters import fmt_race
from config import BASE_PATH, PYTHON_EXE


def render():
    """Render the home/predictions page."""
    st.markdown('<div class="page-title">🏇 今日の予想</div>', unsafe_allow_html=True)

    picks, picks_date = load_picks()
    today_str = datetime.now().strftime("%Y/%m/%d")
    is_today = picks_date == today_str if picks_date else False

    if not is_today and picks_date:
        st.markdown(
            f"<div class='box-warn'>⚠️ 本日（{today_str}）のデータなし。最新: {picks_date} "
            f"— <code>python run_all.py --skip-train</code> を実行してください。</div>",
            unsafe_allow_html=True
        )

    if picks:
        rs = picks.get('risk_summary', {})
        approved = picks.get('approved_bets', [])
        gen = picks.get('generated_at', '')[:16].replace('T', ' ')
        alloc = rs.get('total_allocated', 0)
        ratio = rs.get('day_ratio', 0) * 100
        mult = rs.get('dd_multiplier', 1)

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            kpi_card("承認レース", f"{rs.get('approved_count', 0)}R", "#58a6ff")
        with c2:
            kpi_card("推奨ベット", f"{len(approved)}件", "#e6edf3")
        with c3:
            kpi_card("総投入予定", f"{alloc:,}円", "#e3b341")
        with c4:
            kpi_card("資金消費率", f"{ratio:.1f}%",
                     "#3fb950" if ratio < 15 else "#f85149")
        with c5:
            kpi_card("DD乗数", f"{mult:.2f}x",
                     "#3fb950" if mult == 1 else "#e3b341" if mult > 0 else "#f85149",
                     delta=f"生成: {gen}")

        col_main, col_side = st.columns([3, 1], gap="large")

        with col_main:
            st.markdown(f"<div class='sec-head'>推奨ベット ({picks_date})</div>",
                        unsafe_allow_html=True)
            for bet in approved:
                ev = bet['expected_value'] * 100
                conf = bet.get('confidence', 0) * 100
                odds = bet['odds']
                ticket = bet.get('ticket_type', '単勝')
                grade = bet.get('condition_grade', 'B')
                blood = bet.get('blood_score', 1.0)
                rv = bet.get('race_value', 0)
                ev_col = "#3fb950" if ev > 0 else "#f85149"
                g_cls = "grade-s" if grade == 'S' else "grade-a" if grade in ('A', 'B') else ""
                st.markdown(f"""
<div class="bet-card {g_cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <strong style="color:#e6edf3;font-size:1.05rem">
        {fmt_race(bet.get('race_code',''))}
        {str(bet['umaban'])+'番 ' if bet.get('umaban') else ''}
        {bet.get('bamei','')}
      </strong>
      &nbsp;
      <span class="badge badge-blue">{ticket}</span>
      <span class="badge badge-gold">{odds:.1f}倍</span>
      <span class="badge {'badge-green' if grade in ('S','A') else 'badge-gray'}">Grade {grade}</span>
    </div>
    <strong style="color:#e3b341;font-size:1.2rem">{bet['kelly_bet']:,}円</strong>
  </div>
  <div style="margin-top:6px;font-size:.82rem;color:#8b949e">
    勝率 {bet['win_probability']*100:.1f}%
    &nbsp;|&nbsp; EV <span style="color:{ev_col}">{ev:+.0f}%</span>
    &nbsp;|&nbsp; 確信度 {conf:.0f}%
    &nbsp;|&nbsp; 血統 {blood:.2f}x
    &nbsp;|&nbsp; レース価値 {rv:.2f}
  </div>
  <div style="margin-top:3px;font-size:.78rem;color:#6e7681">{bet.get('comment','')}</div>
</div>""", unsafe_allow_html=True)

            notes = picks.get('supervisor_notes', '')
            if notes:
                st.markdown(f"<div class='box-ok' style='margin-top:10px'>🧠 Supervisor: {notes}</div>",
                            unsafe_allow_html=True)

            with st.expander("📝 SNS投稿テキスト"):
                st.text(picks.get('post_text', ''))

            logs = picks.get('log', [])
            if logs:
                with st.expander("🔍 エージェントログ"):
                    st.text('\n'.join(logs[-30:]))

        with col_side:
            snap = load_odds_snapshot()
            st.markdown("<div class='sec-head'>オッズシグナル</div>", unsafe_allow_html=True)
            if snap:
                sharp = sum(1 for r in snap.get('races', []) if r.get('signal') == 'SHARP')
                steam = sum(1 for r in snap.get('races', []) if r.get('signal') == 'STEAM')
                drift = sum(1 for r in snap.get('races', []) if r.get('signal') == 'DRIFT')
                st.markdown(f"""
<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <span style="color:#8b949e;font-size:.82rem">SHARP</span>
    <strong style="color:#f85149">{sharp}件</strong>
  </div>
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <span style="color:#8b949e;font-size:.82rem">STEAM</span>
    <strong style="color:#e3b341">{steam}件</strong>
  </div>
  <div style="display:flex;justify-content:space-between">
    <span style="color:#8b949e;font-size:.82rem">DRIFT</span>
    <strong style="color:#58a6ff">{drift}件</strong>
  </div>
</div>""", unsafe_allow_html=True)
                ts = snap.get('timestamp', '')[:16]
                st.caption(f"取得: {ts}")
            else:
                st.markdown("<div class='box-warn' style='font-size:.82rem'>スナップショットなし</div>",
                            unsafe_allow_html=True)

            rs_df = load_race_ranking()
            if not rs_df.empty:
                st.markdown("<div class='sec-head' style='margin-top:20px'>Grade S/A レース</div>",
                            unsafe_allow_html=True)
                top_rs = rs_df[rs_df['grade'].isin(['S', 'A'])].head(8).copy()
                if 'race_code' in top_rs.columns:
                    for _, row in top_rs.iterrows():
                        g = row.get('grade', '')
                        col_g = "#f78166" if g == 'S' else "#3fb950"
                        st.markdown(
                            f'<div style="font-size:.82rem;padding:4px 0;border-bottom:1px solid #21262d">'
                            f'<span style="color:{col_g};font-weight:700">[{g}]</span> '
                            f'{fmt_race(row["race_code"])}</div>',
                            unsafe_allow_html=True
                        )

            st.markdown("<div class='sec-head' style='margin-top:20px'>クイック実行</div>",
                        unsafe_allow_html=True)
            if st.button("▶ パイプライン実行", use_container_width=True):
                with st.spinner("実行中..."):
                    res = subprocess.run(
                        [PYTHON_EXE, "-X", "utf8", os.path.join(BASE_PATH, "run_all.py"), "--skip-train"],
                        capture_output=True, text=True, cwd=BASE_PATH,
                        timeout=600
                    )
                if res.returncode == 0:
                    st.success("完了")
                else:
                    st.error("失敗")
                    st.code(res.stderr[-1500:])

            if st.button("📸 オッズ取得", use_container_width=True):
                with st.spinner("Playwright 実行中..."):
                    res = subprocess.run(
                        [PYTHON_EXE, "-X", "utf8",
                         os.path.join(BASE_PATH, "pipeline", "odds_scraper_36.py")],
                        capture_output=True, text=True, cwd=BASE_PATH,
                        timeout=120
                    )
                if res.returncode == 0:
                    st.success("取得完了")
                else:
                    st.error("取得失敗")

    else:
        st.markdown("""
<div class="box-warn">
  マルチエージェントの出力がありません。<br>
  <code>python run_all.py --skip-train</code> を実行してください。
</div>""", unsafe_allow_html=True)
        rs_df = load_race_ranking()
        if not rs_df.empty:
            st.markdown("<div class='sec-head'>本日の参戦候補 (Grade S/A)</div>",
                        unsafe_allow_html=True)
            top_rs = rs_df[rs_df['grade'].isin(['S', 'A'])].head(12)
            st.dataframe(top_rs, use_container_width=True, hide_index=True)
