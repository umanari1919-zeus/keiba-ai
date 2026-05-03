"""
うまなり地蔵AI — パイプライン smoke test
各モジュールの import・DB接続・主要関数を素早くチェック。
python smoke_test.py
"""
import sys, os, traceback
sys.path.insert(0, "D:\\keiba_ai")
os.chdir("D:\\keiba_ai")

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results = []

def test(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f"  [PASS] {name}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  [FAIL] {name}: {e}")
        traceback.print_exc()

# ── DB 接続 ───────────────────────────────────────────────────────
print("\n=== DB接続 ===")

def _db_connect():
    import psycopg2
    from pipeline.config import DB_CONFIG
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM umagoto_race_joho LIMIT 1")
            n = cur.fetchone()[0]
    assert n > 0, "umagoto_race_joho が空"
test("DB接続・umagoto_race_joho", _db_connect)

def _db_tables():
    import psycopg2
    from pipeline.config import DB_CONFIG
    required = ["umagoto_race_joho","race_shosai","kyosoba_master2",
                "hanro_chokyo","woodchip_chokyo","kaisaibi","kishu_master"]
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
            """)
            existing = {r[0] for r in cur.fetchall()}
    missing = [t for t in required if t not in existing]
    assert not missing, f"テーブルなし: {missing}"
test("必須テーブル存在確認", _db_tables)

# ── config ────────────────────────────────────────────────────────
print("\n=== config.py ===")

def _config():
    from pipeline.config import (
        BASE_DIR, DATA_DIR, DB_URL, DB_CONFIG,
        EV_THRESHOLD, KELLY_FRACTION, MIN_ODDS,
        CSV_RAW, CSV_FEATURES,
    )
    assert os.path.isdir(BASE_DIR), f"BASE_DIR not found: {BASE_DIR}"
    assert os.path.isdir(DATA_DIR), f"DATA_DIR not found: {DATA_DIR}"
    assert EV_THRESHOLD == 0.15
    assert KELLY_FRACTION == 0.10
test("config.py インポート", _config)

# ── 主要パイプラインモジュール import ────────────────────────────
print("\n=== モジュール import ===")

modules = {
    "data_fetch_01": "fetch_data",
    "feature_eng_02": "feature_engineering",
    "model_train_03": "train_model",
    "predict_04": "predict_today",
    "ev_engine_10": "run_ev_analysis",
    "portfolio_opt_11": "run_portfolio_optimization",
    "shutsuba_fetch": "save_today_entries",
    "anomaly_detect_16": "run_anomaly_detection",
    "knowledge_curator_41": "run_knowledge_curator",
}

for mod, fn in modules.items():
    def _check(m=mod, f=fn):
        import importlib
        module = importlib.import_module(f"pipeline.{m}")
        assert hasattr(module, f), f"{m} に {f} がない"
    test(f"import pipeline.{mod}", _check)

# ── shutsuba_fetch 各 DB 関数 ────────────────────────────────────
print("\n=== shutsuba_fetch DB 関数 ===")

def _shutsuba_master():
    from pipeline.shutsuba_fetch import _build_master_features
    df = _build_master_features()
    assert len(df) > 0, "kyosoba_master2 が空"
test("_build_master_features", _shutsuba_master)

def _shutsuba_history():
    from pipeline.shutsuba_fetch import _build_horse_history
    df = _build_horse_history()
    assert len(df) > 0, "horse_history が空"
test("_build_horse_history", _shutsuba_history)

def _shutsuba_kishu():
    from pipeline.shutsuba_fetch import _build_kishu_features
    df = _build_kishu_features()
    assert len(df) > 0, "kishu_features が空"
test("_build_kishu_features (PyArrow 正規表現修正確認)", _shutsuba_kishu)

def _shutsuba_prev():
    from pipeline.shutsuba_fetch import _build_prev_race_features
    df = _build_prev_race_features()
    assert len(df) >= 0  # 空でも OK
test("_build_prev_race_features (grade_code修正確認)", _shutsuba_prev)

# ── pace_training 調教クエリ ──────────────────────────────────────
print("\n=== pace_training_analysis_20 ===")

def _wood_query():
    from pipeline.pace_training_analysis_20 import build_training_features
    df = build_training_features(year_from=2024)
    # エラーなく完了すれば OK（空 DataFrame でも）
test("build_training_features (woodchip列名修正確認)", _wood_query)

# ── モデルファイル ────────────────────────────────────────────────
print("\n=== モデルファイル ===")

def _model_exists():
    import glob
    pkls = glob.glob("D:\\keiba_ai\\model_v*.pkl")
    assert pkls, "model_v*.pkl が見つからない"
    latest = sorted(pkls)[-1]
    import pickle
    with open(latest, "rb") as f:
        model = pickle.load(f)
    assert model is not None
test("最新モデル (.pkl) ロード", _model_exists)

def _nn_exists():
    import os
    assert os.path.exists("D:\\keiba_ai\\model_nn.pth"), "model_nn.pth なし"
test("NN モデル (.pth) 存在確認", _nn_exists)

# ── CSV ファイル ──────────────────────────────────────────────────
print("\n=== CSV ファイル ===")

def _csv_raw():
    import pandas as pd
    from pipeline.config import CSV_RAW, CSV_READ_OPTS
    df = pd.read_csv(CSV_RAW, **CSV_READ_OPTS, nrows=100)
    assert len(df) > 0
test("keiba_data.csv 先頭100行読み込み", _csv_raw)

def _csv_features():
    import pandas as pd
    from pipeline.config import CSV_FEATURES, CSV_READ_OPTS
    df = pd.read_csv(CSV_FEATURES, **CSV_READ_OPTS, nrows=100)
    assert len(df) > 0
    required_cols = ["race_code","ketto_toroku_bango","kakutei_chakujun","tansho_odds"]
    missing = [c for c in required_cols if c not in df.columns]
    assert not missing, f"必須列なし: {missing}"
test("keiba_data_features.csv 先頭100行読み込み", _csv_features)

# ── 結果サマリー ─────────────────────────────────────────────────
print("\n" + "="*60)
n_pass = sum(1 for r in results if r[0] == PASS)
n_fail = sum(1 for r in results if r[0] == FAIL)
print(f"PASS: {n_pass}  FAIL: {n_fail}  合計: {len(results)}")
if n_fail:
    print("\n失敗一覧:")
    for r in results:
        if r[0] == FAIL:
            print(f"  [FAIL] {r[1]}: {r[2]}")
print("="*60)
sys.exit(0 if n_fail == 0 else 1)
