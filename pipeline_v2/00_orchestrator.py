"""
00_orchestrator.py  ─  うまなり地蔵AI パイプライン制御塔
=========================================================
DAG仕様書（config/dag_spec.json）に従い、各ステージを順番に実行します。
auto_stop条件に引っかかった場合は即座に停止してログに記録します。

v2: agents/ レイヤーと統合。MonitorAgent による実 auto_stop 評価。

実行方法:
  python 00_orchestrator.py
  python 00_orchestrator.py --dry-run   # 全ステージをスキップ実行

Windows タスクスケジューラ登録例:
  毎日 04:00 に python <project_root>/pipeline_v2/00_orchestrator.py を実行
"""

import subprocess
import json
import logging
import sys
import uuid
import pathlib
from datetime import datetime, timezone

# agents/ レイヤーを PATH に追加
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
# プロジェクトルートを必ず先頭に (worktree より優先)
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# ─── パス設定 ────────────────────────────────────────────────
BASE        = pathlib.Path(__file__).parent
CONFIG_DIR  = BASE / "config"
LOG_DIR     = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ─── ログ設定 ────────────────────────────────────────────────
today    = datetime.now().strftime("%Y%m%d")
log_file = LOG_DIR / f"orchestrator_{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# ─── メタ情報（トレース用） ───────────────────────────────────
TRACE_ID  = str(uuid.uuid4())
RUN_TAG   = f"run_{today}_{TRACE_ID[:8]}"
AGENT_ID  = "orchestrator"
AGENT_VER = "1.0.0"


def load_dag_spec() -> dict:
    spec_path = CONFIG_DIR / "dag_spec.json"
    with open(spec_path, encoding="utf-8") as f:
        return json.load(f)


def run_stage(script_name: str, task_id: str, dry_run: bool = False, extra_args: list[str] | None = None) -> bool:
    """
    1ステージを subprocess で実行し、成否を返す。
    """
    script_path = BASE / script_name
    log.info(f"▶ ステージ開始: {task_id}  ({script_name})")

    if not script_path.exists():
        log.warning(f"  スクリプトが見つかりません: {script_path}  → スキップ")
        return True  # スタブ未実装はスキップ扱い（後で False に変更可）

    if dry_run:
        log.info("  [DRY-RUN] skip: %s", script_name)
        return True

    result = subprocess.run(
        [sys.executable, str(script_path),
         *(extra_args or []),
         "--trace_id", TRACE_ID,
         "--run_tag",  RUN_TAG],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.stdout:
        log.info(result.stdout.strip())
    if result.stderr:
        log.warning(result.stderr.strip())

    if result.returncode == 0:
        log.info(f"  ✅ {task_id} 完了")
        return True
    else:
        log.error(f"  ❌ {task_id} 失敗 (returncode={result.returncode})")
        return False


def check_auto_stop(conditions: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    auto_stop条件をチェック。
    agents.MonitorAgent を使った実メトリクス評価 → フォールバックで DB直接参照。
    戻り値: (停止すべきか, 理由)
    """
    if dry_run:
        log.info("  [DRY-RUN] auto_stop チェックをスキップ")
        return False, ""

    # agents/ MonitorAgent による評価
    try:
        from agents.monitor_agent import MonitorAgent
        from agents.base_agent import AgentMeta

        meta   = AgentMeta(trace_id=TRACE_ID, run_tag=RUN_TAG)
        agent  = MonitorAgent(dry_run=False)
        result = agent.execute(meta, {})

        if result.ok and result.output.get("auto_stop"):
            alerts = result.output.get("alerts", [])
            reason = "; ".join(a["message"] for a in alerts if a.get("severity") == "critical")
            return True, reason

        return False, ""

    except Exception as exc:
        log.debug("MonitorAgent fallback: %s", exc)

    # フォールバック: alerts/ ディレクトリの最新レポートを確認
    alert_dir = BASE / "alerts"
    if alert_dir.exists():
        reports = sorted(alert_dir.glob("monitor_*.json"), reverse=True)
        if reports:
            try:
                data = json.loads(reports[0].read_text(encoding="utf-8"))
                if data.get("auto_stop"):
                    return True, "最新モニターレポートで auto_stop=True"
            except Exception:
                pass

    return False, ""


def resolve_execution_order(dag: list) -> list:
    """
    depends_on を考慮してトポロジカル順にタスクを並べる。
    """
    task_map  = {t["task_id"]: t for t in dag}
    completed = set()
    ordered   = []

    def visit(task_id):
        if task_id in completed:
            return
        task = task_map[task_id]
        for dep in task.get("depends_on", []):
            visit(dep)
        ordered.append(task)
        completed.add(task_id)

    for task in dag:
        visit(task["task_id"])

    return ordered


def main(dry_run: bool = False, start_at: str = ""):
    log.info("=" * 60)
    log.info(f"うまなり地蔵AI パイプライン起動")
    log.info(f"  TRACE_ID : {TRACE_ID}")
    log.info(f"  RUN_TAG  : {RUN_TAG}")
    log.info(f"  開始時刻 : {datetime.now(timezone.utc).isoformat()}")
    log.info("=" * 60)

    # DAG仕様読み込み
    spec            = load_dag_spec()
    auto_stop_conds = spec.get("auto_stop_conditions", {})
    dag             = spec.get("dag", [])

    # 実行順序を解決
    ordered_tasks = resolve_execution_order(dag)
    if start_at:
        task_ids = [task["task_id"] for task in ordered_tasks]
        if start_at not in task_ids:
            log.error("--start-at に未知のステージが指定されました: %s", start_at)
            sys.exit(1)
        ordered_tasks = ordered_tasks[task_ids.index(start_at):]
    log.info(f"実行順序: {[t['task_id'] for t in ordered_tasks]}")

    failed_stages = []

    for task in ordered_tasks:
        task_id     = task["task_id"]
        script_name = task["script"]
        extra_args  = task.get("args", [])

        # auto_stop チェック
        should_stop, reason = check_auto_stop(auto_stop_conds, dry_run=dry_run)
        if should_stop:
            log.error(f"🛑 AUTO_STOP 発動: {reason}")
            log.error(f"  {task_id} 以降のステージをすべて停止します")
            break

        # ステージ実行
        success = run_stage(script_name, task_id, dry_run=dry_run, extra_args=extra_args)

        if not success:
            failed_stages.append(task_id)
            log.error(f"  ⚠️  {task_id} が失敗しました。後続ステージを確認してください。")
            # 依存するステージはスキップ（簡易版: 全停止）
            # 本格運用時は depends_on グラフで影響範囲だけ停止
            break

    # 終了サマリー
    log.info("=" * 60)
    if not failed_stages:
        log.info("[OK] 全ステージ正常完了")
    else:
        log.error("[NG] 失敗ステージ: %s", failed_stages)
    log.info(f"終了時刻: {datetime.now(timezone.utc).isoformat()}")
    log.info(f"ログ: {log_file}")
    log.info("=" * 60)

    sys.exit(0 if not failed_stages else 1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="全ステージをスキップ（構造確認用）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag", default="")
    parser.add_argument("--start-at", default="", help="指定ステージから途中再開する")
    args, _ = parser.parse_known_args()

    if args.trace_id:
        TRACE_ID = args.trace_id
        RUN_TAG = args.run_tag or f"run_{today}_{TRACE_ID[:8]}"
    elif args.run_tag:
        RUN_TAG = args.run_tag

    sys.exit(main(dry_run=args.dry_run, start_at=args.start_at))
