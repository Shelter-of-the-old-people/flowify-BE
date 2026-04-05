from datetime import datetime

from pydantic import BaseModel, Field

from app.models.workflow import EdgeDefinition, NodeDefinition


# ── 워크플로우 실행 ──


class WorkflowExecuteRequest(BaseModel):
    workflow_id: str
    user_id: str
    credentials: dict = Field(default_factory=dict)
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    execution_id: str
    workflow_id: str
    status: str
    message: str


# ── LLM ──


class LLMProcessRequest(BaseModel):
    prompt: str
    context: str | None = None
    max_tokens: int = 1024


class LLMProcessResponse(BaseModel):
    result: str
    tokens_used: int = 0


class GenerateWorkflowRequest(BaseModel):
    prompt: str
    context: str | None = None


class GenerateWorkflowResponse(BaseModel):
    result: dict


# ── 롤백 ──


class RollbackRequest(BaseModel):
    target_node_id: str | None = None


class RollbackResponse(BaseModel):
    execution_id: str
    status: str
    rollback_point: str
    message: str


# ── 트리거 ──


class TriggerCreateRequest(BaseModel):
    workflow_id: str
    user_id: str
    type: str  # "cron" | "interval"
    config: dict
    workflow_definition: dict
    credentials: dict = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    trigger_id: str
    workflow_id: str
    type: str
    status: str
    next_run: datetime | None = None


# ── 공통 성공 응답 래퍼 ──


class SuccessResponse(BaseModel):
    success: bool = True
    data: dict | list | None = None
    message: str | None = None
