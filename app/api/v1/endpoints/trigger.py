from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.common.errors import ErrorCode, FlowifyException
from app.services.scheduler_service import SchedulerService

router = APIRouter()


class TriggerCreateRequest(BaseModel):
    """스케줄 트리거 등록 요청 모델."""

    workflow_id: str
    trigger_type: str = "cron"
    config: dict = {}


class TriggerResponse(BaseModel):
    """스케줄 트리거 응답 모델."""

    trigger_id: str
    workflow_id: str
    trigger_type: str
    next_run: str | None = None


def _get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


@router.get("")
async def list_triggers(request: Request) -> list[dict]:
    """등록된 스케줄 목록을 조회합니다."""
    scheduler = _get_scheduler(request)
    return scheduler.get_jobs()


@router.post("", response_model=TriggerResponse)
async def create_trigger(
    body: TriggerCreateRequest,
    request: Request,
) -> TriggerResponse:
    """워크플로우 스케줄 트리거를 등록합니다.

    trigger_type:
        - "cron": config에 hour, minute 필드 사용
        - "interval": config에 seconds 필드 사용
    """
    scheduler = _get_scheduler(request)
    trigger_id = f"trigger_{body.workflow_id}"

    try:
        if body.trigger_type == "cron":
            hour = body.config.get("hour", 0)
            minute = body.config.get("minute", 0)
            scheduler.add_cron_job(
                job_id=trigger_id,
                func=lambda: None,
                hour=hour,
                minute=minute,
                kwargs={"workflow_id": body.workflow_id},
            )
        elif body.trigger_type == "interval":
            seconds = body.config.get("seconds", 60)
            scheduler.add_interval_job(
                job_id=trigger_id,
                func=lambda: None,
                seconds=seconds,
                kwargs={"workflow_id": body.workflow_id},
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
        )

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
        )
    return {"trigger_id": trigger_id, "status": "deleted"}
