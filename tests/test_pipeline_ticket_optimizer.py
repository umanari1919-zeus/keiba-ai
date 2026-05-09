import pytest
import numpy as np


@pytest.mark.unit
class TestTicketOptimizer:
    def test_estimate_place_prob_small_field(self):
        from pipeline.ticket_optimizer_30 import estimate_place_prob
        result = estimate_place_prob(0.30, 3)
        assert result == min(0.99, 0.30 * 3)

    def test_estimate_place_prob_large_field(self):
        from pipeline.ticket_optimizer_30 import estimate_place_prob
        result = estimate_place_prob(0.10, 16)
        assert result == min(0.92, 0.10 * 3.2)

    def test_harville_p2_basic(self):
        from pipeline.ticket_optimizer_30 import harville_p2
        result = harville_p2(0.3, 0.2)
        assert 0 < result < 1

    def test_harville_p2_zero_prob(self):
        from pipeline.ticket_optimizer_30 import harville_p2
        assert harville_p2(1.0, 0.5) == 0.0

    def test_harville_p3_basic(self):
        from pipeline.ticket_optimizer_30 import harville_p3
        result = harville_p3(0.2, 0.15, 0.10)
        assert 0 < result < 1

    def test_takeout_rates(self):
        from pipeline.ticket_optimizer_30 import TAKEOUT, PAYOUT
        assert TAKEOUT["tansho"] == 0.200
        for k in TAKEOUT:
            assert abs(PAYOUT[k] - (1 - TAKEOUT[k])) < 1e-9

    def test_kelly_frac_constant(self):
        from pipeline.ticket_optimizer_30 import KELLY_FRAC
        assert KELLY_FRAC == 0.10
