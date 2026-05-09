---
name: keiba-db-ops
description: Use when inspecting, optimizing, or changing PostgreSQL schemas, indexes, query plans, seed scripts, database readiness checks, or mykeibadb integration in the keiba_ai project.
---

# Keiba DB Ops

## Overview

Use this for PostgreSQL work that supports faster, safer feature generation. Prefer read-only diagnostics first, then reversible index/schema changes, then data migrations only when necessary.

## Safety Rules

- Do not print secrets from `.env`.
- Prefer read-only SQL until the user approves writes.
- Use `CREATE INDEX CONCURRENTLY IF NOT EXISTS` for large operational tables.
- Avoid long transactions around CSV import, index creation, or feature generation.
- For feature aggregates, filter history strictly before the target race date.
- Keep database connection settings in `pipeline/config.py` or `.env`.

## Useful Local Entry Points

- `tools/db_readiness.py`
- `tools/doctor.py`
- `tools/postgres_advanced.py`
- `tools/seed_core_tables_from_csv.py`
- `tools/verify_integrity.py`
- `memory/project_db.md`

## Diagnostic Flow

1. Confirm DB readiness:

```bash
python3 tools/db_readiness.py
python3 run_all.py --runtime-check
```

2. Inspect schema and row counts with read-only SQL.
3. For slow queries, use `EXPLAIN (ANALYZE, BUFFERS)` only on safe representative queries.
4. Check missing or unused indexes with existing tools before adding new ones.
5. Run `VACUUM (ANALYZE)` or table-specific `ANALYZE` after large imports when appropriate.

## High-Value Index Areas

Prioritize columns used for joins and historical filters:

- `race_code`
- `kaisai_nen`, `kaisai_gappi`
- `ketto_toroku_bango`
- `bamei`
- jockey and trainer codes
- track, distance, surface, class, race date

Composite indexes should match real query predicates. Do not add many speculative indexes; they slow writes and imports.

## PostgreSQL Strengthening Ideas

- Materialized views for expensive historical aggregates, refreshed before daily prediction.
- Partitioning or year-based tables for very large race result histories.
- Covering indexes for common feature joins.
- `pg_stat_statements` for finding slow feature queries.
- Read-only MCP/Postgres access for Codex diagnostics, with write tools disabled by default.

## Verification

After DB changes, run the narrowest relevant checks:

```bash
python3 tools/db_readiness.py
python3 tools/verify_integrity.py
python3 run_all.py --runtime-check
python3 canary_run.py
```
