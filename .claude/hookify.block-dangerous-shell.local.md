---
name: block-dangerous-shell
enabled: true
event: bash
pattern: \brm\s+-rf\s+(/|\*|\.|~|\$HOME|\$PWD|[^&|;]*\s+\*)
action: block
---

🚨 **Dangerous shell deletion detected.**

`rm -rf` can destroy the project, generated data, models, or local database state.

Use a safer scoped command, inspect the target first, and keep backups for any generated data or model artifacts.
