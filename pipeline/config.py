"""
うまなり地蔵AI — 共通設定
全パイプラインファイルはここから定数を import すること。
"""
import os
import pathlib
from urllib.parse import parse_qsl, unquote, urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")


def _normalize_path(path_value: str) -> str:
    """Windows パスを WSL/POSIX 上でも扱える表記に寄せる。"""
    if os.name != "nt" and len(path_value) >= 3 and path_value[1:3] in (":\\", ":/"):
        drive = path_value[0].lower()
        tail = path_value[3:].replace("\\", "/")
        return f"/mnt/{drive}/{tail}"
    return path_value


def _default_mykeibadb_exe() -> str:
    if os.name == "nt":
        return str(pathlib.Path.home() / "Downloads" / "mykeibadb_v3.63" / "mykeibadb.exe")
    windows_user = os.getenv("WINDOWS_USER") or os.getenv("USER") or "uchih"
    return str(pathlib.Path("/mnt/c/Users") / windows_user / "Downloads" / "mykeibadb_v3.63" / "mykeibadb.exe")


# ── パス ───────────────────────────────────────────────
BASE_DIR  = os.getenv("KEIBA_BASE", str(pathlib.Path(__file__).resolve().parent.parent))
DATA_DIR  = os.path.join(BASE_DIR, "data")
PIPELINE_DIR = os.path.join(BASE_DIR, "pipeline")

# JV-Link 同期ツール
MYKEIBADB_EXE = _normalize_path(
    os.getenv("MYKEIBADB_EXE", _default_mykeibadb_exe())
)
MYKEIBADB_DIR = os.path.dirname(MYKEIBADB_EXE)

# ── データベース ────────────────────────────────────────
DB_URL = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")


def _db_config_from_url(db_url: str) -> dict:
    """KEIBA_DB_URL と psycopg2 の dict 設定を常に同期させる。"""
    config = dict(
        host="127.0.0.1",
        port=5433,
        dbname="mykeibadb",
        user="postgres",
        options="-c client_encoding=UTF8",
    )
    parsed = urlparse(db_url)
    if parsed.hostname:
        config["host"] = parsed.hostname
    try:
        if parsed.port:
            config["port"] = parsed.port
    except ValueError:
        pass
    if parsed.path and parsed.path != "/":
        config["dbname"] = unquote(parsed.path.lstrip("/"))
    if parsed.username:
        config["user"] = unquote(parsed.username)
    if parsed.password:
        config["password"] = unquote(parsed.password)

    # sslmode や connect_timeout などの libpq パラメータも URL 側で上書きできる。
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if value != "":
            config[key] = value
    return config


DB_CONFIG = _db_config_from_url(DB_URL)

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

# ── モデルファイル ─────────────────────────────────────
MODEL_PATH    = os.path.join(BASE_DIR, "model_v8.pkl")
MODEL_NN_PATH = os.path.join(BASE_DIR, "model_nn.pth")

# ── CSV ファイル ────────────────────────────────────────
CSV_RAW       = os.path.join(BASE_DIR, "keiba_data.csv")
CSV_FEATURES  = os.path.join(BASE_DIR, "keiba_data_features.csv")
PEDIGREE_OUTPUT_DIR = pathlib.Path(BASE_DIR) / "pedigree_output"

# keiba_data_features.csv 339766行目が破損 → 必ず on_bad_lines='skip' を使用
CSV_READ_OPTS = dict(encoding="utf-8-sig", low_memory=False, on_bad_lines="skip")

# オッズ・人気の派生列は学習特徴量として使用しない（raw odds/ninki はEV評価用に限る）
LEAKY_DERIVED_FEATURE_COLUMNS = (
    "prev_odds",
    "past3_avg_odds",
    "ema3_odds",
    "ema5_odds",
    "ema10_odds",
)

# 学習・推論のモデル入力に入れてはいけない列。
# オッズ・人気はEV評価以降でのみ使用し、結果列や現在時点通算成績はリーク疑いとして除外する。
MODEL_FORBIDDEN_FEATURE_COLUMNS = (
    "kakutei_chakujun",
    "tansho_odds",
    "tansho_ninkijun",
    "bamei",
    "kishumei_ryakusho",
    "chichi",
    "haha",
    "chichi_chichi",
    "haha_chichi",
    "race_date",
    "prev_race_date",
    "race_code",
    "ketto_toroku_bango",
    "kaisai_gappi",
    "win_probability",
    "expected_value",
    "odds_decimal",
    "pred_chakujun",
    "hit",
    "ev",
    "pred_rank",
    "bankroll_after",
    *LEAKY_DERIVED_FEATURE_COLUMNS,
    # kyosoba_master2 の現在時点通算成績は、対象レース以後の結果を含む可能性がある。
    "sogo_1chaku",
    "sogo_2chaku",
    "sogo_3chaku",
    "sogo_total",
    "sogo_win_rate",
    "shiba_ryo_1chaku",
    "shiba_ryo_2chaku",
    "shiba_ryo_3chaku",
    "dirt_ryo_1chaku",
    "dirt_ryo_2chaku",
    "dirt_ryo_3chaku",
    "shiba_short_1chaku",
    "shiba_middle_1chaku",
    "shiba_long_1chaku",
    "dirt_short_1chaku",
    "dirt_middle_1chaku",
    "dirt_long_1chaku",
    "shiba_win_rate",
    "dirt_win_rate",
    "short_win_rate",
    "middle_win_rate",
    "long_win_rate",
)


# =================================================================
# オッズ控除率（ブックメーカー控除 = JRA公式控除率）
# =================================================================
# 出典: JRA公式 「買い目シミュレーション」控除率一覧
# https://www.jra.go.jp/dento/dentosyou/
# 2014年以降の現行控除率
#
# これを EV 計算とバックテストに必ず適用して、「控除前オッズ」で
# 計算したバックテスト ROI の過大評価を防ぐ。
TAKEOUT_RATES = {
    "tansho": 0.20,        # 単勝
    "fukusho": 0.20,       # 複勝
    "wakuren": 0.225,      # 枠連
    "umaren": 0.225,       # 馬連
    "wide": 0.225,         # ワイド
    "umatan": 0.25,        # 馬単
    "sanrenpuku": 0.275,   # 三連複
    "sanrentan": 0.275,    # 三連単
    "win5": 0.30,          # WIN5
}


def get_takeout_rate(ticket_type: str) -> float:
    """馬券種別控除率を返す。未知の種別は保守的に 0.275 を返す。"""
    return TAKEOUT_RATES.get(ticket_type.lower(), 0.275)
