"""
runtime_check.py — pipeline_v2 実行環境診断
===========================================
preflight_check.py が各ステージの dry-run 起動を確認するのに対し、
このスクリプトは本実行に必要な Python 依存・主要ファイル・外部接続を確認する。

実行方法:
  python pipeline_v2/runtime_check.py
  python pipeline_v2/runtime_check.py --profile weekly
  python pipeline_v2/runtime_check.py --json
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, CSV_FEATURES, DATA_DIR, DB_CONFIG, MYKEIBADB_EXE
from pipeline.native_runtime import ensure_native_runtime
from tools.db_readiness import fetch_core_table_health
from tools.local_postgres import resolve_paths

ensure_native_runtime()


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


MODULE_GROUPS = {
    "daily": {
        "required": ["pandas", "numpy", "psycopg2", "sqlalchemy", "httpx", "bs4"],
        "optional": ["lxml", "playwright", "requests", "dotenv"],
    },
    "weekly": {
        "required": ["pandas", "numpy", "lightgbm", "sklearn"],
        "optional": ["xgboost", "catboost", "optuna", "shap", "scipy"],
    },
}

MODULE_ALIASES = {
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "dotenv": "python-dotenv",
}


def _module_label(module_name: str) -> str:
    return MODULE_ALIASES.get(module_name, module_name)


def _hint(detail: str, message: str) -> str:
    return f"{detail} | hint: {message}"


def check_modules(profile: str) -> list[CheckResult]:
    profiles = ["daily", "weekly"] if profile == "all" else [profile]
    required: list[str] = []
    optional: list[str] = []
    for item in profiles:
        required.extend(MODULE_GROUPS[item]["required"])
        optional.extend(MODULE_GROUPS[item]["optional"])

    results: list[CheckResult] = []
    for module_name in sorted(set(required)):
        status = "PASS"
        detail = "installed"
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            status = "FAIL"
            detail = f"import failed: {exc}"
        results.append(CheckResult(
            name=f"module:{_module_label(module_name)}",
            status=status,
            detail=detail,
        ))
    for module_name in sorted(set(optional) - set(required)):
        status = "PASS"
        detail = "installed"
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            status = "WARN"
            detail = f"import failed: {exc}"
        results.append(CheckResult(
            name=f"optional:{_module_label(module_name)}",
            status=status,
            detail=detail,
        ))
    return results


def check_files() -> list[CheckResult]:
    base = pathlib.Path(BASE_DIR)
    data = pathlib.Path(DATA_DIR)
    year = datetime.now().year
    ev_candidates = [
        base / f"ev_analysis_{year}.csv",
        data / f"ev_analysis_{year}.csv",
        base / f"ev_analysis_{year - 1}.csv",
        data / f"ev_analysis_{year - 1}.csv",
    ]
    checks = [
        ("path:BASE_DIR", base.exists(), str(base)),
        ("path:DATA_DIR", data.exists(), str(data)),
        ("file:CSV_FEATURES", pathlib.Path(CSV_FEATURES).exists(), str(CSV_FEATURES)),
        ("file:ev_analysis", any(p.exists() for p in ev_candidates), " / ".join(str(p) for p in ev_candidates)),
    ]
    return [
        CheckResult(name=name, status="PASS" if ok else "FAIL", detail=detail)
        for name, ok, detail in checks
    ]


def _playwright_browser_root() -> pathlib.Path:
    return pathlib.Path.home() / ".cache" / "ms-playwright"


def check_external() -> list[CheckResult]:
    exe = pathlib.Path(MYKEIBADB_EXE)
    status = "PASS" if exe.exists() else "WARN"
    results = [CheckResult(
        name="external:MYKEIBADB_EXE",
        status=status,
        detail=str(exe),
    )]
    if importlib.util.find_spec("playwright"):
        browser_root = _playwright_browser_root()
        has_browsers = browser_root.exists() and any(browser_root.iterdir())
        detail = str(browser_root)
        if not has_browsers:
            detail = _hint(detail, "python3 -m playwright install chromium")
        else:
            try:
                sync_api = importlib.import_module("playwright.sync_api")
                with sync_api.sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, timeout=10000)
                    browser.close()
            except Exception as exc:
                has_browsers = False
                error_lines = str(exc).splitlines()
                reason = error_lines[0] if error_lines else exc.__class__.__name__
                shared_lib_error = next(
                    (line.strip() for line in error_lines if "error while loading shared libraries" in line),
                    "",
                )
                if shared_lib_error and shared_lib_error not in reason:
                    reason = f"{reason}; {shared_lib_error}"
                detail = _hint(
                    f"{browser_root} (launch failed: {reason})",
                    "python3 -m playwright install-deps chromium",
                )
        results.append(CheckResult(
            name="external:playwright-browsers",
            status="PASS" if has_browsers else "WARN",
            detail=detail,
        ))
    return results


def check_database() -> list[CheckResult]:
    results: list[CheckResult] = []

    local_pg = resolve_paths().prefix
    local_psql = local_pg / "bin" / "psql"
    psql = shutil.which("psql") or (str(local_psql) if local_psql.exists() else "")
    results.append(CheckResult(
        name="external:psql",
        status="PASS" if psql else "WARN",
        detail=psql or "not found; psycopg2 can still connect if the DB server is reachable",
    ))

    host = str(DB_CONFIG.get("host", "127.0.0.1"))
    try:
        port = int(DB_CONFIG.get("port", 5433))
    except (TypeError, ValueError):
        port = 5433
    dbname = str(DB_CONFIG.get("dbname", "mykeibadb"))
    user = str(DB_CONFIG.get("user", "postgres"))
    target = f"{host}:{port}/{dbname} user={user}"

    try:
        with socket.create_connection((host, port), timeout=1.5):
            detail = target
        status = "PASS"
    except OSError as exc:
        status = "WARN"
        detail = _hint(
            f"{target} ({exc})",
            "python3 tools/local_postgres.py start でDBを起動し、python3 run_all.py --runtime-check で再確認",
        )

    results.append(CheckResult(
        name="external:postgres-port",
        status=status,
        detail=detail,
    ))

    if status == "PASS":
        try:
            db_status, db_detail = fetch_core_table_health(DB_CONFIG)
        except Exception as exc:
            db_status = "WARN"
            db_detail = f"core table check failed: {exc}"
        results.append(CheckResult(
            name="database:core-tables",
            status=db_status,
            detail=db_detail,
        ))
    return results


def run_checks(profile: str) -> list[CheckResult]:
    return [
        *check_modules(profile),
        *check_files(),
        *check_database(),
        *check_external(),
    ]


def print_report(results: list[CheckResult], profile: str) -> None:
    print("=" * 72)
    print(f"pipeline_v2 runtime check ({profile})")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)
    for result in results:
        print(f"[{result.status}] {result.name:<28} {result.detail}")
    pass_count = sum(1 for r in results if r.status == "PASS")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    print("-" * 72)
    print(f"PASS {pass_count}/{len(results)}  WARN {warn_count}  FAIL {fail_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="pipeline_v2 の実行環境診断")
    parser.add_argument("--profile", choices=["daily", "weekly", "all"], default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = run_checks(args.profile)
    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print_report(results, args.profile)
    return 0 if all(r.status != "FAIL" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
