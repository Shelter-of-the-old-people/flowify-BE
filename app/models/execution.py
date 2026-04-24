from datetime import datetime

from pydantic import BaseModel, Field

from app.core.engine.state import WorkflowState


class NodeSnapshot(BaseModel):
    capturedAt: datetime = Field(default_factory=datetime.utcnow)  # noqa: N815
    stateData: dict = Field(default_factory=dict)  # noqa: N815


class ErrorDetail(BaseModel):
    code: str
    message: str
    stackTrace: str | None = None  # noqa: N815


class NodeExecutionLog(BaseModel):
    """노드 실행 로그.

    Spring Boot가 직접 읽는 MongoDB 스키마와 일치하도록 camelCase 필드명을 사용합니다.
    """

    nodeId: str  # noqa: N815
    status: str = "pending"
    inputData: dict = Field(default_factory=dict)  # noqa: N815
    outputData: dict = Field(default_factory=dict)  # noqa: N815
    snapshot: NodeSnapshot | None = None
    error: ErrorDetail | None = None
    startedAt: datetime = Field(default_factory=datetime.utcnow)  # noqa: N815
    finishedAt: datetime | None = None  # noqa: N815


class WorkflowExecution(BaseModel):
    """워크플로우 실행 상태 모델.

    MongoDB `workflow_executions` 컬렉션에 저장됩니다.
    Spring Boot가 직접 이 컬렉션을 읽으므로 필드명이 camelCase여야 합니다.

    _id 필드는 MongoDB 저장 시 executionId로 설정합니다.
    (executor.py _save_execution 참고)
    """

    workflowId: str  # noqa: N815
    userId: str  # noqa: N815
    state: WorkflowState = WorkflowState.PENDING
    nodeLogs: list[NodeExecutionLog] = Field(default_factory=list)  # noqa: N815
    errorMessage: str | None = None  # noqa: N815
    startedAt: datetime = Field(default_factory=datetime.utcnow)  # noqa: N815
    finishedAt: datetime | None = None  # noqa: N815
