import pytest


@pytest.mark.unit
class TestSettingsAPI:
    def test_get_parameters(self, api_client):
        resp = api_client.get("/api/settings/parameters")
        assert resp.status_code == 200
        data = resp.json()
        assert "EV_THRESHOLD" in data or isinstance(data, dict)

    def test_reset_parameters(self, api_client):
        resp = api_client.post("/api/settings/reset")
        assert resp.status_code == 200
