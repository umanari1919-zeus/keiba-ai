import pytest
import pandas as pd
import numpy as np


@pytest.mark.unit
class TestEvEngine:
    def test_calculate_ev_positive(self):
        from pipeline.ev_engine_10 import EV_THRESHOLD, MIN_ODDS
        assert EV_THRESHOLD == 0.15
        assert MIN_ODDS == 10.0

    def test_get_race_type_debut(self):
        from pipeline.ev_engine_10 import _get_race_type
        row = pd.Series({"joken_cd": "005", "race_name": "", "kyoso_joken_cd": ""})
        assert _get_race_type(row) == "debut"

    def test_get_race_type_default(self):
        from pipeline.ev_engine_10 import _get_race_type
        row = pd.Series({"joken_cd": "010", "race_name": "A race", "kyoso_joken_cd": "0"})
        assert _get_race_type(row) == "default"

    def test_apply_ev_boost_no_map(self, monkeypatch):
        from pipeline import ev_engine_10
        monkeypatch.setattr(ev_engine_10, "_ev_boost_cache", {})
        monkeypatch.setattr(ev_engine_10, "_load_ev_boost_map", lambda: {})
        row = pd.Series({"race_code": "20260101010101"})
        result = ev_engine_10._apply_ev_boost(row, 0.20)
        assert result == 0.20

    def test_apply_ev_boost_with_race_code(self, monkeypatch):
        from pipeline import ev_engine_10
        boost = {"20260101010101": 1.5}
        monkeypatch.setattr(ev_engine_10, "_ev_boost_cache", boost)
        monkeypatch.setattr(ev_engine_10, "_load_ev_boost_map", lambda: boost)
        row = pd.Series({"race_code": "20260101010101"})
        result = ev_engine_10._apply_ev_boost(row, 0.20)
        assert abs(result - 0.30) < 1e-9

    def test_ev_thresholds_by_type(self):
        from pipeline.ev_engine_10 import EV_THRESHOLDS_BY_TYPE
        assert EV_THRESHOLDS_BY_TYPE["debut"] == 0.10
        assert EV_THRESHOLDS_BY_TYPE["shogai"] == 0.10
        assert EV_THRESHOLDS_BY_TYPE["handicap"] == 0.20
        assert EV_THRESHOLDS_BY_TYPE["default"] == 0.15
