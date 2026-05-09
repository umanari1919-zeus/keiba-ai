#!/usr/bin/env python3
"""
ソースコードの軽量 sanity check。

重いパイプラインは動かさず、次のような「人間が見落としやすい」破損を検知する。
- Python の構文エラー
- git diff の空白エラー
- Windows/WSL の個人環境に固定されたパス
- 実投稿・実通知スクリプトの live ガード欠落
- 自動再学習スクリプトの live ガード欠落
"""

from __future__ import annotations

import argparse
import compileall
import json
import pathlib
import shutil
import subprocess
from dataclasses import asdict, dataclass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@dataclass
class SanityResult:
    name: str
    status: str
    detail: str


def _result(name: str, ok: bool, detail: str, warn: bool = False) -> SanityResult:
    return SanityResult(name=name, status="PASS" if ok else ("WARN" if warn else "FAIL"), detail=detail)


def check_compileall() -> SanityResult:
    targets = [
        PROJECT_ROOT / "run_all.py",
        PROJECT_ROOT / "canary_run.py",
        PROJECT_ROOT / "train_model_v2.py",
        PROJECT_ROOT / "feature_engineering.py",
        PROJECT_ROOT / "agents",
        PROJECT_ROOT / "pipeline",
        PROJECT_ROOT / "pipeline_v2",
        PROJECT_ROOT / "tools",
    ]

    ok = True
    checked = 0
    for target in targets:
        if not target.exists():
            continue
        checked += 1
        if target.is_dir():
            ok = compileall.compile_dir(str(target), quiet=1) and ok
        else:
            ok = compileall.compile_file(str(target), quiet=1) and ok
    return _result("python:compileall", ok, f"targets={checked}")


def check_git_diff() -> SanityResult:
    if shutil.which("git") is None:
        return _result("git:diff-check", False, "git not found", warn=True)

    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=str(PROJECT_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode == 0:
        return _result("git:diff-check", True, "clean")

    detail = " | ".join(line.strip() for line in result.stdout.splitlines()[:5] if line.strip())
    return _result("git:diff-check", False, detail or f"exit={result.returncode}")


def _iter_source_files() -> list[pathlib.Path]:
    suffixes = {".bat", ".cmd", ".json", ".ps1", ".py", ".toml", ".yaml", ".yml"}
    excluded_dirs = {
        ".git",
        ".claude",
        ".runtime",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        "archive",
        "catboost_info",
        "data",
        "logs",
        "pipeline_v2/alerts",
        "pipeline_v2/logs",
        "tools/logs",
    }
    files: list[pathlib.Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if any(rel == item or rel.startswith(f"{item}/") for item in excluded_dirs):
            continue
        files.append(path)
    return files


def check_hardcoded_local_paths() -> SanityResult:
    needles = (
        "D:" + "\\keiba_ai",
        "D:" + "/keiba_ai",
        "/mnt/d" + "/keiba_ai",
        "C:" + "\\Users\\uchih",
    )
    hits: list[str] = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for needle in needles:
            if needle in text:
                hits.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{needle}")
                break
    return _result("source:hardcoded-local-paths", not hits, f"hits={hits[:10]}")


def check_outbound_live_guards() -> SanityResult:
    requirements = {
        "pipeline/post_x_05.py": ("KEIBA_SOCIAL_LIVE", "--live", "create_tweet"),
        "pipeline/social_bot_27.py": ("KEIBA_SOCIAL_LIVE", "--live", "create_tweet"),
        "pipeline/notify_08.py": ("KEIBA_NOTIFY_LIVE", "--live", "SMTP_SSL"),
        "pipeline/auto_learn_13.py": ("KEIBA_AUTO_RETRAIN_LIVE", "--live", "auto_retrain"),
        "pipeline_v2/06_publish.py": ("KEIBA_PUBLISH_LIVE", "--live", "publish_live"),
        "pipeline_v2/07_trade.py": ("--live", "paper_trading"),
        "pipeline_v2/19_auto_learn.py": ("--live", "live"),
    }
    missing: list[str] = []
    for rel, tokens in requirements.items():
        path = PROJECT_ROOT / rel
        if not path.exists():
            missing.append(f"{rel}:missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        absent = [token for token in tokens if token not in text]
        if absent:
            missing.append(f"{rel}:{','.join(absent)}")
    return _result("source:outbound-live-guards", not missing, f"missing={missing}")


def run_checks() -> list[SanityResult]:
    return [
        check_compileall(),
        check_git_diff(),
        check_hardcoded_local_paths(),
        check_outbound_live_guards(),
    ]


def print_report(results: list[SanityResult]) -> None:
    print("=" * 72)
    print("Umanari source sanity check")
    print("=" * 72)
    for item in results:
        print(f"[{item.status}] {item.name:<32} {item.detail}")
    pass_count = sum(1 for item in results if item.status == "PASS")
    warn_count = sum(1 for item in results if item.status == "WARN")
    fail_count = sum(1 for item in results if item.status == "FAIL")
    print("-" * 72)
    print(f"PASS {pass_count}/{len(results)}  WARN {warn_count}  FAIL {fail_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="うまなり地蔵AI ソース sanity check")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    results = run_checks()
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        print_report(results)
    return 0 if all(item.status != "FAIL" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
