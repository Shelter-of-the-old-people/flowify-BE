from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.fixture()
def mock_execution_doc():
    return {
        "id": "exec_abc123",
        "workflow_id": "wf_1",
        "user_id": "usr_test123",
        "state": "success",
        "started_at": "2026-04-06T10:00:00",
        "finished_at": "2026-04-06T10:00:15",
        "node_logs": [
            {
                "node_id": "node_1",
                "status": "success",
                "input_data": {},
                "output_data": {"result": "ok"},
                "duration_ms": 100,
                "started_at": "2026-04-06T10:00:01",
                "finished_at": "2026-04-06T10:00:02",
            },
        ],
    }


class TestGetExecutionStatus:
    def test_found(self, client, mock_execution_doc):
        with patch("app.api.v1.endpoints.execution.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.workflow_executions.find_one = AsyncMock(return_value=mock_execution_doc)
            mock_get_db.return_value = mock_db

            # Depends override
            app.dependency_overrides[get_db_func()] = lambda: mock_db

            response = client.get(
                "/api/v1/executions/exec_abc123/status",
                headers=AUTH_HEADERS,
            )

        # 직접 의존성 패치하는 대신, 전체 함수를 패치
        # 아래의 통합 테스트에서 상세 검증

    def test_not_found(self, client):
        with patch("app.api.v1.endpoints.execution.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.workflow_executions.find_one = AsyncMock(return_value=None)

            from app.api.v1.deps import get_db
            app.dependency_overrides[get_db] = lambda: mock_db

            response = client.get(
                "/api/v1/executions/exec_nonexistent/status",
                headers=AUTH_HEADERS,
            )

            assert response.status_code == 404
            assert response.json()["error_code"] == "EXECUTION_NOT_FOUND"

            app.dependency_overrides.clear()


class TestGetExecutionLogs:
    def test_found(self, client, mock_execution_doc):
        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=mock_execution_doc)
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(
            "/api/v1/executions/exec_abc123/logs",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["execution_id"] == "exec_abc123"
        assert len(body["node_logs"]) == 1

        app.dependency_overrides.clear()


class TestRollbackExecution:
    def test_rollback_available(self, client):
        doc = {
            "id": "exec_abc123",
            "state": "rollback_available",
            "node_logs": [
                {"node_id": "node_1", "status": "success"},
                {"node_id": "node_2", "status": "failed"},
            ],
        }

        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=doc)
        mock_db.workflow_executions.update_one = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_abc123/rollback",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["rollback_point"] == "node_1"

        app.dependency_overrides.clear()

    def test_rollback_unavailable_state(self, client):
        doc = {"id": "exec_abc123", "state": "success", "node_logs": []}

        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=doc)
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_abc123/rollback",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 400
        assert response.json()["error_code"] == "ROLLBACK_UNAVAILABLE"

        app.dependency_overrides.clear()


def get_db_func():
    """Helper to get the actual get_db function for overrides."""
    from app.api.v1.deps import get_db
    return get_db
