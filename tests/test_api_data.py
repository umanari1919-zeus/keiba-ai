import pytest


@pytest.mark.unit
class TestDataAPI:
    def test_get_bankroll(self, api_client):
        resp = api_client.get("/api/data/bankroll")
        assert resp.status_code == 200

    def test_get_model_performance(self, api_client):
        resp = api_client.get("/api/data/model-performance")
        assert resp.status_code == 200
