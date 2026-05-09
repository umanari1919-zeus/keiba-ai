"""
PostgreSQL へのスナップショット同期ユーティリティ。

用途:
- keiba_data.csv / keiba_data_features.csv / today_entries_YYYYMMDD.csv を
  PostgreSQL の参照用テーブルへ同期する。
- 既存の分析パイプラインを壊さないよう、失敗時は例外を握りつぶして
  CSV 側の処理を継続できる設計にする。
"""

from __future__ import annotations

import argparse
import time
import pathlib
import sys
from datetime import datetime
from typing import Iterable, Optional

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:
    create_engine = None
    text = None
    Engine = object

from pipeline.config import DB_URL


def check_runtime() -> list[str]:
    issues = []
    if pd is None:
        issues.append("pandas が未インストールです")
    if create_engine is None:
        issues.append("sqlalchemy が未インストールです")
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        issues.append("psycopg2 が未インストールです")
    return issues


def get_engine(db_url: str = DB_URL) -> Engine:
    if create_engine is None or text is None:
        raise RuntimeError("sqlalchemy が未インストールのため DB 接続できません")
    last_err = None
    for attempt in range(1, 4):
        try:
            engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise last_err


def _normalize_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object":
            out[col] = out[col].where(out[col].notna(), None)
    return out


def ensure_ingest_log_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ingest_log (
                id BIGSERIAL PRIMARY KEY,
                table_name TEXT NOT NULL,
                source_name TEXT NOT NULL,
                row_count BIGINT NOT NULL,
                column_count BIGINT NOT NULL,
                mode TEXT NOT NULL,
                ingested_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))


def write_snapshot(
    df: pd.DataFrame,
    table_name: str,
    *,
    db_url: str = DB_URL,
    if_exists: str = "replace",
    chunksize: int = 10_000,
    index: bool = False,
    source_name: Optional[str] = None,
) -> bool:
    """
    DataFrame を PostgreSQL のスナップショット表へ同期する。
    失敗時は False を返し、呼び出し側の CSV 保存を止めない。
    """
    if df is None or len(df) == 0:
        return False

    source_name = source_name or table_name
    engine = get_engine(db_url)
    try:
        safe_df = _normalize_for_sql(df)
        safe_df.to_sql(
            table_name,
            engine,
            if_exists=if_exists,
            index=index,
            chunksize=chunksize,
            method="multi",
        )
        ensure_ingest_log_table(engine)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ingest_log (
                        table_name, source_name, row_count, column_count, mode, ingested_at
                    ) VALUES (:table_name, :source_name, :row_count, :column_count, :mode, :ingested_at)
                """),
                {
                    "table_name": table_name,
                    "source_name": source_name,
                    "row_count": int(len(df)),
                    "column_count": int(len(df.columns)),
                    "mode": if_exists,
                    "ingested_at": datetime.now(),
                },
            )
        return True
    finally:
        engine.dispose()


def add_ingest_meta(df: pd.DataFrame, *, source_name: str, ingested_at: Optional[datetime] = None) -> pd.DataFrame:
    out = df.copy()
    out["source_name"] = source_name
    out["ingested_at"] = ingested_at or datetime.now()
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DB スナップショット同期ユーティリティ")
    parser.add_argument("--dry-run", action="store_true", help="依存関係だけ確認する")
    args, _ = parser.parse_known_args()

    if args.dry_run:
        issues = check_runtime()
        if issues:
            print("[db_sync_42] dry-run: 要確認")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("[db_sync_42] dry-run: 実行要件は概ね満たしています")
        raise SystemExit(0)

    print("[db_sync_42] utility module loaded")
