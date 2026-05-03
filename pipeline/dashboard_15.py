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
DATA_DIR = os.path.join(BASE, "data")

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
/* ─ Theme tokens ─ */
:root {
    --bg: #0b1020;
    --panel: #111827;
    --panel-2: #131d2f;
    --line: #263247;
    --text: #e5eefc;
    --muted: #8da2c0;
    --accent: #77a7ff;
    --accent-2: #8ce6c9;
    --warm: #f3c96b;
    --hot: #ff8a6b;
}

/* ─ グローバル ─ */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(119,167,255,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(140,230,201,0.10), transparent 26%),
        linear-gradient(180deg, #08101f 0%, #0b1020 42%, #09111d 100%);
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f1728 0%, #101a2d 100%);
    border-right: 1px solid var(--line);
}
h1,h2,h3 { color: var(--text) !important; }
p, li, span, label, div { color: var(--text); }

/* ─ Hero ─ */
.hero {
    background: linear-gradient(135deg, rgba(17,24,39,.98), rgba(15,23,42,.92));
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 18px 20px;
    margin: 6px 0 16px;
    box-shadow: 0 14px 40px rgba(0,0,0,.22);
}
.hero-top {
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:16px;
    flex-wrap:wrap;
}
.hero-title {
    font-size: 2rem;
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: 0;
    color: var(--text);
}
.hero-sub {
    margin-top: 6px;
    color: var(--muted);
    font-size: .92rem;
}
.hero-meta {
    display:flex;
    gap:8px;
    flex-wrap:wrap;
}
.pill {
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding: 7px 11px;
    border-radius: 999px;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.08);
    font-size: .82rem;
    color: var(--text);
}
.pill.accent { border-color: rgba(119,167,255,.28); background: rgba(119,167,255,.10); }
.pill.green  { border-color: rgba(140,230,201,.28); background: rgba(140,230,201,.10); }
.pill.warm   { border-color: rgba(243,201,107,.28); background: rgba(243,201,107,.10); }

