from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from app.api.v1.endpoints.trigger import _run_scheduled_workflow
from app.main import app

AUTH_HEADERS = {
    "X-Internal-Token": "test-secret",
    "X-User-ID": "usr_test123",
}


def _build_trigger_payload(**overrides) -> dict:
    payload = {
        "workflow_id": "wf_1",
        "trigger_type": "cron",
        "config": {"hour": 9, "minute": 30},
        "workflow_definition": {
            "id": "wf_1",
            "name": "Scheduler Test Workflow",
            "userId": "usr_test123",
            "nodes": [],
            "edges": [],
        },
        "service_tokens": {"gmail": "ya29.token"},
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def client_with_scheduler():
    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.get_job.return_value = None

    with patch("app.api.v1.middleware.settings") as mock_settings:
        mock_settings.INTERNAL_API_SECRET = AUTH_HEADERS["X-Internal-Token"]

        with TestClient(app, headers=AUTH_HEADERS) as client:
            original_scheduler = getattr(client.app.state, "scheduler", None)
            client.app.state.scheduler = mock_scheduler
            try:
                yield client, mock_scheduler
            finally:
                client.app.state.scheduler = original_scheduler


def test_list_triggers_returns_scheduler_jobs(client_with_scheduler) -> None:
    client, mock_scheduler = client_with_scheduler
    mock_scheduler.get_jobs.return_value = [
        {
            "id": "trigger_wf_1",
            "name": "trigger_wf_1",
            "next_run": "2026-04-25T09:30:00",
            "trigger": "cron[hour='9', minute='30']",
        }
    ]

    response = client.get("/api/v1/triggers")

    assert response.status_code == 200
    assert response.json() == mock_scheduler.get_jobs.return_value


def test_create_cron_trigger_registers_schedulable_job(client_with_scheduler) -> None:
    client, mock_scheduler = client_with_scheduler
    mock_scheduler.get_job.return_value = {"id": "trigger_wf_1", "next_run": "2026-04-25T09:30:00"}

    response = client.post("/api/v1/triggers", json=_build_trigger_payload())

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "trigger_id": "trigger_wf_1",
        "workflow_id": "wf_1",
        "trigger_type": "cron",
        "next_run": "2026-04-25T09:30:00",
    }

    mock_scheduler.add_cron_job.assert_called_once_with(
        job_id="trigger_wf_1",
        func=_run_scheduled_workflow,
        hour=9,
        minute=30,
        kwargs={
            "workflow_id": "wf_1",
            "workflow_definition": {
                "id": "wf_1",
                "name": "Scheduler Test Workflow",
                "user_id": "usr_test123",
                "shared_with": [],
                "template": False,
                "nodes": [],
                "edges": [],
                "active": True,
            },
            "service_tokens": {"gmail": "ya29.token"},
            "user_id": "usr_test123",
        },
        replace_existing=True,
    )


def test_create_interval_trigger_accepts_legacy_fields(client_with_scheduler) -> None:
    client, mock_scheduler = client_with_scheduler
    mock_scheduler.get_job.return_value = {"id": "trigger_wf_1", "next_run": "2026-04-25T09:31:00"}
    payload = _build_trigger_payload(
        trigger_type=None,
        type="interval",
        config={"seconds": 300},
        service_tokens=None,
        credentials={"slack": "xoxb-token"},
    )
    payload.pop("trigger_type")
    payload.pop("service_tokens")

    response = client.post("/api/v1/triggers", json=payload)

    assert response.status_code == 200
    assert response.json()["trigger_type"] == "interval"
    mock_scheduler.add_interval_job.assert_called_once_with(
        job_id="trigger_wf_1",
        func=_run_scheduled_workflow,
        seconds=300,
        kwargs={
            "workflow_id": "wf_1",
            "workflow_definition": {
                "id": "wf_1",
                "name": "Scheduler Test Workflow",
                "user_id": "usr_test123",
                "shared_with": [],
                "template": False,
                "nodes": [],
                "edges": [],
                "active": True,
            },
            "service_tokens": {"slack": "xoxb-token"},
            "user_id": "usr_test123",
        },
        replace_existing=True,
    )


def test_create_trigger_rejects_mismatched_workflow_definition(client_with_scheduler) -> None:
    client, _ = client_with_scheduler
    payload = _build_trigger_payload(
        workflow_definition={
            "id": "wf_other",
            "name": "Scheduler Test Workflow",
            "userId": "usr_test123",
            "nodes": [],
            "edges": [],
        }
    )

    response = client.post("/api/v1/triggers", json=payload)

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"


def test_delete_trigger_removes_existing_job(client_with_scheduler) -> None:
    client, mock_scheduler = client_with_scheduler
    mock_scheduler.get_job.return_value = {"id": "trigger_wf_1", "next_run": None}

    response = client.delete("/api/v1/triggers/trigger_wf_1")

    assert response.status_code == 200
    assert response.json() == {"trigger_id": "trigger_wf_1", "status": "deleted"}
    mock_scheduler.remove_job.assert_called_once_with("trigger_wf_1")


def test_delete_missing_trigger_returns_not_found(client_with_scheduler) -> None:
    client, mock_scheduler = client_with_scheduler
    mock_scheduler.get_job.return_value = None

    response = client.delete("/api/v1/triggers/trigger_missing")

    assert response.status_code == 404
    assert response.json()["error_code"] == "EXECUTION_NOT_FOUND"


@pytest.mark.asyncio
async def test_run_scheduled_workflow_executes_workflow() -> None:
    workflow_definition = {
        "id": "wf_1",
        "name": "Scheduled Workflow",
        "userId": "usr_test123",
        "nodes": [],
        "edges": [],
    }

    with (
        patch("app.api.v1.endpoints.trigger.get_database", return_value=MagicMock()),
        patch("app.api.v1.endpoints.trigger.register_cancellation_event") as mock_register,
        patch(
            "app.api.v1.endpoints.trigger.WorkflowExecutor.generate_execution_id",
            return_value="exec_sched_123",
        ),
        patch(
            "app.api.v1.endpoints.trigger.WorkflowExecutor.execute",
            new_callable=AsyncMock,
        ) as mock_execute,
    ):
        await _run_scheduled_workflow(
            workflow_id="wf_1",
            workflow_definition=workflow_definition,
            service_tokens={"gmail": "ya29.token"},
            user_id="usr_test123",
        )

    mock_register.assert_called_once_with("exec_sched_123")
    mock_execute.assert_awaited_once()
    assert mock_execute.await_args.kwargs["execution_id"] == "exec_sched_123"
    assert mock_execute.await_args.kwargs["workflow_id"] == "wf_1"
    assert mock_execute.await_args.kwargs["user_id"] == "usr_test123"
    assert mock_execute.await_args.kwargs["service_tokens"] == {"gmail": "ya29.token"}
    assert mock_execute.await_args.kwargs["nodes"] == []
    assert mock_execute.await_args.kwargs["edges"] == []
