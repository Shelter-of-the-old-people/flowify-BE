from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.v1.deps import get_db, get_user_id
from app.core.engine.executor import WorkflowExecutor, register_cancellation_event
from app.models.requests import (
    ExecutionResult,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    WorkflowExecuteRequest,
)
from app.services.llm_service import LLMService
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


async def _run_workflow(
    db: AsyncIOMotorDatabase,
    execution_id: str,
    workflow_def,
    service_tokens: dict,
    user_id: str,
) -> None:
    """백그라운드에서 워크플로우를 실행합니다."""
    executor = WorkflowExecutor(db)
    await executor.execute(
        execution_id=execution_id,
        workflow_id=workflow_def.id or "",
        user_id=user_id,
        nodes=workflow_def.nodes,
        edges=workflow_def.edges,
        service_tokens=service_tokens,
    )


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> ExecutionResult:
    """워크플로우 비동기 실행을 시작합니다.

    Spring Boot가 보내는 요청 구조:
        { "workflow": { ...WorkflowDefinition... }, "service_tokens": { ... } }

    응답의 execution_id를 Spring Boot가 클라이언트에 반환합니다.
    """
    execution_id = WorkflowExecutor.generate_execution_id()
    register_cancellation_event(execution_id)

    background_tasks.add_task(
        _run_workflow,
        db,
        execution_id,
        request.workflow,
        request.service_tokens,
        user_id,
    )

    return ExecutionResult(
        execution_id=execution_id,
        workflow_id=workflow_id,
        status="running",
        message="Workflow execution started asynchronously.",
    )


@router.post("/generate")
async def generate_workflow(
    request: GenerateWorkflowRequest,
    user_id: str = Depends(get_user_id),
) -> GenerateWorkflowResponse:
    """LLM 기반 워크플로우 자동 생성.

    Spring Boot가 POST /api/v1/workflows/generate 로 호출합니다.
    응답은 Spring Boot WorkflowCreateRequest 호환 형식이어야 합니다.
    name 필드가 @NotBlank 이므로 반드시 포함해야 합니다.
    """
    service = LLMService()
    result = await service.generate_workflow(request.prompt)

    return GenerateWorkflowResponse(
        name=result.get("name", "AI 생성 워크플로우"),
        description=result.get("description"),
        nodes=result.get("nodes", []),
        edges=result.get("edges", []),
        trigger=result.get("trigger", {"type": "manual", "config": {}}),
    )
