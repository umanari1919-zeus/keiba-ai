---
name: keiba-leakage-audit
description: Use when reviewing feature engineering, training, prediction, backtesting, model inputs, CSV schemas, or any code that could accidentally use odds, popularity, results, payouts, or future information in the keiba_ai project.
---

# Keiba Leakage Audit

## Overview

This skill protects prediction integrity. In this project, odds and popularity are allowed after prediction for EV and bankroll decisions, but they must not enter model features or training labels except as explicit targets for post-race analysis.

## Red Flags

Audit carefully when code touches:

- feature lists, `features`, `FEATURE_COLUMNS`, model inputs, or dataframe column selection
- `pipeline/feature_eng_02.py`, `pipeline/feature_advanced_19.py`, training, prediction, or validation scripts
- backtests that mix current odds, final odds, payouts, rank/popularity, or results with pre-race features
- joins against race results, payout tables, or odds snapshots
- cached CSVs such as `keiba_data_features.csv`

Never assume a column is safe because the script name sounds pre-race.

## Forbidden Model Features

Do not include these or close variants in training/prediction features:

- odds: `odds`, `tansho_odds`, `fukusho_odds`, `final_odds`, `win_odds`
- popularity: `ninki`, `popular`, `rank_popularity`, `fav_rank`
- result leakage: `chakujun`, `kakutei`, `result`, `pay`, `haito`, `refund`, `return`
- race outcome aggregates that include the current race result
- future data relative to the race start time

Japanese column variants require the same care: `単勝`, `複勝`, `人気`, `着順`, `払戻`, `確定`, `配当`.

## Allowed Post-Prediction Uses

Odds may be used after model probabilities are produced:

- EV calculation and filtering
- Kelly sizing and bankroll limits
- ticket optimization
- race value ranking
- morning report display
- X/note explanation, as long as it is not fed back as a feature

The boundary is simple: `predict_proba` inputs must be pre-race non-odds features; downstream betting logic may use odds.

## Audit Workflow

1. Locate feature construction and model input columns:
   - `rg -n "features|FEATURE|predict_proba|fit\\(|drop\\(|select_dtypes|tansho|odds|ninki|人気|着順|払戻" pipeline agents tests`
2. Trace dataframe lineage into `model.fit`, `predict_proba`, validation, and backtest scoring.
3. Check joins for timing. A join from result tables is only safe if it uses historical rows strictly before the target race.
4. Verify constants come from `pipeline/config.py` when thresholds are part of business logic.
5. Run the narrowest relevant verification, usually:
   - `python3 tools/verify_integrity.py`
   - `python3 run_all.py --source-sanity`
   - `python3 canary_run.py` for broad behavioral changes

## Reporting

When reporting an audit, separate:

- **Blocking leakage**: model can see odds, popularity, payouts, current result, or future information.
- **Suspicious but unproven**: unclear join timing, ambiguous column name, or cached artifact risk.
- **Allowed downstream use**: odds appear only after prediction.

Include file and line references for any finding. If no leakage is found, still mention which model input path was checked.
