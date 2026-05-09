"""
23_odds_model_train.py  ─  市場オッズ予測モデル再学習
====================================================
週次 DAG（dag_spec_weekly.json）で weekly_train の後に実行。
pipeline/odds_model.py の train_odds_model() を呼ぶ。

実行方法:
  python pipeline_v2/23_odds_model_train.py
  python pipeline_v2/23_odds_model_train.py --test-year 2025
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
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
        logging.FileHandler(LOG_DIR / f"odds_model_train_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="市場オッズ予測モデル再学習")
    parser.add_argument("--test-year", type=int, default=datetime.now().year,
                        help="検証年 (default: 今年)")
    args, _ = parser.parse_known_args()

    log.info("=== odds_model 再学習 開始 ===")
    try:
        from pipeline.odds_model import train_odds_model
        result = train_odds_model(test_year=args.test_year)
        metrics = result.get("metrics", {})
        log.info(f"R²={metrics.get('r2', 0):.4f}  "
                 f"rank_corr={metrics.get('rank_corr', 0):.4f}  "
                 f"MAE={metrics.get('mae', 0):.1f}")
        log.info("=== odds_model 再学習 完了 ===")
        return 0
    except Exception as e:
        log.exception(f"odds_model 再学習失敗: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
