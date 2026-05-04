"""
11_weekly_train.py  ─  うまなり地蔵AI / weekly_train ステージ
==============================================================
agents.TrainAgent を呼び出してモデル再学習と model_registry 登録を行う。
週次 DAG（dag_spec_weekly.json）の最初のステップ。

実行方法:
  python pipeline_v2/11_weekly_train.py
  python pipeline_v2/11_weekly_train.py --skip-train   # pkl 読み込みのみ（テスト用）
"""

from __future__ import annotations

import argparse
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

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"weekly_train_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", skip_train: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== weekly_train ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.train_agent import TrainAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = TrainAgent(dry_run=False).execute(meta, {"skip_train": skip_train})

    if result.ok:
        out = result.output
        metrics = out.get("metrics", {})
        log.info(
            "weekly_train 完了: model_id=%s ensemble_acc=%s val_acc=%s",
            out.get("model_id"),
            metrics.get("ensemble_acc", "N/A"),
            metrics.get("val_acc", "N/A"),
        )
        return 0
    log.error("weekly_train 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="週次モデル再学習")
    parser.add_argument("--skip-train", action="store_true", help="学習をスキップして pkl のみ読み込む（テスト用）")
    parser.add_argument("--trace_id",   default="")
    parser.add_argument("--run_tag",    default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.skip_train))
