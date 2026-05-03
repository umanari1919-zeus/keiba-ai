"""
15_roi_track.py  ─  うまなり地蔵AI / roi_track ステージ
=========================================================
agents.RoiTrackerAgent を呼び出し、日次・週次・月次の損益サマリーを
集計して MonitorAgent へのインプットを pipeline_v2/logs に保存する。
翌朝レース結果確定後に実行することを想定（scheduler.py 07:00 等）。

実行方法:
  python pipeline_v2/15_roi_track.py
  python pipeline_v2/15_roi_track.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import uuid
from datetime import datetime

_WORKTREE = pathlib.Path(r"D:\keiba_ai\.claude\worktrees\brave-kilby-e79e98")
if _WORKTREE.exists() and str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"roi_track_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== roi_track ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.roi_tracker_agent import RoiTrackerAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = RoiTrackerAgent(dry_run=dry_run).execute(meta, {})

    if result.ok:
        out = result.output
        log.info(
            "roi_track 完了: daily_roi=%.1f%% weekly_roi=%.1f%% monthly_roi=%.1f%% losses=%d",
            out.get("daily_roi",   0) * 100,
            out.get("weekly_roi",  0) * 100,
            out.get("monthly_roi", 0) * 100,
            out.get("consecutive_losses", 0),
        )
        for a in out.get("alerts", []):
            log.warning("  [ROI ALERT] %s", a.get("message", ""))

        # メトリクスをファイル保存（09_monitor.py が読み込める）
        metrics_path = LOG_DIR / f"roi_metrics_{today}.json"
        metrics_path.write_text(
            json.dumps(
                {
                    "trace_id":           trace_id,
                    "daily_roi":          out.get("daily_roi", 0.0),
                    "weekly_roi":         out.get("weekly_roi", 0.0),
                    "monthly_roi":        out.get("monthly_roi", 0.0),
                    "consecutive_losses": out.get("consecutive_losses", 0),
                    "daily_summary":      out.get("daily_summary", {}),
                    "alerts":             out.get("alerts", []),
                    "timestamp":          datetime.utcnow().isoformat() + "Z",
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        log.info("メトリクス保存: %s", metrics_path)
        return 0

    log.error("roi_track 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
