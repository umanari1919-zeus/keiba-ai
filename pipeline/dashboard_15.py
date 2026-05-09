"""
うまなり地蔵AI ダッシュボード v3
起動: streamlit run pipeline/dashboard_15.py
"""
import os, sys, json, glob, subprocess
from datetime import datetime
from collections import Counter

import pandas as pd
import numpy as np
import streamlit as st
from pipeline.config import BASE_DIR as BASE

st.set_page_config(
    page_title="🙏 うまなり地蔵AI",
    page_icon="🙏",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    PLOTLY = False

YEAR = datetime.now().year
PYTHON = os.getenv("KEIBA_PYTHON", sys.executable)

# ── レースコード変換 ──────────────────────────────────────────
_JYO = {
    '01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',
    '06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉',
    '30':'門別','35':'盛岡','36':'水沢','42':'浦和','43':'船橋',
    '44':'大井','45':'川崎','46':'金沢','47':'笠松','48':'名古屋',
    '50':'園田','51':'姫路','54':'高知','55':'佐賀','58':'帯広',
}
_KYAKU = {'1':'逃げ','2':'先行','3':'中団','4':'追込'}
_BABA  = {'0':'良','1':'稍重','2':'重','3':'不良'}

def fmt_condition(cond: dict) -> str:
    parts = []
    if 'keibajo_code' in cond:
        parts.append(_JYO.get(str(cond['keibajo_code']), cond['keibajo_code']))
    if 'kyakushitsu' in cond:
        parts.append(_KYAKU.get(str(cond['kyakushitsu']), cond['kyakushitsu']))
    v = cond.get('baba_jotai', cond.get('baba', ''))
    if v != '':
        parts.append(_BABA.get(str(v), str(v)))
    if 'dist_cat' in cond:
        parts.append(f"{cond['dist_cat']}m級")
    if 'grade_code' in cond:
        parts.append(f"G{cond['grade_code']}")
    if 'kishu' in cond:
        parts.append(str(cond['kishu']))
    if 'chichi' in cond:
        parts.append(f"父:{cond['chichi']}")
    return " / ".join(parts) if parts else str(cond)

def fmt_race(code: str) -> str:
    s = str(code).strip()
    if len(s) != 16:
        return s
    mm, dd = s[4:6], s[6:8]
    jyo = _JYO.get(s[8:10], s[8:10])
    rno = s[14:16].lstrip('0') or '1'
    return f"{int(mm)}/{int(dd)} {jyo}{rno}R"

# ── グローバル CSS ────────────────────────────────────────────
st.markdown("""
<style>
/* ─ ベース ─ */
[data-testid="stAppViewContainer"]  { background:#0d1117; }
[data-testid="stSidebar"]           { background:#0d1117; border-right:1px solid #21262d; }
[data-testid="stSidebarContent"]    { padding:0 12px; }
h1,h2,h3                            { color:#e6edf3 !important; }
p, li, span, label                  { color:#c9d1d9; }
[data-testid="stMetricLabel"]       { color:#8b949e !important; }

/* ─ ナビボタン ─ */
div[data-testid="stButton"] > button {
    background:transparent;
    border:none;
    color:#8b949e;
    text-align:left;
    padding:10px 14px;
    border-radius:8px;
    width:100%;
    font-size:.95rem;
    transition:background .15s, color .15s;
}
div[data-testid="stButton"] > button:hover {
    background:#161b22;
    color:#e6edf3;
}

/* ─ KPI カード ─ */
.kpi {
    background:linear-gradient(135deg,#161b22,#1c2128);
    border:1px solid #21262d;
    border-radius:12px;
    padding:18px 16px;
    text-align:center;
    transition:border-color .2s, transform .2s;
}
.kpi:hover { border-color:#30363d; transform:translateY(-1px); }
.kpi-val   { font-size:2rem; font-weight:700; line-height:1.15; }
.kpi-sub   { font-size:.75rem; color:#8b949e; margin-top:2px; letter-spacing:.04em; }
.kpi-delta { font-size:.82rem; margin-top:4px; color:#8b949e; }

/* ─ セクションヘッダ ─ */
.sec-head {
    font-size:.9rem; font-weight:700; color:#58a6ff;
    border-bottom:1px solid #21262d;
    padding-bottom:5px; margin:22px 0 12px;
    letter-spacing:.03em;
}

/* ─ ベットカード ─ */
.bet-card {
    background:#161b22;
    border:1px solid #21262d;
    border-left:4px solid #30363d;
    border-radius:10px;
    padding:14px 18px;
    margin:6px 0;
    transition:border-color .15s;
}
.bet-card:hover          { border-color:#30363d; border-left-color:#58a6ff; }
.bet-card.grade-s        { border-left-color:#f78166; }
.bet-card.grade-a        { border-left-color:#3fb950; }

/* ─ バッジ ─ */
.badge {
    display:inline-block; padding:2px 9px;
    border-radius:20px; font-size:.75rem; font-weight:600;
}
.badge-green { background:#1a4d2e; color:#3fb950; }
.badge-red   { background:#4d1a1a; color:#f85149; }
.badge-blue  { background:#1a3a5c; color:#58a6ff; }
.badge-gold  { background:#4d3b00; color:#e3b341; }
.badge-gray  { background:#21262d; color:#8b949e; }

/* ─ ステータスボックス ─ */
.box-ok   { background:#0d2818; border:1px solid #238636; border-radius:8px; padding:12px 16px; color:#aff5b4; }
.box-warn { background:#2d2300; border:1px solid #9e6a03; border-radius:8px; padding:12px 16px; color:#e3b341; }
.box-err  { background:#2d0f0f; border:1px solid #da3633; border-radius:8px; padding:12px 16px; color:#ff7b72; }

/* ─ エージェントグリッド ─ */
.agent-chip {
    display:inline-block;
    padding:4px 12px; border-radius:20px;
    font-size:.78rem; font-weight:600; margin:3px;
    border:1px solid #21262d;
}
.agent-ok   { background:#0d2818; border-color:#238636; color:#3fb950; }
.agent-warn { background:#2d2300; border-color:#9e6a03; color:#e3b341; }
.agent-err  { background:#2d0f0f; border-color:#da3633; color:#ff7b72; }
.agent-none { background:#161b22; border-color:#30363d; color:#8b949e; }

/* ─ ページタイトル ─ */
.page-title {
    font-size:1.4rem; font-weight:700; color:#e6edf3;
    margin-bottom:4px;
}
.page-sub {
    font-size:.82rem; color:#8b949e; margin-bottom:16px;
}

/* ─ 区切り線 ─ */
hr { border-color:#21262d !important; }
</style>
""", unsafe_allow_html=True)

# ── データ読込 ────────────────────────────────────────────────
def _jload(path):
    if not os.path.exists(path): return None
    with open(path, encoding='utf-8') as f: return json.load(f)

def _csv(path, **kw):
    if not os.path.exists(path): return pd.DataFrame()
    return pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', **kw)

@st.cache_data(ttl=300)
def load_bankroll():
    d = _jload(os.path.join(BASE,"data","bankroll.json")) or {}
    return {'current': d.get('bankroll', d.get('current',100000)),
            'initial': d.get('initial',100000),
            'peak':    d.get('peak',100000),
            'history': d.get('history',[])}

@st.cache_data(ttl=300)
def load_tracker():
    df = _csv(os.path.join(BASE,"data","roi_tracker.csv"))
    if df.empty: return df
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df

@st.cache_data(ttl=60)
def load_picks():
    files = sorted(glob.glob(os.path.join(BASE,"agent_picks_*.json")), reverse=True)
    if not files: return None, None
    base = os.path.basename(files[0])
    yyyymmdd = base.replace("agent_picks_","").replace(".json","")
    picks_date = f"{yyyymmdd[:4]}/{yyyymmdd[4:6]}/{yyyymmdd[6:8]}" if len(yyyymmdd)==8 else yyyymmdd
    return _jload(files[0]), picks_date

@st.cache_data(ttl=300)
def load_race_ranking():
    return _csv(os.path.join(BASE,"data",f"race_ranking_{YEAR}.csv"))

@st.cache_data(ttl=300)
def load_ticket_recs():
    d = _jload(os.path.join(BASE,"data",f"ticket_recommendations_{YEAR}.json"))
    return pd.DataFrame(d) if d else pd.DataFrame()

@st.cache_data(ttl=300)
def load_walkforward():
    return _jload(os.path.join(BASE,"data","walkforward_result.json"))

@st.cache_data(ttl=300)
def load_wf_folds():
    return _csv(os.path.join(BASE,"data","walkforward_folds.csv"))

@st.cache_data(ttl=300)
def load_backtest_grid():
    return _csv(os.path.join(BASE,"data",f"backtest_grid_{YEAR}.csv"))

@st.cache_data(ttl=300)
def load_condition_roi():
    return _csv(os.path.join(BASE,"data",f"condition_roi_{YEAR}.csv"))

@st.cache_data(ttl=600)
def load_mc():
    return _jload(os.path.join(BASE,"data","monte_carlo_result.json"))

@st.cache_data(ttl=600)
def load_bk_sim():
    return _jload(os.path.join(BASE,"data","bankroll_simulation.json"))

@st.cache_data(ttl=300)
def load_perf():
    d = _jload(os.path.join(BASE,"data","model_performance.json"))
    return d if d else []

@st.cache_data(ttl=600)
def load_nicks():
    return _csv(os.path.join(BASE,"pedigree_output","nicks_roi_top.csv"))

@st.cache_data(ttl=600)
def load_nicks_all():
    return _csv(os.path.join(BASE,"pedigree_output","nicks_all.csv"))

@st.cache_data(ttl=120)
def load_canary_report():
    files = sorted(glob.glob(os.path.join(BASE,"logs","canary_report_*.json")), reverse=True)
    if not files: return None
    return _jload(files[0])

@st.cache_data(ttl=120)
def load_model_registry():
    d = _jload(os.path.join(BASE,"data","model_registry.json"))
    if d and isinstance(d, list): return d
    if d and isinstance(d, dict): return list(d.values())
    return []

def load_odds_snapshot():
    files = sorted(glob.glob(os.path.join(BASE,"data","odds_snapshot_*.json")), reverse=True)
    if not files: return None
    return _jload(files[0])

def _plotly_theme():
    return dict(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font_color='#c9d1d9', margin=dict(l=8,r=8,t=36,b=8),
        xaxis=dict(gridcolor='#21262d', linecolor='#21262d'),
        yaxis=dict(gridcolor='#21262d', linecolor='#21262d'),
    )

# ── ヘルパー: KPIカード ──────────────────────────────────────
def kpi_card(label, value, color="#e6edf3", delta="", width=None):
    style = f"width:{width};" if width else ""
    st.markdown(f"""
<div class="kpi" style="{style}">
  <div class="kpi-sub">{label}</div>
  <div class="kpi-val" style="color:{color}">{value}</div>
  {"<div class='kpi-delta'>"+delta+"</div>" if delta else ""}
</div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# サイドバー
# ════════════════════════════════════════════════════════════
NAV_ITEMS = [
    ("🏇", "今日の予想"),
    ("📊", "成績サマリー"),
    ("💰", "資金管理"),
    ("🔄", "バックテスト"),
    ("🔬", "詳細分析"),
    ("🤖", "エージェント監視"),
]

if "nav" not in st.session_state:
    st.session_state.nav = "今日の予想"

with st.sidebar:
    # ロゴ
    st.markdown("""
<div style="padding:16px 4px 8px">
  <div style="font-size:1.5rem;font-weight:800;color:#e6edf3;letter-spacing:-.01em">
    🙏 うまなり地蔵AI
  </div>
  <div style="font-size:.75rem;color:#8b949e;margin-top:2px">
    穴馬専門 高オッズMLシステム
  </div>
</div>
""", unsafe_allow_html=True)

    # 現在時刻・開催チェック
    now = datetime.now()
    dow_jp = ["月","火","水","木","金","土","日"][now.weekday()]
    is_race_day = now.weekday() in (5, 6)
    race_badge = (
        '<span style="color:#3fb950;font-weight:700">● JRA開催日</span>'
        if is_race_day else
        '<span style="color:#8b949e">○ 非開催</span>'
    )
    st.markdown(
        f'<div style="font-size:.78rem;color:#8b949e;padding:0 4px 12px">'
        f'{now.strftime("%m/%d")}（{dow_jp}）{now.strftime("%H:%M")} | {race_badge}'
        f'</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div style="font-size:.7rem;color:#8b949e;padding:0 4px 6px;letter-spacing:.06em">NAVIGATION</div>', unsafe_allow_html=True)

    for icon, label in NAV_ITEMS:
        active = st.session_state.nav == label
        bg     = "background:#161b22;color:#e6edf3;" if active else ""
        # ボタンで選択状態を視覚化
        if st.button(f"{icon}  {label}", key=f"nav_{label}", use_container_width=True):
            st.session_state.nav = label
            st.rerun()
        if active:
            # アクティブ表示用のマーカー（CSSで対応できないため js trick）
            st.markdown(
                f'<style>div[data-testid="stButton"]:has(button[kind="secondary"]:last-child)'
                f'{{background:#161b22;border-radius:8px;}}</style>',
                unsafe_allow_html=True
            )

    st.markdown("<hr>", unsafe_allow_html=True)

    # サイドバー下部: 資金サマリー
    bk_sb = load_bankroll()
    cur_sb = bk_sb['current']; ini_sb = bk_sb['initial']; peak_sb = bk_sb['peak']
    pnl_sb = cur_sb - ini_sb
    dd_sb  = (peak_sb - cur_sb) / peak_sb * 100 if peak_sb > 0 else 0
    pnl_color = "#3fb950" if pnl_sb >= 0 else "#f85149"
    dd_color_sb = "#3fb950" if dd_sb < 10 else "#e3b341" if dd_sb < 20 else "#f85149"

    st.markdown(f"""
<div style="padding:0 4px">
  <div style="font-size:.7rem;color:#8b949e;letter-spacing:.06em;margin-bottom:8px">BANKROLL</div>
  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
    <span style="color:#8b949e;font-size:.82rem">残高</span>
    <span style="color:{pnl_color};font-weight:700;font-size:.95rem">{cur_sb:,.0f}円</span>
  </div>
  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
    <span style="color:#8b949e;font-size:.82rem">損益</span>
    <span style="color:{pnl_color};font-size:.82rem">{'+'if pnl_sb>=0 else ''}{pnl_sb:,.0f}円</span>
  </div>
  <div style="display:flex;justify-content:space-between">
    <span style="color:#8b949e;font-size:.82rem">DD</span>
    <span style="color:{dd_color_sb};font-size:.82rem">{dd_sb:.1f}%</span>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.button("🔄 データ更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    wf_sb = load_walkforward()
    if wf_sb:
        v = wf_sb.get('verdict', '')
        cls = 'box-ok' if '良好' in v else 'box-warn' if '普通' in v else 'box-err'
        st.markdown(f"<div class='{cls}' style='font-size:.75rem;margin-top:8px'>{v}</div>",
                    unsafe_allow_html=True)

    st.markdown('<div style="font-size:.68rem;color:#30363d;text-align:center;margin-top:16px">v3.0 | Kelly×0.10</div>',
                unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# メインコンテンツ
# ════════════════════════════════════════════════════════════
page = st.session_state.nav

# ────────────────────────────────────────────────────────────
# PAGE: 今日の予想
# ────────────────────────────────────────────────────────────
if page == "今日の予想":
    st.markdown('<div class="page-title">🏇 今日の予想</div>', unsafe_allow_html=True)

    picks, picks_date = load_picks()
    today_str = now.strftime("%Y/%m/%d")
    is_today  = picks_date == today_str if picks_date else False

    if not is_today and picks_date:
        st.markdown(
            f"<div class='box-warn'>⚠️ 本日（{today_str}）のデータなし。最新: {picks_date} "
            f"— <code>python run_all.py --skip-train</code> を実行してください。</div>",
            unsafe_allow_html=True
        )

    # ── KPI バー ────────────────────────────────────────────
    if picks:
        rs   = picks.get('risk_summary', {})
        approved = picks.get('approved_bets', [])
        gen  = picks.get('generated_at','')[:16].replace('T',' ')
        alloc = rs.get('total_allocated', 0)
        ratio = rs.get('day_ratio', 0) * 100
        mult  = rs.get('dd_multiplier', 1)

        c1,c2,c3,c4,c5 = st.columns(5)
        with c1:
            kpi_card("承認レース", f"{rs.get('approved_count',0)}R", "#58a6ff")
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

        # ── 推奨ベット一覧 (左) + オッズシグナル (右) ───────
        col_main, col_side = st.columns([3, 1], gap="large")

        with col_main:
            st.markdown(f"<div class='sec-head'>推奨ベット ({picks_date})</div>",
                        unsafe_allow_html=True)
            for bet in approved:
                ev     = bet['expected_value'] * 100
                conf   = bet.get('confidence', 0) * 100
                odds   = bet['odds']
                ticket = bet.get('ticket_type', '単勝')
                grade  = bet.get('condition_grade', 'B')
                blood  = bet.get('blood_score', 1.0)
                rv     = bet.get('race_value', 0)
                ev_col = "#3fb950" if ev > 0 else "#f85149"
                g_cls  = "grade-s" if grade == 'S' else "grade-a" if grade in ('A','B') else ""
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

            notes = picks.get('supervisor_notes','')
            if notes:
                st.markdown(f"<div class='box-ok' style='margin-top:10px'>🧠 Supervisor: {notes}</div>",
                            unsafe_allow_html=True)

            with st.expander("📝 SNS投稿テキスト"):
                st.text(picks.get('post_text',''))

            logs = picks.get('log',[])
            if logs:
                with st.expander("🔍 エージェントログ"):
                    st.text('\n'.join(logs[-30:]))

        with col_side:
            # オッズシグナル
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
                ts = snap.get('timestamp','')[:16]
                st.caption(f"取得: {ts}")
            else:
                st.markdown("<div class='box-warn' style='font-size:.82rem'>スナップショットなし</div>",
                            unsafe_allow_html=True)

            # レース候補
            rs_df = load_race_ranking()
            if not rs_df.empty:
                st.markdown("<div class='sec-head' style='margin-top:20px'>Grade S/A レース</div>",
                            unsafe_allow_html=True)
                top_rs = rs_df[rs_df['grade'].isin(['S','A'])].head(8).copy()
                if 'race_code' in top_rs.columns:
                    for _, row in top_rs.iterrows():
                        g = row.get('grade','')
                        col_g = "#f78166" if g == 'S' else "#3fb950"
                        st.markdown(
                            f'<div style="font-size:.82rem;padding:4px 0;border-bottom:1px solid #21262d">'
                            f'<span style="color:{col_g};font-weight:700">[{g}]</span> '
                            f'{fmt_race(row["race_code"])}</div>',
                            unsafe_allow_html=True
                        )

            # クイック実行
            st.markdown("<div class='sec-head' style='margin-top:20px'>クイック実行</div>",
                        unsafe_allow_html=True)
            if st.button("▶ パイプライン実行", use_container_width=True):
                with st.spinner("実行中..."):
                    res = subprocess.run(
                        [PYTHON, "-X", "utf8", os.path.join(BASE,"run_all.py"), "--skip-train"],
                        capture_output=True, text=True, cwd=BASE,
                        env={**os.environ,'PYTHONUTF8':'1'}, timeout=600
                    )
                if res.returncode == 0:
                    st.success("完了")
                else:
                    st.error("失敗")
                    st.code(res.stderr[-1500:])

            if st.button("📸 オッズ取得", use_container_width=True):
                with st.spinner("Playwright 実行中..."):
                    res = subprocess.run(
                        [PYTHON, "-X", "utf8",
                         os.path.join(BASE,"pipeline","odds_scraper_36.py")],
                        capture_output=True, text=True, cwd=BASE,
                        env={**os.environ,'PYTHONUTF8':'1'}, timeout=120
                    )
                if res.returncode == 0:
                    st.success("取得完了")
                else:
                    st.error("取得失敗")
                    st.code(res.stderr[-1500:])

            if st.button("📨 SNS投稿", use_container_width=True):
                with st.spinner("投稿中..."):
                    res = subprocess.run(
                        [PYTHON, "-X", "utf8", "-c",
                         f"import sys; sys.path.insert(0,{BASE!r}); "
                         "from pipeline.social_bot_27 import broadcast_picks; broadcast_picks()"],
                        capture_output=True, text=True, cwd=BASE,
                        env={**os.environ,'PYTHONUTF8':'1'}, timeout=60
                    )
                if res.returncode == 0:
                    st.success("投稿完了")
                else:
                    st.error("投稿失敗")
                    st.code(res.stderr[-1500:])

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
            top_rs = rs_df[rs_df['grade'].isin(['S','A'])].head(12)
            st.dataframe(top_rs, use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────────
# PAGE: 成績サマリー
# ────────────────────────────────────────────────────────────
elif page == "成績サマリー":
    st.markdown('<div class="page-title">📊 成績サマリー</div>', unsafe_allow_html=True)

    tracker = load_tracker()
    bk      = load_bankroll()
    cur = bk['current']; ini = bk['initial']; pnl = cur - ini
    roi_all = cur / ini * 100 if ini > 0 else 100

    now_dt = datetime.now()
    if not tracker.empty:
        m_df = tracker[(tracker['date'].dt.year  == now_dt.year) &
                       (tracker['date'].dt.month == now_dt.month)]
        m_bet = m_df['bet_amount'].sum()
        m_ret = m_df['return_amount'].sum()
        m_roi = m_ret/m_bet*100 if m_bet > 0 else 0
        hits  = int(tracker['hit'].sum()); n = len(tracker)
        hr    = hits/n*100 if n > 0 else 0
    else:
        m_roi = hr = 0; n = hits = 0

    c1,c2,c3,c4 = st.columns(4)
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
            # 週次ROI棒グラフ
            st.markdown("<div class='sec-head'>週次回収率推移</div>", unsafe_allow_html=True)
            tracker['week'] = tracker['date'].dt.to_period('W').apply(lambda x: x.start_time)
            wkly = tracker.groupby('week').apply(lambda g: pd.Series({
                'roi':  g['return_amount'].sum()/g['bet_amount'].sum()*100
                        if g['bet_amount'].sum() > 0 else 0,
                'hits': int(g['hit'].sum()), 'count': len(g)
            })).reset_index()
            if PLOTLY:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=wkly['week'].astype(str), y=wkly['roi'],
                    marker_color=wkly['roi'].apply(lambda r:'#3fb950' if r>=100 else '#f85149'),
                ))
                fig.add_hline(y=100, line_dash='dash', line_color='#8b949e', annotation_text='100%')
                fig.add_hline(y=115, line_dash='dot',  line_color='#3fb950', annotation_text='目標115%')
                fig.update_layout(**_plotly_theme(), height=300,
                                  showlegend=False, yaxis_title='回収率(%)')
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            # オッズ帯別成績
            st.markdown("<div class='sec-head'>オッズ帯別成績</div>", unsafe_allow_html=True)
            tc = tracker.copy()
            tc['band'] = pd.cut(tc['odds'],
                bins=[0,5,10,20,50,9999],
                labels=['〜5倍','5〜10倍','10〜20倍','20〜50倍','50倍〜'])
            rows = []
            for band, g in tc.groupby('band', observed=True):
                bet = g['bet_amount'].sum(); ret = g['return_amount'].sum()
                rows.append({
                    'オッズ帯': str(band), '件数': len(g),
                    '的中率': f"{g['hit'].mean()*100:.1f}%",
                    '回収率': f"{ret/bet*100:.1f}%" if bet > 0 else '-',
                    '損益':   f"{ret-bet:+,.0f}円",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("記録なし — `roi_tracker_12.py` でベットを記録してください。")


# ────────────────────────────────────────────────────────────
# PAGE: 資金管理
# ────────────────────────────────────────────────────────────
elif page == "資金管理":
    st.markdown('<div class="page-title">💰 資金管理</div>', unsafe_allow_html=True)

    bk = load_bankroll()
    cur = bk['current']; ini = bk['initial']; peak = bk['peak']
    pnl = cur - ini; dd_cur = (peak - cur)/peak*100 if peak > 0 else 0
    kelly_mult = 1.0 if dd_cur<10 else 0.5 if dd_cur<20 else 0.25 if dd_cur<30 else 0.0

    c1,c2,c3,c4,c5 = st.columns(5)
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
                 "#3fb950" if dd_cur<10 else "#e3b341" if dd_cur<20 else "#f85149")
    with c5:
        kpi_card("ベット乗数", f"{kelly_mult:.2f}x",
                 "#3fb950" if kelly_mult==1 else "#e3b341" if kelly_mult>0 else "#f85149",
                 delta=f"Kelly実効: {0.10*kelly_mult:.3f}")

    col_l, col_r = st.columns([2, 1], gap="large")

    with col_l:
        hist = bk.get('history', [])
        if hist:
            st.markdown("<div class='sec-head'>資金推移</div>", unsafe_allow_html=True)
            hdf = pd.DataFrame(hist)
            date_col    = 'date'          if 'date'          in hdf.columns else 'month'
            balance_col = 'bankroll_after' if 'bankroll_after' in hdf.columns else 'balance'
            hdf[date_col] = pd.to_datetime(hdf[date_col])
            hdf = hdf.sort_values(date_col)
            if PLOTLY:
                fig = go.Figure()
                marker_color = (
                    hdf['hit'].map({1:'#3fb950', 0:'#f85149'})
                    if 'hit' in hdf.columns else '#58a6ff'
                )
                fig.add_trace(go.Scatter(
                    x=hdf[date_col], y=hdf[balance_col],
                    mode='lines+markers', name='残高',
                    line=dict(color='#58a6ff', width=2),
                    marker=dict(color=marker_color, size=6),
                    fill='tozeroy', fillcolor='rgba(88,166,255,0.05)',
                    hovertemplate='%{x|%Y-%m}<br>%{y:,.0f}円<extra></extra>'
                ))
                fig.add_hline(y=ini, line_dash='dash', line_color='#8b949e', annotation_text='初期資金')
                fig.update_layout(**_plotly_theme(), height=280, yaxis_title='残高(円)')
                st.plotly_chart(fig, use_container_width=True)

                peak_s = hdf[balance_col].cummax()
                dd_s   = (hdf[balance_col] - peak_s) / peak_s * 100
                fig2 = px.area(x=hdf[date_col], y=dd_s,
                               title="ドローダウン推移(%)",
                               color_discrete_sequence=['#f85149'])
                fig2.update_layout(**_plotly_theme(), height=180)
                st.plotly_chart(fig2, use_container_width=True)

    with col_r:
        bk_sim = load_bk_sim()
        if bk_sim and bk_sim.get('history_sample'):
            st.markdown("<div class='sec-head'>500レース成長シミュレーション</div>",
                        unsafe_allow_html=True)
            st.metric("最終資金", f"{bk_sim['final']:,.0f}円", f"{bk_sim['growth_rate']:+.1f}%")
            st.metric("最大DD",   f"{bk_sim['max_drawdown']*100:.1f}%")
            st.metric("ピーク",   f"{bk_sim['peak']:,.0f}円")
            if PLOTLY:
                fig = go.Figure(go.Scatter(
                    y=bk_sim['history_sample'], mode='lines',
                    line=dict(color='#3fb950', width=2),
                    fill='tozeroy', fillcolor='rgba(63,185,80,.06)'
                ))
                fig.add_hline(y=bk_sim['initial'], line_dash='dash', line_color='#8b949e')
                fig.update_layout(**_plotly_theme(), height=220,
                                  xaxis_title='レース数', yaxis_title='資金(円)')
                st.plotly_chart(fig, use_container_width=True)

        mc = load_mc()
        if mc:
            st.markdown("<div class='sec-head'>モンテカルロ リスク</div>",
                        unsafe_allow_html=True)
            rows = []
            for key, r in mc.items():
                frac = key.replace('frac_','').replace('pct','')
                rows.append({
                    'ベット率': f"{frac}%",
                    '破産確率': f"{r['ruin_rate']*100:.1f}%",
                    '利益確率': f"{r['profit_prob']*100:.1f}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────────
# PAGE: バックテスト
# ────────────────────────────────────────────────────────────
elif page == "バックテスト":
    st.markdown('<div class="page-title">🔄 バックテスト</div>', unsafe_allow_html=True)

    wf = load_walkforward()
    folds_df = load_wf_folds()

    if wf:
        v = wf.get('verdict', '')
        cls = 'box-ok' if '良好' in v else 'box-warn' if '普通' in v else 'box-err'
        st.markdown(f"<div class='{cls}' style='margin-bottom:16px'>{v}</div>",
                    unsafe_allow_html=True)

        c1,c2,c3,c4 = st.columns(4)
        with c1:
            kpi_card("平均ROI", f"{wf.get('avg_roi',0):+.1f}%", "#3fb950")
        with c2:
            kpi_card("平均的中率", f"{wf.get('avg_hit_rate',0):.1f}%", "#e3b341")
        with c3:
            avg_dd = wf.get('avg_max_dd', 0)
            kpi_card("平均最大DD", f"{avg_dd:.1f}%",
                     "#3fb950" if avg_dd<30 else "#e3b341" if avg_dd<50 else "#f85149")
        with c4:
            n_folds = len(wf.get('folds', []))
            n_pos   = wf.get('n_positive', 0)
            kpi_card("プラス期間", f"{n_pos}/{n_folds}", "#58a6ff")

        col_l, col_r = st.columns([2, 1], gap="large")

        with col_l:
            if not folds_df.empty:
                st.markdown("<div class='sec-head'>検証期間の成績</div>", unsafe_allow_html=True)
                show = [c for c in ['test_year','roi','hit_rate','max_dd','n_bets']
                        if c in folds_df.columns]
                st.dataframe(
                    folds_df[show].style.format({
                        'roi':'{:+.1f}%','hit_rate':'{:.1f}%',
                        'max_dd':'{:.1f}%','n_bets':'{:,}'
                    }),
                    use_container_width=True, hide_index=True
                )
                if PLOTLY and 'roi' in folds_df.columns:
                    fig = px.bar(folds_df, x='test_year', y='roi',
                                 title="年別 ROI（検証期間）",
                                 color='roi',
                                 color_continuous_scale=['#f85149','#3fb950'])
                    fig.add_hline(y=0, line_dash='dash', line_color='#8b949e')
                    fig.update_layout(**_plotly_theme(), height=280,
                                      coloraxis_showscale=False)
                    st.plotly_chart(fig, use_container_width=True)

        with col_r:
            # グリッドサーチ上位
            grid_df = load_backtest_grid()
            if not grid_df.empty:
                st.markdown("<div class='sec-head'>パラメータ最適解</div>",
                            unsafe_allow_html=True)
                top_grid = (grid_df
                            .replace([np.inf,-np.inf], np.nan)
                            .dropna()
                            .head(8))
                show = [c for c in ['ev_threshold','kelly_fraction','roi']
                        if c in top_grid.columns]
                st.dataframe(top_grid[show], use_container_width=True, hide_index=True)

            # 馬券戦略サマリー
            rs_df = load_race_ranking()
            if not rs_df.empty:
                st.markdown("<div class='sec-head'>推奨レースフィルタ</div>",
                            unsafe_allow_html=True)
                grade_filter = st.multiselect("グレード", ['S','A','B','C'],
                                              default=['S','A'])
                filtered = rs_df[rs_df['grade'].isin(grade_filter)].head(20).copy()
                if 'race_code' in filtered.columns:
                    filtered.insert(0, 'レース', filtered['race_code'].apply(fmt_race))
                    filtered = filtered.drop(columns=['race_code'])
                st.dataframe(filtered, use_container_width=True, hide_index=True)

        # ヒートマップ
        if not grid_df.empty and PLOTLY and all(
            c in grid_df.columns for c in ['ev_threshold','kelly_fraction','roi']
        ):
            st.markdown("<div class='sec-head'>パラメータ最適化ヒートマップ</div>",
                        unsafe_allow_html=True)
            pivot = (grid_df
                     .pivot_table(values='roi', index='kelly_fraction', columns='ev_threshold')
                     .replace([np.inf,-np.inf], np.nan).fillna(0).clip(-200, 2000))
            fig = go.Figure(go.Heatmap(
                z=pivot.values,
                x=[f"EV {v:.0%}" for v in pivot.columns],
                y=[f"Kelly {v:.0%}" for v in pivot.index],
                colorscale='RdYlGn', zmid=0,
                text=[[f"{v:+.0f}%" for v in row] for row in pivot.values],
                texttemplate="%{text}"
            ))
            fig.update_layout(**_plotly_theme(), height=320,
                              title="ROI ヒートマップ (EV閾値 × Kelly係数)")
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("`python pipeline/backtest_walkforward_35.py` を実行してください。")

    # 馬券戦略
    st.markdown("<div class='sec-head'>馬券種別分布 (ticket_optimizer)</div>",
                unsafe_allow_html=True)
    tk_df = load_ticket_recs()
    if not tk_df.empty and 'ticket_type' in tk_df.columns:
        col_l2, col_r2 = st.columns([1, 2], gap="large")
        with col_l2:
            dist = tk_df['ticket_type'].value_counts().reset_index()
            dist.columns = ['馬券種','件数']
            if PLOTLY:
                fig = px.pie(dist, values='件数', names='馬券種',
                             hole=0.45,
                             color_discrete_sequence=['#58a6ff','#3fb950','#e3b341','#f85149','#bc8cff'])
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(**_plotly_theme(), height=260, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
        with col_r2:
            top10 = tk_df.nlargest(10,'ev') if 'ev' in tk_df.columns else tk_df.head(10)
            top10 = top10.copy()
            if 'race_code' in top10.columns:
                top10.insert(0,'レース', top10['race_code'].apply(fmt_race))
            show = [c for c in ['レース','ticket_type','est_odds','ev','recommended_bet']
                    if c in top10.columns]
            st.dataframe(top10[show] if show else top10,
                         use_container_width=True, hide_index=True)
    else:
        st.info("`python pipeline/ticket_optimizer_30.py` を実行")


# ────────────────────────────────────────────────────────────
# PAGE: 詳細分析
# ────────────────────────────────────────────────────────────
elif page == "詳細分析":
    st.markdown('<div class="page-title">🔬 詳細分析</div>', unsafe_allow_html=True)

    # ── モデル検証 ──────────────────────────────────────────
    with st.expander("📈 モデル検証 — 回収率・的中率推移", expanded=True):
        perf_hist = load_perf()
        if perf_hist:
            perf_df = pd.DataFrame(perf_hist)
            perf_df['date']    = pd.to_datetime(perf_df['evaluated_at'].str[:10])
            perf_df['roi_pct'] = perf_df['recovery_rate'] * 100
            perf_df['hit_pct'] = perf_df['hit_rate'] * 100
            latest  = perf_hist[-1]
            roi_l   = latest['recovery_rate'] * 100
            box_cls = 'box-ok' if roi_l>=100 else 'box-warn' if roi_l>=80 else 'box-err'
            st.markdown(
                f"<div class='{box_cls}'>直近評価 ({latest['evaluated_at'][:10]}): "
                f"回収率 {roi_l:.1f}% | 的中率 {latest['hit_rate']*100:.1f}% | "
                f"サンプル {latest['total']}件</div>",
                unsafe_allow_html=True
            )
            if PLOTLY:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=perf_df['date'], y=perf_df['roi_pct'],
                    name='回収率(%)', line=dict(color='#58a6ff', width=2)))
                fig.add_trace(go.Scatter(x=perf_df['date'], y=perf_df['hit_pct'],
                    name='的中率(%)', line=dict(color='#e3b341', width=2, dash='dot'),
                    yaxis='y2'))
                fig.add_hline(y=100, line_dash='dash', line_color='#8b949e')
                fig.update_layout(**_plotly_theme(), height=300,
                    yaxis=dict(title='回収率(%)'),
                    yaxis2=dict(title='的中率(%)', overlaying='y', side='right'))
                st.plotly_chart(fig, use_container_width=True)
            avg3 = np.mean([h['recovery_rate'] for h in perf_hist[-3:]]) * 100
            if avg3 < 80:
                st.error(f"🚨 直近3回平均 {avg3:.1f}% — 自動再学習推奨")
            else:
                st.success(f"✅ 直近3回平均 {avg3:.1f}% — モデル良好")
        else:
            st.info("`auto_learn_13.py` を実行するとパフォーマンス履歴が表示されます。")

    # ── SHAP ────────────────────────────────────────────────
    with st.expander("🔬 SHAP 特徴量重要度"):
        SHAP_DIR = os.path.join(BASE, "shap_output")
        shap_files = glob.glob(os.path.join(SHAP_DIR,"*.png")) if os.path.exists(SHAP_DIR) else []
        if shap_files:
            summary = [f for f in shap_files if 'summary' in f]
            if summary:
                st.image(summary[-1], caption="SHAP Summary Plot", use_container_width=True)
            waterfalls = [f for f in shap_files if 'waterfall' in f]
            if waterfalls:
                cols = st.columns(min(3, len(waterfalls)))
                for i, wf_f in enumerate(waterfalls[:6]):
                    with cols[i % 3]:
                        name = os.path.basename(wf_f).replace('.png','').replace('waterfall_','')
                        st.image(wf_f, caption=name, use_container_width=True)
            shap_csvs = glob.glob(os.path.join(SHAP_DIR,"*.csv"))
            if shap_csvs:
                sdf = pd.read_csv(shap_csvs[-1], encoding='utf-8-sig')
                if 'feature' in sdf.columns and 'importance' in sdf.columns and PLOTLY:
                    top20 = sdf.nlargest(20, 'importance')
                    fig = px.bar(top20, x='importance', y='feature', orientation='h',
                                 title="SHAP 特徴量重要度 TOP20",
                                 color='importance',
                                 color_continuous_scale=['#58a6ff','#3fb950'])
                    fig.update_layout(**_plotly_theme(), height=500,
                                      yaxis={'categoryorder':'total ascending'},
                                      coloraxis_showscale=False)
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("SHAP分析を実行: `python pipeline/shap_analysis.py`")
            if st.button("▶️ SHAP分析を今すぐ実行"):
                with st.spinner("SHAP分析中..."):
                    r = subprocess.run(
                        ['python','pipeline/shap_analysis.py'],
                        capture_output=True, text=True, cwd=BASE,
                        env={**os.environ,'PYTHONUTF8':'1'}
                    )
                if r.returncode == 0:
                    st.success("完了！更新ボタンを押してください。")
                else:
                    st.error(r.stderr[-500:])

    # ── 血統分析 ────────────────────────────────────────────
    with st.expander("🧬 血統分析 — ニックス指数"):
        nicks_top = load_nicks()
        nicks_all = load_nicks_all()
        if not nicks_top.empty:
            show = [c for c in ['chichi','haha_chichi','nick_index','nick_roi',
                                 'nick_win_rate','nick_races','nick_significant']
                    if c in nicks_top.columns]
            disp = nicks_top.head(30).copy()
            if 'nick_significant' in disp.columns:
                disp['nick_significant'] = disp['nick_significant'].map(
                    {True:'★',False:'',1:'★',0:''}).fillna('')
            st.dataframe(disp[show], use_container_width=True, hide_index=True)

            if not nicks_all.empty and PLOTLY and 'nick_index' in nicks_all.columns:
                c1, c2 = st.columns(2)
                with c1:
                    fig = px.histogram(nicks_all, x='nick_index', nbins=50,
                                       title="ニックス指数の分布",
                                       color_discrete_sequence=['#58a6ff'])
                    fig.add_vline(x=1.0, line_dash='dash', line_color='#8b949e')
                    fig.add_vline(x=1.5, line_dash='dot',  line_color='#3fb950')
                    fig.update_layout(**_plotly_theme(), height=260)
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    if 'chichi' in nicks_all.columns:
                        sire = (nicks_all.groupby('chichi')
                                .agg(avg=('nick_index','mean'), n=('nick_index','count'))
                                .query('n>=5')
                                .sort_values('avg', ascending=False)
                                .head(15).reset_index())
                        fig = px.bar(sire, x='avg', y='chichi', orientation='h',
                                     title="父系別 平均ニックス指数 TOP15",
                                     color='avg',
                                     color_continuous_scale=['#58a6ff','#3fb950'])
                        fig.add_vline(x=1.0, line_dash='dash', line_color='#8b949e')
                        fig.update_layout(**_plotly_theme(), height=300,
                                          yaxis={'categoryorder':'total ascending'},
                                          coloraxis_showscale=False)
                        st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("`python pipeline/nicks_analysis_18.py` を実行してください。")

        opt_p = os.path.join(BASE,"data","optuna_best_params.json")
        if os.path.exists(opt_p):
            with st.expander("🔬 Optuna 最適パラメータ"):
                st.json(_jload(opt_p))

    # ── 知識ベース ──────────────────────────────────────────
    with st.expander("📚 知識ベース"):
        KB_DIR    = os.path.join(BASE,"data","knowledge_base")
        LATEST    = os.path.join(KB_DIR,"LATEST.json")
        CONF_LOG  = os.path.join(KB_DIR,"confidence_history.csv")
        CHANGELOG = os.path.join(KB_DIR,"changelog.md")
        CAT_LABELS = {
            "BLD":"血統","JKY":"騎手","TRK":"コース","MKT":"市場歪み",
            "TRN":"調教","SEA":"季節","DBT":"新馬戦","SHG":"障害戦",
        }
        CONF_SOFT, CONF_MEDIUM, CONF_HARD = 0.50, 0.70, 0.80

        if not os.path.exists(LATEST):
            st.info("`python pipeline/knowledge_curator_41.py` を実行してください。")
        else:
            kb_state     = json.load(open(LATEST, encoding="utf-8"))
            active_items = {k:v for k,v in kb_state.items() if v.get("status")=="active"}
            depr_items   = {k:v for k,v in kb_state.items() if v.get("status")=="deprecated"}
            high_conf    = sum(1 for v in active_items.values() if v.get("confidence",0)>=CONF_HARD)
            mid_conf     = sum(1 for v in active_items.values() if CONF_MEDIUM<=v.get("confidence",0)<CONF_HARD)

            c1,c2,c3,c4 = st.columns(4)
            with c1: kpi_card("アクティブ知見",  str(len(active_items)), "#58a6ff")
            with c2: kpi_card("高確信度(≥0.80)", str(high_conf), "#3fb950")
            with c3: kpi_card("中確信度(≥0.70)", str(mid_conf),  "#e3b341")
            with c4: kpi_card("廃止済み",         str(len(depr_items)), "#8b949e")

            col_f1, col_f2, col_f3 = st.columns([2,2,1])
            with col_f1:
                cat_filter = st.multiselect(
                    "カテゴリ", list(CAT_LABELS.keys()),
                    default=list(CAT_LABELS.keys()),
                    format_func=lambda x: f"{x} {CAT_LABELS[x]}"
                )
            with col_f2:
                conf_min = st.slider("最小 confidence", 0.0, 1.0, 0.0, 0.05)
            with col_f3:
                sort_by = st.selectbox("並び順", ["confidence↓","sample_count↓","作成日↑"])

            rows = []
            for item_id, item in active_items.items():
                cat  = item.get("category","?")
                conf = item.get("confidence", 0.0)
                if cat not in cat_filter or conf < conf_min: continue
                rows.append({
                    "ID": item_id,
                    "カテゴリ": f"{cat} {CAT_LABELS.get(cat,'')}",
                    "条件": fmt_condition(item.get("condition",{})),
                    "知見": item.get("claim","")[:60],
                    "confidence": conf,
                    "n": item.get("sample_count",0),
                    "lift推定": item.get("metrics",{}).get("estimated_lift",1.0),
                    "使われ方": (
                        "🔴 ハードルール" if conf>=CONF_HARD else
                        "🟡 特徴量追加"   if conf>=CONF_MEDIUM else
                        "🔵 EV boost"     if conf>=CONF_SOFT else
                        "⚫ 待機中"
                    ),
                })
            if sort_by == "confidence↓":     rows.sort(key=lambda x: x["confidence"], reverse=True)
            elif sort_by == "sample_count↓": rows.sort(key=lambda x: x["n"], reverse=True)
            else:                            rows.sort(key=lambda x: x.get("作成",""))

            if rows:
                df_kb = pd.DataFrame(rows)
                st.dataframe(
                    df_kb.style
                         .background_gradient(subset=["confidence"], cmap="RdYlGn", vmin=0, vmax=1)
                         .format({"confidence":"{:.3f}","lift推定":"{:.2f}x","n":"{:,}"}),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("フィルタ条件に一致する知見がありません。")

            if os.path.exists(CONF_LOG):
                conf_df = pd.read_csv(CONF_LOG, parse_dates=["date"])
                if not conf_df.empty and PLOTLY:
                    top_ids = (conf_df.groupby("id")["confidence"].last()
                               .nlargest(10).index.tolist())
                    plot_df = conf_df[conf_df["id"].isin(top_ids)]
                    fig = px.line(plot_df, x="date", y="confidence", color="id",
                                  title="知見 confidence 推移")
                    for y, col, txt in [
                        (CONF_HARD,   "#3fb950","ハードルール"),
                        (CONF_MEDIUM, "#e3b341","特徴量追加"),
                        (CONF_SOFT,   "#58a6ff","EVboost"),
                    ]:
                        fig.add_hline(y=y, line_dash="dash", line_color=col,
                                      annotation_text=txt)
                    fig.update_layout(**_plotly_theme(), height=320)
                    st.plotly_chart(fig, use_container_width=True)

            b1, b2 = st.columns(2)
            with b1:
                if st.button("🔄 知識ベース更新（直近7日）"):
                    with st.spinner("Haiku で知見を抽出中..."):
                        try:
                            from pipeline.knowledge_curator_41 import run_knowledge_curator
                            run_knowledge_curator(days=7)
                            st.success("更新完了！")
                        except Exception as e:
                            st.error(f"エラー: {e}")
            with b2:
                if st.button("📸 スナップショット強制作成"):
                    with st.spinner("作成中..."):
                        try:
                            from pipeline.knowledge_curator_41 import run_knowledge_curator
                            run_knowledge_curator(days=7, force_snapshot=True)
                            st.success("完了！")
                        except Exception as e:
                            st.error(f"エラー: {e}")

            if os.path.exists(CHANGELOG):
                with st.expander("📋 変更履歴"):
                    st.markdown(open(CHANGELOG, encoding="utf-8").read())

    # ── 条件別係数 ──────────────────────────────────────────
    with st.expander("⚙️ 条件別ROI係数 (condition_adjuster)"):
        cond_df = load_condition_roi()
        if not cond_df.empty:
            c1, c2 = st.columns(2)
            with c1:
                top_s = (cond_df[cond_df['grade']=='S'].head(10)
                         if 'grade' in cond_df.columns else cond_df.head(10))
                st.markdown("**得意条件 (Grade S)**")
                show = [c for c in ['cond_key','roi','coeff','n'] if c in top_s.columns]
                st.dataframe(top_s[show], use_container_width=True, hide_index=True)
            with c2:
                st.markdown("**要注意条件 (低係数)**")
                show = [c for c in ['cond_key','roi','coeff','n'] if c in cond_df.columns]
                st.dataframe(cond_df.tail(8)[show], use_container_width=True, hide_index=True)
        else:
            st.info("`python pipeline/condition_adjuster_34.py` をモデル学習後に実行")


# ────────────────────────────────────────────────────────────
# PAGE: エージェント監視
# ────────────────────────────────────────────────────────────
elif page == "エージェント監視":
    st.markdown('<div class="page-title">🤖 エージェント監視</div>', unsafe_allow_html=True)

    canary = load_canary_report()
    registry = load_model_registry()

    col_l, col_r = st.columns([2, 1], gap="large")

    with col_l:
        # カナリア結果
        st.markdown("<div class='sec-head'>カナリアテスト結果</div>", unsafe_allow_html=True)
        if canary:
            total  = canary.get('total', 0)
            passed = canary.get('passed', 0)
            failed = canary.get('failed', 0)
            ts     = canary.get('timestamp','')[:16]
            rate   = passed / total * 100 if total > 0 else 0
            bar_color = "#3fb950" if rate == 100 else "#e3b341" if rate >= 80 else "#f85149"

            st.markdown(f"""
<div style="background:#161b22;border:1px solid #21262d;border-radius:12px;padding:20px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
    <div style="font-size:1.8rem;font-weight:800;color:{bar_color}">{passed}/{total} PASS</div>
    <div style="font-size:.82rem;color:#8b949e">{ts}</div>
  </div>
  <div style="background:#21262d;border-radius:6px;height:8px;overflow:hidden">
    <div style="background:{bar_color};height:100%;width:{rate:.0f}%;border-radius:6px;transition:width .5s"></div>
  </div>
  <div style="display:flex;gap:16px;margin-top:12px;font-size:.82rem">
    <span style="color:#3fb950">✓ PASS: {passed}</span>
    <span style="color:#f85149">✗ FAIL: {failed}</span>
    <span style="color:#8b949e">合格率: {rate:.0f}%</span>
  </div>
</div>""", unsafe_allow_html=True)

            # エージェント別チップ
            st.markdown("<div class='sec-head' style='margin-top:20px'>エージェント別ステータス</div>",
                        unsafe_allow_html=True)
            results = canary.get('results', {})
            chips_html = ""
            for agent_id, res in results.items():
                status = res.get('status', 'unknown')
                cls = "agent-ok" if status == "pass" else "agent-err" if status == "fail" else "agent-none"
                icon = "✓" if status == "pass" else "✗" if status == "fail" else "?"
                chips_html += f'<span class="agent-chip {cls}">{icon} {agent_id}</span>'
            st.markdown(f"<div>{chips_html}</div>", unsafe_allow_html=True)

            # 失敗詳細
            fails = {k:v for k,v in results.items() if v.get('status') != 'pass'}
            if fails:
                st.markdown("<div class='sec-head' style='margin-top:16px'>失敗詳細</div>",
                            unsafe_allow_html=True)
                for agent_id, res in fails.items():
                    st.markdown(
                        f"<div class='box-err' style='margin-bottom:6px'>"
                        f"<strong>{agent_id}</strong>: {res.get('error','')}</div>",
                        unsafe_allow_html=True
                    )
        else:
            st.markdown("<div class='box-warn'>カナリアレポートなし。`python canary_run.py` を実行してください。</div>",
                        unsafe_allow_html=True)

        # カナリア手動実行
        if st.button("▶ カナリアテスト実行", use_container_width=True):
            with st.spinner("30エージェントをテスト中..."):
                res = subprocess.run(
                    [PYTHON, "-X", "utf8", os.path.join(BASE,"canary_run.py")],
                    capture_output=True, text=True, cwd=BASE,
                    env={**os.environ,'PYTHONUTF8':'1'}, timeout=120
                )
            if res.returncode == 0:
                st.success("完了！ページを更新してください。")
            else:
                st.error(res.stderr[-500:])

        # 監査ログ
        st.markdown("<div class='sec-head'>監査ログ (直近50件)</div>", unsafe_allow_html=True)
        audit_log_path = os.path.join(BASE,"data","audit_log.jsonl")
        if os.path.exists(audit_log_path):
            lines = open(audit_log_path, encoding='utf-8').readlines()
            recent = []
            for line in lines[-50:]:
                try:
                    recent.append(json.loads(line.strip()))
                except Exception:
                    pass
            if recent:
                audit_df = pd.DataFrame(recent)
                show = [c for c in ['timestamp','agent_id','event','run_tag','error']
                        if c in audit_df.columns]
                st.dataframe(audit_df[show].tail(50) if show else audit_df.tail(50),
                             use_container_width=True, hide_index=True)
        else:
            st.info("監査ログなし")

    with col_r:
        # スケジュール状況
        st.markdown("<div class='sec-head'>スケジュール</div>", unsafe_allow_html=True)
        schedule_items = [
            ("08:00", "パイプライン実行", "開催日のみ"),
            ("08:30", "平日メール",       "月〜金"),
            ("09:00", "ペーパートレード", "開催日のみ"),
            ("毎時:02", "オッズ取得",    "開催日 07-17時"),
            ("07:00", "回収率精算",       "日次"),
            ("日02:00","モデル再学習",    "週次"),
            ("月03:00","RAG再構築",       "週次"),
            ("月03:30","UpsetScore",      "週次"),
            ("月04:00","知識ベース更新",  "週次"),
        ]
        for time_str, label, note in schedule_items:
            st.markdown(f"""
<div style="display:flex;justify-content:space-between;padding:6px 0;
     border-bottom:1px solid #21262d;font-size:.82rem">
  <span style="color:#58a6ff;font-family:monospace;min-width:60px">{time_str}</span>
  <span style="color:#e6edf3;flex:1;padding:0 8px">{label}</span>
  <span style="color:#8b949e">{note}</span>
</div>""", unsafe_allow_html=True)

        # モデルレジストリ
        st.markdown("<div class='sec-head' style='margin-top:20px'>モデルレジストリ</div>",
                    unsafe_allow_html=True)
        if registry:
            reg_df = pd.DataFrame(registry)
            show = [c for c in ['model_id','version','trained_at','ensemble_acc','status']
                    if c in reg_df.columns]
            st.dataframe(
                reg_df[show].tail(10) if show else reg_df.tail(10),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("レジストリなし")

        # v2 オーケストレーター実行
        st.markdown("<div class='sec-head' style='margin-top:20px'>v2 パイプライン</div>",
                    unsafe_allow_html=True)
        if st.button("▶ v2 日次実行", use_container_width=True):
            with st.spinner("00_orchestrator.py 実行中..."):
                res = subprocess.run(
                    [PYTHON, "-X", "utf8",
                     os.path.join(BASE,"pipeline_v2","00_orchestrator.py")],
                    capture_output=True, text=True, cwd=BASE,
                    env={**os.environ,'PYTHONUTF8':'1'}, timeout=600
                )
            if res.returncode == 0:
                st.success("完了")
            else:
                st.error("失敗")
                st.code(res.stderr[-1000:])

        if st.button("▶ v2 週次実行", use_container_width=True):
            with st.spinner("00_orchestrator_weekly.py 実行中..."):
                res = subprocess.run(
                    [PYTHON, "-X", "utf8",
                     os.path.join(BASE,"pipeline_v2","00_orchestrator_weekly.py")],
                    capture_output=True, text=True, cwd=BASE,
                    env={**os.environ,'PYTHONUTF8':'1'}, timeout=900
                )
            if res.returncode == 0:
                st.success("完了")
            else:
                st.error("失敗")
                st.code(res.stderr[-1000:])

# ── フッター ─────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center;font-size:.75rem;color:#30363d;padding:4px 0">'
    '🙏 うまなり地蔵AI v3.0 | Kelly×0.10 安全運用 | データと閻魔大王の御加護を信じよ👹'
    '</div>',
    unsafe_allow_html=True
)
