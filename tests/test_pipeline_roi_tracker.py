import pytest
import pandas as pd
from datetime import datetime


@pytest.mark.unit
class TestRoiTracker:
    def test_constants(self):
        from pipeline.roi_tracker_12 import TARGET_ROI, ALERT_ROI_WARN, ALERT_ROI_CRIT
        assert TARGET_ROI == 1.15
        assert ALERT_ROI_WARN == 0.90
        assert ALERT_ROI_CRIT == 0.75

    def test_record_bet_hit(self, tmp_path, monkeypatch):
        import pipeline.roi_tracker_12 as rt
        monkeypatch.setattr(rt, "TRACKER_FILE", str(tmp_path / "tracker.csv"))
        df = rt.record_bet("R001", "Horse1", "tansho", 1000, 10.0, True)
        assert len(df) == 1
        assert df.iloc[0]["profit"] == 9000.0
        assert df.iloc[0]["hit"] == 1

    def test_record_bet_miss(self, tmp_path, monkeypatch):
        import pipeline.roi_tracker_12 as rt
        monkeypatch.setattr(rt, "TRACKER_FILE", str(tmp_path / "tracker.csv"))
        df = rt.record_bet("R001", "Horse1", "tansho", 1000, 10.0, False)
        assert df.iloc[0]["profit"] == -1000.0
        assert df.iloc[0]["hit"] == 0

    def test_load_empty(self, tmp_path, monkeypatch):
        import pipeline.roi_tracker_12 as rt
        monkeypatch.setattr(rt, "TRACKER_FILE", str(tmp_path / "tracker.csv"))
        df = rt._load()
        assert len(df) == 0
        assert list(df.columns) == rt.COLS
