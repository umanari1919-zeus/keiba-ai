#!/usr/bin/env python3
"""
うまなり地蔵AI doctor コマンド。

個別に増えた診断をまとめて実行し、運用前に「どこまで健康か」を一画面で見る。
外部依存は既定では WARN 扱いのため、DB 未起動でもコード健全性チェックは続行する。
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from dataclasses import dataclass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@dataclass
class DoctorStep:
    name: str
    cmd: list[str]
    hard_fail: bool = True


def _run_step(step: DoctorStep) -> int:
    print("\n" + "=" * 72, flush=True)
    print(f"doctor: {step.name}", flush=True)
    print("=" * 72, flush=True)
    result = subprocess.run(step.cmd, cwd=str(PROJECT_ROOT))
    status = "PASS" if result.returncode == 0 else ("FAIL" if step.hard_fail else "WARN")
    print(f"doctor: {step.name} -> {status} (exit={result.returncode})", flush=True)
    return result.returncode


def build_steps(skip_canary: bool, strict_external: bool) -> list[DoctorStep]:
    py = sys.executable
    external_cmd = [py, "-X", "utf8", str(PROJECT_ROOT / "tools" / "diagnose_external.py")]
    if strict_external:
        external_cmd.append("--strict")
    else:
        external_cmd.append("--warn-code")

    steps = [
        DoctorStep("external dependencies", external_cmd, hard_fail=strict_external),
        DoctorStep("source sanity", [py, "-X", "utf8", str(PROJECT_ROOT / "tools" / "source_sanity.py")]),
        DoctorStep("runtime check", [py, "-X", "utf8", str(PROJECT_ROOT / "pipeline_v2" / "runtime_check.py"), "--profile", "all"]),
        DoctorStep("integrity check", [py, "-X", "utf8", str(PROJECT_ROOT / "tools" / "verify_integrity.py")]),
        DoctorStep("daily preflight", [py, "-X", "utf8", str(PROJECT_ROOT / "pipeline_v2" / "preflight_check.py")]),
        DoctorStep("weekly preflight", [py, "-X", "utf8", str(PROJECT_ROOT / "pipeline_v2" / "preflight_check.py"), "--weekly"]),
    ]
    if not skip_canary:
        steps.append(DoctorStep("canary run", [py, "-X", "utf8", str(PROJECT_ROOT / "canary_run.py")]))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="うまなり地蔵AI 総合診断")
    parser.add_argument("--skip-canary", action="store_true", help="canary_run.py を省略")
    parser.add_argument("--strict-external", action="store_true", help="外部依存 WARN も失敗扱いにする")
    args = parser.parse_args()

    failures: list[str] = []
    soft_warnings: list[str] = []
    for step in build_steps(skip_canary=args.skip_canary, strict_external=args.strict_external):
        rc = _run_step(step)
        if rc == 0:
            continue
        if step.hard_fail:
            failures.append(step.name)
        else:
            soft_warnings.append(step.name)

    print("\n" + "=" * 72, flush=True)
    print("doctor summary", flush=True)
    print("=" * 72, flush=True)
    if failures:
        print(f"FAIL: {', '.join(failures)}", flush=True)
    else:
        print("FAIL: none", flush=True)
    if soft_warnings:
        print(f"WARN: {', '.join(soft_warnings)}", flush=True)
    else:
        print("WARN: none", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
