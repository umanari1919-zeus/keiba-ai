"""
13_backtest.py  ─  うまなり地蔵AI / backtest ステージ
======================================================
agents.BacktestAgent を呼び出し、ウォークフォワード検証を実行して
汎化性能を評価する。週次 DAG の weekly_train 直後に実行される。

実行方法:
  python pipeline_v2/13_backtest.py
  python pipeline_v2/13_backtest.py --dry-run      # 既存結果を読み込み
  python pipeline_v2/13_backtest.py --retrain       # 各折でモデル再学習
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
import uuid
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
# プロジェクトルートを必ず先頭に (worktree より優先)
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"backtest_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, retrain: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== backtest ステージ開始 trace=%s retrain=%s ===", trace_id, retrain)

    try:
        from agents.backtest_agent import BacktestAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = BacktestAgent(dry_run=dry_run).execute(meta, {
        "retrain":        retrain,
        "skip_backtest":  dry_run,
    })

    if result.ok:
        out = result.output
        verdict = out.get("verdict", "")
        log.info(
            "backtest 完了: avg_roi=%.1f%% avg_hit=%.1f%% avg_dd=%.1f%% %d/%d折プラス 判定=%s",
            out.get("avg_roi", 0),
            out.get("avg_hit_rate", 0),
            out.get("avg_max_dd", 0),
            out.get("n_positive_folds", 0),
            out.get("n_total_folds", 0),
            verdict,
        )
        # FAIL 判定でも終了コード 0（警告として記録するが後続ステージは継続）
        if verdict.startswith("FAIL"):
            log.warning("[BACKTEST WARN] 汎化性能要確認: %s", verdict)
        return 0

    log.error("backtest 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="既存結果を読み込む")
    parser.add_argument("--retrain",  action="store_true", help="各折でモデル再学習（低速）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.retrain))
