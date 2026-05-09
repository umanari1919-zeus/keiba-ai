"""
24_enrich_today.py  ─  当日出馬表の特徴量補完 + 市場オッズ推定
============================================================
日次 DAG（dag_spec.json）で feature_gen の後に実行。
1. enrich_today: 過去データから不足特徴量を補完
2. odds_model predict: 市場オッズを推定し tansho_odds に書き込む

実行方法:
  python pipeline_v2/24_enrich_today.py
  python pipeline_v2/24_enrich_today.py --date 20260510
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, DATA_DIR

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"enrich_today_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="当日出馬表の特徴量補完")
    parser.add_argument("--date", default=None, help="YYYYMMDD")
    args, _ = parser.parse_known_args()

    date_str = args.date or today
    today_file = os.path.join(str(DATA_DIR), f"today_entries_{date_str}.csv")

    if not os.path.exists(today_file):
        log.info(f"出馬表なし: {today_file} → スキップ")
        return 0

    log.info(f"=== enrich_today 開始 ({date_str}) ===")

    try:
        from pipeline.enrich_today import enrich_today_entries
        enrich_today_entries(date_str)
    except Exception as e:
        log.exception(f"enrich_today 失敗: {e}")
        return 1

    odds_model_path = os.path.join(str(BASE_DIR), "odds_model.pkl")
    if os.path.exists(odds_model_path):
        try:
            from pipeline.odds_model import predict_market_odds
            predict_market_odds(date_str)
        except Exception as e:
            log.warning(f"odds_model predict 失敗（非致命的）: {e}")

    log.info("=== enrich_today 完了 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
