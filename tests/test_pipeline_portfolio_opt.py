import pytest


@pytest.mark.unit
class TestPortfolioOpt:
    def test_estimate_probs(self):
        from pipeline.portfolio_opt_11 import _estimate_probs
        probs = _estimate_probs(0.20, 0.15, 0.10)
        assert isinstance(probs, dict)
        assert "tansho" in probs or len(probs) > 0

    def test_optimize_race_portfolio_basic(self):
        from pipeline.portfolio_opt_11 import optimize_race_portfolio
        result = optimize_race_portfolio(
            p1=0.20, p2=0.15, p3=0.10,
            tansho_odds=5.0, fukusho_odds=2.0,
            umaren_odds=15.0, sanrenpuku_odds=30.0,
            bankroll=100000
        )
        assert isinstance(result, dict)
        total = sum(result.values())
        assert total <= 100000 * 0.10 + 100

    def test_optimize_race_portfolio_low_probs(self):
        from pipeline.portfolio_opt_11 import optimize_race_portfolio
        result = optimize_race_portfolio(
            p1=0.01, p2=0.01, p3=0.01,
            tansho_odds=100.0, fukusho_odds=10.0,
            umaren_odds=500.0, sanrenpuku_odds=1000.0,
            bankroll=100000
        )
        assert isinstance(result, dict)
