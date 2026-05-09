#!/usr/bin/env python3
"""PostgreSQL advanced maintenance for the keiba_ai local database.

This tool keeps the local DB upgrade conservative:
- no destructive DDL
- recommended indexes are skipped when target columns are absent
- CREATE INDEX CONCURRENTLY is used so daily work is less likely to block
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Iterable

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from psycopg2 import sql

from pipeline.config import DB_CONFIG
from tools.local_postgres import PGDATA


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str) -> str:
    if not IDENTIFIER_RE.match(value):
        raise ValueError(f"unsafe SQL identifier: {value!r}")
    return value


@dataclass(frozen=True)
class RecommendedIndex:
    name: str
    table: str
    columns: tuple[str, ...]
    include: tuple[str, ...] = ()
    where: str = ""

    def create_sql(self) -> str:
        name = _identifier(self.name)
        table = _identifier(self.table)
        columns = ", ".join(_identifier(column) for column in self.columns)
        statement = (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {table} ({columns})"
        )
        if self.include:
            included = ", ".join(_identifier(column) for column in self.include)
            statement += f" INCLUDE ({included})"
        if self.where:
            statement += f" WHERE {self.where}"
        return statement


@dataclass(frozen=True)
class MykeibadbConflictIndex:
    name: str
    table: str
    columns: tuple[str, ...]

    def create_sql(self) -> str:
        name = _identifier(self.name)
        table = _identifier(self.table)
        columns = ", ".join(_identifier(column) for column in self.columns)
        return (
            f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {table} ({columns})"
        )


RECOMMENDED_INDEXES: tuple[RecommendedIndex, ...] = (
    RecommendedIndex(
        name="idx_keiba_umagoto_race_horse",
        table="umagoto_race_joho",
        columns=("race_code", "ketto_toroku_bango"),
    ),
    RecommendedIndex(
        name="idx_keiba_umagoto_year_day_place",
        table="umagoto_race_joho",
        columns=("kaisai_nen", "kaisai_gappi", "keibajo_code", "race_bango"),
    ),
    RecommendedIndex(
        name="idx_keiba_umagoto_horse_race",
        table="umagoto_race_joho",
        columns=("ketto_toroku_bango", "race_code"),
    ),
    RecommendedIndex(
        name="idx_keiba_umagoto_jockey_place",
        table="umagoto_race_joho",
        columns=("kishu_code", "keibajo_code"),
        where="kakutei_chakujun ~ '^[0-9]+'",
    ),
    RecommendedIndex(
        name="idx_keiba_umagoto_trainer_place",
        table="umagoto_race_joho",
        columns=("chokyoshi_code", "keibajo_code"),
        where="kakutei_chakujun ~ '^[0-9]+'",
    ),
    RecommendedIndex(
        name="idx_keiba_race_shosai_year_day_place",
        table="race_shosai",
        columns=("kaisai_nen", "kaisai_gappi", "keibajo_code", "race_bango"),
    ),
    RecommendedIndex(
        name="idx_keiba_race_shosai_course",
        table="race_shosai",
        columns=("keibajo_code", "track_code", "kyori"),
        where="kyori ~ '^[0-9]+'",
    ),
    RecommendedIndex(
        name="idx_keiba_kyosoba_ketto",
        table="kyosoba_master2",
        columns=("ketto_toroku_bango",),
    ),
    RecommendedIndex(
        name="idx_keiba_odds1_tansho_year_day",
        table="odds1_tansho",
        columns=("kaisai_nen", "kaisai_gappi", "keibajo_code", "race_bango"),
    ),
    RecommendedIndex(
        name="idx_keiba_odds1_tansho_race_umaban",
        table="odds1_tansho",
        columns=("race_code", "umaban"),
    ),
    RecommendedIndex(
        name="idx_keiba_hanro_chokyo_horse_date",
        table="hanro_chokyo",
        columns=("ketto_toroku_bango", "chokyo_nengappi"),
    ),
    RecommendedIndex(
        name="idx_keiba_woodchip_chokyo_horse_date",
        table="woodchip_chokyo",
        columns=("ketto_toroku_bango", "chokyo_nengappi"),
    ),
    RecommendedIndex(
        name="idx_keiba_tokubetsu_year_day",
        table="tokubetsu_torokuba",
        columns=("kaisai_nen", "kaisai_gappi", "keibajo_code"),
    ),
)


MYKEIBADB_CONFLICT_INDEXES: tuple[MykeibadbConflictIndex, ...] = (
    MykeibadbConflictIndex("uidx_mykeibadb_bamei_imi_yurai_ketto", "bamei_imi_yurai", ("ketto_toroku_bango",)),
    MykeibadbConflictIndex("uidx_mykeibadb_banushi_code", "banushi_master", ("banushi_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_chokyoshi_code", "chokyoshi_master", ("chokyoshi_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_mining_taisen_race", "data_mining_taisen", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_mining_time_race", "data_mining_time", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_hanro_chokyo_key", "hanro_chokyo", ("tracen_kubun", "chokyo_nengappi", "chokyo_jikoku", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_haraimodoshi_race", "haraimodoshi", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_race", "hyosu1", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_fukusho_race_umaban", "hyosu1_fukusho", ("race_code", "umaban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_sanrenpuku_race_kumi", "hyosu1_sanrenpuku", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_tansho_race_umaban", "hyosu1_tansho", ("race_code", "umaban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_umaren_race_kumi", "hyosu1_umaren", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_umatan_race_kumi", "hyosu1_umatan", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_wakuren_race_kumi", "hyosu1_wakuren", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu1_wide_race_kumi", "hyosu1_wide", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu6_race", "hyosu6", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_hyosu6_sanrentan_race_kumi", "hyosu6_sanrentan", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_kaisai_schedule_code", "kaisai_schedule", ("kaisai_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_kaisaibi", "kaisaibi", ("kaisaibi",)),
    MykeibadbConflictIndex("uidx_mykeibadb_kishu_code", "kishu_master", ("kishu_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_kyosoba_jogai_key", "kyosoba_jogai_joho", ("race_code", "ketto_toroku_bango", "shutsuba_tohyo_uketsuke")),
    MykeibadbConflictIndex("uidx_mykeibadb_kyosoba_ketto", "kyosoba_master2", ("ketto_toroku_bango",)),
    MykeibadbConflictIndex("uidx_mykeibadb_kyosoba_torihiki_key", "kyosoba_torihiki_kakaku2", ("ketto_toroku_bango", "shusaisha_shijo_code", "kaisai_kikan_kaishibi")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds1_race", "odds1", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_odds1_fukusho_race_umaban", "odds1_fukusho", ("race_code", "umaban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds1_tansho_race_umaban", "odds1_tansho", ("race_code", "umaban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds1_wakuren_race_kumi", "odds1_wakuren", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds2_umaren_race_kumi", "odds2_umaren", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds3_wide_race_kumi", "odds3_wide", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds4_umatan_race_kumi", "odds4_umatan", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds5_sanrenpuku_race_kumi", "odds5_sanrenpuku", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_odds6_sanrentan_race_kumi", "odds6_sanrentan", ("race_code", "kumiban")),
    MykeibadbConflictIndex("uidx_mykeibadb_race_shosai_race_code", "race_shosai", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_record_master_key", "record_master", ("record_shikibetsu_kubun", "race_code", "tokubetsu_kyoso_bango", "kyoso_shubetsu_code", "kyori", "track_code")),
    MykeibadbConflictIndex("uidx_mykeibadb_sanku_ketto", "sanku_master2", ("ketto_toroku_bango",)),
    MykeibadbConflictIndex("uidx_mykeibadb_seisansha_code", "seisansha_master2", ("seisansha_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_baba_key", "shussobetsu_baba", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_banushi_key", "shussobetsu_banushi", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_chokyoshi_key", "shussobetsu_chokyoshi", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_keibajo_key", "shussobetsu_keibajo", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_kishu_key", "shussobetsu_kishu", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_kyori_key", "shussobetsu_kyori", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_shussobetsu_seisansha2_key", "shussobetsu_seisansha2", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_tokubetsu_torokuba_race", "tokubetsu_torokuba", ("race_code",)),
    MykeibadbConflictIndex("uidx_mykeibadb_tokubetsu_torokubagoto_key", "tokubetsu_torokubagoto_joho", ("race_code", "renban")),
    MykeibadbConflictIndex("uidx_mykeibadb_umagoto_race_horse", "umagoto_race_joho", ("race_code", "ketto_toroku_bango")),
    MykeibadbConflictIndex("uidx_mykeibadb_win5_day", "win5", ("kaisai_nen", "kaisai_gappi")),
    MykeibadbConflictIndex("uidx_mykeibadb_win5_haraimodoshi_key", "win5_haraimodoshi", ("kaisai_nen", "kaisai_gappi", "win5_kumiban1", "win5_kumiban2", "win5_kumiban3", "win5_kumiban4", "win5_kumiban5")),
    MykeibadbConflictIndex("uidx_mykeibadb_woodchip_chokyo_key", "woodchip_chokyo", ("tracen_kubun", "chokyo_nengappi", "chokyo_jikoku", "ketto_toroku_bango")),
)


ADVANCED_CONF_MARKER = "# keiba_ai advanced postgres settings"
ADVANCED_SETTINGS = {
    "shared_buffers": "512MB",
    "work_mem": "32MB",
    "maintenance_work_mem": "512MB",
    "effective_cache_size": "4GB",
    "checkpoint_completion_target": "0.9",
    "random_page_cost": "1.1",
    "effective_io_concurrency": "200",
    "max_wal_size": "2GB",
    "shared_preload_libraries": "'pg_stat_statements'",
}


def fetch_existing_columns(conn) -> dict[str, set[str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            """
        )
        columns: dict[str, set[str]] = {}
        for table, column in cur.fetchall():
            columns.setdefault(table, set()).add(column)
    return columns


