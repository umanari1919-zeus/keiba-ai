"""
22_statistics.py — 統計分析ステップ
週次 DAG: 特徴量生成後に実行し統計サマリーを生成する。
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from agents import StatisticsAgent
from agents.base_agent import AgentMeta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace_id",       default="")
    parser.add_argument("--run_tag",        default="weekly")
    parser.add_argument("--year",           type=int, default=0)
    parser.add_argument("--n_clusters",     type=int, default=5)
    parser.add_argument("--mc_simulations", type=int, default=1000)
    parser.add_argument("--dry-run",        action="store_true")
    args = parser.parse_args()

    meta = AgentMeta(
        trace_id=args.trace_id or __import__("uuid").uuid4().hex,
        run_tag=args.run_tag,
    )
    payload: dict = {"n_clusters": args.n_clusters, "mc_simulations": args.mc_simulations}
    if args.year:
        payload["year"] = args.year

    result = StatisticsAgent(dry_run=args.dry_run).execute(meta, payload)
    if not result.ok:
        log.error("StatisticsAgent 失敗: %s", result.error)
        sys.exit(1)
    if args.dry_run:
        log.info("統計分析 dry-run 完了")
        return

    out = result.output
    log.info(
        "統計分析完了: 選択特徴量=%d PCA寄与率[0]=%.3f 破産確率=%.3f",
        len(out.get("selected_features",   [])),
        out.get("pca_variance_ratio",      [0])[0] if out.get("pca_variance_ratio") else 0,
        out.get("mc_ruin_probability",     0.0),
    )
    log.info("結果保存先: %s", out.get("result_path", ""))


if __name__ == "__main__":
    main()
