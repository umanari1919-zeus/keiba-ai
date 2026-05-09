#!/usr/bin/env python3
"""keiba_data.csv から JRA-VAN コア2テーブルを補完する。"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, CSV_RAW, DB_CONFIG


RACE_SHOSAI_COLUMNS = [
    "insert_timestamp",
    "update_timestamp",
    "record_shubetsu_id",
    "data_kubun",
    "data_sakusei_nengappi",
    "race_code",
    "kaisai_nen",
    "kaisai_gappi",
    "keibajo_code",
    "kaisai_kai",
    "kaisai_nichime",
    "race_bango",
    "grade_code",
    "kyori",
    "track_code",
    "shusso_tosu",
    "tenko_code",
    "shiba_babajotai_code",
    "dirt_babajotai_code",
]

UMAGOTO_COLUMNS = [
    "insert_timestamp",
    "update_timestamp",
    "record_shubetsu_id",
    "data_kubun",
    "data_sakusei_nengappi",
    "race_code",
    "kaisai_nen",
    "kaisai_gappi",
    "keibajo_code",
    "kaisai_kaiji",
    "kaisai_nichiji",
    "race_bango",
    "wakuban",
    "umaban",
    "ketto_toroku_bango",
    "bamei",
    "seibetsu_code",
    "barei",
    "chokyoshi_code",
    "chokyoshimei_ryakusho",
    "futan_juryo",
    "kishu_code",
    "kishumei_ryakusho",
    "bataiju",
    "zogen_fugo",
    "zogen_sa",
    "kakutei_chakujun",
    "soha_time",
    "corner4_juni",
    "tansho_odds",
    "tansho_ninkijun",
    "kohan_4f",
    "kohan_3f",
    "kyakushitsu_hantei",
]

CSV_USECOLS = sorted({
    "race_code",
    "kaisai_nen",
    "kaisai_gappi",
    "keibajo_code",
    "bamei",
    "ketto_toroku_bango",
    "barei",
    "seibetsu_code",
    "kishu_code",
    "kishumei_ryakusho",
    "chokyoshi_code",
    "chokyoshimei_ryakusho",
    "futan_juryo",
    "bataiju",
    "zogen_sa",
    "zogen_fugo",
    "tansho_odds",
    "tansho_ninkijun",
    "kyakushitsu_hantei",
    "kakutei_chakujun",
    "wakuban",
    "umaban",
    "kyori",
    "track_code",
    "tenko_code",
    "shiba_babajotai_code",
    "dirt_babajotai_code",
    "shusso_tosu",
    "kaisai_kai",
    "kaisai_nichime",
    "race_grade",
})


def normalize_code(value: Any, *, width: int | None = None, default: str = "") -> str:
    if value is None:
        return default
    if pd.isna(value):
        return default
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return default
    if text.endswith(".0"):
        text = text[:-2]
    if width is not None:
        text = text.zfill(width)
        if len(text) > width:
            text = text[-width:]
    return text


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _race_bango(row: Mapping[str, Any]) -> str:
    explicit = normalize_code(row.get("race_bango"), width=2)
    if explicit:
        return explicit
    race_code = normalize_code(row.get("race_code"))
    return race_code[-2:].zfill(2) if len(race_code) >= 2 else ""


def _grade_code(value: Any) -> str:
    return normalize_code(value)[:1]


def build_race_shosai_row(row: Mapping[str, Any]) -> dict[str, str]:
    now = _timestamp()
    return {
        "insert_timestamp": now,
        "update_timestamp": "0000-00-00 00:00:00",
        "record_shubetsu_id": "RA",
        "data_kubun": "7",
        "data_sakusei_nengappi": _today(),
        "race_code": normalize_code(row.get("race_code"), width=16),
        "kaisai_nen": normalize_code(row.get("kaisai_nen"), width=4),
        "kaisai_gappi": normalize_code(row.get("kaisai_gappi"), width=4),
        "keibajo_code": normalize_code(row.get("keibajo_code"), width=2),
        "kaisai_kai": normalize_code(row.get("kaisai_kai"), width=2),
        "kaisai_nichime": normalize_code(row.get("kaisai_nichime"), width=2),
        "race_bango": _race_bango(row),
        "grade_code": _grade_code(row.get("race_grade")),
        "kyori": normalize_code(row.get("kyori"), width=4),
        "track_code": normalize_code(row.get("track_code"), width=2),
        "shusso_tosu": normalize_code(row.get("shusso_tosu"), width=2),
        "tenko_code": normalize_code(row.get("tenko_code"), width=1),
        "shiba_babajotai_code": normalize_code(row.get("shiba_babajotai_code"), width=1),
        "dirt_babajotai_code": normalize_code(row.get("dirt_babajotai_code"), width=1),
    }


def build_umagoto_row(row: Mapping[str, Any]) -> dict[str, str]:
    now = _timestamp()
    return {
        "insert_timestamp": now,
        "update_timestamp": "0000-00-00 00:00:00",
        "record_shubetsu_id": "SE",
        "data_kubun": "7",
        "data_sakusei_nengappi": _today(),
        "race_code": normalize_code(row.get("race_code"), width=16),
        "kaisai_nen": normalize_code(row.get("kaisai_nen"), width=4),
        "kaisai_gappi": normalize_code(row.get("kaisai_gappi"), width=4),
        "keibajo_code": normalize_code(row.get("keibajo_code"), width=2),
        "kaisai_kaiji": normalize_code(row.get("kaisai_kai"), width=2),
        "kaisai_nichiji": normalize_code(row.get("kaisai_nichime"), width=2),
        "race_bango": _race_bango(row),
        "wakuban": normalize_code(row.get("wakuban"), width=1),
        "umaban": normalize_code(row.get("umaban"), width=2),
        "ketto_toroku_bango": normalize_code(row.get("ketto_toroku_bango"), width=10),
        "bamei": normalize_code(row.get("bamei")),
        "seibetsu_code": normalize_code(row.get("seibetsu_code"), width=1),
        "barei": normalize_code(row.get("barei"), width=2),
        "chokyoshi_code": normalize_code(row.get("chokyoshi_code"), width=5),
        "chokyoshimei_ryakusho": normalize_code(row.get("chokyoshimei_ryakusho")),
        "futan_juryo": normalize_code(row.get("futan_juryo"), width=3),
        "kishu_code": normalize_code(row.get("kishu_code"), width=5),
        "kishumei_ryakusho": normalize_code(row.get("kishumei_ryakusho")),
        "bataiju": normalize_code(row.get("bataiju"), width=3),
        "zogen_fugo": normalize_code(row.get("zogen_fugo"), width=1),
        "zogen_sa": normalize_code(row.get("zogen_sa"), width=3),
        "kakutei_chakujun": normalize_code(row.get("kakutei_chakujun"), width=2),
        "soha_time": "0001",
        "corner4_juni": "",
        "tansho_odds": normalize_code(row.get("tansho_odds"), width=4),
        "tansho_ninkijun": normalize_code(row.get("tansho_ninkijun"), width=2),
        "kohan_4f": "",
        "kohan_3f": "",
        "kyakushitsu_hantei": normalize_code(row.get("kyakushitsu_hantei"), width=1),
    }


def _insert_rows(cur, table: str, columns: list[str], rows: list[dict[str, str]]) -> int:
    if not rows:
        return 0
    values = [[row.get(col, "") for col in columns] for row in rows]
    column_sql = ", ".join(columns)
    query = f"INSERT INTO {table} ({column_sql}) VALUES %s"
    execute_values(cur, query, values, page_size=10_000)
    return len(rows)


def seed_core_tables(csv_path: str, *, replace: bool = False, chunk_size: int = 50_000) -> tuple[int, int]:
    race_rows_by_code: dict[str, dict[str, str]] = {}
    inserted_umagoto = 0

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("SET synchronous_commit TO off")
            if replace:
                cur.execute("TRUNCATE TABLE race_shosai, umagoto_race_joho")

            for chunk in pd.read_csv(
                csv_path,
                usecols=lambda col: col in CSV_USECOLS,
                dtype=str,
                chunksize=chunk_size,
                on_bad_lines="skip",
            ):
                chunk = chunk.where(pd.notna(chunk), None)
                records = chunk.to_dict("records")
                umagoto_rows = [build_umagoto_row(record) for record in records]
                inserted_umagoto += _insert_rows(cur, "umagoto_race_joho", UMAGOTO_COLUMNS, umagoto_rows)

                for record in records:
                    race_row = build_race_shosai_row(record)
                    if race_row["race_code"]:
                        race_rows_by_code[race_row["race_code"]] = race_row
                conn.commit()

            race_rows = list(race_rows_by_code.values())
            inserted_races = _insert_rows(cur, "race_shosai", RACE_SHOSAI_COLUMNS, race_rows)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seed_race_shosai_race_code ON race_shosai(race_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seed_umagoto_race_code ON umagoto_race_joho(race_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seed_umagoto_ketto ON umagoto_race_joho(ketto_toroku_bango)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_seed_umagoto_year ON umagoto_race_joho(kaisai_nen)")
            conn.commit()
    return inserted_races, inserted_umagoto


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed race_shosai and umagoto_race_joho from keiba_data.csv")
    parser.add_argument("--csv", default=str(CSV_RAW or f"{BASE_DIR}/keiba_data.csv"))
    parser.add_argument("--replace", action="store_true", help="TRUNCATE core tables before inserting")
    parser.add_argument("--chunk-size", type=int, default=50_000)
    args = parser.parse_args()

    races, horses = seed_core_tables(args.csv, replace=args.replace, chunk_size=args.chunk_size)
    print(f"seeded race_shosai={races:,} umagoto_race_joho={horses:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
