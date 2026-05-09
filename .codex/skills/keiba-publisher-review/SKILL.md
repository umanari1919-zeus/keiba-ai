---
name: keiba-publisher-review
description: Use when creating, reviewing, or editing X posts, note.com articles, morning report commentary, betting explanations, or public-facing horse racing predictions in the keiba_ai project.
---

# Keiba Publisher Review

## Overview

Use this to make public predictions useful, restrained, and credible. The goal is to communicate value and reasoning without promising wins.

## Voice

- Japanese first.
- Short, concrete, and human.
- Emphasize value, conditions, and risk.
- Avoid guaranteed language such as "必ず", "鉄板", "絶対", "確勝".
- Avoid implying investment advice or certain profit.

## Content Checklist

For each pick, prefer:

- horse name and race context
- odds range or anaba status when available
- one to two reasons: course fit, pace, trainer/jockey, pedigree, condition, EV
- one risk: layoff, class rise, distance, unstable style, market drift
- suggested bet type only when produced by the pipeline

Do not invent facts. If a field is missing, omit it or say the data is unavailable.

## Publishing Safety

- Draft first; live post only when the user explicitly asks.
- Keep X posts within the platform limit and avoid thread sprawl unless requested.
- note.com can include model method, caveats, and backtest context.
- Do not expose API keys, DB URLs with secrets, or private file paths.

## Verification

Before live posting, check:

```bash
python3 pipeline/morning_report.py --no-ollama
python3 run_all.py --source-sanity
```

If using `pipeline/post_x_05.py` or `pipeline/social_bot_27.py`, confirm credentials and target channel without printing secrets.