/* ─ KPI カード ─ */
.kpi {
    background: linear-gradient(145deg, rgba(17,24,39,.98), rgba(21,29,44,.96));
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    transition: transform .2s;
}
.kpi:hover { transform: translateY(-2px); border-color: var(--accent); }
.kpi-val  { font-size: 2.2rem; font-weight: 700; line-height: 1.1; }
.kpi-sub  { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
.kpi-delta{ font-size: 0.85rem; margin-top: 6px; }

/* ─ ベットカード ─ */
.bet-card {
    background: linear-gradient(145deg, rgba(17,24,39,.98), rgba(18,28,44,.96));
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
    border-bottom: 1px solid var(--line);
    padding-bottom: 6px;
    margin: 20px 0 14px;
    font-size: 1rem;
    font-weight: 700;
    color: var(--accent);
}

/* ─ アラートボックス ─ */
.box-ok   { background:#0d2818; border:1px solid #238636; border-radius:8px; padding:12px; color:#aff5b4; }
.box-warn { background:#2d2300; border:1px solid #9e6a03; border-radius:8px; padding:12px; color:#e3b341; }
.box-err  { background:#2d0f0f; border:1px solid #da3633; border-radius:8px; padding:12px; color:#ff7b72; }

/* ─ タブ ─ */
button[data-baseweb="tab"] { font-size:.9rem !important; }

/* ─ Live monitor ─ */
.live-shell {
    background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(12,18,31,.96));
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 16px;
}
.live-grid {
    display:grid;
    grid-template-columns: 1.35fr .95fr;
    gap: 14px;
}
.live-list {
    display:flex;
    flex-direction:column;
    gap:10px;
}
.race-line {
    display:flex;
    justify-content:space-between;
    gap:12px;
    align-items:center;
    padding: 11px 12px;
    border-radius: 10px;
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.06);
}
.race-line strong { color: var(--text); }
.race-line small { color: var(--muted); }
.trend-up { color: #ff8a6b; }
.trend-down { color: #8ce6c9; }
.trend-stable { color: #8da2c0; }
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
def load_ticket_recs_summary():
    path = os.path.join(BASE, "data", f"ticket_recommendations_{YEAR}.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()

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
                font_color='#e5eefc', margin=dict(l=8,r=8,t=36,b=8),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))


def _latest_file(pattern: str):
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


@st.cache_data(ttl=120)
def load_odds_config():
    return _jload(os.path.join(BASE, "data", "odds_monitor_config.json")) or {}


@st.cache_data(ttl=60)
def load_odds_snapshots(limit: int = 8):
    files = sorted(
        glob.glob(os.path.join(BASE, "data", "odds_snapshot_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )[:limit]
    snaps = []
    for f in files:
        data = _jload(f)
        if data:
            snaps.append({"file": f, "data": data})
    return snaps


def _flatten_snapshot_payload(payload):
    rows = []
    for race in payload:
        race_id = str(race.get("race_id", ""))
        ts = race.get("timestamp")
        title = race.get("title", "")
        horses = race.get("horses", {}) or {}
        for name, odds in horses.items():
            rows.append({
                "race_id": race_id,
                "title": title,
                "timestamp": ts,
                "bamei": name,
                "tansho": float(odds.get("tansho", 0) or 0),
                "fukusho_min": float(odds.get("fukusho_min", 0) or 0),
                "fukusho_max": float(odds.get("fukusho_max", 0) or 0),
                "ninki": int(odds.get("ninki", 0) or 0),
                "umaban": int(odds.get("umaban", 0) or 0),
            })
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_live_monitor():
    snaps = load_odds_snapshots(8)
    cfg = load_odds_config()
    if not snaps:
        return {"config": cfg, "latest": None, "prev": None, "latest_df": pd.DataFrame(), "prev_df": pd.DataFrame()}

    latest = snaps[0]
    prev = snaps[1] if len(snaps) > 1 else None
    latest_df = _flatten_snapshot_payload(latest["data"])
    prev_df = _flatten_snapshot_payload(prev["data"]) if prev else pd.DataFrame()
    return {"config": cfg, "latest": latest, "prev": prev, "latest_df": latest_df, "prev_df": prev_df}


def _compute_movement(latest_df: pd.DataFrame, prev_df: pd.DataFrame, sharp_drop=-5.0, steam_rise=10.0, drift_rise=5.0):
    if latest_df.empty:
        return latest_df
    if prev_df.empty:
        out = latest_df.copy()
        out["delta_pct"] = 0.0
        out["movement"] = "STABLE"
        return out

    cols = ["race_id", "bamei", "tansho", "ninki", "umaban", "title"]
    cur = latest_df[cols].rename(columns={"tansho": "current"})
    prv = prev_df[["race_id", "bamei", "tansho"]].rename(columns={"tansho": "opening"})
    out = cur.merge(prv, on=["race_id", "bamei"], how="left")
    out["opening"] = out["opening"].fillna(out["current"])
    out["delta_pct"] = (out["current"] - out["opening"]) / out["opening"].clip(lower=0.1) * 100

    def classify(delta):
        if delta <= sharp_drop:
            return "SHARP"
        if delta >= steam_rise:
            return "STEAM"
        if delta >= drift_rise:
            return "DRIFT"
        return "STABLE"

    out["movement"] = out["delta_pct"].apply(classify)
    return out.sort_values("delta_pct")


def _movement_color(mv: str) -> str:
    return {
        "SHARP": "#8ce6c9",
        "STEAM": "#ff8a6b",
        "DRIFT": "#f3c96b",
        "STABLE": "#8da2c0",
    }.get(mv, "#8da2c0")


def _render_status_strip():
    picks, picks_date = load_picks()
    monitor = load_live_monitor()
    cfg = monitor["config"]
    latest = monitor["latest"]
    latest_df = monitor["latest_df"]
    prev_df = monitor["prev_df"]
    movement = _compute_movement(
        latest_df,
        prev_df,
        sharp_drop=cfg.get("sharp_drop_threshold", -0.05) * 100,
        steam_rise=cfg.get("steam_rise_threshold", 0.10) * 100,
        drift_rise=cfg.get("drift_rise_threshold", 0.05) * 100,
    )
    live_ok = bool(latest)
    sharp_count = int((movement["movement"] == "SHARP").sum()) if not movement.empty else 0
    steam_count = int((movement["movement"] == "STEAM").sum()) if not movement.empty else 0
    last_ts = latest["data"][0]["timestamp"] if latest and latest.get("data") else ""

    cols = st.columns([1.7, 1, 1, 1, 1])
    with cols[0]:
        st.markdown(
            f"""
            <div class="hero">
              <div class="hero-top">
                <div>
                  <div class="hero-title">🙏 うまなり地蔵AI</div>
                  <div class="hero-sub">穴馬専門の予想・資金管理・リアル監視を一画面に集約した運用ボード</div>
                </div>
                <div class="hero-meta">
                  <span class="pill {'green' if live_ok else 'warm'}">{'LIVE' if live_ok else 'NO SNAPSHOT'}</span>
                  <span class="pill accent">更新 {datetime.now().strftime('%m/%d %H:%M')}</span>
                  <span class="pill">監視間隔 {cfg.get('poll_interval_sec', 60)}s</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">最新スナップ</div>
            <div class="kpi-val" style="color:#77a7ff">{'稼働' if live_ok else '待機'}</div>
            <div class="kpi-delta">{last_ts[:16].replace('T',' ') if last_ts else '未取得'}</div></div>""",
            unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">Sharp</div>
            <div class="kpi-val" style="color:#8ce6c9">{sharp_count}</div>
            <div class="kpi-delta">資金流入</div></div>""", unsafe_allow_html=True)
    with cols[3]:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">Steam</div>
            <div class="kpi-val" style="color:#ff8a6b">{steam_count}</div>
            <div class="kpi-delta">資金離脱</div></div>""", unsafe_allow_html=True)
    with cols[4]:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">買い目</div>
            <div class="kpi-val" style="color:#f3c96b">{len((picks or {}).get('approved_bets', []))}</div>
            <div class="kpi-delta">{picks_date or '未生成'}</div></div>""", unsafe_allow_html=True)


def _latest_snapshot_summary():
    monitor = load_live_monitor()
    latest = monitor["latest"]
    latest_df = monitor["latest_df"]
    prev_df = monitor["prev_df"]
    cfg = monitor["config"]
    if latest_df.empty:
        return None
    mv = _compute_movement(
        latest_df,
        prev_df,
        sharp_drop=cfg.get("sharp_drop_threshold", -0.05) * 100,
        steam_rise=cfg.get("steam_rise_threshold", 0.10) * 100,
        drift_rise=cfg.get("drift_rise_threshold", 0.05) * 100,
    )
    summary = {
        "race_count": latest_df["race_id"].nunique(),
        "horse_count": len(latest_df),
        "sharp_count": int((mv["movement"] == "SHARP").sum()) if not mv.empty else 0,
        "steam_count": int((mv["movement"] == "STEAM").sum()) if not mv.empty else 0,
        "latest_title": latest["data"][0]["title"] if latest and latest.get("data") else "",
        "latest_time": latest["data"][0]["timestamp"] if latest and latest.get("data") else "",
        "movement": mv,
        "config": cfg,
    }
    return summary


def _build_race_trend_df(race_id: str, top_n: int = 8):
    snaps = load_odds_snapshots(8)
    if not snaps:
        return pd.DataFrame()

    latest_df = _flatten_snapshot_payload(snaps[0]["data"])
    race_latest = latest_df[latest_df["race_id"] == race_id].copy()
    if race_latest.empty:
        return pd.DataFrame()

    keep_names = (
        race_latest.nsmallest(top_n, "tansho")
        .sort_values("tansho")
        ["bamei"]
        .tolist()
    )

    rows = []
    for snap in reversed(snaps):
        df = _flatten_snapshot_payload(snap["data"])
        race = df[(df["race_id"] == race_id) & (df["bamei"].isin(keep_names))]
        ts = None
        if not race.empty:
            ts = pd.to_datetime(race["timestamp"].iloc[0], errors="coerce")
        for _, row in race.iterrows():
            rows.append({
                "timestamp": ts if pd.notna(ts) else pd.to_datetime(snap["data"][0].get("timestamp", None), errors="coerce"),
                "bamei": row["bamei"],
                "tansho": row["tansho"],
                "ninki": row["ninki"],
                "race_id": race_id,
            })
    return pd.DataFrame(rows)


@st.fragment(run_every="30s")
def render_realtime_monitor():
    summary = _latest_snapshot_summary()
    if not summary:
        st.markdown(
            "<div class='box-warn'>リアルタイムオッズのスナップショットがありません。`pipeline/odds_scraper_36.py` を実行すると監視画面が動きます。</div>",
            unsafe_allow_html=True,
        )
        return

    movement = summary["movement"]
    latest_df = load_live_monitor()["latest_df"]
    cfg = summary["config"]

    st.markdown("<div class='live-shell'>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">監視レース</div>
            <div class="kpi-val" style="color:#77a7ff">{summary['race_count']}</div>
            <div class="kpi-delta">最新スナップ</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">監視頭数</div>
            <div class="kpi-val" style="color:#8ce6c9">{summary['horse_count']}</div>
            <div class="kpi-delta">対象馬</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">Sharp</div>
            <div class="kpi-val" style="color:#8ce6c9">{summary['sharp_count']}</div>
            <div class="kpi-delta">下落 監視</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi"><div class="kpi-sub">Steam</div>
            <div class="kpi-val" style="color:#ff8a6b">{summary['steam_count']}</div>
            <div class="kpi-delta">上昇 監視</div></div>""", unsafe_allow_html=True)

    left, right = st.columns([1.28, 0.92], gap="large")
    race_map = latest_df.groupby("race_id")["title"].first().sort_index()
    race_options = list(race_map.index)
    default_idx = 0
    if summary["sharp_count"] and not movement.empty:
        sharp_races = movement[movement["movement"] == "SHARP"]["race_id"].value_counts()
        if len(sharp_races):
            sharp_race = sharp_races.index[0]
            if sharp_race in race_options:
                default_idx = race_options.index(sharp_race)
    with left:
        selected_race = st.selectbox(
            "注目レース",
            race_options,
            index=default_idx,
            format_func=lambda rc: f"{fmt_race(rc)}  {race_map.get(rc, '')[:24]}",
            label_visibility="collapsed",
        )
        trend_df = _build_race_trend_df(selected_race, top_n=8)
        if not trend_df.empty and PLOTLY:
            fig = px.line(
                trend_df,
                x="timestamp",
                y="tansho",
                color="bamei",
                markers=True,
                title=f"オッズ推移 {fmt_race(selected_race)}",
            )
            fig.update_layout(**_plotly_theme(), height=360, yaxis_title="単勝オッズ")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("選択レースの時系列データが足りません。")

        race_now = latest_df[latest_df["race_id"] == selected_race].sort_values("tansho")
        if not race_now.empty:
            show_cols = [c for c in ["umaban", "bamei", "tansho", "ninki"] if c in race_now.columns]
            race_now = race_now[show_cols].copy()
            race_now.columns = ["馬番", "馬名", "単勝", "人気"]
            st.dataframe(
                race_now.style.format({"単勝": "{:.1f}", "人気": "{:d}"}),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("<div class='sec-head'>⚡ 変動一覧</div>", unsafe_allow_html=True)
        if movement.empty:
            st.info("前回スナップとの差分がありません。")
        else:
            top_move = movement.head(12).copy()
            for _, row in top_move.iterrows():
                color = _movement_color(row["movement"])
                delta = row["delta_pct"]
                st.markdown(
                    f"""
                    <div class="race-line">
                      <div>
                        <strong>{fmt_race(row['race_id'])}</strong><br>
                        <small>{row['bamei']} / {row.get('title','')[:20]}</small>
                      </div>
                      <div style="text-align:right">
                        <strong style="color:{color}">{row['movement']}</strong><br>
                        <small class="trend-{'down' if delta < 0 else 'up' if delta > 0 else 'stable'}">{delta:+.1f}%</small>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("<div class='sec-head'>⚙️ 監視設定</div>", unsafe_allow_html=True)
        cfg_rows = pd.DataFrame(
            [
                {"項目": "Sharp閾値", "値": f"{cfg.get('sharp_drop_threshold', -0.05):.0%}"},
                {"項目": "Steam閾値", "値": f"{cfg.get('steam_rise_threshold', 0.10):.0%}"},
                {"項目": "Drift閾値", "値": f"{cfg.get('drift_rise_threshold', 0.05):.0%}"},
                {"項目": "Poll間隔", "値": f"{cfg.get('poll_interval_sec', 60)} 秒"},
            ]
        )
        st.dataframe(cfg_rows, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


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
_render_status_strip()

# ── タブ ────────────────────────────────────────────────────
tabs = st.tabs([
    "📋 今日の予想", "⚡ ライブ予想", "📡 リアルタイム監視", "📊 成績サマリー", "💰 資金管理",
    "🏇 馬券戦略", "📈 モデル検証", "🔬 SHAP", "🧬 血統", "🔄 バックテスト", "📚 知識ベース", "🐎 レース種別",
    "🤖 エージェント監視",
])
tab_today, tab_live, tab_monitor, tab_sum, tab_bk, tab_strat, tab_model, tab_shap, tab_blood, tab_bt, tab_kb, tab_rt, tab_agents = tabs


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
# TAB 2: リアルタイム監視
# ════════════════════════════════════════════════════════════
with tab_monitor:
    st.markdown("<div class='sec-head'>📡 リアルタイム監視ボード</div>", unsafe_allow_html=True)
    st.caption("最新オッズスナップショットを読み込み、Sharp / Steam / Drift をそのまま追跡します。")
    render_realtime_monitor()


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
        if 'date' in hdf.columns:
            hdf['date'] = pd.to_datetime(hdf['date'])
        elif 'month' in hdf.columns:
            hdf['date'] = pd.to_datetime(hdf['month'].astype(str) + "-01", errors='coerce')
        else:
            hdf['date'] = pd.date_range(end=pd.Timestamp.now(), periods=len(hdf), freq='D')
        hdf = hdf.sort_values('date')
        value_col = 'bankroll_after' if 'bankroll_after' in hdf.columns else 'balance' if 'balance' in hdf.columns else None
        if PLOTLY:
            fig = go.Figure()
            if value_col:
                marker_color = '#58a6ff'
                if 'hit' in hdf.columns:
                    marker_color = hdf['hit'].map({1:'#3fb950',0:'#f85149'}).fillna('#58a6ff')
                fig.add_trace(go.Scatter(
                    x=hdf['date'], y=hdf[value_col],
                    mode='lines+markers', name='資金残高',
                    line=dict(color='#58a6ff',width=2),
                    marker=dict(color=marker_color,size=7),
                    fill='tozeroy', fillcolor='rgba(88,166,255,0.06)',
                    hovertemplate='%{x|%Y-%m}<br>%{y:,.0f}円<extra></extra>'
                ))
            fig.add_hline(y=ini, line_dash='dash', line_color='#8b949e', annotation_text='初期資金')
            fig.update_layout(**_plotly_theme(), height=300, yaxis_title='残高(円)')
            st.plotly_chart(fig, use_container_width=True)

            # DD チャート
            if value_col:
                peak_s = hdf[value_col].cummax()
                dd_s   = (hdf[value_col]-peak_s)/peak_s*100
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
            m1, m2, m3, m4 = st.columns(4)
            avg_ev = float(tk_df['ev'].mean() * 100) if 'ev' in tk_df.columns else 0.0
            max_ev = float(tk_df['ev'].max() * 100) if 'ev' in tk_df.columns else 0.0
            avg_bet = float(tk_df['recommended_bet'].mean()) if 'recommended_bet' in tk_df.columns else 0.0
            with m1:
                st.metric("推奨R数", len(tk_df))
            with m2:
                st.metric("平均期待値", f"{avg_ev:+.1f}%")
            with m3:
                st.metric("最大期待値", f"{max_ev:+.1f}%")
            with m4:
                st.metric("平均推奨額", f"{avg_bet:,.0f}円")

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
            st.markdown("**推奨一覧 TOP10**")
            top10 = tk_df.nlargest(10, 'ev') if 'ev' in tk_df.columns else tk_df.head(10)
            top10 = top10.copy()
            if 'race_code' in top10.columns:
                top10.insert(0, 'レース', top10['race_code'].apply(fmt_race))
            if 'horses' in top10.columns:
                top10['本命'] = top10['horses'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else "-")
                top10['相手'] = top10['horses'].apply(lambda x: " / ".join(x[1:3]) if isinstance(x, list) and len(x) > 1 else "-")
            rename_map = {
                'ticket_type': '馬券種',
                'est_odds': '推定オッズ',
                'ev': '期待値',
                'recommended_bet': '推奨金額',
                'reason': '理由',
            }
            top10 = top10.rename(columns=rename_map)
            show = [c for c in ['レース','馬券種','本命','相手','推定オッズ','期待値','推奨金額','理由']
                    if c in top10.columns]
            df_show = top10[show] if show else top10
            if '期待値' in df_show.columns:
                df_show = df_show.copy()
                df_show['期待値'] = pd.to_numeric(df_show['期待値'], errors='coerce').fillna(0).map(lambda x: f"{x*100:+.1f}%")
            if '推定オッズ' in df_show.columns:
                df_show['推定オッズ'] = pd.to_numeric(df_show['推定オッズ'], errors='coerce').fillna(0).map(lambda x: f"{x:.1f}倍")
            if '推奨金額' in df_show.columns:
                df_show['推奨金額'] = pd.to_numeric(df_show['推奨金額'], errors='coerce').fillna(0).map(lambda x: f"{int(x):,}円")
            st.dataframe(df_show,
                         use_container_width=True, hide_index=True)
            summary_md = load_ticket_recs_summary()
            if summary_md:
                with st.expander("📄 馬券推薦サマリー"):
                    st.markdown(summary_md)
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
    SUMMARY = os.path.join(KB_DIR, "knowledge_summary.json")
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
        kb_summary = json.load(open(SUMMARY, encoding="utf-8")) if os.path.exists(SUMMARY) else {}
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

        # ── 最新サマリー ─────────────────────────────────────
        if kb_summary:
            st.markdown("<div class='sec-head'>🧠 最新サマリー</div>", unsafe_allow_html=True)
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.metric("更新日時", kb_summary.get("generated_at", "")[:19] or "-")
            with s2:
                st.metric("高確信度", kb_summary.get("high_conf_count", 0))
            with s3:
                st.metric("中確信度", kb_summary.get("medium_conf_count", 0))
            with s4:
                st.metric("低確信度", kb_summary.get("low_conf_count", 0))

            cat_rows = []
            for cat, info in kb_summary.get("categories", {}).items():
                cat_rows.append({
                    "カテゴリ": f"{cat} {info.get('label','')}",
                    "件数": info.get("count", 0),
                    "高確信度": info.get("high_conf", 0),
                    "平均confidence": info.get("avg_confidence", 0),
                })
            if cat_rows:
                st.dataframe(
                    pd.DataFrame(cat_rows).sort_values("件数", ascending=False),
                    use_container_width=True, hide_index=True
                )

            top_items = kb_summary.get("top_items", [])[:5]
            if top_items:
                top_df = pd.DataFrame([{
                    "ID": x.get("id", ""),
                    "カテゴリ": x.get("category", ""),
                    "confidence": x.get("confidence", 0),
                    "n": x.get("sample_count", 0),
                    "条件": x.get("condition_summary", ""),
                    "知見": x.get("claim", "")[:50],
                } for x in top_items])
                st.dataframe(
                    top_df.style.background_gradient(subset=["confidence"], cmap="RdYlGn", vmin=0, vmax=1)
                              .format({"confidence": "{:.3f}", "n": "{:,}"}),
                    use_container_width=True, hide_index=True
                )

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

# ════════════════════════════════════════════════════════════
# TAB 11: race type breakdown + EV boost map
# ════════════════════════════════════════════════════════════
with tab_rt:
    st.markdown("### Race type performance & EV boost map")

    EV_CSV = os.path.join(BASE, f"ev_analysis_{datetime.now().year}.csv")
    BOOST_MAP = os.path.join(BASE, "data", "knowledge_base", "ev_boost_map.json")

    RTYPE_LABELS = {
        "debut":    "New Horse",
        "shogai":   "Obstacle",
        "handicap": "Handicap",
        "default":  "Standard",
    }
    RTYPE_THRESHOLDS = {
        "debut":    0.10,
        "shogai":   0.10,
        "handicap": 0.20,
        "default":  0.15,
    }

    # ── EV CSV section ────────────────────────────────────────
    if os.path.exists(EV_CSV):
        ev_df = pd.read_csv(EV_CSV, encoding="utf-8-sig", low_memory=False)

        if "race_type" not in ev_df.columns:
            st.info("race_type column not found -- run ev_engine_10.py to regenerate.")
        else:
            ev_df["race_type_label"] = ev_df["race_type"].map(RTYPE_LABELS).fillna("Standard")

            # KPI row
            c1, c2, c3, c4 = st.columns(4)
            total = len(ev_df)
            pos_mask = ev_df["expected_value"] >= ev_df.get("ev_threshold", pd.Series(0.15, index=ev_df.index))
            pos = pos_mask.sum() if "ev_threshold" in ev_df.columns else (ev_df["expected_value"] >= 0.15).sum()
            with c1:
                st.metric("Total horses", f"{total:,}")
            with c2:
                st.metric("Positive EV", f"{pos:,}")
            with c3:
                avg_ev = ev_df["expected_value"].mean() * 100
                st.metric("Avg EV", f"{avg_ev:+.1f}%")
            with c4:
                avg_odds = ev_df["odds_decimal"].mean() if "odds_decimal" in ev_df.columns else 0
                st.metric("Avg odds", f"{avg_odds:.1f}x")

            st.markdown("---")

            # Per race_type table
            st.markdown("#### EV by race type")
            rows = []
            for rtype, grp in ev_df.groupby("race_type"):
                label     = RTYPE_LABELS.get(rtype, rtype)
                threshold = RTYPE_THRESHOLDS.get(rtype, 0.15)
                pos_grp   = grp[grp["expected_value"] >= threshold]
                hit_col   = "kakutei_chakujun" if "kakutei_chakujun" in grp.columns else None
                hit_rate  = (grp[hit_col] == 1).mean() * 100 if hit_col else float("nan")
                if hit_col and "odds_decimal" in grp.columns:
                    ret = (grp[grp[hit_col] == 1]["odds_decimal"] * 100).sum()
                    roi = ret / (len(grp) * 100) * 100 if len(grp) > 0 else float("nan")
                else:
                    roi = float("nan")
                rows.append({
                    "race type": label,
                    "horses": len(grp),
                    "positive EV": len(pos_grp),
                    "EV threshold": f"{threshold*100:.0f}%",
                    "avg EV": f"{grp['expected_value'].mean()*100:+.1f}%",
                    "hit rate": f"{hit_rate:.1f}%" if hit_rate == hit_rate else "—",
                    "ROI": f"{roi:.1f}%" if roi == roi else "—",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # EV distribution bar chart per race type
            st.markdown("#### EV distribution per race type")
            try:
                import altair as alt
                chart_df = ev_df[["expected_value", "race_type_label"]].copy()
                chart_df["ev_pct"] = chart_df["expected_value"] * 100
                chart = (
                    alt.Chart(chart_df)
                    .mark_bar(opacity=0.7)
                    .encode(
                        x=alt.X("ev_pct:Q", bin=alt.Bin(step=5), title="EV (%)"),
                        y=alt.Y("count()", title="horses"),
                        color=alt.Color("race_type_label:N", title="race type"),
                        tooltip=["race_type_label", "count()"],
                    )
                    .properties(height=280)
                )
                st.altair_chart(chart, use_container_width=True)
            except Exception as e:
                st.caption(f"chart skipped: {e}")
    else:
        st.info(f"ev_analysis_{datetime.now().year}.csv not found -- run ev_engine_10.py")

    st.markdown("---")

    # ── EV boost map section ──────────────────────────────────
    st.markdown("#### knowledge_base EV boost map")

    if os.path.exists(BOOST_MAP):
        with open(BOOST_MAP, encoding="utf-8") as _f:
            boost_map = json.load(_f)

        st.caption(f"{len(boost_map)} boost entries loaded from ev_boost_map.json")

        # Show as table (top 50 by boost value)
        boost_rows = sorted(
            [{"key": k, "boost": float(v)} for k, v in boost_map.items()],
            key=lambda r: abs(r["boost"] - 1.0), reverse=True
        )[:50]
        if boost_rows:
            bdf = pd.DataFrame(boost_rows)
            bdf["boost_pct"] = bdf["boost"].apply(lambda x: f"{(x-1)*100:+.0f}%")
            bdf["type"] = bdf["key"].apply(
                lambda k: "race_code" if k.isdigit() and len(k) >= 8 else "sire_venue"
            )
            st.dataframe(
                bdf[["key", "type", "boost", "boost_pct"]].rename(
                    columns={"key": "key", "type": "type",
                             "boost": "multiplier", "boost_pct": "effect"}
                ),
                use_container_width=True, height=350
            )

        # Manual refresh button
        if st.button("Refresh boost map (run knowledge_curator)"):
            with st.spinner("running knowledge_curator_41..."):
                try:
                    from pipeline.knowledge_curator_41 import run_knowledge_curator
                    run_knowledge_curator(days=7)
                    st.success("Done! Reload the page.")
                except Exception as e:
                    st.error(f"Error: {e}")
    else:
        st.info("ev_boost_map.json not found -- run `python pipeline/knowledge_curator_41.py`")
        if st.button("Generate boost map now"):
            with st.spinner("running knowledge_curator_41..."):
                try:
                    from pipeline.knowledge_curator_41 import run_knowledge_curator
                    run_knowledge_curator(days=7)
                    st.success("Done! Reload the page.")
                except Exception as e:
                    st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 12: 今日の予想
# ════════════════════════════════════════════════════════════
with tab_today:
    import psycopg2, subprocess, sys as _sys

    today_dt  = datetime.now()
    today_str = today_dt.strftime("%Y%m%d")

    # ── データ読み込みヘルパー ──────────────────────────────
    @st.cache_data(ttl=120)
    def _load_today_ev():
        """ev_analysis_YYYY.csv から当日分を抽出"""
        path = os.path.join(BASE, f"ev_analysis_{YEAR}.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
        if "race_code" in df.columns:
            df = df[df["race_code"].astype(str).str.startswith(today_str)]
        return df

    @st.cache_data(ttl=120)
    def _load_race_ranking():
        path = os.path.join(DATA_DIR, f"race_ranking_{YEAR}.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")

    @st.cache_data(ttl=60)
    def _load_odds_snapshot():
        path = os.path.join(DATA_DIR, f"odds_snapshot_{today_str}.json")
        if not os.path.exists(path):
            return {}
        try:
            return json.loads(open(path, encoding="utf-8").read())
        except Exception:
            return {}

    ev_df   = _load_today_ev()
    rank_df = _load_race_ranking()
    snap    = _load_odds_snapshot()

    # ── ヘッダー KPI ────────────────────────────────────────
    st.markdown(f"### 📋 {today_dt.strftime('%Y年%m月%d日（%a）')} 本日の推奨ベット")

    col_a, col_b, col_c, col_d = st.columns(4)
    n_picks  = len(ev_df) if not ev_df.empty else 0
    n_gradeS = len(rank_df[rank_df["grade"] == "S"]) if not rank_df.empty and "grade" in rank_df.columns else 0
    n_gradeA = len(rank_df[rank_df["grade"] == "A"]) if not rank_df.empty and "grade" in rank_df.columns else 0

    col_a.metric("推奨ベット数",   f"{n_picks} 頭")
    col_b.metric("Grade S レース", f"{n_gradeS} R")
    col_c.metric("Grade A レース", f"{n_gradeA} R")
    avg_ev = float(ev_df["ev"].mean()) if not ev_df.empty and "ev" in ev_df.columns else 0.0
    col_d.metric("平均EV",         f"+{avg_ev*100:.1f}%")

    st.divider()

    # ── 推奨ベット一覧テーブル ──────────────────────────────
    if ev_df.empty:
        st.info("本日の予想データがありません。`python run_all.py --v2` を実行してください。")
    else:
        # 表示カラム選択
        show_cols = []
        for c in ["race_code", "bamei", "odds", "ev", "win_probability",
                  "kelly_bet", "bet_amount", "grade"]:
            if c in ev_df.columns:
                show_cols.append(c)

        disp = ev_df[show_cols].copy()
        rename_map = {
            "race_code":       "レースコード",
            "bamei":           "馬名",
            "odds":            "オッズ",
            "ev":              "EV",
            "win_probability": "勝率",
            "kelly_bet":       "Kelly推奨",
            "bet_amount":      "推奨ベット額",
            "grade":           "グレード",
        }
        disp = disp.rename(columns={k: v for k, v in rename_map.items() if k in disp.columns})

        if "EV" in disp.columns:
            disp["EV"] = disp["EV"].apply(lambda x: f"+{x*100:.1f}%" if pd.notna(x) else "—")
        if "勝率" in disp.columns:
            disp["勝率"] = disp["勝率"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
        if "推奨ベット額" in disp.columns:
            disp["推奨ベット額"] = disp["推奨ベット額"].apply(
                lambda x: f"¥{int(x):,}" if pd.notna(x) and x > 0 else "—")
        if "オッズ" in disp.columns:
            disp["オッズ"] = disp["オッズ"].apply(lambda x: f"{x:.1f}倍" if pd.notna(x) else "—")

        if "レースコード" in disp.columns:
            disp["レース"] = disp["レースコード"].astype(str).apply(fmt_race)
            disp = disp.drop(columns=["レースコード"])
            cols_order = ["レース"] + [c for c in disp.columns if c != "レース"]
            disp = disp[cols_order]

        st.dataframe(disp, use_container_width=True, height=400)

        # 合計ベット額
        total_bet = ev_df["bet_amount"].sum() if "bet_amount" in ev_df.columns else 0
        if total_bet > 0:
            st.markdown(f"**本日合計推奨ベット額: ¥{int(total_bet):,}**")

    # ── オッズスナップショット ──────────────────────────────
    st.divider()
    st.markdown("#### 最新オッズスナップショット")
    if snap:
        snap_time = snap.get("timestamp", "")
        st.caption(f"取得時刻: {snap_time}")
        races = snap.get("races", snap)
        if isinstance(races, dict):
            sel_race = st.selectbox("レース選択", list(races.keys())[:20])
            race_data = races.get(sel_race, {})
            if isinstance(race_data, dict) and "horses" in race_data:
                hdf = pd.DataFrame(race_data["horses"])
                st.dataframe(hdf, use_container_width=True, height=250)
            else:
                st.json(race_data)
    else:
        st.info(f"オッズスナップショット未取得 (`data/odds_snapshot_{today_str}.json`)")

    # ── クイック実行ボタン ──────────────────────────────────
    st.divider()
    st.markdown("#### クイック実行")
    c1, c2, c3 = st.columns(3)
    if c1.button("▶ 日次 DAG 実行", use_container_width=True):
        with st.spinner("pipeline_v2/00_orchestrator.py を実行中..."):
            res = subprocess.run(
                [_sys.executable, "-X", "utf8",
                 os.path.join(BASE, "pipeline_v2", "00_orchestrator.py")],
                capture_output=True, text=True, cwd=BASE, timeout=600
            )
            if res.returncode == 0:
                st.success("完了しました")
                st.cache_data.clear()
            else:
                st.error(f"失敗 (rc={res.returncode})")
                st.code(res.stderr[-2000:] if res.stderr else "")

    if c2.button("📸 オッズ取得", use_container_width=True):
        with st.spinner("odds_scraper_36.py を実行中..."):
            res = subprocess.run(
                [_sys.executable, "-X", "utf8",
                 os.path.join(BASE, "pipeline", "odds_scraper_36.py")],
                capture_output=True, text=True, cwd=BASE, timeout=120
            )
            st.success("取得完了") if res.returncode == 0 else st.error("取得失敗")
            st.cache_data.clear()

    if c3.button("📤 SNS 投稿", use_container_width=True):
        st.warning("SNS 投稿は `social_bot_agent` 経由で実行します。本当に投稿しますか？")
        if st.button("✅ 投稿を確認して実行", key="confirm_sns"):
            with st.spinner("social_bot_27.py を実行中..."):
                res = subprocess.run(
                    [_sys.executable, "-X", "utf8",
                     os.path.join(BASE, "pipeline", "social_bot_27.py")],
                    capture_output=True, text=True, cwd=BASE, timeout=60
                )
                st.success("投稿完了") if res.returncode == 0 else st.error("投稿失敗")


# ════════════════════════════════════════════════════════════
# TAB 13: エージェント監視
# ════════════════════════════════════════════════════════════
with tab_agents:
    import psycopg2

    @st.cache_data(ttl=30)
    def _load_audit_log(limit: int = 200):
        try:
            conn = psycopg2.connect(
                host="127.0.0.1", port=5433, dbname="mykeibadb",
                user="postgres", password="zeus"
            )
            df = pd.read_sql(f"""
                SELECT
                    agent_id,
                    status,
                    run_tag,
                    trace_id,
                    started_at,
                    finished_at,
                    EXTRACT(EPOCH FROM (finished_at - started_at))::numeric(8,2) AS elapsed_sec,
                    error_message
                FROM audit_log
                ORDER BY started_at DESC
                LIMIT {limit}
            """, conn)
            conn.close()
            return df
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    @st.cache_data(ttl=30)
    def _load_agent_summary():
        """エージェントごとの最新状態サマリー"""
        try:
            conn = psycopg2.connect(
                host="127.0.0.1", port=5433, dbname="mykeibadb",
                user="postgres", password="zeus"
            )
            df = pd.read_sql("""
                SELECT
                    agent_id,
                    COUNT(*) FILTER (WHERE status='success') AS ok,
                    COUNT(*) FILTER (WHERE status='error')   AS ng,
                    MAX(started_at)                          AS last_run,
                    AVG(EXTRACT(EPOCH FROM (finished_at - started_at)))::numeric(6,2) AS avg_sec
                FROM audit_log
                WHERE started_at >= NOW() - INTERVAL '7 days'
                GROUP BY agent_id
                ORDER BY agent_id
            """, conn)
            conn.close()
            return df
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    @st.cache_data(ttl=30)
    def _load_model_registry():
        try:
            conn = psycopg2.connect(
                host="127.0.0.1", port=5433, dbname="mykeibadb",
                user="postgres", password="zeus"
            )
            df = pd.read_sql("""
                SELECT model_id, status, train_date, avg_roi, spearman_corr, verdict
                FROM model_registry
                ORDER BY train_date DESC
                LIMIT 10
            """, conn)
            conn.close()
            return df
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    # ── ヘッダー ────────────────────────────────────────────
    st.markdown("### 🤖 エージェント監視ダッシュボード")
    st.caption(f"自動更新: 30秒 | audit_log / model_registry | {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 今すぐ更新"):
        st.cache_data.clear()
        st.rerun()

    # ── エージェントサマリー ────────────────────────────────
    st.markdown("#### 直近7日 エージェント稼働状況")
    sum_df = _load_agent_summary()

    if "error" in sum_df.columns:
        st.error(f"DB接続失敗: {sum_df['error'].iloc[0]}")
    elif sum_df.empty:
        st.info("audit_log にデータがありません。`canary_run.py` を実行してください。")
    else:
        # ステータスバッジ列追加
        def _badge(row):
            if row["ng"] > 0:
                return "🔴 エラーあり"
            if row["ok"] == 0:
                return "⚪ 未実行"
            return "🟢 正常"

        sum_df["状態"] = sum_df.apply(_badge, axis=1)
        sum_df["最終実行"] = pd.to_datetime(sum_df["last_run"]).dt.strftime("%m/%d %H:%M")
        sum_df["平均秒数"] = sum_df["avg_sec"].apply(lambda x: f"{x:.1f}s" if pd.notna(x) else "—")

        disp = sum_df[["agent_id", "状態", "ok", "ng", "最終実行", "平均秒数"]].rename(
            columns={"agent_id": "エージェント", "ok": "成功数", "ng": "失敗数"}
        )
        st.dataframe(disp, use_container_width=True, height=500)

    # ── auto_stop / アラート状態 ────────────────────────────
    st.divider()
    st.markdown("#### システムアラート状態")

    canary_path = os.path.join(BASE, ".claude", "worktrees", "brave-kilby-e79e98",
                               "logs")
    reports = sorted(glob.glob(os.path.join(canary_path, "canary_report_*.json")),
                     reverse=True)[:1]

    if reports:
        try:
            rpt = json.loads(open(reports[0], encoding="utf-8").read())
            steps = rpt.get("steps", [])
            failed = [s for s in steps if not s.get("ok")]
            ts = rpt.get("timestamp", "")[:19].replace("T", " ")
            if failed:
                st.error(f"⚠️ canary 最終実行 {ts} — {len(failed)} ステップ失敗")
                for s in failed:
                    st.markdown(f"- `{s.get('name', '?')}`: {s.get('detail', '')}")
            else:
                total = len(steps)
                st.success(f"✅ canary 最終実行 {ts} — {total}/{total} PASS")
        except Exception as e:
            st.warning(f"canary レポート読み込み失敗: {e}")
    else:
        st.info("canary レポートが見つかりません。`python canary_run.py` を実行してください。")

    # ── 直近実行ログ ────────────────────────────────────────
    st.divider()
    st.markdown("#### 直近実行ログ（audit_log）")

    log_limit = st.slider("表示件数", 20, 200, 50, 10)
    audit_df  = _load_audit_log(log_limit)

    if "error" in audit_df.columns:
        st.error(f"DB接続失敗: {audit_df['error'].iloc[0]}")
    elif audit_df.empty:
        st.info("ログなし")
    else:
        def _status_icon(s):
            return {"success": "🟢", "error": "🔴", "start": "🔵"}.get(str(s), "⚪")

        audit_df[""] = audit_df["status"].apply(_status_icon)
        audit_df["開始時刻"] = pd.to_datetime(audit_df["started_at"]).dt.strftime("%m/%d %H:%M:%S")
        audit_df["経過(s)"]  = audit_df["elapsed_sec"].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "—")

        show = audit_df[["", "agent_id", "status", "開始時刻", "経過(s)",
                          "trace_id", "error_message"]].rename(
            columns={"agent_id": "エージェント", "status": "状態",
                     "trace_id": "trace_id", "error_message": "エラー"})
        st.dataframe(show, use_container_width=True, height=400)

    # ── model_registry ──────────────────────────────────────
    st.divider()
    st.markdown("#### モデルレジストリ（直近10件）")
    mreg_df = _load_model_registry()

    if "error" in mreg_df.columns:
        st.error(f"DB接続失敗: {mreg_df['error'].iloc[0]}")
    elif mreg_df.empty:
        st.info("model_registry にデータがありません")
    else:
        if "avg_roi" in mreg_df.columns:
            mreg_df["avg_roi"] = mreg_df["avg_roi"].apply(
                lambda x: f"+{x:.1f}%" if pd.notna(x) and x >= 0 else f"{x:.1f}%" if pd.notna(x) else "—")
        if "spearman_corr" in mreg_df.columns:
            mreg_df["spearman_corr"] = mreg_df["spearman_corr"].apply(
                lambda x: f"{x:.4f}" if pd.notna(x) else "—")
        st.dataframe(mreg_df, use_container_width=True, height=300)
