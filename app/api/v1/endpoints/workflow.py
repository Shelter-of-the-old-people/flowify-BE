from fastapi import APIRouter

router = APIRouter()


@router.post("/{workflow_id}/execute")
async def execute_workflow(workflow_id: str):
    """워크플로우 실행"""
    return {"workflow_id": workflow_id, "status": "queued"}


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """워크플로우 실행 상태 조회"""
    return {"workflow_id": workflow_id, "status": "pending"}


@router.get("/{workflow_id}/logs")
async def get_workflow_logs(workflow_id: str):
    """워크플로우 실행 로그 조회"""
    return {"workflow_id": workflow_id, "logs": []}
