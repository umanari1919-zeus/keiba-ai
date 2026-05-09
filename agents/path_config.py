"""
path_config.py — agents 用パス設定
=================================
pipeline.config のパス定義を Path オブジェクトで再公開する。
"""

from __future__ import annotations

from pathlib import Path

from pipeline.config import BASE_DIR as CONFIG_BASE_DIR
from pipeline.config import DATA_DIR as CONFIG_DATA_DIR
from pipeline.config import PIPELINE_DIR as CONFIG_PIPELINE_DIR

BASE_DIR = Path(CONFIG_BASE_DIR)
DATA_DIR = Path(CONFIG_DATA_DIR)
PIPELINE_DIR = Path(CONFIG_PIPELINE_DIR)

DATA_DIR.mkdir(parents=True, exist_ok=True)
