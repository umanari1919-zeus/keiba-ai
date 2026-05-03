"""
setup_pipeline_v2.py
実行するだけで D:\keiba_ai\pipeline_v2\ の全フォルダ・ファイルを作成します。
既存の pipeline\ フォルダには一切触れません。

実行方法:
  python setup_pipeline_v2.py
"""

import os
import json
import pathlib

BASE = pathlib.Path(r"D:\keiba_ai\pipeline_v2")

# ============================================================
# 1. フォルダ構成
# ============================================================
DIRS = [
    BASE,
    BASE / "config",
    BASE / "logs",
]

# ============================================================
# 2. config に保存する仕様書JSON
# ============================================================
DAG_SPEC = {
    "artifact_type": "orchestrator_dag",
    "prompt_id": "core_umanari_v1_orchestrator",
    "version": "1.0.0",
    "auto_stop_conditions": {
        "mismatch_rate_gt": 0.02,
        "quarantine_24h_increase_gt": 50,
        "spearman_drop_pct": 0.20
    },
    "dag": [
        {"task_id": "ingest",          "script": "01_ingest.py"},
        {"task_id": "normalize",       "script": "02_normalize.py",       "depends_on": ["ingest"]},
        {"task_id": "feature_gen",     "script": "03_feature_gen.py",     "depends_on": ["normalize"]},
        {"task_id": "batch_inference", "script": "04_batch_inference.py", "depends_on": ["feature_gen"]},
        {"task_id": "explain",         "script": "05_explain.py",         "depends_on": ["batch_inference"]},
        {"task_id": "upsetscore",      "script": "08_upsetscore.py",      "depends_on": ["batch_inference"]},
        {"task_id": "publish",         "script": "06_publish.py",         "depends_on": ["explain"]},
        {"task_id": "trade",           "script": "07_trade.py",           "depends_on": ["explain"]},
        {"task_id": "monitor",         "script": "09_monitor.py",         "depends_on": ["publish", "trade"]}
    ]
}

PROMPT_EXPLAIN = {
    "prompt_id": "p_explain_v1",
    "prompt_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "model_name": "local-llm",
    "model_version": "2.5",
    "instructions": (
        "Produce a factual, concise JSON explanation. "
        "Include model_version, featureset, prompt_hash, data_snapshot_id in evidence_links. "
        "If confidence < 0.8 or uncertainty > 0.4, set 'requires_human_review': true. "
        "Ensure output JSON is valid and contains all required fields."
    ),
    "required_fields": [
        "entry_id", "race_id", "prediction", "top_features",
        "explanation_short", "explanation_long", "bet_recommendation",
        "uncertainty", "confidence", "evidence_links",
        "prompt_id", "prompt_hash", "model_name", "model_version",
        "run_tag", "created_at"
    ]
}

UPSETSCORE_SPEC = {
    "job_id": "upsetscore_daily_v1",
    "schedule": "cron: 0 5 * * *",
    "weights": {
        "avg_gap": 0.45,
        "odds_std": 0.15,
        "one_minus_top3_prob": 0.20,
        "pace_mismatch": 0.10,
        "shock_score": 0.10
    },
    "output_table": "race_metrics.upset_scores"
}

CONFIGS = {
    "dag_spec.json":          DAG_SPEC,
    "prompt_explain_v1.json": PROMPT_EXPLAIN,
    "upsetscore_v1.json":     UPSETSCORE_SPEC,
}

# ============================================================
# 3. スクリプトのスタブ（中身は後で実装）
# ============================================================
STUB_TEMPLATE = '''\
"""
{filename}
TODO: 実装予定
DAGステージ: {task_id}
"""

def main():
    print("[{task_id}] 未実装のスタブです")

if __name__ == "__main__":
    main()
'''

STUBS = [
    ("01_ingest.py",          "ingest"),
    ("02_normalize.py",       "normalize"),
    ("03_feature_gen.py",     "feature_gen"),
    ("04_batch_inference.py", "batch_inference"),
    ("05_explain.py",         "explain"),
    ("06_publish.py",         "publish"),
    ("07_trade.py",           "trade"),
    ("08_upsetscore.py",      "upsetscore"),
    ("09_monitor.py",         "monitor"),
]

# ============================================================
# 4. オーケストレーター本体
# ============================================================
ORCHESTRATOR = r'''"""
00_orchestrator.py  ─  うまなり地蔵AI パイプライン制御塔
=========================================================
DAG仕様書（config/dag_spec.json）に従い、各ステージを順番に実行します。
auto_stop条件に引っかかった場合は即座に停止してログに記録します。

実行方法:
  python 00_orchestrator.py

Windows タスクスケジューラ登録例:
  毎日 04:00 に python D:\keiba_ai\pipeline_v2\00_orchestrator.py を実行
"""

import subprocess
import json
import logging
import sys
import hashlib
import uuid
import pathlib
from datetime import datetime, timezone

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
    実際の数値はDBやログから取得する（現在はプレースホルダー）。
    戻り値: (停止すべきか, 理由)
    """
    # TODO: DBから実際のメトリクスを取得して判定する
    # 例: mismatch_rate = db_query("SELECT mismatch_rate FROM monitoring...")
    # 現在は常に通過（False）
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
        log.info("✅ 全ステージ正常完了")
    else:
        log.error(f"❌ 失敗ステージ: {failed_stages}")
    log.info(f"終了時刻: {datetime.now(timezone.utc).isoformat()}")
    log.info(f"ログ: {log_file}")
    log.info("=" * 60)

    sys.exit(0 if not failed_stages else 1)


if __name__ == "__main__":
    main()
'''

# ============================================================
# 5. 実行
# ============================================================
def main():
    print("=" * 60)
    print("うまなり地蔵AI  pipeline_v2  セットアップ開始")
    print("=" * 60)

    # フォルダ作成
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [DIR]  {d}")

    # config JSON保存
    for filename, data in CONFIGS.items():
        path = BASE / "config" / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [JSON] {path}")

    # スタブスクリプト作成（既存があれば上書きしない）
    for filename, task_id in STUBS:
        path = BASE / filename
        if path.exists():
            print(f"  [SKIP] {path}  ← 既存あり")
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(STUB_TEMPLATE.format(filename=filename, task_id=task_id))
            print(f"  [STUB] {path}")

    # オーケストレーター作成
    orch_path = BASE / "00_orchestrator.py"
    with open(orch_path, "w", encoding="utf-8") as f:
        f.write(ORCHESTRATOR)
    print(f"  [MAIN] {orch_path}")

    print()
    print("=" * 60)
    print("✅ セットアップ完了！")
    print()
    print("次のステップ:")
    print("  1. 動作確認:")
    print(r"     python D:\keiba_ai\pipeline_v2\00_orchestrator.py")
    print()
    print("  2. Windowsタスクスケジューラに登録（毎日04:00）:")
    print(r"     python D:\keiba_ai\pipeline_v2\00_orchestrator.py")
    print()
    print("  3. 次に実装するステージを決める（推奨: 05_explain.py）")
    print("=" * 60)


if __name__ == "__main__":
    main()
