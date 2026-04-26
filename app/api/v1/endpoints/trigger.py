from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from app.api.v1.deps import get_user_id
from app.common.errors import ErrorCode, FlowifyException
from app.core.engine.executor import WorkflowExecutor, register_cancellation_event
from app.db.mongodb import get_database
from app.models.workflow import WorkflowDefinition
from app.services.scheduler_service import SchedulerService

router = APIRouter()


class TriggerCreateRequest(BaseModel):
    """스케줄 트리거 등록 요청 모델."""

    model_config = {"populate_by_name": True}

    workflow_id: str
    user_id: str | None = None
    trigger_type: str = "cron"
    config: dict[str, Any] = Field(default_factory=dict)
    workflow_definition: WorkflowDefinition
    service_tokens: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        """이전 설계 문서의 필드명(type, credentials)도 허용합니다."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "trigger_type" not in normalized and "type" in normalized:
            normalized["trigger_type"] = normalized["type"]
        if "service_tokens" not in normalized and "credentials" in normalized:
            normalized["service_tokens"] = normalized["credentials"]
        return normalized


class TriggerResponse(BaseModel):
    """스케줄 트리거 응답 모델."""

    trigger_id: str
    workflow_id: str
    trigger_type: str
    next_run: str | None = None


def _get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


async def _run_scheduled_workflow(
    workflow_id: str,
    workflow_definition: dict[str, Any],
    service_tokens: dict[str, str],
    user_id: str,
) -> None:
    """APScheduler job에서 워크플로우 실행 엔진을 직접 호출합니다."""
    workflow_def = WorkflowDefinition.model_validate(workflow_definition)
    execution_id = WorkflowExecutor.generate_execution_id()
    register_cancellation_event(execution_id)

    executor = WorkflowExecutor(get_database())
    await executor.execute(
        execution_id=execution_id,
        workflow_id=workflow_id or (workflow_def.id or ""),
        user_id=user_id,
        nodes=workflow_def.nodes,
        edges=workflow_def.edges,
        service_tokens=service_tokens,
    )


@router.get("")
async def list_triggers(request: Request) -> list[dict]:
    """등록된 스케줄 목록을 조회합니다."""
    scheduler = _get_scheduler(request)
    return scheduler.get_jobs()


@router.post("", response_model=TriggerResponse)
async def create_trigger(
    body: TriggerCreateRequest,
    request: Request,
    user_id: str = Depends(get_user_id),
) -> TriggerResponse:
    """워크플로우 스케줄 트리거를 등록합니다.

    trigger_type:
        - "cron": config에 hour, minute 필드 사용
        - "interval": config에 seconds 필드 사용
    """
    scheduler = _get_scheduler(request)
    trigger_id = f"trigger_{body.workflow_id}"
    workflow_def = body.workflow_definition

    if body.user_id and body.user_id != user_id:
        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail="요청 본문의 user_id와 인증된 사용자 정보가 일치하지 않습니다.",
        )

    if workflow_def.id and workflow_def.id != body.workflow_id:
        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail="workflow_id와 workflow_definition.id가 일치하지 않습니다.",
        )

    if workflow_def.user_id != user_id:
        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail="workflow_definition.user_id와 인증된 사용자 정보가 일치하지 않습니다.",
        )

    job_kwargs = {
        "workflow_id": body.workflow_id,
        "workflow_definition": workflow_def.model_copy(
            update={"id": body.workflow_id, "user_id": user_id}
        ).model_dump(by_alias=False, exclude_none=True),
        "service_tokens": body.service_tokens,
        "user_id": user_id,
    }

    try:
        if body.trigger_type == "cron":
            hour = body.config.get("hour", 0)
            minute = body.config.get("minute", 0)
            scheduler.add_cron_job(
                job_id=trigger_id,
                func=_run_scheduled_workflow,
                hour=hour,
                minute=minute,
                kwargs=job_kwargs,
                replace_existing=True,
            )
        elif body.trigger_type == "interval":
            seconds = body.config.get("seconds", 60)
            scheduler.add_interval_job(
                job_id=trigger_id,
                func=_run_scheduled_workflow,
                seconds=seconds,
                kwargs=job_kwargs,
                replace_existing=True,
            )
        else:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"지원하지 않는 트리거 타입입니다: {body.trigger_type}",
            )
    except FlowifyException:
        raise
    except Exception as e:
        raise FlowifyException(
            ErrorCode.INTERNAL_ERROR,
            detail=f"스케줄 등록에 실패했습니다: {e}",
        ) from e

    job = scheduler.get_job(trigger_id)
    return TriggerResponse(
        trigger_id=trigger_id,
        workflow_id=body.workflow_id,
        trigger_type=body.trigger_type,
        next_run=job["next_run"] if job else None,
    )


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str, request: Request) -> dict:
    """스케줄 트리거를 삭제합니다."""
    scheduler = _get_scheduler(request)
    job = scheduler.get_job(trigger_id)
    if not job:
        raise FlowifyException(
            ErrorCode.EXECUTION_NOT_FOUND,
            detail=f"트리거 ID '{trigger_id}'을(를) 찾을 수 없습니다.",
        )
    try:
        scheduler.remove_job(trigger_id)
    except Exception as e:
        raise FlowifyException(
            ErrorCode.INTERNAL_ERROR,
            detail=f"트리거 삭제에 실패했습니다: {e}",
        ) from e
    return {"trigger_id": trigger_id, "status": "deleted"}
