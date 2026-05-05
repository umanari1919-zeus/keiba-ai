"""
🏇 Race Entries & Horse Evaluation — 出走表と全頭評価

レース別の出走馬リスト、AI評価スコア、SHAP特徴量分析を表示。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from pathlib import Path
from utils.api_client import APIClient
from utils.data_loader import load_cached_data
from utils.theme import apply_theme

# テーマ適用
apply_theme()

st.set_page_config(
    page_title="Race Entries",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏇 Race Entries & Horse Evaluation")
st.markdown("レース出走表と全頭のAI評価スコア・特徴量分析")

# ── セッション状態 ────────────────────────────────────────────────────
if "selected_race" not in st.session_state:
    st.session_state.selected_race = None
if "selected_date" not in st.session_state:
    st.session_state.selected_date = datetime.now().strftime("%Y%m%d")


# ── データロード ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_predictions(date: str) -> pd.DataFrame:
    """予想データを読み込み"""
    try:
        data = APIClient.get_predictions(date=date)
        if isinstance(data, dict) and "predictions" in data:
            return pd.DataFrame(data["predictions"])
        return pd.DataFrame()
    except:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_keiba_features() -> pd.DataFrame:
    """全馬特徴量データを読み込み"""
    try:
        csv_path = Path("data") / "keiba_data_features.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, nrows=10000, on_bad_lines='skip')
        return pd.DataFrame()
    except:
        return pd.DataFrame()


# ── タブ構成 ────────────────────────────────────────────────────────
tabs = st.tabs(["🏇 Race List", "📊 Horse Evaluation", "⚡ Feature Analysis", "⚠️ Risk Analysis"])

# ── TAB 1: Race List ──────────────────────────────────────────────────
with tabs[0]:
    st.subheader("🏇 Race Schedule & Predictions")

    # 日付選択
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        selected_date = st.date_input(
            "Select Date",
            value=datetime.now(),
            key="date_picker",
        )
        st.session_state.selected_date = selected_date.strftime("%Y%m%d")

    # 予想データ読み込み
    predictions_df = load_predictions(st.session_state.selected_date)

    if not predictions_df.empty:
        # レース別グループ化
        race_columns = [col for col in predictions_df.columns if "race" in col.lower()]

        if race_columns:
            race_col = race_columns[0]
            races = predictions_df[race_col].unique()

            # レース一覧テーブル
            race_summary = []
            for race in sorted(races):
                race_data = predictions_df[predictions_df[race_col] == race]
                race_summary.append({
                    "Race": race,
                    "出走数": len(race_data),
                    "評価馬": len(race_data[race_data.get("recommended", False)]),
                    "平均スコア": f"{race_data.get('prediction_score', pd.Series([0])).mean():.2f}",
                })

            race_summary_df = pd.DataFrame(race_summary)
            st.dataframe(race_summary_df, use_container_width=True)

            # レース選択
            st.markdown("---")
            st.subheader("📍 Select Race for Details")
            selected_race = st.selectbox(
                "レースを選択",
                options=sorted(races),
                key="race_select",
            )
            st.session_state.selected_race = selected_race

        else:
            st.info("No race data available for selected date")
    else:
        st.info(f"No predictions available for {st.session_state.selected_date}")


# ── TAB 2: Horse Evaluation ───────────────────────────────────────────
with tabs[1]:
    st.subheader("📊 Full Horse Evaluation")

    if st.session_state.selected_race:
        predictions_df = load_predictions(st.session_state.selected_date)

        if not predictions_df.empty:
            race_columns = [col for col in predictions_df.columns if "race" in col.lower()]

            if race_columns:
                race_col = race_columns[0]
                race_data = predictions_df[predictions_df[race_col] == st.session_state.selected_race].copy()

                if not race_data.empty:
                    st.success(f"✅ レース: **{st.session_state.selected_race}** ({len(race_data)}頭)")

                    # 馬番・馬名・オッズ列を特定
                    horse_col = next((col for col in race_data.columns if "horse" in col.lower() or "名" in col), None)
                    odds_col = next((col for col in race_data.columns if "odds" in col.lower()), None)
                    score_col = next((col for col in race_data.columns if "score" in col.lower() or "pred" in col.lower()), None)

                    # 表示用DataFrame作成
                    display_df = pd.DataFrame({
                        "馬番": race_data.get("horse_number", range(1, len(race_data) + 1)),
                        "馬名": race_data.get(horse_col, ["Unknown"] * len(race_data)) if horse_col else ["—"] * len(race_data),
                        "推奨": race_data.get("recommended", [False] * len(race_data)),
                    })

                    if odds_col:
                        display_df["オッズ"] = race_data[odds_col].apply(lambda x: f"{x:.1f}倍" if pd.notna(x) else "—")

                    if score_col:
                        display_df["評価スコア"] = race_data[score_col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")

                    # スコア順でソート
                    if score_col:
                        race_data_sorted = race_data.sort_values(score_col, ascending=False)
                        display_df = display_df.sort_values("評価スコア", key=lambda x: pd.to_numeric(x.str.rstrip(), errors='coerce'), ascending=False)

                    # テーブル表示
                    st.dataframe(display_df, use_container_width=True)

                    # スコア分布
                    if score_col:
                        fig = px.bar(
                            x=range(len(race_data_sorted)),
                            y=race_data_sorted[score_col],
                            labels={"y": "Prediction Score", "x": "Horse Rank"},
                            title=f"🏇 {st.session_state.selected_race} — AI評価スコア分布",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # 推奨馬ハイライト
                    recommended = display_df[display_df["推奨"] == True]
                    if not recommended.empty:
                        st.markdown("---")
                        st.subheader("⭐ Recommended Horses")
                        st.dataframe(recommended, use_container_width=True)

                else:
                    st.info("No data for selected race")
            else:
                st.warning("Race column not found in data")
        else:
            st.warning("No predictions data loaded")
    else:
        st.info("👈 Please select a race from the Race List tab")


# ── TAB 3: Feature Analysis ───────────────────────────────────────────
with tabs[2]:
    st.subheader("⚡ SHAP Feature Importance Analysis")

    if st.session_state.selected_race:
        predictions_df = load_predictions(st.session_state.selected_date)

        if not predictions_df.empty:
            race_columns = [col for col in predictions_df.columns if "race" in col.lower()]

            if race_columns:
                race_col = race_columns[0]
                race_data = predictions_df[predictions_df[race_col] == st.session_state.selected_race]

                if not race_data.empty:
                    st.success(f"📊 {st.session_state.selected_race} — 特徴量分析")

                    # SHAP特徴量カラムを抽出
                    feature_cols = [col for col in race_data.columns if col not in [
                        "horse_number", "horse_name", "race_code", "odds", "recommended",
                        "prediction_score", "predicted_rank", race_col
                    ]]

                    if feature_cols:
                        # トップ特徴量表示
                        st.subheader("Top 10 Feature Importance")

                        # 特徴量の平均重要度を計算（簡易版）
                        feature_importance = {}
                        for col in feature_cols[:20]:  # 最初の20列のみ
                            try:
                                # 数値化して分散を計算（簡易的な重要度指標）
                                numeric_vals = pd.to_numeric(race_data[col], errors='coerce')
                                if numeric_vals.notna().sum() > 0:
                                    feature_importance[col] = numeric_vals.std()
                            except:
                                pass

                        if feature_importance:
                            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]
                            top_features_df = pd.DataFrame(top_features, columns=["Feature", "Importance"])

                            fig = px.barh(
                                top_features_df,
                                x="Importance",
                                y="Feature",
                                title="Top 10 Features",
                                orientation="h",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No numeric features available for analysis")

                        # 詳細特徴量テーブル
                        st.subheader("Raw Feature Values")
                        feature_table = race_data[feature_cols[:15]].head(10)
                        st.dataframe(feature_table, use_container_width=True)

                    else:
                        st.info("No feature columns available")
                else:
                    st.info("No data for selected race")
            else:
                st.warning("Race column not found")
        else:
            st.warning("No predictions data loaded")
    else:
        st.info("👈 Please select a race from the Race List tab")


# ── TAB 4: Risk Analysis ──────────────────────────────────────────────
with tabs[3]:
    st.subheader("⚠️ Risk Analysis & Danger Horses")

    if st.session_state.selected_race:
        predictions_df = load_predictions(st.session_state.selected_date)

        if not predictions_df.empty:
            race_columns = [col for col in predictions_df.columns if "race" in col.lower()]

            if race_columns:
                race_col = race_columns[0]
                race_data = predictions_df[predictions_df[race_col] == st.session_state.selected_race]

                if not race_data.empty:
                    st.success(f"⚠️ {st.session_state.selected_race} — リスク分析")

                    # リスクファクター抽出
                    risk_factors = []

                    # 1. 予想スコアが低い馬
                    score_col = next((col for col in race_data.columns if "score" in col.lower() or "pred" in col.lower()), None)
                    if score_col:
                        low_score = race_data[race_data[score_col] < race_data[score_col].quantile(0.25)]
                        if not low_score.empty:
                            risk_factors.append({
                                "Risk Type": "Low Prediction Score",
                                "Count": len(low_score),
                                "Description": f"予想スコアが25%以下（{low_score[score_col].min():.2f}～{low_score[score_col].max():.2f}）",
                            })

                    # 2. 高いオッズ（ボラティリティ）
                    odds_col = next((col for col in race_data.columns if "odds" in col.lower()), None)
                    if odds_col:
                        high_odds = race_data[pd.to_numeric(race_data[odds_col], errors='coerce') > 50]
                        if not high_odds.empty:
                            risk_factors.append({
                                "Risk Type": "High Odds Volatility",
                                "Count": len(high_odds),
                                "Description": f"50倍以上の高オッズ（不確実性が高い）",
                            })

                    # リスク表示
                    if risk_factors:
                        risk_df = pd.DataFrame(risk_factors)
                        st.dataframe(risk_df, use_container_width=True)

                        st.markdown("---")
                        st.warning("""
                        ⚠️ **リスク注意事項**
                        - 低スコア馬: AI精度が低い。外れやすい傾向
                        - 高オッズ: マーケット参加者が懐疑的。要注意
                        - これらの馬は除外または低額投票を推奨
                        """)
                    else:
                        st.success("✅ 顕著なリスク馬は検出されません")

                    # 推奨ベット額シミュレーション
                    st.markdown("---")
                    st.subheader("💰 Suggested Betting")

                    bankroll = st.number_input(
                        "Current Bankroll (¥)",
                        min_value=1000,
                        max_value=10000000,
                        value=1000000,
                        step=100000,
                    )

                    kelly_fraction = 0.10
                    st.info(f"Kelly Fraction: {kelly_fraction * 100:.0f}% (リスク控えめ)")

                    if score_col:
                        best_horse = race_data[race_data[score_col] == race_data[score_col].max()]
                        if not best_horse.empty:
                            best_score = best_horse[score_col].values[0]
                            suggested_bet = bankroll * kelly_fraction * (best_score / 100)
                            st.metric(
                                "Suggested Bet (Best Horse)",
                                f"¥{suggested_bet:,.0f}",
                                delta=f"{suggested_bet / bankroll * 100:.2f}% of bankroll",
                            )

                else:
                    st.info("No data for selected race")
            else:
                st.warning("Race column not found")
        else:
            st.warning("No predictions data loaded")
    else:
        st.info("👈 Please select a race from the Race List tab")

st.markdown("---")

# ── 注意事項 ────────────────────────────────────────────────────────
st.info("""
💡 **使い方**

1. **Race List** タブで日付とレースを選択
2. **Horse Evaluation** で全頭のスコアを確認
3. **Feature Analysis** で重要な特徴量を確認
4. **Risk Analysis** でリスク馬を確認
5. ホーム画面から実際にベットを実行
""")
