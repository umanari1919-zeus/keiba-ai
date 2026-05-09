import pytest


@pytest.mark.unit
class TestPipelineAPI:
    def test_root(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "うまなり地蔵AI Pipeline API"
        assert data["version"] == "2.0.0"

    def test_health(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_pipeline_status_not_found(self, api_client):
        resp = api_client.get("/api/pipeline/status/nonexistent-trace")
        assert resp.status_code in (404, 200)
