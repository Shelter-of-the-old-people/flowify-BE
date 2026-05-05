from typing import Any

from pydantic import BaseModel, Field

from app.models.workflow import WorkflowDefinition


class NodePreviewRequest(BaseModel):
    """Spring Boot가 노드 미리보기를 요청할 때 사용하는 바디입니다."""

    workflow: WorkflowDefinition
    service_tokens: dict[str, str] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)
    include_content: bool = False


class NodePreviewResponse(BaseModel):
    """실행 기록에 저장하지 않는 노드 미리보기 응답입니다."""

    workflow_id: str
    node_id: str
    status: str
    available: bool
    reason: str | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    preview_data: dict[str, Any] | None = None
    missing_fields: list[str] | None = None
    metadata: dict[str, Any] | None = None
