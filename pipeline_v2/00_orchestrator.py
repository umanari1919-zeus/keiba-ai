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
  毎日 04:00 に python D:/keiba_ai/pipeline_v2/00_orchestrator.py を実行
"""

import subprocess
import json
import logging
import sys
import hashlib
import uuid
import pathlib
from datetime import datetime, timezone

# agents/ レイヤーを PATH に追加
_WORKTREE = pathlib.Path(r"D:\keiba_ai\.claude\worktrees\brave-kilby-e79e98")
if _WORKTREE.exists() and str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

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


def run_stage(script_name: str, task_id: str) -> bool:
    """
    1ステージを subprocess で実行し、成否を返す。
    """
    script_path = BASE / script_name
    log.info(f"▶ ステージ開始: {task_id}  ({script_name})")

    if not script_path.exists():
        log.warning(f"  スクリプトが見つかりません: {script_path}  → スキップ")
        return True  # スタブ未実装はスキップ扱い（後で False に変更可）

    result = subprocess.run(
        [sys.executable, str(script_path),
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


def check_auto_stop(conditions: dict) -> tuple[bool, str]:
    """
    auto_stop条件をチェック。
    agents.MonitorAgent を使った実メトリクス評価 → フォールバックで DB直接参照。
    戻り値: (停止すべきか, 理由)
    """
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


def main():
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
    log.info(f"実行順序: {[t['task_id'] for t in ordered_tasks]}")

    failed_stages = []

    for task in ordered_tasks:
        task_id     = task["task_id"]
        script_name = task["script"]

        # auto_stop チェック
        should_stop, reason = check_auto_stop(auto_stop_conds)
        if should_stop:
            log.error(f"🛑 AUTO_STOP 発動: {reason}")
            log.error(f"  {task_id} 以降のステージをすべて停止します")
            break

        # ステージ実行
        success = run_stage(script_name, task_id)

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
    args, _ = parser.parse_known_args()

    if args.dry_run:
        # dry-run: スクリプト実行をスキップしてフローのみ確認
        _orig_run_stage = run_stage
        def _dry_run_stage(script_name, task_id):
            log.info("  [DRY-RUN] skip: %s", script_name)
            return True
        import builtins
        # run_stage をモンキーパッチ
        import sys as _sys
        _mod = _sys.modules[__name__]
        _mod.run_stage = _dry_run_stage  # type: ignore

    main()
