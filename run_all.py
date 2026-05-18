"""
うまなり地蔵AI 世界最強バージョン 全自動実行
43項目の分析・AI・資金管理・SNS配信を一括実行
"""
import sys
import os
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR as CONFIG_BASE_DIR
from pipeline.config import DATA_DIR as CONFIG_DATA_DIR
from pipeline.config import MYKEIBADB_EXE as CONFIG_MYKEIBADB_EXE

BASE_DIR = pathlib.Path(CONFIG_BASE_DIR)
DATA_DIR = pathlib.Path(CONFIG_DATA_DIR)
MYKEIBADB_EXE = pathlib.Path(CONFIG_MYKEIBADB_EXE)


def _safe(name, fn, *args, **kwargs):
    """エラーでも続行するラッパー"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"  ⚠️ [{name}] スキップ: {e}")
        return None


def _run_subprocess(cmd: list[str], cwd: pathlib.Path | None = None) -> int:
    import subprocess

    return subprocess.run(cmd, cwd=str(cwd or BASE_DIR)).returncode


def _run_mykeibadb_sync(timeout_seconds: int = 300) -> bool:
    import subprocess

    if not MYKEIBADB_EXE.exists():
        print(f"  ⚠️ mykeibadb.exe が見つかりません: {MYKEIBADB_EXE}")
        return False

    try:
        result = subprocess.run(
            [str(MYKEIBADB_EXE)],
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(MYKEIBADB_EXE.parent),
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            print("  ✅ mykeibadb 同期完了")
            return True

        print(f"  ⚠️ mykeibadb 終了コード {result.returncode}")
        if result.stdout:
            print(result.stdout[-500:])
        if result.stderr:
            print(result.stderr[-200:])
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ mykeibadb タイムアウト（{timeout_seconds}秒）")
    except Exception as e:
        print(f"  ⚠️ mykeibadb エラー: {e}")
    return False


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
    skip_results=True,
):
    print("=" * 60)
    print(f"🙏 うまなり地蔵AI 世界最強版 全自動実行")
    print(f"⏰ {datetime.now(tz=JST).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    year = datetime.now(tz=JST).year

    # ══════════════════════════════════════════════════════
    # PHASE 1: データ取得・特徴量エンジニアリング
    # ══════════════════════════════════════════════════════
    print("\n" + "─"*60)
    print("📦 PHASE 1: データ取得・特徴量エンジニアリング")
    print("─"*60)

    if not skip_fetch:
        print("\n【STEP 0/16】JV-Link DB同期 (mykeibadb.exe)")
        _run_mykeibadb_sync()

        print("\n【STEP 0b/16】当日出馬表取得 (shutsuba_fetch)")
        from pipeline.shutsuba_fetch import save_today_entries
        _safe("shutsuba_fetch", save_today_entries)

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

        print("\n【STEP 6b】調教マルチセッション分析 (training_analysis_37)")
        from pipeline.training_analysis_37 import run_training_analysis
        _safe("training_analysis", run_training_analysis)

        print("\n【STEP 6c】調教師特性分析 (trainer_analysis_38)")
        from pipeline.trainer_analysis_38 import run_trainer_analysis
        _safe("trainer_analysis", run_trainer_analysis)

        print("\n【STEP 6d】新馬戦強化分析 (debut_analysis_39)")
        from pipeline.debut_analysis_39 import run_debut_analysis
        _safe("debut_analysis", run_debut_analysis)

        print("\n【STEP 6e】障害戦強化分析 (shogai_analysis_40)")
        from pipeline.shogai_analysis_40 import run_shogai_analysis
        _safe("shogai_analysis", run_shogai_analysis)

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
    _safe("auto_learn", run_auto_learn, str(BASE_DIR / f"simulation_{year}.csv"))

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
    from pipeline.predict_04 import predict_today, simulate_recovery
    today_str = datetime.now(tz=JST).strftime("%Y%m%d")
    import os as _os
    today_file = _os.path.join(str(DATA_DIR), f"today_entries_{today_str}.csv")
    if _os.path.exists(today_file):
        print("  → 当日出馬表あり: リアル予測モードで実行")
        result = _safe("predict_today", predict_today, today_str)
    else:
        print("  → 当日出馬表なし: バックテストモードで実行")
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

    print("\n【STEP 15h】Playwright リアルタイムオッズ取得 (odds_scraper_36)")
    from pipeline.odds_scraper_36 import run_odds_scraper
    _safe("odds_scraper", run_odds_scraper)

    if not skip_stats and isinstance(result, dict):
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

    print("\n【STEP 15i】知識ベース自動進化 (knowledge_curator_41)")
    from pipeline.knowledge_curator_41 import run_knowledge_curator
    _safe("knowledge", run_knowledge_curator, 7)

    print("\n【STEP 16/16】発信・レポート")
    from pipeline.claude_comment_06 import generate_todays_post
    from pipeline.note_07 import generate_note_article
    from pipeline.notify_08 import send_pipeline_report
    from pipeline.roi_tracker_12 import print_roi_report

    post_text = _safe("comment", generate_todays_post)
    _safe("note", generate_note_article)
    _safe("roi_report", print_roi_report)
    _safe("perf_trend", show_performance_trend)

    print("\n【STEP 16b】買い目シート生成 (morning_report)")
    from pipeline.morning_report import run_morning_report
    _safe("morning_report", run_morning_report, today_str)

    print("\n【STEP 16d】Ollama 予想解説記事生成 (ollama_analyst)")
    from pipeline.ollama_analyst import run_ollama_analyst
    _safe("ollama_analyst", run_ollama_analyst, today_str)

    print("\n【STEP 16e】LLM解説付与 (llm_predictor)")
    picks_path = str(DATA_DIR / f"agent_picks_{today_str}.json")
    feat_path  = os.path.join(str(BASE_DIR), "keiba_data_features.csv")
    if os.path.exists(picks_path):
        from pipeline.llm_predictor import add_explanations_to_picks
        explained = _safe("llm_predictor", add_explanations_to_picks,
                          picks_path, feat_path)
        if explained:
            out_path = os.path.join(str(DATA_DIR), f"agent_picks_{today_str}.json")
            import json as _json
            with open(out_path, "w", encoding="utf-8") as _f:
                _json.dump(explained, _f, ensure_ascii=False, indent=2)
            print(f"  [llm_predictor] 解説付きpicks保存: {out_path}")
    else:
        print(f"  [llm_predictor] picks未生成のためスキップ: {picks_path}")

    if not skip_results:
        print("\n【STEP 16c】レース結果取得 & roi_tracker 更新 (result_fetcher)")
        from pipeline.result_fetcher import run_result_fetcher
        _safe("result_fetcher", run_result_fetcher, today_str)

    if not skip_social:
        from pipeline.social_bot_27 import broadcast_picks
        _safe("social", broadcast_picks, post_text)

    _safe("notify", send_pipeline_report, {})

    # ══════════════════════════════════════════════════════
    # 最終サマリー
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print(f"✅ うまなり地蔵AI 全自動実行完了!")
    print(f"⏰ {datetime.now(tz=JST).strftime('%Y-%m-%d %H:%M:%S')}")
    if isinstance(result, dict):
        emoji = "🎉" if result.get('recovery_rate', 0) >= 100 else "📊"
        print(f"{emoji} {year}年 回収率: {result.get('recovery_rate', 0):.1f}%"
              f" | 的中率: {result.get('hit_rate', 0):.1f}%"
              f" | 損益: {result.get('profit', 0):+,.0f}円")
    elif isinstance(result, list) and result:
        print(f"📋 当日予測完了: {len(result)}頭分の予測を生成")
    print("=" * 60)
    print(f"\n📱 ダッシュボード: streamlit run pipeline/dashboard_15.py")


def run_morning(skip_social=False, skip_fetch=False):
    """
    Morning prediction mode v2 -- parallelized for speed.
    serial:  DB sync -> entries -> data fetch -> features -> adv features
    parallel: anomaly + bankroll
    serial:  predict
    parallel: ev + race_sel + backtest + odds_scraper + condition + odds_mon
    parallel: portfolio + ticket + bet_portfolio  (after ev)
    serial:  multi_agent -> knowledge_curator
    parallel: comment + note + morning_report + roi_report
    """
    from concurrent.futures import ThreadPoolExecutor

    print("=" * 62)
    print(f"[morning v2] {datetime.now(tz=JST).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    today_str = datetime.now(tz=JST).strftime("%Y%m%d")
    year      = datetime.now(tz=JST).year

    # P1: serial data + features
    print("\n[P1] data fetch + features (serial)")

    if not skip_fetch:
        _run_mykeibadb_sync()

        from pipeline.shutsuba_fetch import save_today_entries
        from pipeline.data_fetch_01 import fetch_data
        _safe("shutsuba",    save_today_entries)
        _safe("data_fetch",  fetch_data)
    else:
        print("  [skip] data fetch skipped")

    from pipeline.feature_eng_02 import feature_engineering
    _safe("feature_eng", feature_engineering)

    # advanced features: serial (shared CSV writes - cannot parallelize)
    print("  [P1b] advanced features (serial)")
    from pipeline.feature_advanced_19 import run_advanced_feature_engineering
    from pipeline.pace_training_analysis_20 import run_pace_training_analysis
    from pipeline.jockey_trainer_analysis_21 import run_jockey_trainer_analysis
    from pipeline.training_analysis_37 import run_training_analysis
    from pipeline.trainer_analysis_38 import run_trainer_analysis
    from pipeline.debut_analysis_39 import run_debut_analysis
    from pipeline.shogai_analysis_40 import run_shogai_analysis
    _safe("adv_feat",    run_advanced_feature_engineering)
    _safe("pace",        run_pace_training_analysis)
    _safe("jockey",      run_jockey_trainer_analysis)
    _safe("training_a",  run_training_analysis)
    _safe("trainer_a",   run_trainer_analysis)
    _safe("debut_a",     run_debut_analysis)
    _safe("shogai_a",    run_shogai_analysis)

    # P2: anomaly + bankroll (parallel)
    print("\n[P2] anomaly + bankroll (parallel)")
    from pipeline.anomaly_detect_16 import run_anomaly_detection
    from pipeline.bankroll_advanced_24 import run_bankroll_advanced
    from pipeline.auto_learn_13 import run_auto_learn, show_performance_trend

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(_safe, "anomaly",  run_anomaly_detection, year, True)
        fb = ex.submit(_safe, "bankroll", run_bankroll_advanced)
        alerts    = fa.result() or []
        dd_status = fb.result() or {}

    crits = sum(1 for a in alerts if a.get("level") == "CRITICAL")
    if crits:
        print(f"  CRITICAL alerts: {crits}")
    if dd_status.get("multiplier", 1) == 0:
        print("  bankroll protection: bets halted")

    _safe("auto_learn", run_auto_learn,
          os.path.join(str(BASE_DIR), f"simulation_{year}.csv"))

    # P3: enrich today_entries + market odds (serial, before prediction)
    today_file = os.path.join(str(DATA_DIR), f"today_entries_{today_str}.csv")
    if os.path.exists(today_file):
        print("\n[P3] enrich features + market odds")
        from pipeline.enrich_today import enrich_today_entries
        _safe("enrich", enrich_today_entries, today_str)

        odds_model_path = os.path.join(str(BASE_DIR), "odds_model.pkl")
        if os.path.exists(odds_model_path):
            from pipeline.odds_model import predict_market_odds
            _safe("odds_predict", predict_market_odds, today_str)

    # P4a: predict (serial)
    print("\n[P4a] predict")
    from pipeline.predict_04 import predict_today, simulate_recovery
    if os.path.exists(today_file):
        print("  today entries found: real prediction mode")
        result = _safe("predict_today", predict_today, today_str)
    else:
        print("  no today entries: backtest mode")
        result = _safe("predict", simulate_recovery, year)

    # P4b: analysis group A (parallel)
    print("\n[P4b] analysis group A (parallel x4)")
    from pipeline.ev_engine_10 import run_ev_analysis
    from pipeline.race_selector_31 import run_race_selector
    from pipeline.backtest_engine_32 import run_backtest_engine
    from pipeline.backtest_walkforward_35 import run_walkforward_backtest
    from pipeline.condition_adjuster_34 import run_condition_adjuster
    from pipeline.odds_monitor_33 import run_odds_monitor
    from pipeline.odds_scraper_36 import run_odds_scraper

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures_a = [
            ex.submit(_safe, "ev",          run_ev_analysis,          year),
            ex.submit(_safe, "race_sel",    run_race_selector,        year),
            ex.submit(_safe, "backtest",    run_backtest_engine,      year),
            ex.submit(_safe, "walkfwd",     run_walkforward_backtest, False),
            ex.submit(_safe, "cond_adj",    run_condition_adjuster,   year),
            ex.submit(_safe, "odds_mon",    run_odds_monitor,         year),
            ex.submit(_safe, "odds_scrape", run_odds_scraper),
        ]
        for f in futures_a:
            f.result()

    # P4c: portfolio group (parallel, needs ev output)
    print("\n[P4c] portfolio group (parallel x3)")
    from pipeline.portfolio_opt_11 import run_portfolio_optimization
    from pipeline.ticket_optimizer_30 import run_ticket_optimizer
    from pipeline.bet_portfolio_29 import run_bet_portfolio

    with ThreadPoolExecutor(max_workers=3) as ex:
        fp  = ex.submit(_safe, "portfolio",  run_portfolio_optimization, year)
        ft  = ex.submit(_safe, "ticket_opt", run_ticket_optimizer,       year)
        fb2 = ex.submit(_safe, "bet_port",   run_bet_portfolio,          year)
        for f in (fp, ft, fb2):
            f.result()

    # P4d: multi_agent -> knowledge_curator (serial)
    print("\n[P4d] multi_agent + knowledge_curator")
    try:
        from pipeline.multi_agent_v2_28 import run_multi_agent
        _safe("multi_agent", run_multi_agent, year)
    except ImportError:
        print("  LangGraph not installed -> skip")

    from pipeline.knowledge_curator_41 import run_knowledge_curator
    _safe("knowledge", run_knowledge_curator, 7)

    # P5: publishing (parallel)
    print("\n[P5] publishing (parallel)")
    from pipeline.claude_comment_06 import generate_todays_post
    from pipeline.note_07 import generate_note_article
    from pipeline.morning_report import run_morning_report
    from pipeline.roi_tracker_12 import print_roi_report
    from pipeline.notify_08 import send_pipeline_report
    from pipeline.ollama_analyst import run_ollama_analyst

    with ThreadPoolExecutor(max_workers=4) as ex:
        fc = ex.submit(_safe, "comment",     generate_todays_post)
        fn = ex.submit(_safe, "note",        generate_note_article)
        fm = ex.submit(_safe, "morning_rpt", run_morning_report, today_str)
        fr = ex.submit(_safe, "roi_report",  print_roi_report)
        post_text = fc.result()
        for f in (fn, fm, fr):
            f.result()

    picks_path = os.path.join(str(DATA_DIR), f"agent_picks_{today_str}.json")
    feat_path  = os.path.join(str(BASE_DIR), "keiba_data_features.csv")
    with ThreadPoolExecutor(max_workers=2) as ex:
        foa  = ex.submit(_safe, "ollama_analyst", run_ollama_analyst, today_str)
        fllm = None
        if os.path.exists(picks_path):
            from pipeline.llm_predictor import add_explanations_to_picks
            fllm = ex.submit(_safe, "llm_pred",
                             add_explanations_to_picks, picks_path, feat_path)
        foa.result()
        if fllm:
            explained = fllm.result()
            if explained:
                import json as _json
                with open(picks_path, "w", encoding="utf-8") as _fh:
                    _json.dump(explained, _fh, ensure_ascii=False, indent=2)
                print("  llm_predictor: explained picks saved")

    _safe("perf_trend", show_performance_trend)

    if not skip_social:
        from pipeline.social_bot_27 import broadcast_picks
        _safe("social", broadcast_picks, post_text)

    _safe("notify", send_pipeline_report, {})

    print("\n" + "=" * 62)
    print(f"[morning v2] DONE  {datetime.now(tz=JST).strftime('%Y-%m-%d %H:%M:%S')}")
    if isinstance(result, list) and result:
        print(f"  predictions: {len(result)} horses")
    elif isinstance(result, dict):
        print(f"  ROI: {result.get('recovery_rate', 0):.1f}%"
              f"  hit: {result.get('hit_rate', 0):.1f}%")
    print(f"  sheet: reports/morning_{today_str}.txt")
    print("=" * 62)


def run_v2_preflight(weekly: bool = False) -> int:
    """pipeline_v2 の事前診断を実行する。"""
    mode = "週次" if weekly else "日次"
    print(f"pipeline_v2 {mode} preflight を実行します", flush=True)
    cmd = [sys.executable, "-X", "utf8", str(BASE_DIR / "pipeline_v2" / "preflight_check.py")]
    if weekly:
        cmd.append("--weekly")
    return _run_subprocess(cmd)


def run_v2_runtime_check(profile: str = "all", strict: bool = False) -> int:
    """pipeline_v2 の本実行向け依存・ファイル診断を実行する。"""
    print(f"pipeline_v2 runtime check を実行します (profile={profile})", flush=True)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(BASE_DIR / "pipeline_v2" / "runtime_check.py"),
        "--profile",
        profile,
    ]
    if strict:
        cmd.append("--strict")
    return _run_subprocess(cmd)


def run_mykeibadb_daily_sync(timeout_seconds: int = 900) -> int:
    """WSL PostgreSQL 接続先を更新してから mykeibadb を同期する。"""
    print("mykeibadb 日次同期を実行します", flush=True)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(BASE_DIR / "tools" / "mykeibadb_sync.py"),
        "--timeout",
        str(timeout_seconds),
    ]
    return _run_subprocess(cmd)


def run_integrity_check() -> int:
    """成果物の不変条件（リーク・RAG重複など）を確認する。"""
    print("うまなり地蔵AI integrity check を実行します", flush=True)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(BASE_DIR / "tools" / "verify_integrity.py"),
    ]
    return _run_subprocess(cmd)


def run_source_sanity() -> int:
    """構文・空白・固定ローカルパスの軽量チェックを実行する。"""
    print("うまなり地蔵AI source sanity check を実行します", flush=True)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(BASE_DIR / "tools" / "source_sanity.py"),
    ]
    return _run_subprocess(cmd)


def run_doctor(skip_canary: bool = False, strict_external: bool = False) -> int:
    """外部依存・source sanity・runtime・integrity・preflight・canary をまとめて診断する。"""
    print("うまなり地蔵AI doctor を実行します", flush=True)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(BASE_DIR / "tools" / "doctor.py"),
    ]
    if skip_canary:
        cmd.append("--skip-canary")
    if strict_external:
        cmd.append("--strict-external")
    return _run_subprocess(cmd)


def run_v2_daily(trace_id: str = "", preflight: bool = True, preflight_only: bool = False) -> int:
    """pipeline_v2/00_orchestrator.py（日次 DAG）を呼び出す"""
    if preflight and not preflight_only:
        rc = run_v2_runtime_check("daily", strict=True)
        if rc != 0:
            print("pipeline_v2 runtime check で要修復項目があります。必要なら --skip-preflight で続行してください。")
            return rc
    if preflight:
        rc = run_v2_preflight(weekly=False)
        if rc != 0 or preflight_only:
            if rc != 0:
                print("pipeline_v2 日次 preflight で要確認項目があります。必要なら --skip-preflight で続行してください。")
            return rc
    cmd = [sys.executable, "-X", "utf8",
           str(BASE_DIR / "pipeline_v2" / "00_orchestrator.py")]
    if trace_id:
        cmd += ["--trace_id", trace_id]
    return _run_subprocess(cmd)


def run_v2_weekly(trace_id: str = "", preflight: bool = True, preflight_only: bool = False) -> int:
    """pipeline_v2/00_orchestrator_weekly.py（週次 DAG）を呼び出す"""
    if preflight and not preflight_only:
        rc = run_v2_runtime_check("weekly", strict=True)
        if rc != 0:
            print("pipeline_v2 runtime check で要修復項目があります。必要なら --skip-preflight で続行してください。")
            return rc
    if preflight:
        rc = run_v2_preflight(weekly=True)
        if rc != 0 or preflight_only:
            if rc != 0:
                print("pipeline_v2 週次 preflight で要確認項目があります。必要なら --skip-preflight で続行してください。")
            return rc
    cmd = [sys.executable, "-X", "utf8",
           str(BASE_DIR / "pipeline_v2" / "00_orchestrator_weekly.py")]
    if trace_id:
        cmd += ["--trace_id", trace_id]
    return _run_subprocess(cmd)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="うまなり地蔵AI 実行コントロール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
実行モード早見表:
  --v2         pipeline_v2 日次 DAG を実行（推奨）
  --v2-weekly  pipeline_v2 週次 DAG を実行（推奨）
  --morning    朝の予想のみ（約3分）: 出馬表取得→予想→オッズ→買い目シート
  --results    夕方の結果取得（約1分）: 確定結果取得→roi_tracker 更新
  --evening    --results の別名
  --quick      高速モード（約10分）: 学習スキップ・主要ステップのみ
  （引数なし）  フルモード（約60分）: 旧全ステップ実行

例:
  python run_all.py --v2                  # pipeline_v2 日次 DAG（推奨）
  python run_all.py --v2 --sync-mykeibadb # mykeibadb同期→pipeline_v2 日次 DAG
  python run_all.py --v2-weekly           # pipeline_v2 週次 DAG（推奨）
  python run_all.py --v2 --preflight-only # pipeline_v2 日次の事前診断だけ実行
  python run_all.py --runtime-check       # 本実行に必要な依存・ファイルを確認
  python run_all.py --runtime-check --runtime-strict # WARN も失敗扱いで確認
  python run_all.py --integrity-check     # リーク・RAG重複・モデル成果物を確認
  python run_all.py --source-sanity       # 構文・空白・固定ローカルパスを確認
  python run_all.py --doctor              # 総合診断を実行
  python run_all.py --morning             # 朝の予想のみ
  python run_all.py --results             # レース終了後に結果を記録
  python run_all.py --skip-fetch --skip-train  # 予想のみ再実行
""")
    parser.add_argument('--v2',          action='store_true', help='pipeline_v2 日次 DAG を実行（推奨）')
    parser.add_argument('--v2-weekly',   action='store_true', help='pipeline_v2 週次 DAG を実行（推奨）')
    parser.add_argument('--sync-mykeibadb', action='store_true', help='pipeline_v2 実行前に mykeibadb を同期')
    parser.add_argument('--sync-timeout', type=int, default=900, help='mykeibadb 同期待機秒数')
    parser.add_argument('--skip-preflight', action='store_true', help='pipeline_v2 実行前の preflight を省略')
    parser.add_argument('--preflight-only', action='store_true', help='pipeline_v2 の preflight のみ実行して終了')
    parser.add_argument('--runtime-check', action='store_true', help='pipeline_v2 本実行向けの依存・ファイル診断のみ実行')
    parser.add_argument('--runtime-strict', action='store_true', help='--runtime-check 実行時に WARN も失敗扱いにする')
    parser.add_argument('--integrity-check', action='store_true', help='リーク・RAG重複・モデル成果物の整合性チェックのみ実行')
    parser.add_argument('--source-sanity', action='store_true', help='構文・空白・固定ローカルパスの軽量チェックのみ実行')
    parser.add_argument('--doctor',      action='store_true', help='外部依存・source sanity・runtime・integrity・preflight・canary の総合診断を実行')
    parser.add_argument('--doctor-skip-canary', action='store_true', help='--doctor 実行時に canary_run.py を省略')
    parser.add_argument('--doctor-strict-external', action='store_true', help='--doctor 実行時に外部依存 WARN も失敗扱いにする')
    parser.add_argument('--skip-fetch',  action='store_true', help='データ取得をスキップ')
    parser.add_argument('--skip-train',  action='store_true', help='モデル学習をスキップ')
    parser.add_argument('--skip-adv',    action='store_true', help='高度特徴量をスキップ')
    parser.add_argument('--skip-nn',     action='store_true', help='NNをスキップ')
    parser.add_argument('--skip-rl',     action='store_true', help='強化学習をスキップ')
    parser.add_argument('--skip-stats',  action='store_true', help='統計分析をスキップ')
    parser.add_argument('--skip-social', action='store_true', help='SNS投稿をスキップ')
    parser.add_argument('--full-optuna', action='store_true', help='Optuna最適化を実行（重い）')
    parser.add_argument('--quick',       action='store_true', help='高速モード（主要ステップのみ）')
    parser.add_argument('--morning',     action='store_true',
                        help='朝の予想モード（約3分）: 出馬表取得→予想→オッズ→買い目シートのみ')
    parser.add_argument('--results',     action='store_true',
                        help='夕方の結果取得モード: netkeiba から確定結果を取得し roi_tracker を更新')
    parser.add_argument('--evening',     action='store_true',
                        help='夕方モード（--results の別名）')
    args = parser.parse_args()

    if args.runtime_check:
        profile = "weekly" if getattr(args, 'v2_weekly', False) else ("daily" if args.v2 else "all")
        raise SystemExit(run_v2_runtime_check(profile, strict=args.runtime_strict))
    if args.integrity_check:
        raise SystemExit(run_integrity_check())
    if args.source_sanity:
        raise SystemExit(run_source_sanity())
    if args.doctor:
        raise SystemExit(run_doctor(
            skip_canary=args.doctor_skip_canary,
            strict_external=args.doctor_strict_external,
        ))
    if getattr(args, 'v2_weekly', False):
        import uuid
        if not args.preflight_only:
            print("pipeline_v2 週次 DAG を実行します")
        rc = run_v2_weekly(
            trace_id=uuid.uuid4().hex,
            preflight=(not args.skip_preflight) or args.preflight_only,
            preflight_only=args.preflight_only,
        )
        raise SystemExit(rc)
    elif args.v2 or args.preflight_only:
        import uuid
        if not args.preflight_only:
            print("pipeline_v2 日次 DAG を実行します")
        if args.sync_mykeibadb and not args.preflight_only:
            sync_rc = run_mykeibadb_daily_sync(timeout_seconds=args.sync_timeout)
            if sync_rc != 0:
                raise SystemExit(sync_rc)
        rc = run_v2_daily(
            trace_id=uuid.uuid4().hex,
            preflight=(not args.skip_preflight) or args.preflight_only,
            preflight_only=args.preflight_only,
        )
        raise SystemExit(rc)
    elif args.results or args.evening:
        # 夕方の結果取得モード: 予想・学習はスキップして結果だけ取得
        print("🌙 夕方の結果取得モードで実行します")
        from pipeline.result_fetcher import run_result_fetcher
        from zoneinfo import ZoneInfo
        today = datetime.now(tz=ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
        run_result_fetcher(date_str=today)
    elif args.morning:
        # 朝の予想モード: 学習・高度特徴量・NN・RL・統計をスキップ
        print("🌅 朝の予想モードで実行します（約3分）")
        run_morning(skip_social=args.skip_social, skip_fetch=args.skip_fetch)
    else:
        run_all(
            skip_fetch=args.skip_fetch,
            skip_train=args.skip_train,
            skip_advanced_features=args.skip_adv,
            skip_nn=args.skip_nn,
            skip_rl=args.skip_rl,
            skip_social=args.skip_social,
            full_optuna=args.full_optuna,
        )
