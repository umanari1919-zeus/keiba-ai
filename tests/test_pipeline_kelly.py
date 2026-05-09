import pytest


@pytest.mark.unit
class TestKellyBankroll:
    def test_kelly_positive_ev(self, monkeypatch):
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet
        bet = calculate_kelly_bet(bankroll=100000, p_win=0.15, odds=30.0)
        assert bet >= 100
        assert bet <= 100000 * 0.05

    def test_kelly_negative_ev_returns_zero(self):
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet
        bet = calculate_kelly_bet(bankroll=100000, p_win=0.01, odds=2.0)
        assert bet == 0

    def test_kelly_zero_prob(self):
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet
        assert calculate_kelly_bet(100000, 0.0, 10.0) == 0

    def test_kelly_zero_odds(self):
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet
        assert calculate_kelly_bet(100000, 0.5, 1.0) == 0

    def test_kelly_respects_max_bet_ratio(self):
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet, MAX_BET_RATIO
        bet = calculate_kelly_bet(bankroll=1000000, p_win=0.90, odds=50.0)
        assert bet <= 1000000 * MAX_BET_RATIO + 100

    def test_update_bankroll_hit(self, tmp_path, monkeypatch):
        import pipeline.kelly_bankroll_09 as kb
        bf = tmp_path / "bankroll.json"
        monkeypatch.setattr(kb, "BANKROLL_FILE", str(bf))
        kb.load_bankroll()
        new_val = kb.update_bankroll("R001", "Horse1", 1000, 10.0, True)
        assert new_val == 100000 + (1000 * 10.0 - 1000)

    def test_update_bankroll_miss(self, tmp_path, monkeypatch):
        import pipeline.kelly_bankroll_09 as kb
        bf = tmp_path / "bankroll.json"
        monkeypatch.setattr(kb, "BANKROLL_FILE", str(bf))
        kb.load_bankroll()
        new_val = kb.update_bankroll("R001", "Horse1", 1000, 10.0, False)
        assert new_val == 100000 - 1000
