"""
⚙️ Settings — パラメータ設定

EV_THRESHOLD / KELLY_FRACTION / MIN_ODDS / MIN_ODDS_BACKTEST を
スライダーで調整し、API経由で pipeline/config.py に永続化する。
"""
import streamlit as st
from datetime import datetime
from utils.api_client import APIClient
from utils.theme import apply_theme

# テーマ適用
apply_theme()

st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚙️ Pipeline Settings")
st.markdown("パラメータを調整して、予想アルゴリズムの動作を制御します。")

# ── 現在のパラメータを取得 ────────────────────────────────────────
try:
    current_params = APIClient.get_parameters()
    st.success("✅ Settings loaded")
except RuntimeError as e:
    st.error(f"❌ Failed to load settings: {e}")
    st.info("💡 FastAPI サーバーが起動していることを確認してください: `uvicorn api.main:app --reload`")
    st.stop()

# ── パラメータ調整セクション ────────────────────────────────────────
st.header("📊 Expected Value (EV) Threshold")
st.markdown("""
**EV_THRESHOLD**: 予想をフィルタリングする最小期待値（%）

- 値が高いほど、高確度の予想のみに絞られる
- 例: 0.15 = 期待値 15% 以上の予想をピック
- 推奨値: 0.10 ~ 0.20
""")

col1, col2 = st.columns([3, 1])
with col1:
    ev_threshold = st.slider(
        "EV Threshold",
        min_value=0.01,
        max_value=0.50,
        value=float(current_params.get("EV_THRESHOLD", 0.15)),
        step=0.01,
        format="%.2f",
        key="ev_threshold",
    )
with col2:
    st.metric("Current", f"{current_params.get('EV_THRESHOLD', 0.15):.2f}")

st.markdown("---")

st.header("💰 Kelly Fraction")
st.markdown("""
**KELLY_FRACTION**: Kelly基準に基づくベット比率

- 値が高いほどアグレッシブなベット（リスク↑、リターン↑）
- 値が低いほど保守的（リスク↓、リターン↓）
- 推奨値: 0.05 ~ 0.15 (完全Kelly の 5%-15%)
""")

col1, col2 = st.columns([3, 1])
with col1:
    kelly_fraction = st.slider(
        "Kelly Fraction",
        min_value=0.01,
        max_value=0.25,
        value=float(current_params.get("KELLY_FRACTION", 0.10)),
        step=0.01,
        format="%.2f",
        key="kelly_fraction",
    )
with col2:
    st.metric("Current", f"{current_params.get('KELLY_FRACTION', 0.10):.2f}")

st.markdown("---")

st.header("🎯 Minimum Odds")
st.markdown("""
**MIN_ODDS**: 予想対象の最小オッズ（倍数）

- 値が高いほど穴馬（高オッズ）に絞られる
- 例: 10.0 = 10倍以上のオッズのみ対象
- 推奨値: 5.0 ~ 20.0
""")

col1, col2 = st.columns([3, 1])
with col1:
    min_odds = st.slider(
        "Minimum Odds",
        min_value=1.0,
        max_value=50.0,
        value=float(current_params.get("MIN_ODDS", 10.0)),
        step=0.5,
        format="%.1f",
        key="min_odds",
    )
with col2:
    st.metric("Current", f"{current_params.get('MIN_ODDS', 10.0):.1f}")

st.markdown("---")

st.header("📈 Minimum Odds (Backtest)")
st.markdown("""
**MIN_ODDS_BACKTEST**: バックテスト時の最小オッズ

- 過去検証用の設定（異なる値を使用可能）
- 推奨値: MIN_ODDS と同じ、または少し低め
""")

col1, col2 = st.columns([3, 1])
with col1:
    min_odds_backtest = st.slider(
        "Minimum Odds (Backtest)",
        min_value=1.0,
        max_value=50.0,
        value=float(current_params.get("MIN_ODDS_BACKTEST", 10.0)),
        step=0.5,
        format="%.1f",
        key="min_odds_backtest",
    )
with col2:
    st.metric("Current", f"{current_params.get('MIN_ODDS_BACKTEST', 10.0):.1f}")

st.markdown("---")

# ── 更新・リセットボタン ────────────────────────────────────────
st.header("🔧 Actions")

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("✅ Apply Changes", key="apply_btn", use_container_width=True):
        try:
            with st.spinner("Updating parameters..."):
                result = APIClient.update_parameters(
                    EV_THRESHOLD=ev_threshold,
                    KELLY_FRACTION=kelly_fraction,
                    MIN_ODDS=min_odds,
                    MIN_ODDS_BACKTEST=min_odds_backtest,
                )
            st.success(f"✅ {result['message']}")
            st.rerun()
        except RuntimeError as e:
            st.error(f"❌ Update failed: {e}")

with col2:
    if st.button("🔄 Reset to Defaults", key="reset_btn", use_container_width=True):
        # 確認ダイアログ
        confirm = st.checkbox("⚠️ Confirm reset to default values")
        if confirm:
            try:
                with st.spinner("Resetting parameters..."):
                    result = APIClient.reset_parameters()
                st.success(f"✅ {result['message']}")
                st.rerun()
            except RuntimeError as e:
                st.error(f"❌ Reset failed: {e}")

with col3:
    if st.button("🔃 Reload", key="reload_btn", use_container_width=True):
        try:
            current_params = APIClient.get_parameters()
            st.success("✅ Settings reloaded")
            st.rerun()
        except RuntimeError as e:
            st.error(f"❌ Reload failed: {e}")

st.markdown("---")

# ── パラメータプレビュー ────────────────────────────────────────────
st.header("📋 Current Configuration")

params_display = {
    "EV_THRESHOLD": ev_threshold,
    "KELLY_FRACTION": kelly_fraction,
    "MIN_ODDS": min_odds,
    "MIN_ODDS_BACKTEST": min_odds_backtest,
    "Updated At": current_params.get("updated_at", "Unknown"),
}

st.json(params_display)

st.markdown("---")

# ── 注意事項 ────────────────────────────────────────────────────
st.warning("""
⚠️ **注意事項**

1. パラメータ変更は **次のパイプライン実行** から有効です
2. バックテストを実行してパラメータの妥当性を検証してください（Admin → Job Trigger）
3. 極端な値（EV < 0.05 など）は精度低下の原因になります
4. パラメータを戻したい場合は「Reset to Defaults」ボタンを使用してください
""")

st.info("""
💡 **推奨ワークフロー**

1. ここでパラメータを調整
2. Admin ページで「backtest」ジョブを実行
3. 結果を確認して、必要に応じて再調整
4. 本運用パイプラインを実行
""")
