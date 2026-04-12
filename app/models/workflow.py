from datetime import datetime

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel


class NodeDefinition(BaseModel):
    """노드 정의 모델.

    Spring Boot는 camelCase JSON을 전송하므로 alias_generator로 자동 매핑합니다.
    예: dataType -> data_type, authWarning -> auth_warning
    """

    model_config = {"populate_by_name": True, "alias_generator": to_camel}

    id: str
    category: str | None = None
    type: str
    label: str | None = None
    config: dict = Field(default_factory=dict)
    position: dict = Field(default_factory=lambda: {"x": 0, "y": 0})
    data_type: str | None = None
    output_data_type: str | None = None
    role: str | None = None
    auth_warning: bool = False


class EdgeDefinition(BaseModel):
    """엣지 정의 모델.

    Spring Boot는 id 필드를 포함해 전송합니다.
    """

    id: str | None = None
    source: str
    target: str


class TriggerConfig(BaseModel):
    """트리거 설정 모델."""

    model_config = {"populate_by_name": True, "alias_generator": to_camel}

    type: str = "manual"
    config: dict = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """워크플로우 전체 정의 모델.

    Spring Boot의 Workflow 엔티티 Jackson 직렬화 결과를 수신합니다.

    ⚠️ boolean 필드 주의:
    Java `boolean isActive` → Lombok이 `isActive()` getter 생성
    → Jackson이 "is" 접두사를 제거하여 JSON 키를 **"active"** 로 직렬화.
    `alias_generator = to_camel`을 사용하면 Python 필드 `is_active` → `isActive`가 생성되어
    실제 JSON 키 "active"와 불일치합니다.

    해결: 필드명 자체를 "active"/"template"으로 선언하고 명시적 alias를 제거.
    alias_generator는 나머지 snake_case 필드(user_id → userId 등)에만 적용됩니다.
    """

    model_config = {"populate_by_name": True, "alias_generator": to_camel}

    id: str | None = None
    name: str
    description: str | None = None
    user_id: str
    shared_with: list[str] = Field(default_factory=list)
    # Spring Boot: boolean isTemplate → Jackson → "template"
    # alias_generator가 to_camel("template") = "template" 을 생성하므로 별도 alias 불필요
    template: bool = False
    template_id: str | None = None
    nodes: list[NodeDefinition] = Field(default_factory=list)
    edges: list[EdgeDefinition] = Field(default_factory=list)
    trigger: TriggerConfig | None = None
    # Spring Boot: boolean isActive → Jackson → "active"
    # alias_generator가 to_camel("active") = "active" 를 생성하므로 별도 alias 불필요
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
