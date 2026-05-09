"""
preflight_check.py — pipeline_v2 事前診断
=========================================
DAG 定義を読み込み、各ステージの `--dry-run` を順番に実行して
依存不足・入力不足・起動可否をまとめて確認する。

実行方法:
  python pipeline_v2/preflight_check.py
  python pipeline_v2/preflight_check.py --json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

BASE = pathlib.Path(__file__).resolve().parent
CONFIG_DIR = BASE / "config"

DEFAULT_SPEC = "dag_spec.json"
WEEKLY_SPEC = "dag_spec_weekly.json"


@dataclass
class StageResult:
    task_id: str
    script: str
    ok: bool
    warn: bool
    returncode: int
    summary: str
    stdout_tail: str
    stderr_tail: str


def load_dag_spec(spec_name: str) -> dict:
    with open(CONFIG_DIR / spec_name, encoding="utf-8") as f:
        return json.load(f)


def iter_tasks(spec: dict) -> list[tuple[str, str, list[str]]]:
    if "dag" in spec:
        return [(task["task_id"], task["script"], task.get("args", [])) for task in spec.get("dag", [])]
    if "steps" in spec:
        return [(task["id"], task["script"], task.get("args", [])) for task in spec.get("steps", [])]
    return []


def summarize_output(stdout: str, stderr: str, returncode: int) -> str:
    text = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
    if not text:
        return "OK" if returncode == 0 else f"returncode={returncode}"

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "dry-run: 要確認" in line:
            return "依存/入力の要確認あり"
        if "未インストール" in line:
            return line
        if "見つかりません" in line:
            return line
        if "FAILURE:" in line:
            return line
        if "error:" in line.lower():
            return line
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:200] if lines else f"returncode={returncode}"


def detect_warning(stdout: str, stderr: str, summary: str) -> bool:
    text = "\n".join([stdout, stderr, summary])
    warning_markers = [
        "dry-run: 要確認",
        "未インストール",
        "見つかりません",
        "読み込みエラー",
        "warning",
        "DeprecationWarning",
        "要確認",
    ]
    return any(marker in text for marker in warning_markers)


def run_stage(task_id: str, script_name: str, extra_args: list[str] | None = None) -> StageResult:
    script_path = pathlib.Path(script_name)
    if not script_path.is_absolute():
        base_local = BASE / script_name
        script_path = base_local if base_local.exists() else BASE.parent / script_name
    if not script_path.exists():
        return StageResult(
            task_id=task_id,
            script=script_name,
            ok=False,
            warn=False,
            returncode=127,
            summary=f"スクリプトなし: {script_path}",
            stdout_tail="",
            stderr_tail="",
        )

    result = subprocess.run(
        [sys.executable, str(script_path), *(extra_args or []), "--dry-run"],
        cwd=str(BASE.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stdout_tail = "\n".join(result.stdout.strip().splitlines()[-8:])
    stderr_tail = "\n".join(result.stderr.strip().splitlines()[-8:])
    summary = summarize_output(result.stdout, result.stderr, result.returncode)
    warn = result.returncode == 0 and detect_warning(result.stdout, result.stderr, summary)
    return StageResult(
        task_id=task_id,
        script=script_name,
        ok=result.returncode == 0,
        warn=warn,
        returncode=result.returncode,
        summary=summary,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
    )


def print_report(results: list[StageResult]) -> None:
    print("=" * 72)
    print("pipeline_v2 preflight check")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    ok_count = sum(1 for r in results if r.ok and not r.warn)
    warn_count = sum(1 for r in results if r.warn)
    for result in results:
        status = "FAIL"
        if result.ok and result.warn:
            status = "WARN"
        elif result.ok:
            status = "PASS"
        print(f"[{status}] {result.task_id:<18} {result.summary}")

    print("-" * 72)
    print(f"PASS {ok_count}/{len(results)}  WARN {warn_count}  FAIL {len(results) - ok_count - warn_count}")

    followups = [r for r in results if (not r.ok) or r.warn]
    if followups:
        print("-" * 72)
        print("要確認ステージ詳細")
        for result in followups:
            print(f"* {result.task_id} ({result.script})")
            if result.stdout_tail:
                print(result.stdout_tail)
            if result.stderr_tail:
                print(result.stderr_tail)
            print("-" * 40)


def main() -> int:
    parser = argparse.ArgumentParser(description="pipeline_v2 の事前診断")
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.add_argument("--weekly", action="store_true", help="週次 DAG を診断する")
    parser.add_argument(
        "--spec",
        help="使用する DAG 定義ファイル名を指定する（config/ 配下）",
    )
    args = parser.parse_args()

    spec_name = args.spec or (WEEKLY_SPEC if args.weekly else DEFAULT_SPEC)
    spec = load_dag_spec(spec_name)
    results = [run_stage(task_id, script, extra_args) for task_id, script, extra_args in iter_tasks(spec)]

    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print_report(results)

    return 0 if all(r.ok and not r.warn for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
