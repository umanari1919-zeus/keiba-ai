---
name: block-dangerous-sql
enabled: true
event: bash
pattern: (?i)\b(drop\s+database|truncate\s+table|delete\s+from\s+\w+\s*(;|$))\b
action: block
---

🚨 **Dangerous SQL detected.**

This project must not run destructive SQL without explicit safeguards.

Before any destructive database operation, verify:

- backup or restore point exists
- target DB is not production
- row count and join count are understood
- NULL rates and time-series leakage risk are checked
- `EXPLAIN ANALYZE` has been reviewed when changing query behavior

Prefer a reversible migration or a scoped transaction with a rollback plan.
