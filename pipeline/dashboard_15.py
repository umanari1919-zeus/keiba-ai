"""
うまなり地蔵AI ダッシュボード v2
起動: streamlit run pipeline/dashboard_15.py
"""
import os, json, glob
from datetime import datetime

import pandas as pd
import numpy as np
import streamlit as st

# ── ページ設定 ────────────────────────────────────────────────
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

# ── 定数 ────────────────────────────────────────────────────
BASE = "D:\\keiba_ai"
YEAR = datetime.now().year

# ── レースコード → 人間向け表示 ─────────────────────────────
_JYO = {
    '01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',
    '06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉',
    '30':'門別','35':'盛岡','36':'水沢','42':'浦和','43':'船橋',
    '44':'大井','45':'川崎','46':'金沢','47':'笠松','48':'名古屋',
    '50':'園田','51':'姫路','54':'高知','55':'佐賀','58':'帯広',
}

_KYAKU = {'1':'逃げ','2':'先行','3':'中団','4':'追込','逃げ':'逃げ','先行':'先行','中団':'中団','追込':'追込'}
_BABA  = {'0':'良','1':'稍重','2':'重','3':'不良','良':'良','稍重':'稍重','重':'重','不良':'不良'}

def fmt_condition(cond: dict) -> str:
    """condition dictを読みやすい文字列に変換"""
    parts = []
    if 'keibajo_code' in cond:
        parts.append(_JYO.get(str(cond['keibajo_code']), cond['keibajo_code']))
    if 'kyakushitsu' in cond:
        parts.append(_KYAKU.get(str(cond['kyakushitsu']), cond['kyakushitsu']))
    if 'baba_jotai' in cond or 'baba' in cond:
        v = cond.get('baba_jotai', cond.get('baba', ''))
        parts.append(_BABA.get(str(v), str(v)))
    if 'dist_cat' in cond:
        parts.append(f"{cond['dist_cat']}m級")
    if 'grade_code' in cond:
        parts.append(f"G{cond['grade_code']}")
    if 'ninki_cat' in cond:
        parts.append(f"人気{cond['ninki_cat']}")
    if 'kishu' in cond:
        parts.append(str(cond['kishu']))
    if 'chichi' in cond:
        parts.append(f"父:{cond['chichi']}")
    return " / ".join(parts) if parts else str(cond)

def fmt_race(code: str) -> str:
    """'2026020710010511' → '2/7 小倉11R'"""
    s = str(code).strip()
    if len(s) != 16:
        return s
    mm, dd = s[4:6], s[6:8]
    jyo = _JYO.get(s[8:10], s[8:10])
    rno = s[14:16].lstrip('0') or '1'
    return f"{int(mm)}/{int(dd)} {jyo}{rno}R"

# ── CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
/* ─ グローバル ─ */
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }
h1,h2,h3 { color: #e6edf3 !important; }
p, li, span { color: #c9d1d9; }

/* ─ KPI カード ─ */
.kpi {
    background: linear-gradient(145deg,#161b22,#1c2128);
    border: 1px solid #30363d;
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
    transition: transform .2s;
}
.kpi:hover { transform: translateY(-2px); border-color:#58a6ff; }
.kpi-val  { font-size: 2.2rem; font-weight: 700; line-height: 1.1; }
.kpi-sub  { font-size: 0.78rem; color: #8b949e; margin-top: 4px; }
.kpi-delta{ font-size: 0.85rem; margin-top: 6px; }

/* ─ ベットカード ─ */
.bet-card {
    background: #161b22;
    border-left: 4px solid #1f6feb;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
}
.bet-card.grade-s { border-left-color: #f78166; }
.bet-card.grade-a { border-left-color: #3fb950; }

/* ─ バッジ ─ */
.badge {
    display:inline-block;
    padding:2px 10px;
    border-radius:20px;
    font-size:.78rem;
    font-weight:600;
}
.badge-green { background:#1a4d2e; color:#3fb950; }
.badge-red   { background:#4d1a1a; color:#f85149; }
.badge-blue  { background:#1a3a5c; color:#58a6ff; }
.badge-gold  { background:#4d3b00; color:#e3b341; }

/* ─ セクションヘッダ ─ */
.sec-head {
    border-bottom: 1px solid #30363d;
    padding-bottom: 6px;
    margin: 20px 0 14px;
    font-size: 1rem;
    font-weight: 700;
    color: #58a6ff;
}

/* ─ アラートボックス ─ */
.box-ok   { background:#0d2818; border:1px solid #238636; border-radius:8px; padding:12px; color:#aff5b4; }
.box-warn { background:#2d2300; border:1px solid #9e6a03; border-radius:8px; padding:12px; color:#e3b341; }
.box-err  { background:#2d0f0f; border:1px solid #da3633; border-radius:8px; padding:12px; color:#ff7b72; }

/* ─ タブ ─ */
button[data-baseweb="tab"] { font-size:.9rem !important; }
</style>
""", unsafe_allow_html=True)


# ── データ読込 ────────────────────────────────────────────────
def _jload(path):
    if not os.path.exists(path): return None
    with open(path, encoding='utf-8') as f: return json.load(f)

def _csv(path, **kw):
    if not os.path.exists(path): return pd.DataFrame()
    return pd.read_csv(path, encoding='utf-8-sig', **kw)

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
    df['date'] = pd.to_datetime(df['date'])
    return df

@st.cache_data(ttl=60)
def load_picks():
    files = sorted(glob.glob(os.path.join(BASE,"agent_picks_*.json")), reverse=True)
    if not files: return None, None
    f = files[0]
    # ファイル名から日付抽出: agent_picks_20260419.json → "2026/04/19"
    base = os.path.basename(f)          # agent_picks_20260419.json
    yyyymmdd = base.replace("agent_picks_","").replace(".json","")
    picks_date = f"{yyyymmdd[:4]}/{yyyymmdd[4:6]}/{yyyymmdd[6:8]}" if len(yyyymmdd)==8 else yyyymmdd
    return _jload(f), picks_date

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

def _plotly_theme():
    return dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                font_color='#c9d1d9', margin=dict(l=8,r=8,t=36,b=8))


# ── サイドバー ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🙏 うまなり地蔵AI")
    st.caption(f"v2 | {datetime.now().strftime('%m/%d %H:%M')}")
    st.divider()

    if st.button("🔄 全データ更新", use_container_width=True):
        st.cache_data.clear(); st.rerun()

    # バンクロール概要
    bk = load_bankroll()
    cur = bk['current']; ini = bk['initial']; peak = bk['peak']
    pnl = cur - ini
    dd  = (peak - cur) / peak * 100 if peak > 0 else 0
    col_sign = "#3fb950" if pnl >= 0 else "#f85149"

    st.markdown(f"""
<div class="kpi" style="margin-top:12px">
  <div class="kpi-sub">現在資金</div>
  <div class="kpi-val" style="color:{col_sign}">{cur:,.0f}<span style="font-size:1rem">円</span></div>
  <div class="kpi-delta" style="color:{col_sign}">{'▲' if pnl>=0 else '▼'} {abs(pnl):,.0f}円</div>
</div>""", unsafe_allow_html=True)

    st.markdown(f"<div style='color:#8b949e;font-size:.78rem;text-align:center;margin-top:6px'>DD: {dd:.1f}% | Peak: {peak:,.0f}円</div>", unsafe_allow_html=True)

    st.divider()

    # 戦略設定表示
    st.markdown("**⚙️ 戦略設定**")
    st.markdown("""
| 項目 | 値 |
|------|-----|
| Kelly係数 | **0.10** |
| EV閾値 | **5%** |
| 最小オッズ | **5倍** |
| 1日上限 | **20%** |
""")

    # WF判定バッジ
    wf = load_walkforward()
    if wf:
        v = wf.get('verdict','')
        cls = 'box-ok' if '良好' in v else 'box-warn' if '普通' in v else 'box-err'
        st.markdown(f"<div class='{cls}' style='font-size:.8rem;margin-top:8px'>{v}</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("**🚀 クイック実行**")
    st.code("python run_all.py --quick", language="bash")
    st.code("python run_all.py --full-optuna", language="bash")


# ── ヘッダー ────────────────────────────────────────────────
st.markdown("# 🙏 うまなり地蔵AI")
st.caption(f"穴馬専門 高オッズMLシステム | {YEAR}年シーズン | Kelly×0.10 安全運用モード")

# ── タブ ────────────────────────────────────────────────────
tabs = st.tabs([
    "⚡ ライブ予想", "📊 成績サマリー", "💰 資金管理",
    "🏇 馬券戦略", "📈 モデル検証", "🔬 SHAP", "🧬 血統", "🔄 バックテスト", "📚 知識ベース"
])
tab_live, tab_sum, tab_bk, tab_strat, tab_model, tab_shap, tab_blood, tab_bt, tab_kb = tabs


# ════════════════════════════════════════════════════════════
# TAB 1: ライブ予想
# ════════════════════════════════════════════════════════════
with tab_live:
    picks, picks_date = load_picks()
    today_str = datetime.now().strftime("%Y/%m/%d")
    is_today = picks_date == today_str if picks_date else False

    if picks:
        gen = picks.get('generated_at','')[:16].replace('T',' ')
        rs  = picks.get('risk_summary', {})
        approved = picks.get('approved_bets', [])

        st.caption(f"生成: {gen}  |  DD乗数: {rs.get('dd_multiplier',1):.2f}x")

        # KPI 4列
        c1,c2,c3,c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class="kpi">
              <div class="kpi-sub">承認レース</div>
              <div class="kpi-val" style="color:#58a6ff">{rs.get('approved_count',0)}<span style="font-size:1rem">R</span></div>
            </div>""", unsafe_allow_html=True)
        with c2:
            alloc = rs.get('total_allocated',0)
            st.markdown(f"""<div class="kpi">
              <div class="kpi-sub">総投入予定</div>
              <div class="kpi-val" style="color:#e3b341">{alloc:,}<span style="font-size:1rem">円</span></div>
            </div>""", unsafe_allow_html=True)
        with c3:
            ratio = rs.get('day_ratio',0)*100
            color = "#3fb950" if ratio < 15 else "#f85149"
            st.markdown(f"""<div class="kpi">
              <div class="kpi-sub">資金消費率</div>
              <div class="kpi-val" style="color:{color}">{ratio:.1f}<span style="font-size:1rem">%</span></div>
            </div>""", unsafe_allow_html=True)
        with c4:
            mult = rs.get('dd_multiplier',1)
            color = "#3fb950" if mult == 1 else "#e3b341" if mult > 0 else "#f85149"
            label = "正常" if mult==1 else f"縮小{mult:.0%}"
            st.markdown(f"""<div class="kpi">
              <div class="kpi-sub">ベット乗数</div>
              <div class="kpi-val" style="color:{color}">{mult:.2f}<span style="font-size:.9rem">x</span></div>
              <div class="kpi-delta">{label}</div>
            </div>""", unsafe_allow_html=True)

        if is_today:
            st.markdown(f"<div class='sec-head'>🔥 推奨ベット（{picks_date}）</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='sec-head'>🔥 推奨ベット（{picks_date}）</div>", unsafe_allow_html=True)
            st.warning(f"⚠️ 本日（{today_str}）のデータがありません。最新: {picks_date}　→ `python run_all.py --skip-train` を実行してください。")

        for i, bet in enumerate(approved, 1):
            ev  = bet['expected_value'] * 100
            conf= bet.get('confidence', 0) * 100
            odds= bet['odds']
            blood = bet.get('blood_score', 1.0)
            ticket = bet.get('ticket_type', '単勝')
            grade  = bet.get('condition_grade', 'B')
            rv     = bet.get('race_value', 0)

            ev_color  = "#3fb950" if ev > 0 else "#f85149"
            grade_cls = "grade-s" if grade == 'S' else "grade-a" if grade in ('A','B') else ""

            st.markdown(f"""
<div class="bet-card {grade_cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <strong style="font-size:1.1rem;color:#e6edf3">{fmt_race(bet.get('race_code',''))} {str(bet['umaban'])+"番 " if bet.get('umaban') else ""}{bet.get('bamei','')}</strong>
      &nbsp;
      <span class="badge badge-blue">{ticket}</span>
      <span class="badge badge-gold">{odds:.1f}倍</span>
      <span class="badge {'badge-green' if grade in ('S','A') else 'badge-red'}">Grade {grade}</span>
    </div>
    <div style="text-align:right">
      <strong style="color:#e3b341;font-size:1.2rem">{bet['kelly_bet']:,}円</strong>
    </div>
  </div>
  <div style="margin-top:8px;font-size:.85rem;color:#8b949e">
    勝率 {bet['win_probability']*100:.1f}%
    &nbsp;|&nbsp; EV <span style="color:{ev_color}">{ev:+.0f}%</span>
    &nbsp;|&nbsp; 確信度 {conf:.0f}%
    &nbsp;|&nbsp; 血統 {blood:.2f}x
    &nbsp;|&nbsp; レース価値 {rv:.2f}
  </div>
  <div style="margin-top:4px;font-size:.8rem;color:#6e7681">{bet.get('comment','')}</div>
</div>""", unsafe_allow_html=True)

        # Supervisor コメント
        notes = picks.get('supervisor_notes', '')
        if notes:
            st.markdown(f"<div class='box-ok' style='margin-top:12px'>🧠 Supervisor: {notes}</div>",
                        unsafe_allow_html=True)

        with st.expander("📝 SNS投稿テキスト"):
            st.text(picks.get('post_text', ''))

        # 実行ログ
        logs = picks.get('log', [])
        if logs:
            with st.expander("🔍 エージェント実行ログ"):
                st.text('\n'.join(logs[-30:]))

    else:
        st.markdown("<div class='box-warn'>マルチエージェントの出力がありません。<br><code>python pipeline/multi_agent_v2_28.py</code> を実行してください。</div>",
                    unsafe_allow_html=True)

        # レーススコアリングのプレビューだけ表示
        rs_df = load_race_ranking()
        if not rs_df.empty:
            st.markdown("<div class='sec-head'>🏇 本日の参戦候補レース (Grade S/A)</div>", unsafe_allow_html=True)
            top_rs = rs_df[rs_df['grade'].isin(['S','A'])].head(10)
            st.dataframe(top_rs, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# TAB 2: 成績サマリー
# ════════════════════════════════════════════════════════════
with tab_sum:
    tracker = load_tracker()
    bk      = load_bankroll()
    cur = bk['current']; ini = bk['initial']; pnl = cur - ini
    roi_all = cur / ini * 100 if ini > 0 else 100

    # KPI
    c1,c2,c3,c4 = st.columns(4)
    cols_kpi = [c1,c2,c3,c4]
    now = datetime.now()

    if not tracker.empty:
        m_df = tracker[(tracker['date'].dt.year==now.year)&(tracker['date'].dt.month==now.month)]
        m_bet= m_df['bet_amount'].sum(); m_ret = m_df['return_amount'].sum()
        m_roi= m_ret/m_bet*100 if m_bet>0 else 0
        hits = int(tracker['hit'].sum()); n = len(tracker)
        hr   = hits/n*100 if n>0 else 0
    else:
        m_roi = hr = 0; n = 0

    kpis = [
        ("累計損益", f"{'+'if pnl>=0 else ''}{pnl:,.0f}円", "#3fb950" if pnl>=0 else "#f85149", ""),
        ("回収率(全期)", f"{roi_all:.1f}%", "#3fb950" if roi_all>=100 else "#f85149", f"初期 {ini:,.0f}円"),
        ("月次回収率", f"{m_roi:.1f}%", "#3fb950" if m_roi>=100 else "#f85149", f"{now.month}月"),
        ("累計的中率", f"{hr:.1f}%", "#e3b341", f"{hits}/{n}件"),
    ]
    for c, (lbl,val,col,sub) in zip(cols_kpi, kpis):
        with c:
            st.markdown(f"""<div class="kpi">
              <div class="kpi-sub">{lbl}</div>
              <div class="kpi-val" style="color:{col}">{val}</div>
              <div class="kpi-delta" style="color:#8b949e">{sub}</div>
            </div>""", unsafe_allow_html=True)

    # 週次ROI
    if not tracker.empty:
        st.markdown("<div class='sec-head'>📅 週次回収率推移</div>", unsafe_allow_html=True)
        tracker['week'] = tracker['date'].dt.to_period('W').apply(lambda x: x.start_time)
        wkly = tracker.groupby('week').apply(lambda g: pd.Series({
            'roi': g['return_amount'].sum()/g['bet_amount'].sum()*100 if g['bet_amount'].sum()>0 else 0,
            'hits': int(g['hit'].sum()), 'count': len(g)
        })).reset_index()

        if PLOTLY:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=wkly['week'].astype(str), y=wkly['roi'],
                marker_color=wkly['roi'].apply(lambda r:'#3fb950' if r>=100 else '#f85149'),
                name='週次ROI'
            ))
            fig.add_hline(y=100, line_dash='dash', line_color='#8b949e', annotation_text='100%')
            fig.add_hline(y=115, line_dash='dot',  line_color='#3fb950', annotation_text='目標115%')
            fig.update_layout(**_plotly_theme(), height=280, showlegend=False, yaxis_title='回収率(%)')
            st.plotly_chart(fig, use_container_width=True)

        # オッズ帯別
        st.markdown("<div class='sec-head'>📊 オッズ帯別成績</div>", unsafe_allow_html=True)
        tc = tracker.copy()
        tc['band'] = pd.cut(tc['odds'], bins=[0,5,10,20,50,9999],
                             labels=['〜5倍','5〜10倍','10〜20倍','20〜50倍','50倍〜'])
        band_rows = []
        for band, g in tc.groupby('band', observed=True):
            bet=g['bet_amount'].sum(); ret=g['return_amount'].sum()
            band_rows.append({'オッズ帯':str(band),'件数':len(g),
                '的中率':f"{g['hit'].mean()*100:.1f}%",
                '回収率':f"{ret/bet*100:.1f}%" if bet>0 else '-',
                '損益':f"{ret-bet:+,.0f}円"})
        if band_rows:
            st.dataframe(pd.DataFrame(band_rows), use_container_width=True, hide_index=True)
    else:
        st.info("記録なし — `roi_tracker_12.py` でベットを記録してください。")


# ════════════════════════════════════════════════════════════
# TAB 3: 資金管理
# ════════════════════════════════════════════════════════════
with tab_bk:
    bk = load_bankroll()
    cur=bk['current']; ini=bk['initial']; peak=bk['peak']
    pnl=cur-ini; dd_cur=(peak-cur)/peak*100 if peak>0 else 0

    # KPI
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">現在資金</div>
          <div class="kpi-val" style="color:{'#3fb950' if pnl>=0 else '#f85149'}">{cur:,.0f}円</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">ピーク資金</div>
          <div class="kpi-val" style="color:#58a6ff">{peak:,.0f}円</div></div>""", unsafe_allow_html=True)
    with c3:
        dd_color = "#3fb950" if dd_cur<10 else "#e3b341" if dd_cur<20 else "#f85149"
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">現在DD</div>
          <div class="kpi-val" style="color:{dd_color}">{dd_cur:.1f}%</div></div>""", unsafe_allow_html=True)
    with c4:
        kelly_mult = 1.0 if dd_cur<10 else 0.5 if dd_cur<20 else 0.25 if dd_cur<30 else 0.0
        km_color = "#3fb950" if kelly_mult==1 else "#e3b341" if kelly_mult>0 else "#f85149"
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">ベット乗数</div>
          <div class="kpi-val" style="color:{km_color}">{kelly_mult:.2f}x</div>
          <div class="kpi-delta">Kelly×0.10 実効: {0.10*kelly_mult:.3f}</div></div>""", unsafe_allow_html=True)

    # 資金推移
    hist = bk.get('history',[])
    if hist:
        st.markdown("<div class='sec-head'>📈 資金推移</div>", unsafe_allow_html=True)
        hdf = pd.DataFrame(hist)
        hdf['date'] = pd.to_datetime(hdf['date'])
        hdf = hdf.sort_values('date')
        if PLOTLY:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hdf['date'], y=hdf['bankroll_after'],
                mode='lines+markers', name='資金残高',
                line=dict(color='#58a6ff',width=2),
                marker=dict(color=hdf['hit'].map({1:'#3fb950',0:'#f85149'}),size=7),
                fill='tozeroy', fillcolor='rgba(88,166,255,0.06)',
                hovertemplate='%{x|%m/%d}<br>%{y:,.0f}円<extra></extra>'
            ))
            fig.add_hline(y=ini, line_dash='dash', line_color='#8b949e', annotation_text='初期資金')
            fig.update_layout(**_plotly_theme(), height=300, yaxis_title='残高(円)')
            st.plotly_chart(fig, use_container_width=True)

            # DD チャート
            peak_s = hdf['bankroll_after'].cummax()
            dd_s   = (hdf['bankroll_after']-peak_s)/peak_s*100
            fig2 = px.area(x=hdf['date'], y=dd_s, title="ドローダウン推移(%)",
                           color_discrete_sequence=['#f85149'])
            fig2.update_layout(**_plotly_theme(), height=180)
            st.plotly_chart(fig2, use_container_width=True)

    # バンクロール成長シミュレーション
    bk_sim = load_bk_sim()
    if bk_sim and bk_sim.get('history_sample'):
        st.markdown("<div class='sec-head'>🔮 500レース成長シミュレーション</div>", unsafe_allow_html=True)
        hist_s = bk_sim['history_sample']
        c1,c2,c3 = st.columns(3)
        c1.metric("最終資金", f"{bk_sim['final']:,.0f}円", f"{bk_sim['growth_rate']:+.1f}%")
        c2.metric("最大DD",   f"{bk_sim['max_drawdown']*100:.1f}%")
        c3.metric("ピーク",   f"{bk_sim['peak']:,.0f}円")
        if PLOTLY:
            fig = go.Figure(go.Scatter(y=hist_s, mode='lines',
                line=dict(color='#3fb950',width=2),
                fill='tozeroy', fillcolor='rgba(63,185,80,.07)'))
            fig.add_hline(y=bk_sim['initial'], line_dash='dash', line_color='#8b949e')
            fig.update_layout(**_plotly_theme(), height=220,
                              xaxis_title='レース数', yaxis_title='資金(円)')
            st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════
# TAB 4: 馬券戦略
# ════════════════════════════════════════════════════════════
with tab_strat:
    c_left, c_right = st.columns([1,1], gap="large")

    with c_left:
        # レース価値スコアリング
        st.markdown("<div class='sec-head'>🏇 レース価値スコア (race_selector)</div>", unsafe_allow_html=True)
        rs_df = load_race_ranking()
        if not rs_df.empty:
            grade_cnt = rs_df['grade'].value_counts()
            g1,g2,g3,g4 = st.columns(4)
            for col, g, color in [(g1,'S','#f85149'),(g2,'A','#3fb950'),(g3,'B','#58a6ff'),(g4,'C','#8b949e')]:
                cnt = int(grade_cnt.get(g,0))
                with col:
                    st.markdown(f"""<div class="kpi"><div class="kpi-sub">Grade {g}</div>
                      <div class="kpi-val" style="color:{color}">{cnt}</div>
                      <div class="kpi-delta">レース</div></div>""", unsafe_allow_html=True)

            top_s = rs_df[rs_df['grade']=='S'].head(8).copy()
            if not top_s.empty:
                top_s['レース'] = top_s['race_code'].apply(fmt_race)
                if PLOTLY:
                    fig = px.bar(top_s, x='value_score', y='レース',
                                 orientation='h', title="Grade S レース (荒れ×EV)",
                                 color='upset_score',
                                 color_continuous_scale=['#58a6ff','#f85149'])
                    fig.update_layout(**_plotly_theme(), height=280,
                                      yaxis={'categoryorder':'total ascending'},
                                      coloraxis_colorbar_title='荒れ')
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("`python pipeline/race_selector_31.py` を実行")

    with c_right:
        # 馬券種別分布
        st.markdown("<div class='sec-head'>🎟️ 推奨馬券種 (ticket_optimizer)</div>", unsafe_allow_html=True)
        tk_df = load_ticket_recs()
        if not tk_df.empty and 'ticket_type' in tk_df.columns:
            dist = tk_df['ticket_type'].value_counts().reset_index()
            dist.columns = ['馬券種','件数']
            if PLOTLY:
                fig = px.pie(dist, values='件数', names='馬券種',
                             title="推奨馬券種の分布",
                             color_discrete_sequence=['#58a6ff','#3fb950','#e3b341','#f85149','#bc8cff'])
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(**_plotly_theme(), height=260, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # EV比較テーブル（上位10件）
            st.markdown("**EV比較 TOP10**")
            top10 = tk_df.nlargest(10, 'ev') if 'ev' in tk_df.columns else tk_df.head(10)
            top10 = top10.copy()
            if 'race_code' in top10.columns:
                top10.insert(0, 'レース', top10['race_code'].apply(fmt_race))
            show = [c for c in ['レース','ticket_type','est_odds','ev','recommended_bet']
                    if c in top10.columns]
            st.dataframe(top10[show] if show else top10,
                         use_container_width=True, hide_index=True)
        else:
            st.info("`python pipeline/ticket_optimizer_30.py` を実行")

    # 条件別ベット係数
    st.markdown("<div class='sec-head'>⚙️ 条件別ROI係数 (condition_adjuster)</div>", unsafe_allow_html=True)
    cond_df = load_condition_roi()
    if not cond_df.empty:
        c1,c2 = st.columns(2)
        with c1:
            top_s = cond_df[cond_df['grade']=='S'].head(10) if 'grade' in cond_df.columns else cond_df.head(10)
            st.markdown("**得意条件 (Grade S)**")
            show = [c for c in ['cond_key','roi','coeff','n'] if c in top_s.columns]
            st.dataframe(top_s[show], use_container_width=True, hide_index=True)
        with c2:
            worst = cond_df.tail(8)
            st.markdown("**要注意条件 (低係数)**")
            show = [c for c in ['cond_key','roi','coeff','n'] if c in worst.columns]
            st.dataframe(worst[show], use_container_width=True, hide_index=True)
    else:
        st.info("`python pipeline/condition_adjuster_34.py` をモデル学習後に実行")

    # ポートフォリオ結果
    port_path = os.path.join(BASE,"data",f"portfolio_v2_{YEAR}.json")
    port_data = _jload(port_path)
    if port_data:
        st.markdown("<div class='sec-head'>📊 多点買いポートフォリオ最適化</div>", unsafe_allow_html=True)
        s = port_data.get('summary',{})
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("対象レース",  f"{s.get('total_races',0)}R")
        c2.metric("最適ベット数", f"{s.get('total_bets',0)}点")
        c3.metric("総投入額",    f"{s.get('total_amount',0):,}円")
        c4.metric("投入比率",    f"{s.get('portfolio_ratio',0)*100:.1f}%")


# ════════════════════════════════════════════════════════════
# TAB 5: モデル検証
# ════════════════════════════════════════════════════════════
with tab_model:
    perf_hist = load_perf()

    if perf_hist:
        perf_df = pd.DataFrame(perf_hist)
        perf_df['date']    = pd.to_datetime(perf_df['evaluated_at'].str[:10])
        perf_df['roi_pct'] = perf_df['recovery_rate'] * 100
        perf_df['hit_pct'] = perf_df['hit_rate'] * 100

        latest = perf_hist[-1]
        roi_l  = latest['recovery_rate']*100
        box_cls = 'box-ok' if roi_l>=100 else 'box-warn' if roi_l>=80 else 'box-err'
        st.markdown(f"<div class='{box_cls}'>直近評価 ({latest['evaluated_at'][:10]}): "
                    f"回収率 {roi_l:.1f}% | 的中率 {latest['hit_rate']*100:.1f}% | "
                    f"サンプル {latest['total']}件</div>", unsafe_allow_html=True)

        if PLOTLY:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=perf_df['date'], y=perf_df['roi_pct'],
                name='回収率(%)', line=dict(color='#58a6ff',width=2)))
            fig.add_trace(go.Scatter(x=perf_df['date'], y=perf_df['hit_pct'],
                name='的中率(%)', line=dict(color='#e3b341',width=2,dash='dot'), yaxis='y2'))
            fig.add_hline(y=100, line_dash='dash', line_color='#8b949e')
            fig.update_layout(**_plotly_theme(), height=320,
                yaxis=dict(title='回収率(%)'),
                yaxis2=dict(title='的中率(%)', overlaying='y', side='right'))
            st.plotly_chart(fig, use_container_width=True)

        avg3 = np.mean([h['recovery_rate'] for h in perf_hist[-3:]])*100
        if avg3 < 80:
            st.error(f"🚨 直近3回平均 {avg3:.1f}% — 自動再学習推奨")
        else:
            st.success(f"✅ 直近3回平均 {avg3:.1f}% — モデル良好")
    else:
        st.info("`auto_learn_13.py` を実行するとパフォーマンス履歴が表示されます。")

    # モンテカルロ
    mc = load_mc()
    if mc:
        st.markdown("<div class='sec-head'>🎲 モンテカルロ リスク分析</div>", unsafe_allow_html=True)
        rows = []
        for key, r in mc.items():
            frac = key.replace('frac_','').replace('pct','')
            rows.append({'ベット率':f"{frac}%",
                '中央値最終資金':f"{r['median_final']:,.0f}円",
                '破産確率':f"{r['ruin_rate']*100:.1f}%",
                '最大DD中央値':f"{r['median_maxdd']*100:.1f}%",
                '利益確率':f"{r['profit_prob']*100:.1f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# TAB 6: SHAP
# ════════════════════════════════════════════════════════════
with tab_shap:
    st.markdown("<div class='sec-head'>🔬 SHAP 特徴量重要度</div>", unsafe_allow_html=True)
    SHAP_DIR = os.path.join(BASE,"shap_output")
    shap_files = glob.glob(os.path.join(SHAP_DIR,"*.png")) if os.path.exists(SHAP_DIR) else []

    if shap_files:
        summary = [f for f in shap_files if 'summary' in f]
        if summary:
            st.image(summary[-1], caption="SHAP Summary Plot", use_container_width=True)
        waterfalls = [f for f in shap_files if 'waterfall' in f]
        if waterfalls:
            st.markdown("**個別予測根拠 (Waterfall)**")
            cols = st.columns(min(3,len(waterfalls)))
            for i,wf_f in enumerate(waterfalls[:6]):
                with cols[i%3]:
                    name = os.path.basename(wf_f).replace('.png','').replace('waterfall_','')
                    st.image(wf_f, caption=name, use_container_width=True)
        shap_csvs = glob.glob(os.path.join(SHAP_DIR,"*.csv"))
        if shap_csvs:
            sdf = pd.read_csv(shap_csvs[-1], encoding='utf-8-sig')
            if 'feature' in sdf.columns and 'importance' in sdf.columns:
                top20 = sdf.nlargest(20,'importance')
                if PLOTLY:
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
            import subprocess
            with st.spinner("SHAP分析中..."):
                r = subprocess.run(['python','pipeline/shap_analysis.py'],
                    capture_output=True, text=True, cwd=BASE,
                    env={**os.environ,'PYTHONUTF8':'1'})
            if r.returncode == 0: st.success("完了！更新ボタンを押してください。")
            else: st.error(r.stderr[-500:])


# ════════════════════════════════════════════════════════════
# TAB 7: 血統分析
# ════════════════════════════════════════════════════════════
with tab_blood:
    nicks_top = load_nicks()
    nicks_all = load_nicks_all()

    if not nicks_top.empty:
        st.markdown("<div class='sec-head'>🧬 ニックス指数 TOP30（父×母父）</div>", unsafe_allow_html=True)
        show = [c for c in ['chichi','haha_chichi','nick_index','nick_roi',
                             'nick_win_rate','nick_races','nick_significant']
                if c in nicks_top.columns]
        disp = nicks_top.head(30).copy()
        if 'nick_significant' in disp.columns:
            disp['nick_significant'] = disp['nick_significant'].map(
                {True:'★',False:'',1:'★',0:''}).fillna('')
        st.dataframe(disp[show], use_container_width=True, hide_index=True)

        if not nicks_all.empty and PLOTLY and 'nick_index' in nicks_all.columns:
            c1,c2 = st.columns(2)
            with c1:
                fig = px.histogram(nicks_all, x='nick_index', nbins=50,
                                   title="ニックス指数の分布",
                                   color_discrete_sequence=['#58a6ff'])
                fig.add_vline(x=1.0, line_dash='dash', line_color='#8b949e')
                fig.add_vline(x=1.5, line_dash='dot',  line_color='#3fb950')
                fig.update_layout(**_plotly_theme(), height=280)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                if 'chichi' in nicks_all.columns:
                    sire = (nicks_all.groupby('chichi')
                            .agg(avg=('nick_index','mean'), n=('nick_index','count'))
                            .query('n>=5').sort_values('avg',ascending=False).head(15).reset_index())
                    fig = px.bar(sire, x='avg', y='chichi', orientation='h',
                                 title="父系別 平均ニックス指数 TOP15",
                                 color='avg', color_continuous_scale=['#58a6ff','#3fb950'])
                    fig.add_vline(x=1.0, line_dash='dash', line_color='#8b949e')
                    fig.update_layout(**_plotly_theme(), height=280,
                                      yaxis={'categoryorder':'total ascending'},
                                      coloraxis_showscale=False)
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("`python pipeline/nicks_analysis_18.py` を実行すると血統分析が表示されます。")

    opt_p = os.path.join(BASE,"data","optuna_best_params.json")
    if os.path.exists(opt_p):
        with st.expander("🔬 Optuna 最適パラメータ"):
            st.json(_jload(opt_p))


# ════════════════════════════════════════════════════════════
# TAB 8: バックテスト
# ════════════════════════════════════════════════════════════
with tab_bt:
    wf = load_walkforward()
    folds_df = load_wf_folds()

    if wf:
        v = wf.get('verdict','')
        cls = 'box-ok' if '良好' in v else 'box-warn' if '普通' in v else 'box-err'
        st.markdown(f"<div class='{cls}'>{v}</div>", unsafe_allow_html=True)

        c1,c2,c3,c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">平均OOS ROI</div>
              <div class="kpi-val" style="color:#3fb950">{wf.get('avg_roi',0):+.1f}%</div></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">平均的中率</div>
              <div class="kpi-val" style="color:#e3b341">{wf.get('avg_hit_rate',0):.1f}%</div></div>""", unsafe_allow_html=True)
        with c3:
            avg_dd = wf.get('avg_max_dd',0)
            dd_color = "#3fb950" if avg_dd<30 else "#e3b341" if avg_dd<50 else "#f85149"
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">平均最大DD</div>
              <div class="kpi-val" style="color:{dd_color}">{avg_dd:.1f}%</div></div>""", unsafe_allow_html=True)
        with c4:
            n_folds = len(wf.get('folds',[]))
            n_pos   = wf.get('n_positive',0)
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">プラス折</div>
              <div class="kpi-val" style="color:#58a6ff">{n_pos}<span style="font-size:1rem">/{n_folds}</span></div></div>""", unsafe_allow_html=True)

        if not folds_df.empty:
            st.markdown("<div class='sec-head'>📅 折ごとの成績 (アウトオブサンプル)</div>", unsafe_allow_html=True)
            show = [c for c in ['test_year','roi','hit_rate','max_dd','n_bets'] if c in folds_df.columns]
            st.dataframe(folds_df[show].style.format({
                'roi':'{:+.1f}%','hit_rate':'{:.1f}%','max_dd':'{:.1f}%','n_bets':'{:,}'
            }), use_container_width=True, hide_index=True)

            if PLOTLY and 'roi' in folds_df.columns:
                fig = px.bar(folds_df, x='test_year', y='roi',
                             title="年別 OOS ROI (アウトオブサンプル)",
                             color='roi', color_continuous_scale=['#f85149','#3fb950'])
                fig.add_hline(y=0, line_dash='dash', line_color='#8b949e')
                fig.update_layout(**_plotly_theme(), height=260, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("`python pipeline/backtest_walkforward_35.py` を実行してください。")

    # グリッドサーチ ヒートマップ
    grid_df = load_backtest_grid()
    if not grid_df.empty:
        st.markdown("<div class='sec-head'>🗺️ パラメータ最適化ヒートマップ</div>", unsafe_allow_html=True)
        if PLOTLY and all(c in grid_df.columns for c in ['ev_threshold','kelly_fraction','roi']):
            pivot = grid_df.pivot_table(values='roi', index='kelly_fraction', columns='ev_threshold')
            # inf/nan を cap
            pivot = pivot.replace([np.inf,-np.inf], np.nan).fillna(0).clip(-200,2000)
            fig = go.Figure(go.Heatmap(
                z=pivot.values,
                x=[f"EV {v:.0%}" for v in pivot.columns],
                y=[f"Kelly {v:.0%}" for v in pivot.index],
                colorscale='RdYlGn', zmid=0,
                text=[[f"{v:+.0f}%" for v in row] for row in pivot.values],
                texttemplate="%{text}"
            ))
            fig.update_layout(**_plotly_theme(), title="ROI ヒートマップ (EV閾値 × Kelly係数)", height=320)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("**上位パラメータ組み合わせ**")
        top_grid = grid_df.replace([np.inf,-np.inf],np.nan).dropna().head(10)
        show = [c for c in ['ev_threshold','kelly_fraction','roi','hit_rate','max_dd','n_bets'] if c in top_grid.columns]
        st.dataframe(top_grid[show], use_container_width=True, hide_index=True)

    # レーススコアリングフィルタ
    rs_df = load_race_ranking()
    if not rs_df.empty:
        st.markdown("<div class='sec-head'>🏇 参戦推奨レース</div>", unsafe_allow_html=True)
        grade_filter = st.multiselect("グレードフィルタ", ['S','A','B','C'], default=['S','A'])
        filtered = rs_df[rs_df['grade'].isin(grade_filter)].head(50).copy()
        if 'race_code' in filtered.columns:
            filtered.insert(0, 'レース', filtered['race_code'].apply(fmt_race))
            filtered = filtered.drop(columns=['race_code'])
        st.dataframe(filtered, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# TAB 9: 知識ベース
# ════════════════════════════════════════════════════════════
with tab_kb:
    KB_DIR  = os.path.join(BASE, "data", "knowledge_base")
    LATEST  = os.path.join(KB_DIR, "LATEST.json")
    CONF_LOG = os.path.join(KB_DIR, "confidence_history.csv")
    CHANGELOG = os.path.join(KB_DIR, "changelog.md")

    CAT_LABELS = {
        "BLD": "血統", "JKY": "騎手", "TRK": "コース",
        "MKT": "市場歪み", "TRN": "調教", "SEA": "季節",
        "DBT": "新馬戦", "SHG": "障害戦",
    }
    CONF_SOFT, CONF_MEDIUM, CONF_HARD = 0.50, 0.70, 0.80

    def _kb_color(conf: float) -> str:
        if conf >= CONF_HARD:   return "#3fb950"
        if conf >= CONF_MEDIUM: return "#e3b341"
        if conf >= CONF_SOFT:   return "#58a6ff"
        return "#8b949e"

    if not os.path.exists(LATEST):
        st.info("📚 知識ベースがまだ生成されていません。`python pipeline/knowledge_curator_41.py` を実行してください。")
    else:
        kb_state = json.load(open(LATEST, encoding="utf-8"))
        active_items = {k: v for k, v in kb_state.items() if v.get("status") == "active"}
        depr_items   = {k: v for k, v in kb_state.items() if v.get("status") == "deprecated"}

        # ── KPI ────────────────────────────────────────────────
        high_conf = sum(1 for v in active_items.values() if v.get("confidence", 0) >= CONF_HARD)
        mid_conf  = sum(1 for v in active_items.values() if CONF_MEDIUM <= v.get("confidence", 0) < CONF_HARD)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">アクティブ知見</div>
              <div class="kpi-val" style="color:#58a6ff">{len(active_items)}</div></div>""",
              unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">高確信度(≥0.80)</div>
              <div class="kpi-val" style="color:#3fb950">{high_conf}</div></div>""",
              unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">中確信度(≥0.70)</div>
              <div class="kpi-val" style="color:#e3b341">{mid_conf}</div></div>""",
              unsafe_allow_html=True)
        with c4:
            st.markdown(f"""<div class="kpi"><div class="kpi-sub">廃止済み</div>
              <div class="kpi-val" style="color:#8b949e">{len(depr_items)}</div></div>""",
              unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── フィルタ ─────────────────────────────────────────
        col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
        with col_f1:
            cat_filter = st.multiselect(
                "カテゴリ", list(CAT_LABELS.keys()),
                default=list(CAT_LABELS.keys()),
                format_func=lambda x: f"{x} {CAT_LABELS[x]}"
            )
        with col_f2:
            conf_min = st.slider("最小 confidence", 0.0, 1.0, 0.0, 0.05)
        with col_f3:
            sort_by = st.selectbox("並び順", ["confidence↓", "sample_count↓", "作成日↑"])

        # ── テーブル表示 ──────────────────────────────────────
        rows = []
        for item_id, item in active_items.items():
            cat  = item.get("category", "?")
            conf = item.get("confidence", 0.0)
            if cat not in cat_filter or conf < conf_min:
                continue
            rows.append({
                "ID":       item_id,
                "カテゴリ": f"{cat} {CAT_LABELS.get(cat,'')}",
                "条件":     fmt_condition(item.get("condition", {})),
                "知見":     item.get("claim", "")[:60],
                "confidence": conf,
                "n":        item.get("sample_count", 0),
                "lift推定":  item.get("metrics", {}).get("estimated_lift", 1.0),
                "作成":     item.get("created_at", ""),
                "確認日":   item.get("last_verified", ""),
                "使われ方": (
                    "🔴 ハードルール" if conf >= CONF_HARD else
                    "🟡 特徴量追加"   if conf >= CONF_MEDIUM else
                    "🔵 EV boost"     if conf >= CONF_SOFT else
                    "⚫ 待機中"
                ),
            })

        if sort_by == "confidence↓":
            rows.sort(key=lambda x: x["confidence"], reverse=True)
        elif sort_by == "sample_count↓":
            rows.sort(key=lambda x: x["n"], reverse=True)
        else:
            rows.sort(key=lambda x: x["作成"])

        st.markdown(f"<div class='sec-head'>📋 知見一覧（{len(rows)}件）</div>", unsafe_allow_html=True)

        if rows:
            df_kb = pd.DataFrame(rows)
            st.dataframe(
                df_kb.style.background_gradient(subset=["confidence"], cmap="RdYlGn", vmin=0, vmax=1)
                     .format({"confidence": "{:.3f}", "lift推定": "{:.2f}x", "n": "{:,}"}),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("フィルタ条件に一致する知見がありません。")

        # ── 信頼度推移グラフ ─────────────────────────────────
        if os.path.exists(CONF_LOG):
            conf_df = pd.read_csv(CONF_LOG, parse_dates=["date"])
            if not conf_df.empty and PLOTLY:
                st.markdown("<div class='sec-head'>📈 信頼度推移（上位10知見）</div>", unsafe_allow_html=True)
                top_ids = (
                    conf_df.groupby("id")["confidence"].last()
                    .nlargest(10).index.tolist()
                )
                plot_df = conf_df[conf_df["id"].isin(top_ids)]
                fig = px.line(
                    plot_df, x="date", y="confidence", color="id",
                    title="知見 confidence 推移",
                )
                fig.add_hline(y=CONF_HARD,   line_dash="dash", line_color="#3fb950",
                              annotation_text="ハードルール(0.80)")
                fig.add_hline(y=CONF_MEDIUM, line_dash="dash", line_color="#e3b341",
                              annotation_text="特徴量追加(0.70)")
                fig.add_hline(y=CONF_SOFT,   line_dash="dot",  line_color="#58a6ff",
                              annotation_text="EVboost(0.50)")
                fig.update_layout(**_plotly_theme(), height=350)
                st.plotly_chart(fig, use_container_width=True)

        # ── カテゴリ別 分布 ──────────────────────────────────
        if active_items and PLOTLY:
            st.markdown("<div class='sec-head'>🗂️ カテゴリ別 知見数・平均confidence</div>", unsafe_allow_html=True)
            from collections import Counter
            cat_counts = Counter(v.get("category") for v in active_items.values())
            cat_confs  = {
                cat: round(
                    sum(v.get("confidence", 0) for v in active_items.values()
                        if v.get("category") == cat) / max(cnt, 1), 3
                )
                for cat, cnt in cat_counts.items()
            }
            cat_df = pd.DataFrame([
                {"カテゴリ": f"{c} {CAT_LABELS.get(c,'')}", "件数": n, "平均confidence": cat_confs.get(c, 0)}
                for c, n in cat_counts.most_common()
            ])
            c_left, c_right = st.columns(2)
            with c_left:
                fig_pie = px.pie(cat_df, names="カテゴリ", values="件数",
                                 title="カテゴリ構成比", hole=0.4)
                fig_pie.update_layout(**_plotly_theme(), height=280)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c_right:
                fig_bar = px.bar(cat_df, x="カテゴリ", y="平均confidence",
                                 title="カテゴリ別 平均confidence",
                                 color="平均confidence",
                                 color_continuous_scale=["#f85149", "#e3b341", "#3fb950"])
                fig_bar.add_hline(y=CONF_HARD, line_dash="dash", line_color="#8b949e")
                fig_bar.update_layout(**_plotly_theme(), height=280, coloraxis_showscale=False)
                st.plotly_chart(fig_bar, use_container_width=True)

        # ── 変更履歴 ────────────────────────────────────────
        if os.path.exists(CHANGELOG):
            with st.expander("📋 変更履歴 (changelog.md)"):
                st.markdown(open(CHANGELOG, encoding="utf-8").read())

        # ── 手動実行ボタン ───────────────────────────────────
        st.markdown("<div class='sec-head'>⚙️ 手動操作</div>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🔄 知識ベースを今すぐ更新（直近7日）"):
                with st.spinner("Haiku で知見を抽出中..."):
                    try:
                        from pipeline.knowledge_curator_41 import run_knowledge_curator
                        run_knowledge_curator(days=7)
                        st.success("更新完了！ページを再読込してください。")
                    except Exception as e:
                        st.error(f"エラー: {e}")
        with b2:
            if st.button("📸 スナップショットを強制作成"):
                with st.spinner("スナップ作成中..."):
                    try:
                        from pipeline.knowledge_curator_41 import run_knowledge_curator
                        run_knowledge_curator(days=7, force_snapshot=True)
                        st.success("スナップ作成完了！")
                    except Exception as e:
                        st.error(f"エラー: {e}")


# ── フッター ─────────────────────────────────────────────────
st.divider()
st.caption("🙏 うまなり地蔵AI v2 | Kelly×0.10 安全運用 | データと閻魔大王の御加護を信じよ👹")
