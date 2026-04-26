import logging
from typing import Any

import httpx

from app.config import settings
from app.core.engine.state import WorkflowState
from app.models.execution import WorkflowExecution

logger = logging.getLogger(__name__)


class SpringExecutionCallbackService:
    """Spring Boot 실행 완료 콜백 전송 서비스."""

    async def notify_execution_complete(
        self, execution_id: str, execution: WorkflowExecution
    ) -> None:
        """Spring Boot에 실행 종료 상태를 전송합니다."""
        if not settings.SPRING_BASE_URL:
            logger.debug("Spring callback skipped: SPRING_BASE_URL not configured")
            return

        if not settings.INTERNAL_API_SECRET:
            logger.warning("Spring callback skipped: INTERNAL_API_SECRET not configured")
            return

        callback_url = self._build_callback_url(execution_id)
        callback_payload = self._build_payload(execution)
        headers = {"X-Internal-Token": settings.INTERNAL_API_SECRET}

        try:
            async with httpx.AsyncClient(
                timeout=settings.SPRING_CALLBACK_TIMEOUT_SECONDS
            ) as client:
                response = await client.request(
                    method="POST",
                    url=callback_url,
                    headers=headers,
                    json=callback_payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Spring callback failed with HTTP %s for execution %s: %s",
                e.response.status_code,
                execution_id,
                e.response.text,
            )
        except httpx.HTTPError as e:
            logger.warning("Spring callback request failed for execution %s: %s", execution_id, e)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(
                "Spring callback raised an unexpected error for execution %s: %s",
                execution_id,
                e,
            )

    @staticmethod
    def _build_callback_url(execution_id: str) -> str:
        """실행 완료 콜백 URL을 생성합니다."""
        base_url = settings.SPRING_BASE_URL.rstrip("/")
        return f"{base_url}/api/internal/executions/{execution_id}/complete"

    def _build_payload(self, execution: WorkflowExecution) -> dict[str, Any]:
        """Spring Boot 계약에 맞는 콜백 payload를 생성합니다."""
        payload: dict[str, Any] = {
            "status": self._map_status(execution.state),
        }

        duration_ms = self._calculate_duration_ms(execution)
        if duration_ms is not None:
            payload["durationMs"] = duration_ms

        output_data = self._extract_output(execution)
        if output_data:
            payload["output"] = output_data

        error_message = self._extract_error_message(execution)
        if error_message:
            payload["error"] = error_message

        return payload

    @staticmethod
    def _map_status(state: WorkflowState | str) -> str:
        """FastAPI 실행 상태를 Spring 콜백 상태로 변환합니다."""
        state_value = state.value if hasattr(state, "value") else str(state)

        if state_value == WorkflowState.SUCCESS.value:
            return "completed"
        if state_value == WorkflowState.STOPPED.value:
            return WorkflowState.STOPPED.value
        return "failed"

    @staticmethod
    def _calculate_duration_ms(execution: WorkflowExecution) -> int | None:
        """실행 시간을 밀리초 단위로 계산합니다."""
        if not execution.startedAt or not execution.finishedAt:
            return None

        delta = execution.finishedAt - execution.startedAt
        return max(int(delta.total_seconds() * 1000), 0)

    @staticmethod
    def _extract_output(execution: WorkflowExecution) -> dict[str, Any] | None:
        """마지막 성공 노드의 출력 데이터를 추출합니다."""
        for node_log in reversed(execution.nodeLogs):
            if node_log.status == "success" and node_log.outputData:
                return node_log.outputData
        return None

    @staticmethod
    def _extract_error_message(execution: WorkflowExecution) -> str | None:
        """실행 실패 메시지를 추출합니다."""
        if execution.errorMessage:
            return execution.errorMessage

        for node_log in reversed(execution.nodeLogs):
            if node_log.error and node_log.error.message:
                return node_log.error.message
        return None
