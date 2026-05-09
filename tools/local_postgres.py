#!/usr/bin/env python3
"""
ユーザー領域 PostgreSQL 管理ツール。

sudo なしの WSL 環境向けに、conda-forge PostgreSQL を
`~/.keiba_ai/postgres18`、データを `~/.keiba_ai/pgdata18` に置いて使う。
PG18 が未配置の場合は旧 `~/.keiba_ai/postgres` にフォールバックする。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class PgPaths:
    prefix: pathlib.Path
    data_dir: pathlib.Path
    log_file: pathlib.Path


def _as_path(value: str | os.PathLike[str]) -> pathlib.Path:
    return pathlib.Path(value).expanduser()


def resolve_paths(
    *,
    home: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> PgPaths:
    home = home or pathlib.Path.home()
    env = env if env is not None else os.environ
    root = home / ".keiba_ai"

    if env.get("KEIBA_PG_PREFIX"):
        prefix = _as_path(env["KEIBA_PG_PREFIX"])
    else:
        pg18 = root / "postgres18"
        prefix = pg18 if pg18.exists() else root / "postgres"

    if env.get("KEIBA_PGDATA"):
        data_dir = _as_path(env["KEIBA_PGDATA"])
    else:
        data_dir = root / ("pgdata18" if prefix.name == "postgres18" else "pgdata")

    log_file = _as_path(env.get("KEIBA_PGLOG", root / f"{prefix.name}.log"))
    return PgPaths(prefix=prefix, data_dir=data_dir, log_file=log_file)


PATHS = resolve_paths()
HOME = pathlib.Path.home()
PG_PREFIX = PATHS.prefix
PGDATA = PATHS.data_dir
PGLOG = PATHS.log_file
PGPORT = int(os.getenv("KEIBA_PGPORT", "5433"))
PGUSER = os.getenv("KEIBA_PGUSER", "postgres")
PGPASSWORD = os.getenv("KEIBA_PGPASSWORD", "trust")
PGDATABASE = os.getenv("KEIBA_PGDATABASE", "mykeibadb")


def _bin(name: str) -> pathlib.Path:
    return PG_PREFIX / "bin" / name


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PGPASSWORD"] = PGPASSWORD
    return env


def _run(cmd: list[str], *, check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        env=_env(),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout, end="")
        raise SystemExit(result.returncode)
    return result


def ensure_binaries() -> None:
    missing = [str(_bin(name)) for name in ("initdb", "pg_ctl", "psql", "createdb") if not _bin(name).exists()]
    if missing:
        print("PostgreSQL binaries not found:")
        for item in missing:
            print(f"  {item}")
        print("Install with micromamba into ~/.keiba_ai/postgres18 or set KEIBA_PG_PREFIX.")
        raise SystemExit(1)


def configure() -> None:
    conf = PGDATA / "postgresql.conf"
    text = conf.read_text(encoding="utf-8") if conf.exists() else ""
    marker = "# keiba_ai local settings"
    if marker in text:
        return
    with conf.open("a", encoding="utf-8") as f:
        f.write(f"\n{marker}\nlisten_addresses = '127.0.0.1'\nport = {PGPORT}\n")


def initdb() -> None:
    ensure_binaries()
    if (PGDATA / "PG_VERSION").exists():
        configure()
        print(f"already initialized: {PGDATA}")
        return
    PGDATA.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(PGPASSWORD + "\n")
        pwfile = f.name
    try:
        _run([
            str(_bin("initdb")),
            "-D", str(PGDATA),
            "-U", PGUSER,
            f"--pwfile={pwfile}",
            "--auth-host=scram-sha-256",
            "--auth-local=trust",
            "--encoding=UTF8",
            "--locale=C",
        ], check=True)
    finally:
        pathlib.Path(pwfile).unlink(missing_ok=True)
    configure()


def _isready(dbname: str) -> subprocess.CompletedProcess:
    ensure_binaries()
    return _run([
        str(_bin("pg_isready")),
        "-h", "127.0.0.1",
        "-p", str(PGPORT),
        "-U", PGUSER,
        "-d", dbname,
    ], capture=True)


def status() -> int:
    ready = _isready(PGDATABASE)
    if ready.stdout:
        print(ready.stdout, end="")
    return ready.returncode


def start() -> None:
    initdb()
    if _isready("postgres").returncode == 0:
        create_db()
        status()
        return
    _run([str(_bin("pg_ctl")), "-D", str(PGDATA), "-l", str(PGLOG), "-w", "start"], check=True)
    create_db()


def stop() -> None:
    ensure_binaries()
    if not (PGDATA / "PG_VERSION").exists():
        print(f"not initialized: {PGDATA}")
        return
    _run([str(_bin("pg_ctl")), "-D", str(PGDATA), "-m", "fast", "-w", "stop"], check=True)


def create_db() -> None:
    ensure_binaries()
    query = f"select 1 from pg_database where datname = '{PGDATABASE}'"
    result = _run([
        str(_bin("psql")),
        "-h", "127.0.0.1",
        "-p", str(PGPORT),
        "-U", PGUSER,
        "-d", "postgres",
        "-tAc", query,
    ], capture=True)
    if result.stdout and result.stdout.strip() == "1":
        print(f"database exists: {PGDATABASE}")
        return
    _run([
        str(_bin("createdb")),
        "-h", "127.0.0.1",
        "-p", str(PGPORT),
        "-U", PGUSER,
        PGDATABASE,
    ], check=True)
    print(f"database created: {PGDATABASE}")


def main() -> int:
    parser = argparse.ArgumentParser(description="local PostgreSQL manager for keiba_ai")
    parser.add_argument("command", choices=["init", "start", "stop", "restart", "status", "create-db"])
    args = parser.parse_args()

    if args.command == "init":
        initdb()
    elif args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "restart":
        stop()
        start()
    elif args.command == "status":
        return status()
    elif args.command == "create-db":
        create_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
