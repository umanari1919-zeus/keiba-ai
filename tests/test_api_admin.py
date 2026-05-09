import pytest


@pytest.mark.unit
class TestAdminAPI:
    def test_get_agents_list(self, api_client):
        resp = api_client.get("/api/admin/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_agent_stats(self, api_client):
        resp = api_client.get("/api/admin/agents/IngestAgent/stats")
        assert resp.status_code in (200, 404)
