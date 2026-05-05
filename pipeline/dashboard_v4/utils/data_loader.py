"""
Cached data loading utilities for Dashboard v4
Uses Streamlit caching with TTL to minimize file I/O
"""
import os
import json
import glob
import pandas as pd
import streamlit as st
from datetime import datetime
from .constants import BASE_PATH


def _jload(path: str) -> dict | list | None:
    """Load JSON file."""
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _csv(path: str, **kwargs) -> pd.DataFrame:
    """Load CSV file with standard options."""
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, encoding='utf-8-sig', on_bad_lines='skip', **kwargs)


@st.cache_data(ttl=300)
def load_bankroll() -> dict:
    """Load bankroll state from JSON."""
    d = _jload(os.path.join(BASE_PATH, "data", "bankroll.json")) or {}
    return {
        'current': d.get('bankroll', d.get('current', 100000)),
        'initial': d.get('initial', 100000),
        'peak': d.get('peak', 100000),
        'history': d.get('history', [])
    }


@st.cache_data(ttl=300)
def load_roi_tracker() -> pd.DataFrame:
    """Load ROI tracking CSV."""
    df = _csv(os.path.join(BASE_PATH, "data", "roi_tracker.csv"))
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df


@st.cache_data(ttl=60)
def load_picks() -> tuple[dict | None, str]:
    """Load latest agent_picks JSON."""
    files = sorted(glob.glob(os.path.join(BASE_PATH, "agent_picks_*.json")), reverse=True)
    if not files:
        return None, None
    base = os.path.basename(files[0])
    yyyymmdd = base.replace("agent_picks_", "").replace(".json", "")
    picks_date = f"{yyyymmdd[:4]}/{yyyymmdd[4:6]}/{yyyymmdd[6:8]}" if len(yyyymmdd) == 8 else yyyymmdd
    return _jload(files[0]), picks_date


@st.cache_data(ttl=300)
def load_race_ranking() -> pd.DataFrame:
    """Load race ranking CSV."""
    year = datetime.now().year
    return _csv(os.path.join(BASE_PATH, "data", f"race_ranking_{year}.csv"))


@st.cache_data(ttl=300)
def load_ticket_recommendations() -> pd.DataFrame:
    """Load ticket recommendations JSON."""
    year = datetime.now().year
    d = _jload(os.path.join(BASE_PATH, "data", f"ticket_recommendations_{year}.json"))
    return pd.DataFrame(d) if d else pd.DataFrame()


@st.cache_data(ttl=300)
def load_walkforward() -> dict | None:
    """Load walkforward validation results."""
    return _jload(os.path.join(BASE_PATH, "data", "walkforward_result.json"))


@st.cache_data(ttl=300)
def load_walkforward_folds() -> pd.DataFrame:
    """Load walkforward folds CSV."""
    return _csv(os.path.join(BASE_PATH, "data", "walkforward_folds.csv"))


@st.cache_data(ttl=300)
def load_backtest_grid() -> pd.DataFrame:
    """Load backtest grid search results."""
    year = datetime.now().year
    return _csv(os.path.join(BASE_PATH, "data", f"backtest_grid_{year}.csv"))


@st.cache_data(ttl=300)
def load_condition_roi() -> pd.DataFrame:
    """Load condition-adjusted ROI results."""
    year = datetime.now().year
    return _csv(os.path.join(BASE_PATH, "data", f"condition_roi_{year}.csv"))


@st.cache_data(ttl=600)
def load_monte_carlo() -> dict | None:
    """Load Monte Carlo simulation results."""
    return _jload(os.path.join(BASE_PATH, "data", "monte_carlo_result.json"))


@st.cache_data(ttl=600)
def load_bankroll_simulation() -> dict | None:
    """Load bankroll simulation results."""
    return _jload(os.path.join(BASE_PATH, "data", "bankroll_simulation.json"))


@st.cache_data(ttl=300)
def load_model_performance() -> list:
    """Load model performance history."""
    d = _jload(os.path.join(BASE_PATH, "data", "model_performance.json"))
    return d if d else []


@st.cache_data(ttl=600)
def load_pedigree_nicks() -> pd.DataFrame:
    """Load top pedigree nicks analysis."""
    return _csv(os.path.join(BASE_PATH, "pedigree_output", "nicks_roi_top.csv"))


@st.cache_data(ttl=600)
def load_pedigree_nicks_all() -> pd.DataFrame:
    """Load all pedigree nicks analysis."""
    return _csv(os.path.join(BASE_PATH, "pedigree_output", "nicks_all.csv"))


@st.cache_data(ttl=120)
def load_canary_report() -> dict | None:
    """Load latest canary test report."""
    files = sorted(glob.glob(os.path.join(BASE_PATH, "logs", "canary_report_*.json")), reverse=True)
    if not files:
        return None
    return _jload(files[0])


@st.cache_data(ttl=120)
def load_model_registry() -> list:
    """Load model registry."""
    d = _jload(os.path.join(BASE_PATH, "data", "model_registry.json"))
    if d and isinstance(d, list):
        return d
    if d and isinstance(d, dict):
        return list(d.values())
    return []


@st.cache_data(ttl=600)
def load_shap_summary() -> pd.DataFrame:
    """Load SHAP feature importance summary."""
    return _csv(os.path.join(BASE_PATH, "data", "shap_summary.csv"))


@st.cache_data(ttl=600)
def load_knowledge_base() -> pd.DataFrame:
    """Load knowledge base insights."""
    d = _jload(os.path.join(BASE_PATH, "data", "knowledge_base", "ev_boost_map.json")) or {}
    if not d:
        return pd.DataFrame()
    rows = []
    for key, val in d.items():
        if isinstance(val, dict):
            rows.append({
                'insight': key,
                'category': val.get('category', 'General'),
                'confidence': val.get('confidence', 0.5),
                'last_updated': val.get('last_updated', ''),
                'frequency': val.get('frequency', 0)
            })
    return pd.DataFrame(rows)


def load_odds_snapshot() -> dict | None:
    """Load latest odds snapshot (no cache for real-time data)."""
    files = sorted(glob.glob(os.path.join(BASE_PATH, "data", "odds_snapshot_*.json")), reverse=True)
    if not files:
        return None
    return _jload(files[0])


def clear_all_cache():
    """Clear all dashboard data cache."""
    st.cache_data.clear()
