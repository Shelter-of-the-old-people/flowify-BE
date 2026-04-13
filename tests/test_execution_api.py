from unittest.mock import AsyncMock, MagicMock

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
    from unittest.mock import patch
    with patch("app.api.v1.middleware.settings") as mock_settings:
        mock_settings.INTERNAL_API_SECRET = TEST_SECRET
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_execution_doc():
    """MongoDB에 저장된 실행 문서 — camelCase 필드명, _id 기준."""
    return {
        "_id": "exec_abc123",
        "workflowId": "wf_1",
        "userId": "usr_test123",
        "state": "success",
        "startedAt": "2026-04-06T10:00:00",
        "finishedAt": "2026-04-06T10:00:15",
        "nodeLogs": [
            {
                "nodeId": "node_1",
                "status": "success",
                "inputData": {},
                "outputData": {"result": "ok"},
                "startedAt": "2026-04-06T10:00:01",
                "finishedAt": "2026-04-06T10:00:02",
            },
        ],
    }


class TestGetExecutionStatus:
    def test_not_found(self, client):
        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=None)
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(
            "/api/v1/executions/exec_nonexistent/status",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "EXECUTION_NOT_FOUND"

        app.dependency_overrides.clear()

    def test_found_returns_camel_execution_id(self, client, mock_execution_doc):
        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=mock_execution_doc)
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(
            "/api/v1/executions/exec_abc123/status",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["execution_id"] == "exec_abc123"
        assert body["status"] == "success"

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
    def test_rollback_available_state(self, client):
        """rollback_available 상태에서 롤백 허용."""
        doc = {
            "_id": "exec_abc123",
            "state": "rollback_available",
            "nodeLogs": [
                {"nodeId": "node_1", "status": "success"},
                {"nodeId": "node_2", "status": "failed"},
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

    def test_rollback_failed_state_allowed(self, client):
        """failed 상태에서도 롤백 허용 (Spring Boot 명세 기준)."""
        doc = {
            "_id": "exec_abc123",
            "state": "failed",
            "nodeLogs": [
                {"nodeId": "node_1", "status": "success"},
                {"nodeId": "node_2", "status": "failed"},
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

        app.dependency_overrides.clear()

    def test_rollback_with_specific_node_id(self, client):
        """node_id 지정 시 해당 노드로 롤백."""
        doc = {
            "_id": "exec_abc123",
            "state": "rollback_available",
            "nodeLogs": [
                {"nodeId": "node_1", "status": "success"},
                {"nodeId": "node_2", "status": "success"},
                {"nodeId": "node_3", "status": "failed"},
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
            json={"node_id": "node_1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rollback_point"] == "node_1"

        app.dependency_overrides.clear()

    def test_rollback_unavailable_state(self, client):
        """success 상태에서는 롤백 불가."""
        doc = {"_id": "exec_abc123", "state": "success", "nodeLogs": []}

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


class TestStopExecution:
    def test_stop_running_execution(self, client):
        """running 상태 실행 중지 → 200."""
        doc = {"_id": "exec_abc123", "state": "running", "nodeLogs": []}

        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=doc)
        mock_db.workflow_executions.update_one = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_abc123/stop",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "stopped"
        mock_db.workflow_executions.update_one.assert_called_once()

        app.dependency_overrides.clear()

    def test_stop_already_stopped_idempotent(self, client):
        """이미 stopped → 멱등 200, update 미호출."""
        doc = {"_id": "exec_abc123", "state": "stopped", "nodeLogs": []}

        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=doc)
        mock_db.workflow_executions.update_one = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_abc123/stop",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "stopped"
        mock_db.workflow_executions.update_one.assert_not_called()

        app.dependency_overrides.clear()

    def test_stop_already_success_idempotent(self, client):
        """이미 success → 멱등 200."""
        doc = {"_id": "exec_abc123", "state": "success", "nodeLogs": []}

        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=doc)
        mock_db.workflow_executions.update_one = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_abc123/stop",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_db.workflow_executions.update_one.assert_not_called()

        app.dependency_overrides.clear()

    def test_stop_not_found(self, client):
        """실행 ID 없음 → 404."""
        from app.api.v1.deps import get_db
        mock_db = MagicMock()
        mock_db.workflow_executions.find_one = AsyncMock(return_value=None)
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post(
            "/api/v1/executions/exec_nonexistent/stop",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "EXECUTION_NOT_FOUND"

        app.dependency_overrides.clear()
