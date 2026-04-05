from datetime import datetime

from pydantic import BaseModel, Field

from app.core.engine.state import WorkflowState


class NodeSnapshot(BaseModel):
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    state_data: dict = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    stack_trace: str | None = None


class NodeExecutionLog(BaseModel):
    node_id: str
    status: str = "pending"
    input_data: dict = Field(default_factory=dict)
    output_data: dict = Field(default_factory=dict)
    snapshot: NodeSnapshot | None = None
    error: ErrorDetail | None = None
    duration_ms: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


class WorkflowExecution(BaseModel):
    id: str | None = None
    workflow_id: str
    user_id: str
    state: WorkflowState = WorkflowState.PENDING
    node_logs: list[NodeExecutionLog] = Field(default_factory=list)
    error_message: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
