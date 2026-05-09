#!/usr/bin/env python3
"""
PostgreSQL / mykeibadb 外部依存の診断ツール。

runtime_check.py はパイプライン全体の健全性を見る。
このツールは外部依存だけを詳しく見て、運用時に設定すべき環境変数を出す。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import shutil
import socket
import sys
from dataclasses import asdict, dataclass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import DB_CONFIG, DB_URL, MYKEIBADB_EXE
from tools.db_readiness import fetch_core_table_health
from tools.local_postgres import resolve_paths


@dataclass
class ExternalStatus:
    name: str
    status: str
    detail: str
    suggestion: str = ""


def _check_tcp(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "reachable"
    except OSError as exc:
        return False, str(exc)


def _find_mykeibadb_candidates() -> list[str]:
    patterns = [
        "/mnt/c/Users/*/Downloads/mykeibadb*/mykeibadb.exe",
        "/mnt/c/Users/*/Desktop/mykeibadb*/mykeibadb.exe",
        "/mnt/d/*mykeibadb*/mykeibadb.exe",
        str(PROJECT_ROOT / "**" / "mykeibadb.exe"),
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern, recursive=True))
    return sorted(set(candidates))


def run_checks() -> list[ExternalStatus]:
    results: list[ExternalStatus] = []

    local_pg = resolve_paths().prefix
    local_psql = local_pg / "bin" / "psql"
    psql = shutil.which("psql") or (str(local_psql) if local_psql.exists() else "")
    results.append(ExternalStatus(
        name="psql",
        status="PASS" if psql else "WARN",
        detail=psql or "not found",
        suggestion="" if psql else "Install PostgreSQL client tools or run tools/local_postgres.py start.",
    ))

    host = str(DB_CONFIG.get("host", "localhost"))
    try:
        port = int(DB_CONFIG.get("port", 5433))
    except (TypeError, ValueError):
        port = 5433
    dbname = str(DB_CONFIG.get("dbname", "mykeibadb"))
    ok, detail = _check_tcp(host, port)
    results.append(ExternalStatus(
        name="postgres-port",
        status="PASS" if ok else "WARN",
        detail=f"{host}:{port}/{dbname} ({detail})",
        suggestion="" if ok else f"Start PostgreSQL or set KEIBA_DB_URL. Current KEIBA_DB_URL={DB_URL}",
    ))
    if ok:
        try:
            table_status, table_detail = fetch_core_table_health(DB_CONFIG)
            suggestion = "" if table_status == "PASS" else "Restore mykeibadb.dump/mykeibadb_fast or run the JRA-VAN sync."
        except Exception as exc:
            table_status = "WARN"
            table_detail = f"core table check failed: {exc}"
            suggestion = "Verify DB_CONFIG/KEIBA_DB_URL and restore the local database."
        results.append(ExternalStatus(
            name="core-tables",
            status=table_status,
            detail=table_detail,
            suggestion=suggestion,
        ))

    configured = pathlib.Path(MYKEIBADB_EXE)
    if configured.exists():
        results.append(ExternalStatus(
            name="MYKEIBADB_EXE",
            status="PASS",
            detail=str(configured),
        ))
    else:
        candidates = _find_mykeibadb_candidates()
        suggestion = "Set MYKEIBADB_EXE to the installed mykeibadb.exe path."
        if candidates:
            suggestion = f"export MYKEIBADB_EXE='{candidates[0]}'"
        results.append(ExternalStatus(
            name="MYKEIBADB_EXE",
            status="WARN",
            detail=f"configured path not found: {configured}",
            suggestion=suggestion,
        ))
        for candidate in candidates[:5]:
            results.append(ExternalStatus(
                name="mykeibadb-candidate",
                status="INFO",
                detail=candidate,
                suggestion=f"export MYKEIBADB_EXE='{candidate}'",
            ))

    return results


def print_report(results: list[ExternalStatus]) -> None:
    print("=" * 72)
    print("External dependency diagnosis")
    print("=" * 72)
    for item in results:
        print(f"[{item.status}] {item.name:<22} {item.detail}")
        if item.suggestion:
            print(f"       suggestion: {item.suggestion}")
    warn_count = sum(1 for item in results if item.status == "WARN")
    pass_count = sum(1 for item in results if item.status == "PASS")
    print("-" * 72)
    print(f"PASS {pass_count}  WARN {warn_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL / mykeibadb 外部依存診断")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    parser.add_argument("--strict", action="store_true", help="WARN があれば終了コード 1")
    parser.add_argument("--warn-code", action="store_true", help="WARN があれば終了コード 2")
    args = parser.parse_args()

    results = run_checks()
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        print_report(results)

    has_warn = any(item.status == "WARN" for item in results)
    if args.strict and has_warn:
        return 1
    if args.warn_code and has_warn:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
