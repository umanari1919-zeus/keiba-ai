import pytest
import numpy as np


@pytest.mark.unit
class TestRaceSelector:
    def test_calc_odds_entropy_uniform(self):
        from pipeline.race_selector_31 import calc_odds_entropy
        odds = [10.0, 10.0, 10.0, 10.0]
        ent = calc_odds_entropy(odds)
        assert ent > 0
        assert abs(ent - 2.0) < 0.01  # log2(4) = 2.0

    def test_calc_odds_entropy_single(self):
        from pipeline.race_selector_31 import calc_odds_entropy
        assert calc_odds_entropy([5.0]) == 0.0

    def test_calc_odds_entropy_dominant(self):
        from pipeline.race_selector_31 import calc_odds_entropy
        odds = [1.5, 100.0, 100.0, 100.0]
        ent = calc_odds_entropy(odds)
        assert ent < 1.0

    def test_race_class_upset_mapping(self):
        from pipeline.race_selector_31 import race_class_upset
        assert race_class_upset("A") == 0.20
        assert race_class_upset("C") == 0.35
        assert race_class_upset("0") == 0.85
        assert race_class_upset("") == 0.72

    def test_upset_weights_sum(self):
        from pipeline.race_selector_31 import UPSET_W
        total = sum(UPSET_W.values())
        assert abs(total - 1.0) < 1e-9

    def test_season_upset_all_months(self):
        from pipeline.race_selector_31 import _SEASON_UPSET
        assert len(_SEASON_UPSET) == 12
        for m in range(1, 13):
            assert 0 < _SEASON_UPSET[m] < 1
