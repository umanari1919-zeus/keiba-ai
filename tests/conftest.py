"""
conftest.py — うまなり地蔵AI テスト共通フィクスチャ
=================================================
Codex が生成する全テストファイルはここの fixture を import して使う。

使い方:
  pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# プロジェクトルートを PATH に追加
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ================================================================== #
#  環境変数: テスト時は DB 接続しない
# ================================================================== #

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """全テストで DB 接続・ファイル書き出しを隔離する。"""
    monkeypatch.setenv("KEIBA_DB_URL", "postgresql://test:test@localhost:5433/testdb")
    monkeypatch.setenv("KEIBA_BASE", str(tmp_path))
    audit_dir = tmp_path / "data" / "audit_logs"
    audit_dir.mkdir(parents=True, exist_ok=True)


# ================================================================== #
#  DB モック
# ================================================================== #

class FakeCursor:
    """psycopg2 カーソルのスタブ。"""
    description = [("col",)]
    rowcount = 0

    def __init__(self):
        self._rows: list = []

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeConnection:
    """psycopg2 コネクションのスタブ。"""
    def __init__(self):
        self._cursor = FakeCursor()

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture()
def fake_db_conn():
    """FakeConnection を返す。テスト内でカーソルの _rows を書き換えて応答を制御できる。"""
    return FakeConnection()


@pytest.fixture()
def mock_psycopg2(fake_db_conn):
    """psycopg2.connect をモックし、fake_db_conn を返す。"""
    with patch("psycopg2.connect", return_value=fake_db_conn):
        yield fake_db_conn


# ================================================================== #
#  AgentMeta ファクトリ
# ================================================================== #

@pytest.fixture()
def agent_meta():
    """再現性のある AgentMeta を返す。"""
    from agents.base_agent import AgentMeta

    return AgentMeta(
        trace_id="test-trace-00000000-0000-0000-0000-000000000001",
        run_tag="test_run_20260508",
        data_snapshot_id="snap_test_001",
    )


@pytest.fixture()
def agent_meta_factory():
    """呼ぶたびに新しい AgentMeta を返すファクトリ。"""
    from agents.base_agent import AgentMeta

    def _make(**overrides):
        defaults = dict(
            trace_id=str(uuid.uuid4()),
            run_tag=f"test_run_{uuid.uuid4().hex[:8]}",
            data_snapshot_id="snap_test",
        )
        defaults.update(overrides)
        return AgentMeta(**defaults)
    return _make


# ================================================================== #
#  ダミーエージェント（BaseAgent テスト用）
# ================================================================== #

@pytest.fixture()
def DummyAgent():
    """BaseAgent を継承した最小限の具象エージェント。"""
    from agents.base_agent import BaseAgent

    class _DummyAgent(BaseAgent):
        agent_id = "test-dummy"
        agent_version = "0.1.0"

        def __init__(self, *, return_value=None, raise_error=None, **kwargs):
            super().__init__(**kwargs)
            self._return_value = return_value or {"status": "ok"}
            self._raise_error = raise_error

        def _run(self, meta, payload):
            if self._raise_error:
                raise self._raise_error
            return self._return_value

    return _DummyAgent


# ================================================================== #
#  サンプルデータ
# ================================================================== #

@pytest.fixture()
def sample_predictions():
    """BatchInferenceAgent / TradingAgent / EV計算で使える予測リスト。"""
    return [
        {
            "race_id": "202509050811",
            "entry_id": "3",
            "win_prob": 0.12,
            "place_prob": 0.25,
            "expected_return": 0.18,
            "uncertainty": 0.30,
            "odds": 15.0,
            "model_agreement_count": 3,
        },
        {
            "race_id": "202509050811",
            "entry_id": "7",
            "win_prob": 0.08,
            "place_prob": 0.18,
            "expected_return": 0.22,
            "uncertainty": 0.35,
            "odds": 32.0,
            "model_agreement_count": 2,
        },
        {
            "race_id": "202509050812",
            "entry_id": "1",
            "win_prob": 0.05,
            "place_prob": 0.10,
            "expected_return": 0.08,
            "uncertainty": 0.45,
            "odds": 45.0,
            "model_agreement_count": 1,
        },
    ]


@pytest.fixture()
def sample_csv_path(tmp_path):
    """最小限の keiba_data_features.csv を生成して Path を返す。"""
    csv_content = (
        "race_code,horse_num,horse_name,tansho_odds,ninki,chakujun,"
        "kishu_win_rate,chokyoshi_win_rate,past3_avg_chakujun\n"
        "202509050811,3,テスト馬A,150,5,1,0.15,0.12,3.2\n"
        "202509050811,7,テスト馬B,320,10,3,0.08,0.09,5.1\n"
        "202509050812,1,テスト馬C,450,12,5,0.06,0.07,7.3\n"
    )
    p = tmp_path / "keiba_data_features.csv"
    p.write_text(csv_content, encoding="utf-8")
    return p


@pytest.fixture()
def sample_ev_csv_path(tmp_path):
    """ev_analysis CSV を生成して Path を返す。"""
    csv_content = (
        "race_code,horse_num,win_probability,ev,odds,horse_name,race_type\n"
        "202509050811,3,0.12,0.18,15.0,テスト馬A,default\n"
        "202509050811,7,0.08,0.22,32.0,テスト馬B,default\n"
        "202509050812,1,0.05,0.08,45.0,テスト馬C,debut\n"
    )
    p = tmp_path / "ev_analysis_2025.csv"
    p.write_text(csv_content, encoding="utf-8")
    return p


@pytest.fixture()
def sample_bankroll_json(tmp_path):
    """bankroll.json を生成して Path を返す。"""
    data = {
        "balance": 100000,
        "initial_balance": 100000,
        "peak_balance": 105000,
        "drawdown": 0.0,
        "updated_at": "2025-09-01T00:00:00",
    }
    p = tmp_path / "bankroll.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture()
def sample_model_pkl(tmp_path):
    """ダミーの model_v8.pkl を生成して Path を返す。"""
    import pickle
    model_data = {
        "lgb_model": MagicMock(),
        "xgb_model": MagicMock(),
        "cb_model": MagicMock(),
        "features": ["feat1", "feat2", "feat3"],
        "lgb_acc": 0.65,
        "xgb_acc": 0.63,
        "cb_acc": 0.61,
        "ensemble_acc": 0.67,
        "logloss": 0.55,
        "trained_at": "2025-09-01",
    }
    p = tmp_path / "model_v8.pkl"
    with open(p, "wb") as f:
        pickle.dump(model_data, f)
    return p


# ================================================================== #
#  API テスト用
# ================================================================== #

@pytest.fixture()
def api_client():
    """FastAPI TestClient を返す。DB接続はモック済み。"""
    try:
        from fastapi.testclient import TestClient
        with patch("psycopg2.connect", return_value=FakeConnection()):
            from api.main import app
            with TestClient(app) as client:
                yield client
    except ImportError:
        pytest.skip("fastapi or httpx not installed")


# ================================================================== #
#  pytest マーカー登録
# ================================================================== #

def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (no DB, no network)")
    config.addinivalue_line("markers", "integration: integration tests (may need DB)")
    config.addinivalue_line("markers", "slow: slow tests (>10s)")
