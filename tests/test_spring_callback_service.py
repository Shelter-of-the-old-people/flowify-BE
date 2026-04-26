from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.engine.state import WorkflowState
from app.models.execution import ErrorDetail, NodeExecutionLog, WorkflowExecution
from app.services.spring_callback_service import SpringExecutionCallbackService


def _make_execution(
    state: WorkflowState,
    *,
    output_data: dict | None = None,
    error_message: str | None = None,
) -> WorkflowExecution:
    started_at = datetime(2026, 4, 26, 10, 0, 0)
    finished_at = started_at + timedelta(milliseconds=1250)

    node_logs = [
        NodeExecutionLog(
            nodeId="node_1",
            status="success",
            outputData=output_data or {},
            startedAt=started_at,
            finishedAt=finished_at,
        )
    ]

    if error_message:
        node_logs.append(
            NodeExecutionLog(
                nodeId="node_2",
                status="failed",
                error=ErrorDetail(code="NODE_EXECUTION_FAILED", message=error_message),
                startedAt=started_at,
                finishedAt=finished_at,
            )
        )

    return WorkflowExecution(
        workflowId="wf_1",
        userId="usr_1",
        state=state,
        nodeLogs=node_logs,
        errorMessage=error_message,
        startedAt=started_at,
        finishedAt=finished_at,
    )


class TestSpringExecutionCallbackService:
    @pytest.mark.asyncio
    async def test_notify_execution_complete_skips_without_base_url(self):
        """SPRING_BASE_URL이 없으면 콜백을 전송하지 않습니다."""
        service = SpringExecutionCallbackService()
        execution = _make_execution(WorkflowState.SUCCESS, output_data={"type": "TEXT"})

        with (
            patch("app.services.spring_callback_service.settings") as mock_settings,
            patch("app.services.spring_callback_service.httpx.AsyncClient") as mock_client,
        ):
            mock_settings.SPRING_BASE_URL = ""
            mock_settings.INTERNAL_API_SECRET = "test-secret"
            mock_settings.SPRING_CALLBACK_TIMEOUT_SECONDS = 5.0

            await service.notify_execution_complete("exec_1", execution)

        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_execution_complete_sends_expected_payload(self):
        """성공 종료 시 Spring 계약 payload를 전송합니다."""
        service = SpringExecutionCallbackService()
        execution = _make_execution(
            WorkflowState.SUCCESS,
            output_data={"type": "TEXT", "content": "ok"},
        )

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(
            return_value=httpx.Response(
                200,
                request=httpx.Request(
                    "POST",
                    "http://spring.test/api/internal/executions/exec_1/complete",
                ),
            )
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.spring_callback_service.settings") as mock_settings,
            patch(
                "app.services.spring_callback_service.httpx.AsyncClient",
                return_value=mock_async_client,
            ),
        ):
            mock_settings.SPRING_BASE_URL = "http://spring.test"
            mock_settings.INTERNAL_API_SECRET = "test-secret"
            mock_settings.SPRING_CALLBACK_TIMEOUT_SECONDS = 5.0

            await service.notify_execution_complete("exec_1", execution)

        mock_client.request.assert_awaited_once_with(
            method="POST",
            url="http://spring.test/api/internal/executions/exec_1/complete",
            headers={"X-Internal-Token": "test-secret"},
            json={
                "status": "completed",
                "durationMs": 1250,
                "output": {"type": "TEXT", "content": "ok"},
            },
        )

    @pytest.mark.asyncio
    async def test_notify_execution_complete_swallows_http_errors(self):
        """HTTP 오류가 나도 executor 흐름을 깨지 않습니다."""
        service = SpringExecutionCallbackService()
        execution = _make_execution(
            WorkflowState.ROLLBACK_AVAILABLE,
            error_message="LLM failed",
        )

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(
            return_value=httpx.Response(
                500,
                request=httpx.Request(
                    "POST",
                    "http://spring.test/api/internal/executions/exec_2/complete",
                ),
            )
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.spring_callback_service.settings") as mock_settings,
            patch(
                "app.services.spring_callback_service.httpx.AsyncClient",
                return_value=mock_async_client,
            ),
        ):
            mock_settings.SPRING_BASE_URL = "http://spring.test"
            mock_settings.INTERNAL_API_SECRET = "test-secret"
            mock_settings.SPRING_CALLBACK_TIMEOUT_SECONDS = 5.0

            await service.notify_execution_complete("exec_2", execution)

        mock_client.request.assert_awaited_once()
