from datetime import datetime

from pydantic import BaseModel, Field

from app.core.engine.state import WorkflowState


class NodeExecutionLog(BaseModel):
    node_id: str
    status: str
    input_data: dict = Field(default_factory=dict)
    output_data: dict = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


class WorkflowExecution(BaseModel):
    id: str | None = None
    workflow_id: str
    user_id: str
    state: WorkflowState = WorkflowState.PENDING
    node_logs: list[NodeExecutionLog] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
