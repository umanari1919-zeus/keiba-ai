"""
21_backtest_engine.py — EV×Kelly グリッドサーチ ステップ
週次 DAG: backtest 完了後に実行し最適パラメータを探索する。
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from agents import BacktestEngineAgent
from agents.base_agent import AgentMeta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="weekly")
    parser.add_argument("--year",     type=int, default=0)
    args = parser.parse_args()

    meta = AgentMeta(
        trace_id=args.trace_id or __import__("uuid").uuid4().hex,
        run_tag=args.run_tag,
    )
    payload: dict = {}
    if args.year:
        payload["year"] = args.year

    result = BacktestEngineAgent(dry_run=False).execute(meta, payload)
    if not result.ok:
        log.error("BacktestEngineAgent 失敗: %s", result.error)
        sys.exit(1)

    out = result.output
    log.info(
        "グリッドサーチ完了: best_ev=%.2f best_kf=%.2f best_roi=%.1f%%",
        out.get("best_ev_threshold",   0.15),
        out.get("best_kelly_fraction", 0.10),
        out.get("best_roi", 0.0) * 100,
    )
    log.info("結果保存先: %s", out.get("result_path", ""))


if __name__ == "__main__":
    main()
