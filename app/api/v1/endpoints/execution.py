from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.v1.deps import get_db
from app.common.errors import ErrorCode, FlowifyException
from app.core.engine.state import WorkflowState
from app.models.requests import RollbackRequest, RollbackResponse

router = APIRouter()


async def _get_execution_doc(db: AsyncIOMotorDatabase, execution_id: str) -> dict:
    doc = await db.workflow_executions.find_one({"id": execution_id})
    if not doc:
        raise FlowifyException(
            ErrorCode.EXECUTION_NOT_FOUND,
            detail=f"실행 ID '{execution_id}'을(를) 찾을 수 없습니다.",
        )
    return doc


@router.get("/{execution_id}/status")
async def get_execution_status(
    execution_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """워크플로우 실행 상태를 조회합니다."""
    doc = await _get_execution_doc(db, execution_id)
    node_logs = doc.get("node_logs", [])
    completed = sum(1 for log in node_logs if log.get("status") in ("success", "failed", "skipped"))
    total = len(node_logs)

    # 현재 실행 중인 노드 찾기 (running 상태가 없으면 마지막 성공 노드)
    current_node = None
    for log in node_logs:
        if log.get("status") == "running":
            current_node = log.get("node_id")
            break
    if not current_node and node_logs:
        current_node = node_logs[-1].get("node_id")

    return {
        "execution_id": doc["id"],
        "workflow_id": doc["workflow_id"],
        "status": doc["state"],
        "current_node": current_node,
        "progress": {
            "total_nodes": total,
            "completed_nodes": completed,
        },
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
    }


@router.get("/{execution_id}/logs")
async def get_execution_logs(
    execution_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """워크플로우 실행의 노드별 상세 로그를 조회합니다."""
    doc = await _get_execution_doc(db, execution_id)

    return {
        "execution_id": doc["id"],
        "workflow_id": doc["workflow_id"],
        "status": doc["state"],
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
        "node_logs": doc.get("node_logs", []),
    }


@router.post("/{execution_id}/rollback")
async def rollback_execution(
    execution_id: str,
    body: RollbackRequest | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RollbackResponse:
    """실패한 워크플로우를 스냅샷으로 롤백합니다."""
    doc = await _get_execution_doc(db, execution_id)

    current_state = doc.get("state")
    if current_state != WorkflowState.ROLLBACK_AVAILABLE.value:
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail=f"현재 상태({current_state})에서는 롤백할 수 없습니다.",
            context={"current_state": current_state},
        )

    # 롤백 대상 노드 결정
    node_logs = doc.get("node_logs", [])
    target_node_id = body.target_node_id if body else None

    if not target_node_id:
        # 마지막 성공 노드 찾기
        for log in reversed(node_logs):
            if log.get("status") == "success":
                target_node_id = log.get("node_id")
                break

    if not target_node_id:
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail="롤백할 수 있는 성공 노드가 없습니다.",
        )

    # 상태를 PENDING으로 전환
    await db.workflow_executions.update_one(
        {"id": execution_id},
        {"$set": {"state": WorkflowState.PENDING.value}},
    )

    return RollbackResponse(
        execution_id=execution_id,
        status="pending",
        rollback_point=target_node_id,
        message=f"Rolled back to {target_node_id}. Ready for re-execution.",
    )
