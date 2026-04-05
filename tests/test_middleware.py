from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_SECRET = "test-secret-key"

AUTH_HEADERS = {
    "X-Internal-Token": TEST_SECRET,
    "X-User-ID": "usr_test123",
}


@pytest.fixture()
def client():
    with patch("app.api.v1.middleware.settings") as mock_settings:
        mock_settings.INTERNAL_API_SECRET = TEST_SECRET
        yield TestClient(app, raise_server_exceptions=False)


class TestHealthExcluded:
    def test_health_no_auth_required(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestAuthRequired:
    def test_missing_token_returns_401(self, client):
        response = client.post("/api/v1/workflows/wf_1/execute")
        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False
        assert body["error_code"] == "UNAUTHORIZED"

    def test_wrong_token_returns_401(self, client):
        response = client.post(
            "/api/v1/workflows/wf_1/execute",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_valid_token_passes_through(self, client):
        response = client.post(
            "/api/v1/workflows/wf_1/execute",
            headers=AUTH_HEADERS,
            json={
                "workflow_id": "wf_1",
                "user_id": "usr_test123",
                "nodes": [],
            },
        )
        assert response.status_code != 401
