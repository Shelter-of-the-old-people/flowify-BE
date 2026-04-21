import pytest
from pydantic import ValidationError

from app.models.requests import (
    ExecutionResult,
    GenerateWorkflowRequest,
    LLMProcessRequest,
    LLMProcessResponse,
    RollbackRequest,
    TriggerCreateRequest,
    WorkflowExecuteRequest,
)
from app.models.workflow import EdgeDefinition, NodeDefinition, TriggerConfig, WorkflowDefinition


class TestNodeDefinition:
    def test_minimal(self):
        node = NodeDefinition(id="n1", type="input")
        assert node.id == "n1"
        assert node.category is None
        assert node.auth_warning is False
        assert node.label is None

    def test_full_snake_case(self):
        """snake_case 필드명 직접 생성 (내부 코드 및 테스트용)."""
        node = NodeDefinition(
            id="n1",
            type="llm",
            config={"action": "summarize"},
            category="ai",
            data_type="FILE_LIST",
            output_data_type="TEXT",
            role="middle",
            label="LLM 처리 노드",
        )
        assert node.category == "ai"
        assert node.output_data_type == "TEXT"
        assert node.label == "LLM 처리 노드"

    def test_camel_case_from_spring_boot(self):
        """Spring Boot가 보내는 camelCase JSON 매핑 확인."""
        node = NodeDefinition.model_validate({
            "id": "node_abc12345",
            "category": "service",
            "type": "gmail",
            "label": "Gmail 수신",
            "config": {"action": "read"},
            "position": {"x": 100.0, "y": 200.0},
            "dataType": "EMAIL_LIST",
            "outputDataType": "TEXT",
            "role": "start",
            "authWarning": True,
        })
        assert node.data_type == "EMAIL_LIST"
        assert node.output_data_type == "TEXT"
        assert node.auth_warning is True
        assert node.label == "Gmail 수신"


class TestEdgeDefinition:
    def test_with_id(self):
        """Spring Boot가 보내는 id 필드 포함 엣지."""
        edge = EdgeDefinition(id="edge_abc12345", source="node_1", target="node_2")
        assert edge.id == "edge_abc12345"
        assert edge.source == "node_1"

    def test_without_id(self):
        """id 없는 엣지도 허용 (선택 필드)."""
        edge = EdgeDefinition(source="node_1", target="node_2")
        assert edge.id is None


class TestWorkflowDefinition:
    def test_camel_case_from_spring_boot(self):
        """Spring Boot Workflow 엔티티 직렬화 결과 매핑 확인."""
        wf = WorkflowDefinition.model_validate({
            "id": "wf_abc123",
            "name": "테스트 워크플로우",
            "description": "설명",
            "userId": "usr_abc123",
            "sharedWith": ["usr_other"],
            "template": False,
            "templateId": None,
            "nodes": [],
            "edges": [],
            "trigger": {"type": "manual", "config": {}},
            "active": True,
            "createdAt": "2026-04-13T00:00:00Z",
            "updatedAt": "2026-04-13T00:00:00Z",
        })
        assert wf.name == "테스트 워크플로우"
        assert wf.user_id == "usr_abc123"
        assert wf.active is True
        assert wf.template is False
        assert wf.shared_with == ["usr_other"]


class TestWorkflowExecuteRequest:
    def test_valid_spring_boot_format(self):
        """Spring Boot가 전송하는 {workflow, service_tokens} 형식."""
        req = WorkflowExecuteRequest.model_validate({
            "workflow": {
                "id": "wf_1",
                "name": "테스트",
                "userId": "usr_1",
                "nodes": [{"id": "node_1", "type": "gmail", "category": "service"}],
                "edges": [],
                "trigger": {"type": "manual", "config": {}},
                "active": True,
                "template": False,
            },
            "service_tokens": {"gmail": "ya29.access_token"},
        })
        assert req.workflow.name == "테스트"
        assert req.service_tokens["gmail"] == "ya29.access_token"
        assert len(req.workflow.nodes) == 1

    def test_empty_service_tokens(self):
        req = WorkflowExecuteRequest.model_validate({
            "workflow": {
                "name": "워크플로우",
                "userId": "usr_1",
                "nodes": [],
                "edges": [],
                "trigger": {"type": "manual", "config": {}},
                "active": True,
                "template": False,
            },
            "service_tokens": {},
        })
        assert req.service_tokens == {}

    def test_missing_workflow_raises(self):
        with pytest.raises(ValidationError):
            WorkflowExecuteRequest.model_validate({"service_tokens": {}})


class TestLLMModels:
    def test_process_request_defaults(self):
        req = LLMProcessRequest(prompt="hello")
        assert req.max_tokens == 1024
        assert req.context is None

    def test_process_response(self):
        resp = LLMProcessResponse(result="answer", tokens_used=42)
        assert resp.tokens_used == 42

    def test_generate_workflow_request(self):
        req = GenerateWorkflowRequest(prompt="make a workflow")
        assert req.prompt == "make a workflow"


class TestRollbackRequest:
    def test_optional_node_id(self):
        """node_id는 선택 필드 (Spring Boot에서 null 가능)."""
        req = RollbackRequest()
        assert req.node_id is None

    def test_with_node_id(self):
        req = RollbackRequest(node_id="node_2")
        assert req.node_id == "node_2"


class TestTriggerCreateRequest:
    def test_valid(self):
        req = TriggerCreateRequest(
            workflow_id="wf_1",
            user_id="usr_1",
            type="cron",
            config={"hour": 9, "minute": 0},
            workflow_definition={"nodes": [], "edges": []},
        )
        assert req.type == "cron"


class TestExecutionResult:
    def test_valid(self):
        result = ExecutionResult(
            execution_id="exec_1",
        )
        assert result.execution_id == "exec_1"
