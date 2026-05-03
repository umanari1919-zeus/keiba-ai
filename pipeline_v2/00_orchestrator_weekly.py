"""
00_orchestrator_weekly.py  ─  うまなり地蔵AI 週次バッチ制御塔
=============================================================
dag_spec_weekly.json に従い週次ステージを実行する。
毎週日曜 02:00 に scheduler.py から起動されることを想定。

実行方法:
  python pipeline_v2/00_orchestrator_weekly.py
  python pipeline_v2/00_orchestrator_weekly.py --dry-run
"""

import json
import logging
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime, timezone

# ─── agents/ パス ────────────────────────────────────────────
_WORKTREE = pathlib.Path(r"D:\keiba_ai\.claude\worktrees\brave-kilby-e79e98")
if _WORKTREE.exists() and str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

BASE       = pathlib.Path(__file__).parent
CONFIG_DIR = BASE / "config"
LOG_DIR    = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today    = datetime.now().strftime("%Y%m%d")
log_file = LOG_DIR / f"orchestrator_weekly_{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

TRACE_ID = str(uuid.uuid4())
RUN_TAG  = f"weekly_{today}_{TRACE_ID[:8]}"


def load_dag_spec() -> dict:
    spec_path = CONFIG_DIR / "dag_spec_weekly.json"
    with open(spec_path, encoding="utf-8") as f:
        return json.load(f)


def run_stage(script_name: str, task_id: str, extra_args: list[str] | None = None) -> bool:
    script_path = BASE / script_name
    log.info(">> ステージ開始: %s (%s)", task_id, script_name)

    if not script_path.exists():
        log.warning("  スクリプトが見つかりません: %s -> スキップ", script_path)
        return True

    cmd = [
        sys.executable, "-X", "utf8", str(script_path),
        "--trace_id", TRACE_ID,
        "--run_tag",  RUN_TAG,
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.stdout:
        log.info(result.stdout.strip())
    if result.stderr:
        log.warning(result.stderr.strip())

    if result.returncode == 0:
        log.info("  [OK] %s 完了", task_id)
        return True
    log.error("  [NG] %s 失敗 (returncode=%d)", task_id, result.returncode)
    return False


def check_ops_health() -> tuple[bool, str]:
    """OpsAgent でシステムヘルスを確認。問題があれば (False, reason) を返す。"""
    try:
        from agents.ops_agent import OpsAgent
        from agents.base_agent import AgentMeta
        meta   = AgentMeta(trace_id=TRACE_ID, run_tag=RUN_TAG)
        result = OpsAgent(dry_run=False).execute(meta, {})
        if result.ok:
            ok      = result.output.get("overall_ok", True)
            alerts  = result.output.get("alerts", [])
            reason  = "; ".join(alerts) if alerts else ""
            return ok, reason
    except Exception as exc:
        log.debug("OpsAgent fallback: %s", exc)
    return True, ""


def resolve_execution_order(dag: list) -> list:
    task_map  = {t["task_id"]: t for t in dag}
    completed: set = set()
    ordered:   list = []

    def visit(task_id: str) -> None:
        if task_id in completed:
            return
        for dep in task_map[task_id].get("depends_on", []):
            visit(dep)
        ordered.append(task_map[task_id])
        completed.add(task_id)

    for task in dag:
        visit(task["task_id"])
    return ordered


def main(dry_run: bool = False) -> int:
    log.info("=" * 60)
    log.info("うまなり地蔵AI 週次バッチ起動")
    log.info("  TRACE_ID : %s", TRACE_ID)
    log.info("  RUN_TAG  : %s", RUN_TAG)
    log.info("  開始時刻 : %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)

    # ─── Ops ヘルスチェック ───────────────────────────────────
    healthy, reason = check_ops_health()
    if not healthy:
        log.error("[OPS] ヘルスチェック失敗: %s", reason)
        log.error("  週次バッチを中止します")
        return 1
    log.info("[OPS] ヘルスチェック OK")

    # ─── DAG 読み込み ─────────────────────────────────────────
    spec          = load_dag_spec()
    dag           = spec.get("dag", [])
    ordered_tasks = resolve_execution_order(dag)
    log.info("実行順序: %s", [t["task_id"] for t in ordered_tasks])

    failed_stages: list[str] = []

    for task in ordered_tasks:
        task_id     = task["task_id"]
        script_name = task["script"]

        if dry_run:
            log.info("  [DRY-RUN] skip: %s", script_name)
            continue

        success = run_stage(script_name, task_id)
        if not success:
            failed_stages.append(task_id)
            log.error("  %s が失敗。後続ステージを停止します", task_id)
            break

    # ─── 終了サマリー ─────────────────────────────────────────
    log.info("=" * 60)
    if not failed_stages:
        log.info("[OK] 週次バッチ全ステージ正常完了")
    else:
        log.error("[NG] 失敗ステージ: %s", failed_stages)
    log.info("終了時刻: %s", datetime.now(timezone.utc).isoformat())
    log.info("ログ: %s", log_file)
    log.info("=" * 60)

    return 0 if not failed_stages else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args, _ = parser.parse_known_args()

    if args.dry_run:
        import sys as _sys
        _mod = _sys.modules[__name__]
        _orig = run_stage
        def _dry(script_name, task_id, extra_args=None):
            log.info("  [DRY-RUN] skip: %s", script_name)
            return True
        _mod.run_stage = _dry  # type: ignore

    sys.exit(main(dry_run=args.dry_run))
