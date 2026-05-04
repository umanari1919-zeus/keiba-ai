"""
09_monitor.py  ─  うまなり地蔵AI / monitor ステージ
=====================================================
agents.MonitorAgent + OpsAgent を呼び出し、
パイプライン実行後の自動停止条件と稼働状態を確認する。

実行方法:
  python pipeline_v2/09_monitor.py
  python pipeline_v2/09_monitor.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import uuid
from datetime import datetime, timezone

_BASE_DIR = pathlib.Path(r"D:\keiba_ai")
# BASE_DIR を必ず先頭に (worktree より優先)
if str(_BASE_DIR) in sys.path:
    sys.path.remove(str(_BASE_DIR))
sys.path.insert(0, str(_BASE_DIR))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
ALERT_DIR = BASE / "alerts"
LOG_DIR.mkdir(exist_ok=True)
ALERT_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"monitor_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== monitor ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.monitor_agent import MonitorAgent
        from agents.ops_agent import OpsAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta = AgentMeta(trace_id=trace_id, run_tag=run_tag)

    # ─── MonitorAgent: auto_stop 判定 ────────────────────────────
    mon_result = MonitorAgent(dry_run=False).execute(meta, {})
    auto_stop  = False
    alerts_mon: list = []
    if mon_result.ok:
        auto_stop  = mon_result.output.get("auto_stop", False)
        alerts_mon = mon_result.output.get("alerts", [])
        log.info("MonitorAgent: auto_stop=%s alerts=%d", auto_stop, len(alerts_mon))
    else:
        log.warning("MonitorAgent 失敗: %s", mon_result.error)

    # ─── OpsAgent: システムヘルス ────────────────────────────────
    ops_result = OpsAgent(dry_run=False).execute(meta, {})
    ops_ok     = True
    alerts_ops: list = []
    if ops_result.ok:
        ops_ok     = ops_result.output.get("overall_ok", True)
        alerts_ops = ops_result.output.get("alerts", [])
        checks     = ops_result.output.get("checks", {})
        log.info(
            "OpsAgent: ok=%s db=%s disk=%sGB rag=%s",
            ops_ok,
            checks.get("db_connectivity", {}).get("ok"),
            checks.get("disk_space", {}).get("free_gb"),
            checks.get("rag_store_size", {}).get("entries"),
        )
        for a in alerts_ops:
            log.warning("  [OPS ALERT] %s", a)
    else:
        log.warning("OpsAgent 失敗: %s", ops_result.error)

    # ─── レポート保存 ────────────────────────────────────────────
    report = {
        "trace_id":   trace_id,
        "run_tag":    run_tag,
        "auto_stop":  auto_stop,
        "ops_ok":     ops_ok,
        "alerts":     alerts_mon + alerts_ops,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }
    report_path = ALERT_DIR / f"monitor_{today}_{trace_id[:8]}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("レポート保存: %s", report_path)

    if auto_stop:
        log.error("[AUTO-STOP] 自動停止条件が発動しました")
        return 2  # オーケストレーターが AUTO_STOP として認識できる終了コード

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
