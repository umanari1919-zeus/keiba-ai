"""
うまなり地蔵AI — 共通設定
全パイプラインファイルはここから定数を import すること。
"""
import os

# ── パス ───────────────────────────────────────────────
BASE_DIR  = "D:\\keiba_ai"
DATA_DIR  = os.path.join(BASE_DIR, "data")
PIPELINE_DIR = os.path.join(BASE_DIR, "pipeline")

# JV-Link 同期ツール
MYKEIBADB_EXE = r"C:\Users\uchih\Downloads\mykeibadb_v3.63\mykeibadb.exe"
MYKEIBADB_DIR = os.path.dirname(MYKEIBADB_EXE)

# ── データベース ────────────────────────────────────────
DB_URL = "postgresql://postgres:trust@localhost:5433/mykeibadb"
DB_CONFIG = dict(
    host="127.0.0.1",
    port=5433,
    dbname="mykeibadb",
    user="postgres",
    options="-c client_encoding=UTF8",
)

# ── モデル閾値 ─────────────────────────────────────────
# 本番予測・EV分析用
EV_THRESHOLD     = 0.15   # 期待値閾値（15%以上）
MIN_ODDS         = 10.0   # 最低オッズ（10倍以上）
MIN_ODDS_RAW     = 100    # tansho_odds は x10 格納形式（10倍 = 100）
ANABA_ODDS_RAW   = 300    # 穴馬定義（30倍 = 300）
KELLY_FRACTION   = 0.10   # Kelly 基準の分数（1/10 Kelly）

# レースタイプ別 EV 閾値
EV_THRESHOLDS_BY_TYPE = {
    "debut":    0.10,   # 新馬戦
    "shogai":   0.10,   # 障害戦
    "handicap": 0.20,   # ハンデ戦
    "default":  0.15,
}

# バックテスト用（保守的な閾値）
EV_THRESHOLD_BACKTEST = 0.05
MIN_ODDS_BACKTEST     = 5.0

# ── CSV ファイル ────────────────────────────────────────
CSV_RAW       = os.path.join(BASE_DIR, "keiba_data.csv")
CSV_FEATURES  = os.path.join(BASE_DIR, "keiba_data_features.csv")

# keiba_data_features.csv 339766行目が破損 → 必ず on_bad_lines='skip' を使用
CSV_READ_OPTS = dict(encoding="utf-8-sig", low_memory=False, on_bad_lines="skip")
