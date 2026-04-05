from fastapi import APIRouter, BackgroundTasks, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.v1.deps import get_db, get_user_id
from app.core.engine.executor import WorkflowExecutor
from app.models.requests import ExecutionResult, WorkflowExecuteRequest

router = APIRouter()


async def _run_workflow(
    db: AsyncIOMotorDatabase,
    execution_id: str,
    request: WorkflowExecuteRequest,
) -> None:
    """백그라운드에서 워크플로우를 실행합니다."""
    executor = WorkflowExecutor(db)
    await executor.execute(
        execution_id=execution_id,
        workflow_id=request.workflow_id,
        user_id=request.user_id,
        nodes=request.nodes,
        edges=request.edges,
        credentials=request.credentials,
    )


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks,
    req: Request = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ExecutionResult:
    """워크플로우 비동기 실행을 시작합니다."""
    execution_id = WorkflowExecutor.generate_execution_id()

    background_tasks.add_task(_run_workflow, db, execution_id, request)

    return ExecutionResult(
        execution_id=execution_id,
        workflow_id=workflow_id,
        status="running",
        message="Workflow execution started asynchronously.",
    )
