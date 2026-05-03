"""
canary_run.py — end-to-end ドライラン検証スクリプト
=====================================================
マニフェスト immediate_actions #9:
  "canary: ingest → normalize → feature_gen → batch_inference → explain (dry-run)
   and validate monitor auto-stop"

実行方法:
  python canary_run.py               # ドライラン（実発注なし）
  python canary_run.py --live        # 実際のスクリプトを実行（要注意）
  python canary_run.py --schema-only # スキーマ登録のみ
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time
from datetime import datetime, timezone

# ─── パス設定 ──────────────────────────────────────────────────────
BASE_DIR  = pathlib.Path("D:/keiba_ai")
WORKTREE  = pathlib.Path(__file__).parent
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(BASE_DIR))

# ─── ログ設定 ──────────────────────────────────────────────────────
LOG_DIR = WORKTREE / "logs"
LOG_DIR.mkdir(exist_ok=True)
today   = datetime.now().strftime("%Y%m%d_%H%M%S")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"canary_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("canary")


# ================================================================== #
# ヘルパー
# ================================================================== #

class CanaryResult:
    def __init__(self) -> None:
        self.steps:   list[dict] = []
        self.passed   = 0
        self.failed   = 0
        self.skipped  = 0

    def record(self, step: str, ok: bool | None, detail: str = "") -> None:
        status = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
        self.steps.append({"step": step, "status": status, "detail": detail})
        if ok is True:
            self.passed  += 1
        elif ok is False:
            self.failed  += 1
        else:
            self.skipped += 1
        icon = "[PASS]" if ok is True else ("[SKIP]" if ok is None else "[FAIL]")
        log.info("%s %s %s", icon, step, detail or "")

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def summary(self) -> str:
        total = self.passed + self.failed + self.skipped
        return (
            f"\n{'='*60}\n"
            f"カナリアラン結果: {self.passed}/{total} PASS  "
            f"({self.failed} FAIL, {self.skipped} SKIP)\n"
            f"{'='*60}"
        )


# ================================================================== #
# カナリアラン本体
# ================================================================== #

def run_canary(dry_run: bool = True, schema_only: bool = False) -> CanaryResult:
    from agents import BaseAgent, AgentMeta, SchemaRegistry, AuditLogger

    res  = CanaryResult()
    meta = AgentMeta()
    meta.data_snapshot_id = f"canary_{today}"

    log.info("=== カナリアラン開始 trace_id=%s dry_run=%s ===",
             meta.trace_id, dry_run)

    # ─────────────────────────────────────────────
    # STEP 0: スキーマレジストリ登録
    # ─────────────────────────────────────────────
    try:
        registry = SchemaRegistry(strict=True)
        registry.register_to_db()
        res.record("schema_registry.register_to_db", True, f"{len(registry._check_jsonschema() and [])} schemas")
    except Exception as exc:
        res.record("schema_registry.register_to_db", False, str(exc))

    if schema_only:
        return res

    # ─────────────────────────────────────────────
    # STEP 1: IngestAgent
    # ─────────────────────────────────────────────
    try:
        from agents.ingest_agent import IngestAgent
        agent  = IngestAgent(dry_run=dry_run)
        result = agent.execute(meta, {"source": "canary"})
        res.record("ingest_agent", result.ok, result.error or "")
        if result.ok:
            meta.data_snapshot_id = result.output.get("data_snapshot_id", meta.data_snapshot_id)
    except Exception as exc:
        res.record("ingest_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 2: NormalizerAgent
    # ─────────────────────────────────────────────
    try:
        from agents.normalizer_agent import NormalizerAgent
        agent  = NormalizerAgent(dry_run=dry_run)
        result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
        mismatch = result.output.get("mismatch_rate", 0)
        res.record("normalizer_agent", result.ok,
                   f"mismatch_rate={mismatch:.4f}" if result.ok else result.error)
    except Exception as exc:
        res.record("normalizer_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 3: FeatureAgent
    # ─────────────────────────────────────────────
    try:
        from agents.feature_agent import FeatureAgent
        agent  = FeatureAgent(dry_run=dry_run)
        result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
        fset_id = result.output.get("feature_set_id", "")
        res.record("feature_agent", result.ok,
                   f"feature_set_id={fset_id}" if result.ok else result.error)
    except Exception as exc:
        res.record("feature_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 3.2: TrainAgent（skip_train モード）
    # ─────────────────────────────────────────────
    try:
        from agents.train_agent import TrainAgent
        agent  = TrainAgent(dry_run=False)
        result = agent.execute(meta, {"skip_train": True})
        mid    = result.output.get("model_id", "") if result.ok else ""
        res.record("train_agent(skip_train)", result.ok,
                   f"model_id={mid}" if result.ok else result.error)
    except Exception as exc:
        res.record("train_agent(skip_train)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 3.5: RAGStore 類似馬検索
    # ─────────────────────────────────────────────
    try:
        from agents.rag_store import get_default_store
        store = get_default_store()
        # インデックスが空でも search() がクラッシュしないか確認
        hits = store.search({"win_probability": 0.15, "tansho_odds": 2500}, top_k=3)
        res.record("rag_store.search", True, f"hits={len(hits)} backend={store._backend}")
    except Exception as exc:
        res.record("rag_store.search", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 4: BatchInferenceAgent
    # ─────────────────────────────────────────────
    try:
        from agents.batch_inference_agent import BatchInferenceAgent
        agent  = BatchInferenceAgent(dry_run=dry_run)
        result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
        n_preds = len(result.output.get("predictions", []))
        res.record("batch_inference_agent", result.ok,
                   f"predictions={n_preds}" if result.ok else result.error)
        predictions = result.output.get("predictions", [])
    except Exception as exc:
        res.record("batch_inference_agent", False, str(exc))
        predictions = []

    # ─────────────────────────────────────────────
    # STEP 4.5: MarketAgent スリッページ推定
    # ─────────────────────────────────────────────
    try:
        from agents.market_agent import MarketAgent
        slip = MarketAgent.estimate_slippage(
            stake=10000, odds=15.0, liquidity=0.6, steam_detected=False
        )
        ok_slip = "slippage_pct" in slip and "expected_odds" in slip
        res.record("market_agent.estimate_slippage", ok_slip,
                   f"slippage={slip.get('slippage_pct'):.4f} expected_odds={slip.get('expected_odds')}")
    except Exception as exc:
        res.record("market_agent.estimate_slippage", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 4.6: UpsetScore dry-run
    # ─────────────────────────────────────────────
    try:
        sys.path.insert(0, str(BASE_DIR / "pipeline_v2"))
        from importlib import import_module
        us_mod = import_module("08_upsetscore")
        result_us = us_mod.run_upsetscore(dry_run=True)
        races = result_us.get("races_computed", 0)
        res.record("upsetscore.run_upsetscore(dry-run)", True,
                   f"races={races} top_upset={result_us.get('top_upsets', [{}])[0].get('upset_score', 0) if result_us.get('top_upsets') else 'N/A'}")
    except Exception as exc:
        res.record("upsetscore.run_upsetscore(dry-run)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 5: LLMExplainAgent（dry-run）
    # ─────────────────────────────────────────────
    try:
        from agents.llm_explain_agent import LLMExplainAgent
        agent  = LLMExplainAgent(dry_run=True)  # explain は常に dry-run
        result = agent.execute(meta, {"predictions": predictions[:3]})
        n_review = len(result.output.get("requires_human_review", []))
        res.record("llm_explain_agent(dry-run)", result.ok,
                   f"requires_review={n_review}" if result.ok else result.error)
        llm_output = result.output
    except Exception as exc:
        res.record("llm_explain_agent(dry-run)", False, str(exc))
        llm_output = {}

    # ─────────────────────────────────────────────
    # STEP 6: TradingAgent（paper_trading）
    # ─────────────────────────────────────────────
    try:
        from agents.trading_agent import TradingAgent
        agent  = TradingAgent(paper_trading=True, dry_run=dry_run)
        result = agent.execute(meta, {
            "predictions":     predictions[:3],
            "quarantine_count": 0,
        })
        n_bets = len(result.output.get("candidate_bets", []))
        res.record("trading_agent(paper)", result.ok,
                   f"candidate_bets={n_bets}" if result.ok else result.error)
    except Exception as exc:
        res.record("trading_agent(paper)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 7: MonitorAgent — auto_stop 検証
    # ─────────────────────────────────────────────
    try:
        from agents.monitor_agent import MonitorAgent
        agent  = MonitorAgent(dry_run=False)  # monitor は常に実行
        result = agent.execute(meta, {
            "mismatch_rate":    0.005,   # 正常値（0.02 以下）
            "quarantine_count": 0,
            "spearman":         0.72,
            "daily_roi":        0.01,
            "consecutive_losses": 1,
        })
        auto_stop = result.output.get("auto_stop", False)
        n_alerts  = len(result.output.get("alerts", []))
        res.record("monitor_agent", result.ok,
                   f"auto_stop={auto_stop} alerts={n_alerts}" if result.ok else result.error)

        # auto_stop が発動したらカナリアは失敗
        if auto_stop:
            res.record("auto_stop_check", False, "auto_stop が発動しました（閾値超過）")
        else:
            res.record("auto_stop_check", True, "auto_stop 未発動（正常）")
    except Exception as exc:
        res.record("monitor_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 8: スキーマ検証（inference_output_v1）
    # ─────────────────────────────────────────────
    try:
        from agents.schema_registry import SchemaRegistry
        reg   = SchemaRegistry()
        dummy = {
            "trace_id":         meta.trace_id,
            "run_tag":          meta.run_tag,
            "agent_id":         "batch-inference-agent",
            "agent_version":    "2.0.0",
            "data_snapshot_id": meta.data_snapshot_id,
            "predictions": [{
                "race_id":         "2026050301",
                "entry_id":        "12",
                "win_prob":        0.22,
                "place_prob":      0.45,
                "expected_return": 1.18,
                "uncertainty":     0.25,
            }],
            "output_hash": "abc123",
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }
        ok, errs = reg.validate("inference_output_v1", dummy)
        res.record("schema_validate.inference_output_v1", ok,
                   "" if ok else str(errs))
    except Exception as exc:
        res.record("schema_validate.inference_output_v1", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 9: OpsAgent ヘルスチェック
    # ─────────────────────────────────────────────
    try:
        from agents.ops_agent import OpsAgent
        agent  = OpsAgent(dry_run=False)
        result = agent.execute(meta, {})
        checks = result.output.get("checks", {}) if result.ok else {}
        db_ok  = checks.get("db_connectivity", {}).get("ok", False)
        disk_gb= checks.get("disk_space", {}).get("free_gb", 0)
        rag_sz = checks.get("rag_store_size", {}).get("entries", 0)
        res.record("ops_agent.health_check", result.ok,
                   f"db={db_ok} disk={disk_gb:.1f}GB rag={rag_sz}entries" if result.ok else result.error)
    except Exception as exc:
        res.record("ops_agent.health_check", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 10: KnowledgeAgent（dry_run モード）
    # ─────────────────────────────────────────────
    try:
        from agents.knowledge_agent import KnowledgeAgent
        agent  = KnowledgeAgent(dry_run=True)
        result = agent.execute(meta, {"days": 7})
        active = result.output.get("active_count", 0) if result.ok else 0
        res.record("knowledge_agent(dry-run)", result.ok,
                   f"active_count={active}" if result.ok else result.error)
    except Exception as exc:
        res.record("knowledge_agent(dry-run)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11: AnomalyAgent（DB なし・dry-run モード）
    # ─────────────────────────────────────────────
    try:
        from agents.anomaly_agent import AnomalyAgent
        agent  = AnomalyAgent(dry_run=dry_run)
        result = agent.execute(meta, {"use_db": False})
        critical = result.output.get("critical_count", 0) if result.ok else -1
        auto_stp = result.output.get("auto_stop", False)  if result.ok else False
        res.record("anomaly_agent(no-db)", result.ok,
                   f"critical={critical} auto_stop={auto_stp}" if result.ok else result.error)
    except Exception as exc:
        res.record("anomaly_agent(no-db)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11.2: RaceSelectorAgent（特徴量 CSV なし時も安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.race_selector_agent import RaceSelectorAgent
        agent  = RaceSelectorAgent(dry_run=dry_run)
        result = agent.execute(meta, {})
        n_s = len(result.output.get("grade_s", [])) if result.ok else -1
        n_a = len(result.output.get("grade_a", [])) if result.ok else -1
        res.record("race_selector_agent", result.ok,
                   f"grade_S={n_s} grade_A={n_a}" if result.ok else result.error)
    except Exception as exc:
        res.record("race_selector_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11.5: PortfolioAgent（空 candidate_bets で安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.portfolio_agent import PortfolioAgent
        agent  = PortfolioAgent(dry_run=dry_run)
        result = agent.execute(meta, {
            "candidate_bets": predictions[:2],  # batch_inference の予測を流用
        })
        n_final = len(result.output.get("finalized_bets", [])) if result.ok else -1
        summary = result.output.get("summary", {})                if result.ok else {}
        res.record("portfolio_agent", result.ok,
                   f"finalized={n_final} amount={summary.get('total_amount',0)}"
                   if result.ok else result.error)
    except Exception as exc:
        res.record("portfolio_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11.7: ConditionAdjusterAgent（空ベットで安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.condition_adjuster_agent import ConditionAdjusterAgent
        agent  = ConditionAdjusterAgent(dry_run=dry_run)
        result = agent.execute(meta, {"finalized_bets": []})
        avg_c  = result.output.get("avg_coeff", 1.0) if result.ok else -1.0
        res.record("condition_adjuster_agent", result.ok,
                   f"avg_coeff={avg_c:.3f}" if result.ok else result.error)
    except Exception as exc:
        res.record("condition_adjuster_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11.9: AutoLearnAgent（dry-run モード）
    # ─────────────────────────────────────────────
    try:
        from agents.auto_learn_agent import AutoLearnAgent
        agent  = AutoLearnAgent(dry_run=True)
        result = agent.execute(meta, {})
        triggered = result.output.get("retrain_triggered", False) if result.ok else None
        reason    = result.output.get("reason", "")              if result.ok else ""
        res.record("auto_learn_agent(dry-run)", result.ok,
                   f"triggered={triggered} reason={reason[:40]}" if result.ok else result.error)
    except Exception as exc:
        res.record("auto_learn_agent(dry-run)", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 11.8: BankrollAgent（bankroll.json なし時も安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.bankroll_agent import BankrollAgent
        agent  = BankrollAgent(dry_run=dry_run)
        result = agent.execute(meta, {"adjusted_bets": []})
        dd     = result.output.get("drawdown",    0.0)  if result.ok else -1.0
        mult   = result.output.get("multiplier",  1.0)  if result.ok else -1.0
        stop   = result.output.get("stop_betting", False) if result.ok else None
        res.record("bankroll_agent", result.ok,
                   f"drawdown={dd:.3f} multiplier={mult:.2f} stop={stop}"
                   if result.ok else result.error)
    except Exception as exc:
        res.record("bankroll_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 12: RoiTrackerAgent（tracker CSV なし時も安全に動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.roi_tracker_agent import RoiTrackerAgent
        agent  = RoiTrackerAgent(dry_run=dry_run)
        result = agent.execute(meta, {})
        d_roi  = result.output.get("daily_roi", 0.0) if result.ok else 0.0
        losses = result.output.get("consecutive_losses", 0) if result.ok else 0
        res.record("roi_tracker_agent", result.ok,
                   f"daily_roi={d_roi:.3f} losses={losses}" if result.ok else result.error)
    except Exception as exc:
        res.record("roi_tracker_agent", False, str(exc))

    # ─────────────────────────────────────────────
    # STEP 13: BacktestAgent（skip_backtest モード）
    # ─────────────────────────────────────────────
    try:
        from agents.backtest_agent import BacktestAgent
        agent  = BacktestAgent(dry_run=False)
        result = agent.execute(meta, {"skip_backtest": True})
        verdict = result.output.get("verdict", "") if result.ok else ""
        res.record("backtest_agent(skip)", result.ok,
                   f"verdict={verdict}" if result.ok else result.error)
    except Exception as exc:
        res.record("backtest_agent(skip)", False, str(exc))

    # STEP 14: BacktestEngineAgent（既存結果ファイルなし時も安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.backtest_engine_agent import BacktestEngineAgent
        agent  = BacktestEngineAgent(dry_run=dry_run)
        result = agent.execute(meta, {})
        best_ev = result.output.get("best_ev_threshold", 0.15) if result.ok else 0.15
        res.record("backtest_engine_agent", result.ok,
                   f"best_ev={best_ev:.2f}" if result.ok else result.error)
    except Exception as exc:
        res.record("backtest_engine_agent", False, str(exc))

    # STEP 15: StatisticsAgent（特徴量 CSV なし時も安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.statistics_agent import StatisticsAgent
        agent  = StatisticsAgent(dry_run=dry_run)
        result = agent.execute(meta, {"n_clusters": 3, "mc_simulations": 100})
        skipped = "skipped_reason" in (result.output or {})
        res.record("statistics_agent", result.ok,
                   ("skip: " + result.output.get("skipped_reason", "")) if skipped
                   else f"features={len(result.output.get('selected_features', []))}")
    except Exception as exc:
        res.record("statistics_agent", False, str(exc))

    # STEP 17: SocialBotAgent（dry_run モード — 実 SNS 配信をスキップ）
    # ─────────────────────────────────────────────
    try:
        from agents.social_bot_agent import SocialBotAgent
        agent  = SocialBotAgent(dry_run=True)
        result = agent.execute(meta, {})
        skipped = "skipped_reason" in (result.output or {})
        res.record("social_bot_agent(dry)", result.ok,
                   "skip:dry_run" if skipped else f"posted={result.output.get('posted_channels', [])}")
    except Exception as exc:
        res.record("social_bot_agent(dry)", False, str(exc))

    # STEP 18: OddsScraperAgent（dry_run モード — Playwright 呼び出しをスキップ）
    # ─────────────────────────────────────────────
    try:
        from agents.odds_scraper_agent import OddsScraperAgent
        agent  = OddsScraperAgent(dry_run=True)
        result = agent.execute(meta, {})
        skipped = "skipped_reason" in (result.output or {})
        res.record("odds_scraper_agent(dry)", result.ok,
                   "skip:dry_run" if skipped else f"races={result.output.get('race_count', 0)}")
    except Exception as exc:
        res.record("odds_scraper_agent(dry)", False, str(exc))

    # STEP 19: OddsMonitorAgent（スクリプト未存在時も安全動作確認）
    # ─────────────────────────────────────────────
    try:
        from agents.odds_monitor_agent import OddsMonitorAgent
        agent  = OddsMonitorAgent(dry_run=dry_run)
        result = agent.execute(meta, {})
        skipped = "skipped_reason" in (result.output or {})
        res.record("odds_monitor_agent", result.ok,
                   ("skip: " + result.output.get("skipped_reason", "")) if skipped
                   else f"SHARP={result.output.get('sharp_count',0)} STEAM={result.output.get('steam_count',0)}")
    except Exception as exc:
        res.record("odds_monitor_agent", False, str(exc))

    # STEP 16: MultiAgentV2Agent（dry_run モード — LangGraph 呼び出しをスキップ）
    # ─────────────────────────────────────────────
    try:
        from agents.multi_agent_v2_agent import MultiAgentV2Agent
        agent  = MultiAgentV2Agent(dry_run=True)
        result = agent.execute(meta, {"mode": "pipeline"})
        skipped = "skipped_reason" in (result.output or {})
        res.record("multi_agent_v2_agent(dry)", result.ok,
                   "skip:dry_run" if skipped else f"picks={result.output.get('total_bets',0)}")
    except Exception as exc:
        res.record("multi_agent_v2_agent(dry)", False, str(exc))

    # ─────────────────────────────────────────────
    # 結果サマリ
    # ─────────────────────────────────────────────
    log.info(res.summary())

    # JSON レポート保存
    report = {
        "trace_id":   meta.trace_id,
        "run_tag":    meta.run_tag,
        "dry_run":    dry_run,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "steps":      res.steps,
        "all_passed": res.all_passed,
    }
    report_path = LOG_DIR / f"canary_report_{today}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("レポート保存: %s", report_path)

    return res


# ================================================================== #
# エントリーポイント
# ================================================================== #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="うまなり地蔵AI カナリアラン")
    parser.add_argument("--live",        action="store_true", help="実スクリプト実行（デフォルト: dry-run）")
    parser.add_argument("--schema-only", action="store_true", help="スキーマ登録のみ")
    args = parser.parse_args()

    result = run_canary(
        dry_run=not args.live,
        schema_only=args.schema_only,
    )
    sys.exit(0 if result.all_passed else 1)
