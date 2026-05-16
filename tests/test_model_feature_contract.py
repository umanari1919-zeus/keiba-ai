"""モデル特徴量のリーク境界テスト。"""

from __future__ import annotations

import pandas as pd


def test_detect_features_excludes_current_total_result_aggregates():
    from pipeline.model_train_03 import _detect_features

    df = pd.DataFrame({
        "barei": [3],
        "kyori": [1200],
        "sogo_1chaku": [9],
        "sogo_win_rate": [0.5],
        "shiba_ryo_1chaku": [4],
        "dirt_win_rate": [0.2],
        "kakutei_chakujun": [1],
        "tansho_odds": [2379],
    })

    features = _detect_features(df)

    assert "barei" in features
    assert "kyori" in features
    assert "sogo_1chaku" not in features
    assert "sogo_win_rate" not in features
    assert "shiba_ryo_1chaku" not in features
    assert "dirt_win_rate" not in features
    assert "kakutei_chakujun" not in features
    assert "tansho_odds" not in features


def test_model_train_has_writable_model_path_constant():
    from pipeline.model_train_03 import MODEL_PATH

    assert str(MODEL_PATH).endswith("model_v8.pkl")


def test_predict_rejects_saved_model_features_with_leaky_columns():
    from pipeline.predict_04 import _prepare_model_input

    df = pd.DataFrame({
        "barei": [3],
        "kyori": [1200],
        "tansho_odds": [2379],
    })

    try:
        _prepare_model_input(df, ["barei", "tansho_odds", "kyori"])
    except ValueError as exc:
        assert "tansho_odds" in str(exc)
    else:
        raise AssertionError("leaky saved model feature was accepted")


def test_predict_model_input_uses_exact_saved_feature_order_and_fills_missing():
    from pipeline.predict_04 import _prepare_model_input

    df = pd.DataFrame({
        "kyori": [1200],
        "barei": ["3"],
        "unused_extra": [999],
    })

    X = _prepare_model_input(df, ["barei", "missing_speed", "kyori"])

    assert list(X.columns) == ["barei", "missing_speed", "kyori"]
    assert X.loc[0, "barei"] == 3
    assert X.loc[0, "missing_speed"] == 0
    assert X.loc[0, "kyori"] == 1200
