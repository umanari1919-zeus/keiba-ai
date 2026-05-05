"""
Theme and styling utilities for Dashboard v4
"""
import streamlit as st


def apply_base_theme():
    """Apply GitHub Copilot dark theme CSS."""
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


def plotly_theme() -> dict:
    """Return Plotly theme config dict."""
    return dict(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='#c9d1d9',
        margin=dict(l=8, r=8, t=36, b=8),
        xaxis=dict(gridcolor='#21262d', linecolor='#21262d'),
        yaxis=dict(gridcolor='#21262d', linecolor='#21262d'),
    )
