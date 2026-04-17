# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**うまなり地蔵AI** — An automated horse racing (競馬) prediction system that identifies high-odds long-shot horses (30x+ odds) using an ensemble ML model, then posts predictions to X (Twitter) and note.com.

## Running the Pipeline

```bash
# Full pipeline (all 6 stages)
python run_all.py

# Continuous scheduler (runs pipeline Sat/Sun at 08:00, posts to X at 09:00)
python scheduler.py

# Individual stages
python pipeline/data_fetch_01.py       # Fetch raw data from PostgreSQL → keiba_data.csv
python pipeline/feature_eng_02.py     # Engineer 60+ features → keiba_data_features.csv
python pipeline/model_train_03.py     # Train ensemble → model_v8.pkl
python pipeline/predict_04.py         # Generate predictions → simulation_2025.csv
python pipeline/validation.py         # Walk-forward validation (2023–2025)
python pipeline/analysis.py           # Performance breakdown by segment

# Test database connection
python test_connection.py
```

No automated test suite (pytest/unittest) exists.

## Architecture

### 6-Stage Pipeline

```
PostgreSQL (localhost:5433/mykeibadb)
  └─ data_fetch_01.py      → keiba_data.csv (137 MB, ~450k races, 1954–present)
  └─ feature_eng_02.py     → keiba_data_features.csv (228 MB)
  └─ model_train_03.py     → model_v8.pkl (85 MB ensemble)
  └─ predict_04.py         → simulation_2025.csv (current-year predictions)
  └─ post_x_05.py          → X (Twitter) post
  └─ claude_comment_06.py  → AI commentary in "うまなり地蔵" persona
  └─ note_07.py            → note.com monthly report markdown
  └─ notify_08.py          → Gmail summary email
```

### Ensemble Model (model_v8.pkl)

- LightGBM 50% + XGBoost 30% + CatBoost 20% weighted vote
- **Deliberately excludes odds/popularity from features** to avoid data leakage; odds are used only as a post-prediction filter (≥30x)
- Rolling averages use `shift(1)` to prevent look-ahead bias
- ~60+ features: pedigree codes, jockey/trainer win rates, track/distance/ground conditions, weight changes, training times, cross-features

### Database Tables

| Table | Contents |
|-------|----------|
| `umagoto_race_joho` | Race entries and results |
| `race_shosai` | Race details (distance, track, weather, ground) |
| `kyosoba_master2` | Horse genealogy, per-horse performance by track/distance/ground |
| `hanro_chokyo` | Training times |
| `odds1_fukusho` … `odds5_sanrenpuku` | Ticket-type odds |

## Environment Variables (`.env`)

```
# X (Twitter) API — optional, falls back to printing post text
X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

# Gmail notifications
GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NOTIFY_TO
```

## Key Dependencies

pandas, numpy, sqlalchemy, psycopg2, lightgbm, xgboost, catboost, scikit-learn, tweepy, schedule, python-dotenv

No `requirements.txt` exists; dependencies must be installed manually.

## Deprecated / Archived Files

- `model_v2.py`, `model_v2.pkl`–`model_v7.pkl` — superseded by `model_v8.pkl`
- `feature_engineering.py` — superseded by `pipeline/feature_eng_02.py`
- `test_connection.py` — diagnostic only, uses RandomForest (not production)
