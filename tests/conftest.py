"""
pytest 共通設定ファイル

役割:
- sys.path にプロジェクトルートを追加（import を通すため）
- DB モック用フィクスチャを提供（本物の DB なしでテスト可能）
- config パスが Windows 絶対パスに依存しないようにする
"""
import sys
import pathlib
from unittest.mock import MagicMock, patch

import pytest

# プロジェクトルート（このファイルの 1 つ上）を sys.path に追加
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# D:\keiba_ai 本体も追加（pipeline.config などのインポート用）
_MAIN = pathlib.Path(r"D:\keiba_ai")
if _MAIN.exists() and str(_MAIN) not in sys.path:
    sys.path.insert(0, str(_MAIN))


@pytest.fixture
def mock_psycopg2_connect():
    """DB 接続をモックにする。実際の PostgreSQL なしでテスト可能。"""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur

    with patch("psycopg2.connect", return_value=mock_conn) as mock:
        yield mock, mock_conn, mock_cur


@pytest.fixture
def tmp_base_dir(tmp_path, monkeypatch):
    """
    一時ディレクトリを BASE_DIR として使う。
    D:\\keiba_ai への絶対パス依存を排除したいテストで使用。
    """
    monkeypatch.setenv("KEIBA_BASE", str(tmp_path))
    return tmp_path


@pytest.fixture
def sample_model_pkl(tmp_path):
    """テスト用の最小限 model_v8.pkl を生成する。"""
    import pickle
    model_path = tmp_path / "model_v8.pkl"
    dummy = {
        "lgb_model": None,
        "xgb_model": None,
        "cb_model": None,
        "le": None,
        "features": ["feature_a", "feature_b"],
        "ensemble_weights": [0.5, 0.3, 0.2],
        "metrics": {"ensemble_acc": 0.55, "ensemble_logloss": 1.0},
    }
    with open(model_path, "wb") as f:
        pickle.dump(dummy, f)
    return model_path