def filter_available_indexes(
    indexes: Iterable[RecommendedIndex],
    existing_columns: dict[str, set[str]],
) -> tuple[list[RecommendedIndex], list[tuple[RecommendedIndex, str]]]:
    available: list[RecommendedIndex] = []
    skipped: list[tuple[RecommendedIndex, str]] = []
    for index in indexes:
        columns = existing_columns.get(index.table)
        if columns is None:
            skipped.append((index, "missing table"))
            continue
        needed = set(index.columns) | set(index.include)
        missing = sorted(needed - columns)
        if missing:
            skipped.append((index, "missing columns: " + ", ".join(missing)))
            continue
        available.append(index)
    return available, skipped


def filter_available_conflict_indexes(
    indexes: Iterable[MykeibadbConflictIndex],
    existing_columns: dict[str, set[str]],
) -> tuple[list[MykeibadbConflictIndex], list[tuple[MykeibadbConflictIndex, str]]]:
    available: list[MykeibadbConflictIndex] = []
    skipped: list[tuple[MykeibadbConflictIndex, str]] = []
    for index in indexes:
        columns = existing_columns.get(index.table)
        if columns is None:
            skipped.append((index, "missing table"))
            continue
        missing = sorted(set(index.columns) - columns)
        if missing:
            skipped.append((index, "missing columns: " + ", ".join(missing)))
            continue
        available.append(index)
    return available, skipped


