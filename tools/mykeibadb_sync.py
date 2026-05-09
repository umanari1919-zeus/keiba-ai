#!/usr/bin/env python3
"""mykeibadb daily sync helper.

This keeps the Windows mykeibadb client pointed at the WSL PostgreSQL server.
WSL IPs can change after reboot, so the ini file is refreshed before running.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2

from pipeline.config import DB_CONFIG, MYKEIBADB_EXE


TERMINAL_LOG_PATTERNS = (
    "0B30:更新終了",
    "0B30:譖ｴ譁ｰ邨ゆｺ",
    "JVClose",
)


def get_wsl_ip() -> str:
    result = subprocess.run(
        ["hostname", "-I"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for item in result.stdout.split():
        if re.match(r"^172\.\d+\.\d+\.\d+$", item):
            return item
    for item in result.stdout.split():
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", item) and not item.startswith("127."):
            return item
    raise RuntimeError(f"WSL IPv4 address not found: {result.stdout!r}")


def mykeibadb_paths(exe: str | pathlib.Path = MYKEIBADB_EXE) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    exe_path = pathlib.Path(exe)
    ini_path = exe_path.with_name("mykeibadb.ini")
    log_path = exe_path.parent / "log" / "log.txt"
    return exe_path, ini_path, log_path


def update_ini_text(text: str, *, server: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    section = ""
    db_server_written = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section == "DB" and not db_server_written:
                output.append(f"SERVER={server}")
                db_server_written = True
            section = stripped[1:-1]
            output.append(line)
            continue

        if section == "DB" and stripped.startswith("SERVER="):
            output.append(f"SERVER={server}")
            db_server_written = True
            continue

        if section == "DB" and not db_server_written:
            output.append(f"SERVER={server}")
            db_server_written = True

        if section == "JIKEIRETSU" and stripped in {"O1=1", "O2=1"}:
            output.append(stripped.replace("=1", "=0"))
            continue

        output.append(line)

    if section == "DB" and not db_server_written:
        output.append(f"SERVER={server}")
    return "\n".join(output).rstrip() + "\n"


def update_ini_file(ini_path: pathlib.Path, *, server: str, dry_run: bool = False) -> pathlib.Path | None:
    text = ini_path.read_text(encoding="cp932", errors="replace")
    updated = update_ini_text(text, server=server)
    if updated == text:
        return None
    backup = ini_path.with_name(ini_path.name + ".bak-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    if not dry_run:
        backup.write_text(text, encoding="cp932", errors="replace")
        ini_path.write_text(updated, encoding="cp932", errors="replace")
    return backup


def is_terminal_log_text(text: str) -> bool:
    return any(pattern in text for pattern in TERMINAL_LOG_PATTERNS)


def powershell_single_quote(value: pathlib.Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def to_windows_path(value: pathlib.Path) -> str:
    text = value.as_posix()
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", text)
    if not match:
        return str(value)
    drive = match.group(1).upper()
    tail = match.group(2).replace("/", "\\")
    return f"{drive}:\\{tail}"


def parse_started_pid(output: str) -> int:
    matches = re.findall(r"MYKEIBADB_PID=(\d+)", output)
    if not matches:
        raise RuntimeError(f"mykeibadb process id not found in PowerShell output: {output!r}")
    return int(matches[-1])


def start_mykeibadb(exe_path: pathlib.Path) -> int:
    windows_exe = pathlib.Path(to_windows_path(exe_path))
    windows_cwd = pathlib.Path(to_windows_path(exe_path.parent))
    command = (
        "$p = Start-Process "
        f"-FilePath {powershell_single_quote(windows_exe)} "
        f"-WorkingDirectory {powershell_single_quote(windows_cwd)} "
        "-PassThru; Write-Output \"MYKEIBADB_PID=$($p.Id)\""
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return parse_started_pid(result.stdout)


def stop_mykeibadb() -> None:
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-Process mykeibadb -ErrorAction SilentlyContinue | Stop-Process",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def read_new_log_tail(log_path: pathlib.Path, start_size: int, *, max_chars: int = 4000) -> str:
    if not log_path.exists():
        return ""
    raw = log_path.read_bytes()
    new_bytes = raw[start_size:]
    return new_bytes.decode("cp932", errors="replace")[-max_chars:]


def wait_for_sync(log_path: pathlib.Path, *, timeout_seconds: int = 900, idle_seconds: int = 45) -> str:
    started = time.monotonic()
    start_size = log_path.stat().st_size if log_path.exists() else 0
    last_size = start_size
    last_change = time.monotonic()

    while time.monotonic() - started < timeout_seconds:
        if log_path.exists():
            size = log_path.stat().st_size
            if size != last_size:
                last_size = size
                last_change = time.monotonic()
            tail = read_new_log_tail(log_path, start_size)
            if is_terminal_log_text(tail):
                return tail
        if time.monotonic() - last_change >= idle_seconds:
            return read_new_log_tail(log_path, start_size)
        time.sleep(5)
    raise TimeoutError(f"mykeibadb sync did not finish within {timeout_seconds} seconds")


def fetch_today_counts() -> dict[str, int]:
    tables = (
        "race_shosai",
        "umagoto_race_joho",
        "odds1_tansho",
        "odds1",
        "odds1_fukusho",
        "odds2_umaren",
        "odds3_wide",
        "odds4_umatan",
        "odds5_sanrenpuku",
        "odds6_sanrentan",
    )
    counts: dict[str, int] = {}
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE race_code LIKE %s",
                    (dt.date.today().strftime("%Y%m") + "%",),
                )
                counts[table] = cur.fetchone()[0]
    return counts


def print_counts(counts: dict[str, int]) -> None:
    print("mykeibadb table counts for this month:")
    for table, count in counts.items():
        print(f"  {table:<22} {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and run mykeibadb against WSL PostgreSQL")
    parser.add_argument("--prepare-only", action="store_true", help="update ini only")
    parser.add_argument("--dry-run", action="store_true", help="show what would be changed")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for mykeibadb log completion")
    args = parser.parse_args()

    exe_path, ini_path, log_path = mykeibadb_paths()
    if not exe_path.exists():
        print(f"mykeibadb.exe not found: {exe_path}")
        return 1
    if not ini_path.exists():
        print(f"mykeibadb.ini not found: {ini_path}")
        return 1

    server = get_wsl_ip()
    backup = update_ini_file(ini_path, server=server, dry_run=args.dry_run)
    print(f"WSL PostgreSQL server for mykeibadb: {server}")
    if backup:
        print(f"ini backup: {backup if not args.dry_run else '(dry-run)'}")
    else:
        print("ini already up to date")

    if args.prepare_only or args.dry_run:
        return 0

    pid = start_mykeibadb(exe_path)
    print(f"mykeibadb started: pid={pid}")
    try:
        wait_for_sync(log_path, timeout_seconds=args.timeout)
    finally:
        stop_mykeibadb()

    counts = fetch_today_counts()
    print_counts(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
