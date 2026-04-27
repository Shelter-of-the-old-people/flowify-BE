from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.v1.deps import get_db
from app.common.errors import ErrorCode, FlowifyException
from app.core.engine.executor import request_cancellation
from app.core.engine.state import WorkflowState
from app.models.requests import RollbackRequest, RollbackResponse

router = APIRouter()

# Spring Boot 명세 기준: 이 두 상태에서만 롤백 허용
_ROLLBACK_ALLOWED_STATES = {
    WorkflowState.ROLLBACK_AVAILABLE.value,
    WorkflowState.FAILED.value,
}


def _has_snapshot_state(log: dict) -> bool:
    snapshot = log.get("snapshot")
    return isinstance(snapshot, dict) and "stateData" in snapshot


def _is_valid_rollback_target(log: dict) -> bool:
    return log.get("status") == "success" or _has_snapshot_state(log)


def _find_rollback_target_node_id(
    node_logs: list[dict],
    requested_node_id: str | None,
) -> str | None:
    if requested_node_id:
        for log in node_logs:
            if log.get("nodeId") == requested_node_id and _is_valid_rollback_target(log):
                return requested_node_id
        return None

    for log in reversed(node_logs):
        if log.get("status") == "success":
            return log.get("nodeId")
    return None


async def _get_execution_doc(db: AsyncIOMotorDatabase, execution_id: str) -> dict:
    """MongoDB에서 실행 문서를 조회합니다. _id 기준으로 검색."""
    doc = await db.workflow_executions.find_one({"_id": execution_id})
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
    node_logs = doc.get("nodeLogs", [])
    completed = sum(1 for log in node_logs if log.get("status") in ("success", "failed", "skipped"))
    total = len(node_logs)

    # 현재 실행 중인 노드 찾기 (running 상태가 없으면 마지막 성공 노드)
    current_node = None
    for log in node_logs:
        if log.get("status") == "running":
            current_node = log.get("nodeId")
            break
    if not current_node and node_logs:
        current_node = node_logs[-1].get("nodeId")

    return {
        "execution_id": str(doc["_id"]),
        "workflow_id": doc.get("workflowId"),
        "status": doc.get("state"),
        "current_node": current_node,
        "progress": {
            "total_nodes": total,
            "completed_nodes": completed,
        },
        "started_at": doc.get("startedAt"),
        "finished_at": doc.get("finishedAt"),
    }


@router.get("/{execution_id}/logs")
async def get_execution_logs(
    execution_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """워크플로우 실행의 노드별 상세 로그를 조회합니다."""
    doc = await _get_execution_doc(db, execution_id)

    return {
        "execution_id": str(doc["_id"]),
        "workflow_id": doc.get("workflowId"),
        "status": doc.get("state"),
        "started_at": doc.get("startedAt"),
        "finished_at": doc.get("finishedAt"),
        "node_logs": doc.get("nodeLogs", []),
    }


@router.post("/{execution_id}/rollback")
async def rollback_execution(
    execution_id: str,
    body: RollbackRequest | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RollbackResponse:
    """실패한 워크플로우를 스냅샷으로 롤백합니다.

    Spring Boot 명세:
        - 허용 상태: "rollback_available" 또는 "failed"
        - 요청 바디: { "node_id": "string | null" }
        - HTTP 2xx 응답이면 성공 (응답 바디는 Spring Boot에서 무시)
    """
    doc = await _get_execution_doc(db, execution_id)

    current_state = doc.get("state")
    if current_state not in _ROLLBACK_ALLOWED_STATES:
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail=f"현재 상태({current_state})에서는 롤백할 수 없습니다.",
            context={"current_state": current_state},
        )

    # 롤백 대상 노드 결정
    node_logs = doc.get("nodeLogs", [])
    requested_node_id = body.node_id if body else None
    target_node_id = _find_rollback_target_node_id(node_logs, requested_node_id)

    if not target_node_id:
        detail = "롤백할 수 있는 성공 노드가 없습니다."
        context = {}
        if requested_node_id:
            detail = "지정한 롤백 노드에 성공 로그 또는 스냅샷이 없습니다."
            context = {"node_id": requested_node_id}
        raise FlowifyException(
            ErrorCode.ROLLBACK_UNAVAILABLE,
            detail=detail,
            context=context,
        )

    # 상태를 PENDING으로 전환하고 에러 정보 초기화
    await db.workflow_executions.update_one(
        {"_id": execution_id},
        {
            "$set": {
                "state": WorkflowState.PENDING.value,
                "errorMessage": None,
                "finishedAt": None,
            }
        },
    )

    return RollbackResponse(
        execution_id=execution_id,
        status="pending",
        rollback_point=target_node_id,
        message=f"Rolled back to {target_node_id}. Ready for re-execution.",
    )


# 이미 종료된 상태 (stop 요청 시 멱등 처리)
_ALREADY_TERMINAL_STATES = {
    WorkflowState.STOPPED.value,
    WorkflowState.SUCCESS.value,
    WorkflowState.FAILED.value,
    WorkflowState.ROLLBACK_AVAILABLE.value,
}


@router.post("/{execution_id}/stop")
async def stop_execution(
    execution_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """실행 중인 워크플로우를 중지합니다.

    Spring Boot 명세:
        - Spring Boot가 state == "running" 확인 후 호출
        - 실행 중지 후 state를 "stopped"로 변경
        - 중복 요청은 멱등하게 2xx 반환
        - 응답 바디는 Spring Boot에서 무시
    """
    doc = await _get_execution_doc(db, execution_id)
    current_state = doc.get("state")

    # 이미 종료 상태 → 멱등하게 200
    if current_state in _ALREADY_TERMINAL_STATES:
        return {"execution_id": execution_id, "status": current_state}

    # in-memory 취소 시그널
    request_cancellation(execution_id)

    # MongoDB 직접 업데이트 (safety net — executor가 아직 체크 안 했을 경우 대비)
    await db.workflow_executions.update_one(
        {"_id": execution_id, "state": WorkflowState.RUNNING.value},
        {
            "$set": {
                "state": WorkflowState.STOPPED.value,
                "errorMessage": "Execution stopped by user request",
            }
        },
    )

    return {"execution_id": execution_id, "status": "stopped"}