def duplicate_key_probe_sql(index: MykeibadbConflictIndex) -> str:
    table = _identifier(index.table)
    columns = ", ".join(_identifier(column) for column in index.columns)
    return (
        "SELECT COUNT(*) FROM ("
        f"SELECT 1 FROM {table} "
        f"GROUP BY {columns} "
        "HAVING COUNT(*) > 1 "
        "LIMIT 1"
        ") AS duplicate_keys"
    )


def drop_index_sql(index: MykeibadbConflictIndex) -> str:
    return f"DROP INDEX CONCURRENTLY IF EXISTS {_identifier(index.name)}"


def has_duplicate_key(conn, index: MykeibadbConflictIndex) -> bool:
    with conn.cursor() as cur:
        cur.execute(duplicate_key_probe_sql(index))
        return cur.fetchone()[0] > 0


def configure_postgresql_conf(*, dry_run: bool = False) -> pathlib.Path:
    conf = PGDATA / "postgresql.conf"
    if not conf.exists():
        raise FileNotFoundError(f"postgresql.conf not found: {conf}")

    block_lines = [ADVANCED_CONF_MARKER]
    block_lines.extend(f"{key} = {value}" for key, value in ADVANCED_SETTINGS.items())
    block = "\n".join(block_lines) + "\n"

    text = conf.read_text(encoding="utf-8")
    if ADVANCED_CONF_MARKER in text:
        before = text.split(ADVANCED_CONF_MARKER, 1)[0].rstrip()
        text = before + "\n\n" + block
    else:
        text = text.rstrip() + "\n\n" + block

    if not dry_run:
        conf.write_text(text, encoding="utf-8")
    return conf


