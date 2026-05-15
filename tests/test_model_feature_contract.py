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
