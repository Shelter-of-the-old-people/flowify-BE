from datetime import datetime

from pydantic import BaseModel, Field

from app.models.workflow import WorkflowDefinition


# ── 워크플로우 실행 ──


class WorkflowExecuteRequest(BaseModel):
    """Spring Boot가 /api/v1/workflows/{workflowId}/execute 로 보내는 요청 바디.

    구조:
        {
            "workflow": { ...WorkflowDefinition... },
            "service_tokens": { "gmail": "ya29...", "slack": "xoxb-..." }
        }

    service_tokens 키: NodeDefinition.type (category == "service" 인 노드만)
    service_tokens 값: OAuth 액세스 토큰 복호화 평문
    """

    workflow: WorkflowDefinition
    service_tokens: dict[str, str] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    """워크플로우 실행 시작 응답.

    Spring Boot는 response["execution_id"]만 읽습니다.
    이 키가 없으면 EXECUTION_FAILED 에러가 발생합니다.
    """

    execution_id: str


# ── AI 워크플로우 생성 ──


class GenerateWorkflowRequest(BaseModel):
    """Spring Boot가 /api/v1/workflows/generate 로 보내는 요청 바디."""

    prompt: str


class GenerateWorkflowResponse(BaseModel):
    """Spring Boot WorkflowCreateRequest 호환 응답.

    Spring Boot는 이 응답을 ObjectMapper.convertValue()로
    WorkflowCreateRequest에 매핑 후 MongoDB에 저장합니다.
    name 필드가 없거나 비어 있으면 @NotBlank 검증으로 저장 실패합니다.
    """

    name: str
    description: str | None = None
    nodes: list[dict]
    edges: list[dict]
    trigger: dict


# ── LLM (FastAPI 내부 전용) ──


class LLMProcessRequest(BaseModel):
    prompt: str
    context: str | None = None
    max_tokens: int = 1024


class LLMProcessResponse(BaseModel):
    result: str
    tokens_used: int = 0


# ── 롤백 ──


class RollbackRequest(BaseModel):
    """Spring Boot가 /api/v1/executions/{executionId}/rollback 으로 보내는 요청.

    node_id: 롤백 기준 노드 ID. Spring Boot에서 null을 보낼 수 있으므로 Optional.
    """

    node_id: str | None = None


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
