"""
うまなり地蔵AI 世界最強バージョン 全自動実行
43項目の分析・AI・資金管理・SNS配信を一括実行
"""
import sys
import os
from datetime import datetime

sys.path.append("D:\\keiba_ai")


def _safe(name, fn, *args, **kwargs):
    """エラーでも続行するラッパー"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"  ⚠️ [{name}] スキップ: {e}")
        return None


def run_all(
    skip_fetch=False,
    skip_train=False,
    skip_advanced_features=False,
    skip_nn=False,
    skip_optuna=False,
    skip_rl=False,
    skip_stats=False,
    skip_social=False,
    full_optuna=False,
):
    print("=" * 60)
    print(f"🙏 うまなり地蔵AI 世界最強版 全自動実行")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    year = datetime.now().year

    # ══════════════════════════════════════════════════════
    # PHASE 1: データ取得・特徴量エンジニアリング
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("📦 PHASE 1: データ取得・特徴量エンジニアリング")
    print("─"*60)

    if not skip_fetch:
        print("\n【STEP 1/16】データ取得 (data_fetch_01)")
        from pipeline.data_fetch_01 import fetch_data
        _safe("data_fetch", fetch_data)

    print("\n【STEP 2/16】基本特徴量計算 (feature_eng_02)")
    from pipeline.feature_eng_02 import feature_engineering
    _safe("feature_eng", feature_engineering)

    if not skip_advanced_features:
        print("\n【STEP 3/16】高度特徴量 (feature_advanced_19)")
        from pipeline.feature_advanced_19 import run_advanced_feature_engineering
        _safe("adv_feat", run_advanced_feature_engineering)

        print("\n【STEP 4/16】ペース・調教分析 (pace_training_analysis_20)")
        from pipeline.pace_training_analysis_20 import run_pace_training_analysis
        _safe("pace", run_pace_training_analysis)

        print("\n【STEP 5/16】騎手・調教師・3代ニックス (jockey_trainer_analysis_21)")
        from pipeline.jockey_trainer_analysis_21 import run_jockey_trainer_analysis
        _safe("jockey", run_jockey_trainer_analysis)

        print("\n【STEP 6/16】統計分析・クラスタリング (statistical_tools_23)")
        from pipeline.statistical_tools_23 import run_statistical_analysis
        _safe("stats", run_statistical_analysis)

    # ══════════════════════════════════════════════════════
    # PHASE 2: 異常検知・自動学習
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("🔍 PHASE 2: 異常検知・自動学習")
    print("─"*60)

    print("\n【STEP 7/16】異常検知 (anomaly_detect_16)")
    from pipeline.anomaly_detect_16 import run_anomaly_detection
    alerts = _safe("anomaly", run_anomaly_detection, year, use_db=True) or []
    critical = [a for a in alerts if a.get('level') == 'CRITICAL']
    if critical:
        print(f"  🚨 CRITICALアラート {len(critical)}件 — ベット額に注意")

    print("\n【STEP 8/16】ドローダウン管理 (bankroll_advanced_24)")
    from pipeline.bankroll_advanced_24 import run_bankroll_advanced
    dd_status = _safe("bankroll", run_bankroll_advanced) or {}
    if dd_status.get('multiplier', 1) == 0:
        print("  🛑 資金保護モード: ベット停止")

    print("\n【STEP 9/16】自動学習チェック (auto_learn_13)")
    from pipeline.auto_learn_13 import run_auto_learn, show_performance_trend
    _safe("auto_learn", run_auto_learn, f"D:\\keiba_ai\\simulation_{year}.csv")

    # ══════════════════════════════════════════════════════
    # PHASE 3: モデル学習・最適化
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("🤖 PHASE 3: モデル学習・最適化")
    print("─"*60)

    if not skip_train:
        print("\n【STEP 10/16】アンサンブル学習 (model_train_03)")
        from pipeline.model_train_03 import train_model
        _safe("train", train_model)

    if not skip_optuna and full_optuna:
        print("\n【STEP 11/16】Optuna最適化 (optuna_advanced_25) [--full-optuna]")
        from pipeline.optuna_advanced_25 import run_optuna_advanced
        _safe("optuna", run_optuna_advanced, 40, 30, 25)

    if not skip_nn:
        print("\n【STEP 12/16】Neural Network + Stacking (nn_stacking_22)")
        from pipeline.nn_stacking_22 import train_nn_stacking
        _safe("nn", train_nn_stacking)

    if not skip_rl:
        print("\n【STEP 13/16】強化学習戦略 (rl_strategy_26)")
        from pipeline.rl_strategy_26 import RL_MODEL
        if not os.path.exists(RL_MODEL + '.zip'):
            from pipeline.rl_strategy_26 import train_rl_strategy
            _safe("rl_train", train_rl_strategy, 50_000)
        else:
            print("  ✅ 学習済みRLモデルを使用")

    print("\n【STEP 13b】SHAP 特徴量重要度可視化 (shap_analysis)")
    from pipeline.shap_analysis import main as run_shap
    _safe("shap", run_shap)

    # ══════════════════════════════════════════════════════
    # PHASE 4: 予想生成・資金管理
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("🏇 PHASE 4: 予想生成・資金管理")
    print("─"*60)

    print("\n【STEP 14/16】予想生成 (predict_04)")
    from pipeline.predict_04 import simulate_recovery
    result = _safe("predict", simulate_recovery, year)

    print("\n【STEP 15/16】期待値・ポートフォリオ (ev_engine_10 / portfolio_opt_11)")
    from pipeline.ev_engine_10 import run_ev_analysis
    from pipeline.portfolio_opt_11 import run_portfolio_optimization
    _safe("ev", run_ev_analysis, year)
    _safe("portfolio", run_portfolio_optimization, year)

    print("\n【STEP 15b】レース価値スコアリング (race_selector_31)")
    from pipeline.race_selector_31 import run_race_selector
    _safe("race_selector", run_race_selector, year)

    print("\n【STEP 15c】馬券種別選択 (ticket_optimizer_30)")
    from pipeline.ticket_optimizer_30 import run_ticket_optimizer
    _safe("ticket_optimizer", run_ticket_optimizer, year)

    print("\n【STEP 15d】多点買いポートフォリオ (bet_portfolio_29)")
    from pipeline.bet_portfolio_29 import run_bet_portfolio
    _safe("bet_portfolio", run_bet_portfolio, year)

    print("\n【STEP 15e】バックテスト (backtest_engine_32)")
    from pipeline.backtest_engine_32 import run_backtest_engine
    _safe("backtest", run_backtest_engine, year)

    print("\n【STEP 15e2】ウォークフォワード検証 (backtest_walkforward_35)")
    from pipeline.backtest_walkforward_35 import run_walkforward_backtest
    _safe("walkforward", run_walkforward_backtest, False)  # fast mode

    print("\n【STEP 15f】条件別ベット係数 (condition_adjuster_34)")
    from pipeline.condition_adjuster_34 import run_condition_adjuster
    _safe("condition_adj", run_condition_adjuster, year)

    print("\n【STEP 15g】オッズ変動分析 (odds_monitor_33)")
    from pipeline.odds_monitor_33 import run_odds_monitor
    _safe("odds_monitor", run_odds_monitor, year)

    if not skip_stats and result:
        from pipeline.statistical_tools_23 import run_monte_carlo
        hr  = result.get('hit_rate', 38.8) / 100
        roi = result.get('recovery_rate', 478.2) / 100
        avg_odds = roi / (hr + 1e-6)
        _safe("monte_carlo", run_monte_carlo, 100000, hr, avg_odds)

    try:
        from pipeline.multi_agent_v2_28 import run_multi_agent
        _safe("multi_agent", run_multi_agent, year)
    except ImportError:
        print("  ⚠️ LangGraph未インストール（スキップ）: pip install langgraph")

    # ══════════════════════════════════════════════════════
    # PHASE 5: 発信・レポート
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("📢 PHASE 5: 発信・レポート")
    print("─"*60)

    print("\n【STEP 16/16】発信・レポート")
    from pipeline.claude_comment_06 import generate_todays_post
    from pipeline.note_07 import generate_note_article
    from pipeline.notify_08 import send_pipeline_report
    from pipeline.roi_tracker_12 import print_roi_report

    post_text = _safe("comment", generate_todays_post)
    _safe("note", generate_note_article)
    _safe("roi_report", print_roi_report)
    _safe("perf_trend", show_performance_trend)

    if not skip_social:
        from pipeline.social_bot_27 import broadcast_picks
        _safe("social", broadcast_picks, post_text)

    if result:
        notify_result = {
            'hit_rate':      result.get('hit_rate', 0),
            'recovery_rate': result.get('recovery_rate', 0),
            'profit':        result.get('profit', 0),
            'total_races':   result.get('races', 0),
            'total_profit':  result.get('profit', 0),
            'honmei':        (post_text or '')[:100]
        }
        _safe("notify", send_pipeline_report, notify_result)

    # ══════════════════════════════════════════════════════
    # 最終サマリー
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print(f"✅ うまなり地蔵AI 全自動実行完了!")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if result:
        emoji = "🎉" if result.get('recovery_rate', 0) >= 100 else "📊"
        print(f"{emoji} {year}年 回収率: {result.get('recovery_rate', 0):.1f}%"
              f" | 的中率: {result.get('hit_rate', 0):.1f}%"
              f" | 損益: {result.get('profit', 0):+,.0f}円")
    print("=" * 60)
    print(f"\n📱 ダッシュボード: streamlit run pipeline/dashboard_15.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="うまなり地蔵AI 実行コントロール")
    parser.add_argument('--skip-fetch',  action='store_true', help='データ取得をスキップ')
    parser.add_argument('--skip-train',  action='store_true', help='モデル学習をスキップ')
    parser.add_argument('--skip-adv',    action='store_true', help='高度特徴量をスキップ')
    parser.add_argument('--skip-nn',     action='store_true', help='NNをスキップ')
    parser.add_argument('--skip-rl',     action='store_true', help='強化学習をスキップ')
    parser.add_argument('--skip-stats',  action='store_true', help='統計分析をスキップ')
    parser.add_argument('--skip-social', action='store_true', help='SNS投稿をスキップ')
    parser.add_argument('--full-optuna', action='store_true', help='Optuna最適化を実行（重い）')
    parser.add_argument('--quick',       action='store_true', help='高速モード（主要ステップのみ）')
    args = parser.parse_args()

    if args.quick:
        run_all(skip_fetch=True, skip_advanced_features=True,
                skip_nn=True, skip_rl=True, skip_stats=True,
                skip_social=args.skip_social, full_optuna=False)
    else:
        run_all(
            skip_fetch=args.skip_fetch,
            skip_train=args.skip_train,
            skip_advanced_features=args.skip_adv,
            skip_nn=args.skip_nn,
            skip_rl=args.skip_rl,
            skip_stats=args.skip_stats,
            skip_social=args.skip_social,
            full_optuna=args.full_optuna,
        )
