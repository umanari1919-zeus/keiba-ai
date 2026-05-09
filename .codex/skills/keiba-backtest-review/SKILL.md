---
name: keiba-backtest-review
description: Use when reviewing ROI, hit rate, recovery rate, expected value thresholds, Kelly sizing, walk-forward tests, or betting strategy results in the keiba_ai project.
---

# Keiba Backtest Review

## Overview

Use this to judge whether a strategy is useful in practice, not just accurate as a classifier. The project cares about long-odds value, bankroll survival, and repeatable out-of-sample behavior.

## Required Metrics

Always look for:

- total bets, hit count, hit rate
- stake, payout, profit, ROI, recovery rate
- max drawdown and longest losing streak
- average odds and count of anaba picks at 30x or higher
- EV threshold used, usually `EV_THRESHOLD = 0.15`
- Kelly cap used, usually `KELLY_FRACTION = 0.10`
- train/test split method and whether it is time-aware

Accuracy alone is not enough. A model can be accurate while destroying bankroll.

## Review Flow

1. Identify the result file or script:
   - `data/backtest_summary_*.json`
   - `data/walkforward_result.json`
   - `pipeline/backtest_engine_32.py`
   - `pipeline/backtest_walkforward_35.py`
   - `pipeline/validation.py`
2. Confirm the test period is after the training period.
3. Confirm odds are used only after prediction, not as features.
4. Compare ROI against bet count. Treat tiny sample wins as unproven.
5. Check drawdown. A positive ROI with intolerable drawdown is not deployable.
6. Report whether the result is:
   - **deployable**: enough bets, positive ROI, controlled drawdown, no leakage
   - **promising**: positive signal but small sample or rough drawdown
   - **not ready**: negative ROI, leakage risk, or unclear split

## Threshold Guidance

- 30x+ picks need patience; judge over enough races, not one day.
- Raising `EV_THRESHOLD` may reduce bets and improve selectivity.
- Lowering `EV_THRESHOLD` may increase action but can dilute edge.
- Kelly should stay capped unless a long OOS test justifies change.

## Verification Commands

Prefer the smallest relevant command:

```bash
python3 tools/verify_integrity.py
python3 run_all.py --source-sanity
python3 canary_run.py
python3 run_all.py --v2-weekly
```

Use `--v2-weekly` only when retraining/backtesting cost is acceptable.
