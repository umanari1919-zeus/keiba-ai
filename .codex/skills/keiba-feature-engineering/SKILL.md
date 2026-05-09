---
name: keiba-feature-engineering
description: Use when designing, reviewing, or implementing new pre-race horse racing features, feature pipelines, historical aggregates, pedigree/training/course features, or feature quality checks in the keiba_ai project.
---

# Keiba Feature Engineering

## Overview

Use this to strengthen model signal without leaking market or result information. New features must be available before race start and must improve long-odds discovery, not merely explain past winners.

## Safe Feature Families

Prefer features from:

- horse history: rest days, rotation, distance change, surface change, class change, recent pace, closing speed, consistency
- course fit: track, distance, turn direction, slope, surface, season, weather, going
- jockey/trainer: historical rates before target race, course-distance compatibility, combo history
- pedigree: sire/dam-sire course fit, debut aptitude, dirt/turf, distance bands, track condition
- training: woodchip/pool/slope trends, lap change, speed z-score, multi-session trend
- race shape: pace pressure, front-runner count, field size, draw bias from past races
- anomaly/context: long layoff, first surface, first distance, jockey switch, stable form

## Forbidden Shortcuts

Do not add model features based on:

- current odds, final odds, popularity, market rank
- payout, refund, confirmed result, finishing position for the same race
- post-race comments or data published after the target race
- aggregates that accidentally include the target race

When in doubt, require an `as_of_date` or strict historical filter before computing aggregates.

## Implementation Pattern

1. Define the feature idea in plain language and the pre-race data source.
2. Identify the target grain: horse-race, race, jockey-race, trainer-race, or pedigree-race.
3. Add constants or paths in `pipeline/config.py` when needed.
4. Use historical windows that end before the target race date.
5. Fill missing values explicitly and keep the reason clear.
6. Add the feature to the model input list only after leakage review.
7. Verify with:

```bash
python3 tools/verify_integrity.py
python3 run_all.py --source-sanity
python3 canary_run.py
```

## High-Value Next Ideas

- Course-distance-surface rolling performance by sire and dam-sire.
- Jockey-trainer combo form over 30/90/365 days before race date.
- Draw bias by track, distance, surface, field size, and going.
- Pace pressure index from recent running style and field composition.
- Long-layoff return pattern by trainer and horse age.
- Training trend deltas across last 2-3 sessions, normalized by facility.
- New horse and jump-race specialist features that mirror `debut_analysis_39.py` and `shogai_analysis_40.py`.

## Review Standard

For every new feature, report:

- data source and timing
- exact columns added
- missing-value handling
- leakage risk
- expected reason it helps 30x+ anaba discovery
- verification command run
