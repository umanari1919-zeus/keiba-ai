import pytest
import numpy as np


@pytest.mark.unit
class TestBetPortfolio:
    def test_kelly_single_positive_ev(self):
        from pipeline.bet_portfolio_29 import kelly_single
        k = kelly_single(p=0.15, b=29.0)
        assert k > 0
        assert k <= 0.10

    def test_kelly_single_negative_ev(self):
        from pipeline.bet_portfolio_29 import kelly_single
        assert kelly_single(p=0.01, b=1.0) == 0.0

    def test_kelly_single_edge_cases(self):
        from pipeline.bet_portfolio_29 import kelly_single
        assert kelly_single(p=0.0, b=10.0) == 0.0
        assert kelly_single(p=1.0, b=10.0) == 0.0
        assert kelly_single(p=0.5, b=0.0) == 0.0

    def test_expected_log_growth_single_bet(self):
        from pipeline.bet_portfolio_29 import expected_log_growth
        fracs = np.array([0.05])
        probs = np.array([0.15])
        odds = np.array([29.0])
        g = expected_log_growth(fracs, probs, odds)
        assert isinstance(g, float)
        assert g > -1e8

    def test_expected_log_growth_overbetting(self):
        from pipeline.bet_portfolio_29 import expected_log_growth
        fracs = np.array([0.6, 0.6])
        probs = np.array([0.3, 0.3])
        odds = np.array([10.0, 10.0])
        assert expected_log_growth(fracs, probs, odds) == -1e9

    def test_constants(self):
        from pipeline.bet_portfolio_29 import (
            MAX_HORSES_PER_RACE, MAX_PORTFOLIO_RATIO, MAX_RACE_RATIO, KELLY_FRACTION
        )
        assert MAX_HORSES_PER_RACE == 3
        assert MAX_PORTFOLIO_RATIO == 0.20
        assert MAX_RACE_RATIO == 0.10
        assert KELLY_FRACTION == 0.10
