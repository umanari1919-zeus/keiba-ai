"""tools/leak_audit.py のユニットテスト。"""

from __future__ import annotations

import pickle


def test_audit_odds_leak_initializes_native_runtime_before_unpickle(tmp_path, monkeypatch):
    model_path = tmp_path / "model_v8.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"features": ["speed_index"], "metrics": {}}, f)

    import tools.leak_audit as leak_audit

    calls: list[str] = []

    monkeypatch.setattr(leak_audit, "BASE_DIR", tmp_path)
    monkeypatch.setattr(leak_audit, "ensure_native_runtime", lambda: calls.append("native"))

    result = leak_audit.audit_odds_leak(None)

    assert calls == ["native"]
    assert result["verdict"] == "SHALLOW_OK"


def test_audit_odds_leak_flags_odds_named_model_features(tmp_path, monkeypatch):
    model_path = tmp_path / "model_v8.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"features": ["speed_index", "prev_odds"], "metrics": {}}, f)

    import tools.leak_audit as leak_audit

    monkeypatch.setattr(leak_audit, "BASE_DIR", tmp_path)
    monkeypatch.setattr(leak_audit, "ensure_native_runtime", lambda: [])

    result = leak_audit.audit_odds_leak(None)

    assert result["verdict"] == "LEAK"
    assert result["suspicious_features"] == ["prev_odds"]


def test_audit_odds_leak_flags_current_result_aggregate_features(tmp_path, monkeypatch):
    model_path = tmp_path / "model_v8.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"features": ["speed_index", "sogo_1chaku"], "metrics": {}}, f)

    import tools.leak_audit as leak_audit

    monkeypatch.setattr(leak_audit, "BASE_DIR", tmp_path)
    monkeypatch.setattr(leak_audit, "ensure_native_runtime", lambda: [])

    result = leak_audit.audit_odds_leak(None)

    assert result["verdict"] == "SUSPICIOUS_RETRAIN_REQUIRED"
    assert result["result_aggregate_features"] == ["sogo_1chaku"]