def print_audit() -> None:
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            print(cur.fetchone()[0])
            cur.execute(
                """
                SELECT name, setting, unit
                FROM pg_settings
                WHERE name IN (
                    'shared_buffers',
                    'work_mem',
                    'maintenance_work_mem',
                    'effective_cache_size',
                    'checkpoint_completion_target',
                    'random_page_cost',
                    'effective_io_concurrency',
                    'max_wal_size',
                    'shared_preload_libraries'
                )
                ORDER BY name
                """
            )
            print("\nsettings:")
            for name, setting, unit in cur.fetchall():
                suffix = unit or ""
                print(f"  {name}: {setting}{suffix}")

            existing_columns = fetch_existing_columns(conn)
            available, skipped = filter_available_indexes(RECOMMENDED_INDEXES, existing_columns)
            print("\nrecommended indexes:")
            for index in available:
                print(f"  OK   {index.name}")
            for index, reason in skipped:
                print(f"  SKIP {index.name}: {reason}")

            cur.execute(
                """
                SELECT schemaname, tablename, indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = ANY(%s)
                ORDER BY tablename, indexname
                """,
                ([index.name for index in RECOMMENDED_INDEXES],),
            )
            installed = cur.fetchall()
            print(f"\ninstalled recommended indexes: {len(installed)}/{len(available)}")
            for _, table, index in installed:
                print(f"  {table}: {index}")

            conflict_available, conflict_skipped = filter_available_conflict_indexes(
                MYKEIBADB_CONFLICT_INDEXES,
                existing_columns,
            )
            cur.execute(
                """
                SELECT schemaname, tablename, indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = ANY(%s)
                ORDER BY tablename, indexname
                """,
                ([index.name for index in MYKEIBADB_CONFLICT_INDEXES],),
            )
            conflict_installed = cur.fetchall()
            print(
                "\nmykeibadb conflict indexes: "
                f"{len(conflict_installed)}/{len(conflict_available)} installed"
            )
            for _, table, index in conflict_installed:
                print(f"  {table}: {index}")
            for index, reason in conflict_skipped:
                print(f"  SKIP {index.name}: {reason}")


def apply_indexes(*, dry_run: bool = False, analyze: bool = True) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.autocommit = True
        existing_columns = fetch_existing_columns(conn)
        available, skipped = filter_available_indexes(RECOMMENDED_INDEXES, existing_columns)
        with conn.cursor() as cur:
            for index in available:
                statement = index.create_sql()
                print(statement)
                if not dry_run:
                    cur.execute(statement)
            if analyze:
                for table in sorted({index.table for index in available}):
                    statement = sql.SQL("ANALYZE {}").format(sql.Identifier(table))
                    print(statement.as_string(conn))
                    if not dry_run:
                        cur.execute(statement)
        for index, reason in skipped:
            print(f"SKIP {index.name}: {reason}")
    finally:
        conn.close()


