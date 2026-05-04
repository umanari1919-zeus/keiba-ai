"""
07_trade.py  ─  うまなり地蔵AI / trade ステージ
=================================================
agents.TradingAgent を呼び出し、MarketAgent シグナルと
LLM 説明を組み合わせてベット候補を算出・記録する。
paper_trading=True の間は実発注しない。

実行方法:
  python pipeline_v2/07_trade.py
  python pipeline_v2/07_trade.py --dry-run
  python pipeline_v2/07_trade.py --live       # 実発注（慎重に）
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import uuid
from datetime import datetime

_BASE_DIR = pathlib.Path(r"D:\keiba_ai")
# BASE_DIR を必ず先頭に (worktree より優先)
if str(_BASE_DIR) in sys.path:
    sys.path.remove(str(_BASE_DIR))
sys.path.insert(0, str(_BASE_DIR))

BASE_DIR = pathlib.Path("D:/keiba_ai")
DATA_DIR = BASE_DIR / "data"
BASE     = pathlib.Path(__file__).parent
LOG_DIR  = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"trade_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_predictions() -> list:
    """ev_analysis_{year}.csv から当日の予測を読み込む。"""
    year = datetime.now().year
    for search in [DATA_DIR, BASE_DIR]:
        path = search / f"ev_analysis_{year}.csv"
        if path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
                preds = []
                for _, row in df.iterrows():
                    preds.append({
                        "race_id":               str(row.get("race_code", row.get("race_id", ""))),
                        "entry_id":              str(row.get("umaban",    row.get("entry_id", ""))),
                        "win_prob":              float(row.get("win_probability",  0)),
                        "place_prob":            float(row.get("place_probability", 0)),
                        "expected_return":       float(row.get("expected_value",    row.get("ev", 0))),
                        "uncertainty":           float(row.get("uncertainty", 0.30)),
                        "odds":                  float(row.get("odds_decimal", row.get("tansho_odds", 100)) / (100 if float(row.get("tansho_odds", 100)) > 100 else 1)),
                        "model_agreement_count": int(row.get("model_agreement_count", 2)),
                    })
                log.info("予測読み込み: %s (%d件)", path.name, len(preds))
                return preds
            except Exception as exc:
                log.warning("予測読み込みエラー: %s", exc)
    log.warning("ev_analysis CSV が見つかりません")
    return []


def _load_market_signals() -> dict:
    """当日の MarketAgent シグナルを読み込む（あれば）。"""
    snaps = sorted(DATA_DIR.glob("odds_snapshot_*.json"), reverse=True)
    if not snaps:
        return {}
    try:
        from agents.market_agent import MarketAgent
        from agents.base_agent import AgentMeta
        meta   = AgentMeta()
        result = MarketAgent(dry_run=False).execute(meta, {})
        if result.ok:
            return result.output.get("market_signals", {})
    except Exception as exc:
        log.debug("MarketAgent 呼び出し失敗: %s", exc)
    return {}


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, live: bool = False) -> int:
    trace_id     = trace_id or str(uuid.uuid4())
    run_tag      = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    paper_trading = not live
    log.info("=== trade ステージ開始 trace=%s paper=%s ===", trace_id, paper_trading)

    try:
        from agents.trading_agent import TradingAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    predictions    = _load_predictions()
    market_signals = _load_market_signals()

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = TradingAgent(paper_trading=paper_trading, dry_run=dry_run).execute(meta, {
        "predictions":     predictions,
        "quarantine_count": 0,
        "market_signals":   market_signals,
    })

    if result.ok:
        out = result.output
        log.info(
            "trade 完了: candidates=%s skipped_s1=%s skipped_s2=%s paper=%s",
            len(out.get("candidate_bets", [])),
            out.get("skipped_stage1", 0),
            out.get("skipped_stage2", 0),
            out.get("paper_trading", True),
        )
        return 0
    log.error("trade 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--live",     action="store_true", help="実発注（デフォルトはペーパー）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.live))
