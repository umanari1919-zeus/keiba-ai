import pytest


@pytest.mark.unit
class TestPredict:
    def test_constants(self):
        from pipeline.predict_04 import MIN_ODDS_RAW, ANABA_ODDS_RAW
        assert MIN_ODDS_RAW == 100
        assert ANABA_ODDS_RAW == 300

    def test_fmt_race_valid(self):
        from pipeline.predict_04 import _fmt_race
        result = _fmt_race("2026050105010301")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fmt_race_short_code(self):
        from pipeline.predict_04 import _fmt_race
        result = _fmt_race("short")
        assert isinstance(result, str)
