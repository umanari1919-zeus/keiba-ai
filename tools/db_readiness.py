#!/usr/bin/env python3
"""mykeibadb の実運用向けコアテーブル診断。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import psycopg2
from psycopg2 import sql


CORE_TABLES = (
    "umagoto_race_joho",
    "race_shosai",
    "kyosoba_master2",
    "kaisaibi",
    "odds1_tansho",
)


def summarize_core_table_health(
    table_has_rows: Mapping[str, bool | None],
    *,
    core_tables: tuple[str, ...] = CORE_TABLES,
) -> tuple[str, str]:
    missing = [table for table in core_tables if table_has_rows.get(table) is None]
    empty = [table for table in core_tables if table_has_rows.get(table) is False]
    if missing or empty:
        parts: list[str] = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if empty:
            parts.append("empty: " + ", ".join(empty))
        return "WARN", "; ".join(parts)
    return "PASS", f"ready: {len(core_tables)}/{len(core_tables)} core tables have rows"


def fetch_core_table_health(
    db_config: Mapping[str, Any],
    *,
    core_tables: tuple[str, ...] = CORE_TABLES,
) -> tuple[str, str]:
    table_has_rows: dict[str, bool | None] = {table: None for table in core_tables}
    with psycopg2.connect(**dict(db_config)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (list(core_tables),),
            )
            existing = {row[0] for row in cur.fetchall()}
            for table in core_tables:
                if table not in existing:
                    continue
                cur.execute(
                    sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(
                        sql.Identifier(table)
                    )
                )
                table_has_rows[table] = bool(cur.fetchone()[0])
    return summarize_core_table_health(table_has_rows, core_tables=core_tables)