def apply_mykeibadb_conflict_indexes(
    *,
    dry_run: bool = False,
    analyze: bool = True,
    skip_duplicate_check: bool = False,
) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.autocommit = True
        existing_columns = fetch_existing_columns(conn)
        available, skipped = filter_available_conflict_indexes(
            MYKEIBADB_CONFLICT_INDEXES,
            existing_columns,
        )
        created_tables: set[str] = set()
        with conn.cursor() as cur:
            for index in available:
                if not skip_duplicate_check and has_duplicate_key(conn, index):
                    print(f"SKIP {index.name}: duplicate keys exist")
                    continue
                statement = index.create_sql()
                print(statement, flush=True)
                if not dry_run:
                    try:
                        cur.execute(statement)
                    except psycopg2.Error as exc:
                        print(f"SKIP {index.name}: {str(exc).strip().splitlines()[0]}")
                        cur.execute(drop_index_sql(index))
                    else:
                        created_tables.add(index.table)
            if analyze:
                for table in sorted(created_tables):
                    statement = sql.SQL("ANALYZE {}").format(sql.Identifier(table))
                    print(statement.as_string(conn), flush=True)
                    if not dry_run:
                        cur.execute(statement)
        for index, reason in skipped:
            print(f"SKIP {index.name}: {reason}")
    finally:
        conn.close()


def install_extensions(*, dry_run: bool = False) -> None:
    statements = [
        "CREATE EXTENSION IF NOT EXISTS pg_stat_statements",
        "CREATE EXTENSION IF NOT EXISTS btree_gin",
    ]
    with psycopg2.connect(**DB_CONFIG) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for statement in statements:
                print(statement)
                if not dry_run:
                    cur.execute(statement)


def main() -> int:
    parser = argparse.ArgumentParser(description="Advanced PostgreSQL maintenance for keiba_ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("audit", help="show current settings and recommended index status")

    configure_parser = subparsers.add_parser("configure", help="write advanced local postgresql.conf settings")
    configure_parser.add_argument("--dry-run", action="store_true")

    extension_parser = subparsers.add_parser("extensions", help="install safe optional extensions")
    extension_parser.add_argument("--dry-run", action="store_true")

    indexes_parser = subparsers.add_parser("indexes", help="create recommended indexes")
    indexes_parser.add_argument("--dry-run", action="store_true")
    indexes_parser.add_argument("--no-analyze", action="store_true")

    conflict_parser = subparsers.add_parser(
        "mykeibadb-indexes",
        help="create unique indexes needed by mykeibadb ON CONFLICT upserts",
    )
    conflict_parser.add_argument("--dry-run", action="store_true")
    conflict_parser.add_argument("--no-analyze", action="store_true")
    conflict_parser.add_argument(
        "--skip-duplicate-check",
        action="store_true",
        help="let CREATE UNIQUE INDEX validate duplicates instead of pre-scanning",
    )

    upgrade_parser = subparsers.add_parser("upgrade", help="configure, install extensions, and create indexes")
    upgrade_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "audit":
        print_audit()
    elif args.command == "configure":
        conf = configure_postgresql_conf(dry_run=args.dry_run)
        print(f"advanced config {'would update' if args.dry_run else 'updated'}: {conf}")
        if not args.dry_run:
            print("restart PostgreSQL to activate postgresql.conf changes")
    elif args.command == "extensions":
        install_extensions(dry_run=args.dry_run)
    elif args.command == "indexes":
        apply_indexes(dry_run=args.dry_run, analyze=not args.no_analyze)
    elif args.command == "mykeibadb-indexes":
        apply_mykeibadb_conflict_indexes(
            dry_run=args.dry_run,
            analyze=not args.no_analyze,
            skip_duplicate_check=args.skip_duplicate_check,
        )
    elif args.command == "upgrade":
        conf = configure_postgresql_conf(dry_run=args.dry_run)
        print(f"advanced config {'would update' if args.dry_run else 'updated'}: {conf}")
        install_extensions(dry_run=args.dry_run)
        apply_indexes(dry_run=args.dry_run, analyze=True)
        if not args.dry_run:
            print("restart PostgreSQL to activate postgresql.conf changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
