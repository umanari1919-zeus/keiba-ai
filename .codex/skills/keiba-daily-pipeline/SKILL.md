---
name: keiba-daily-pipeline
description: Use when running, checking, or changing the daily JRA prediction pipeline, morning reports, publish preparation, bankroll checks, or operational diagnostics in the keiba_ai project.
---

# Keiba Daily Pipeline

## Overview

Use this for daily operation of `D:\keiba_ai`. Keep the work boring and repeatable: verify prerequisites, run the smallest safe command, inspect outputs, and avoid live SNS posting unless the user explicitly asks for it.

## Guardrails

- Treat `pipeline_v2` as the preferred path.
- Use constants from `pipeline/config.py`; do not create duplicate thresholds in pipeline scripts.
- Do not change `EV_THRESHOLD = 0.15`, `KELLY_FRACTION = 0.10`, `MIN_ODDS = 10.0`, or the 30x anaba definition unless the user clearly asks.
- Do not use odds or popularity as model features. Odds may be used only after prediction for EV filtering, bankroll, and reporting.
- Keep `advanced features` serial because CSV writes can conflict.
- Prefer dry checks before commands that publish to X, note.com, Discord, Telegram, or LINE.

## Command Flow

1. Check repository context:
   - `git status --short`
   - `python3 --version` or the project's configured Python launcher
2. For broad health checks, run:
   - `python3 run_all.py --doctor`
   - If that is too heavy, use `python3 run_all.py --runtime-check` and `python3 run_all.py --source-sanity`.
3. For a daily prediction run, prefer:
   - `python3 run_all.py --v2 --preflight-only`
   - then `python3 run_all.py --v2`
4. For today's ticket sheet only:
   - `python3 pipeline/morning_report.py`
   - Use `--no-ollama` when local LLM availability is uncertain.
5. For weekly learning:
   - `python3 run_all.py --v2-weekly`
6. For end-to-end dry validation:
   - `python3 canary_run.py`

If `python3` is not the active launcher on the user's machine, inspect local docs or scripts before substituting another command.

## Output Checks

After a run, report only the important evidence:

- whether preflight/doctor/canary passed
- generated report paths such as `reports/morning_YYYYMMDD.txt`
- count of recommended bets, if available
- any CRITICAL anomaly, bankroll drawdown stop, missing model, missing DB, or missing dependency

When a command fails, preserve the first concrete error and the command used. Do not bury the user in full logs.

## Publishing Safety

For X/note preparation:

- Generate or review content first.
- Confirm the target channel and live-posting intent before posting.
- Use Japanese that is confident but not deterministic; avoid promising wins.
- Include the model basis only when it helps readers: EV, anaba odds, race conditions, and risk.

## When Editing Pipeline Code

- Read `AGENTS.md`, `CLAUDE.md`, and `pipeline/AGENTS.md` if present.
- Use `pipeline/config.py` for new constants.
- Use `CSV_READ_OPTS` or `on_bad_lines='skip'` for CSV reads.
- Verify with the smallest command that covers the changed behavior, then run `python3 run_all.py --source-sanity` or `python3 canary_run.py` when risk is broader.
