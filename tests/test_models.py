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
from app.models.workflow import EdgeDefinition, NodeDefinition


class TestNodeDefinition:
    def test_minimal(self):
        node = NodeDefinition(id="n1", type="input")
        assert node.id == "n1"
        assert node.category is None
        assert node.auth_warning is False

    def test_full(self):
        node = NodeDefinition(
            id="n1",
            type="llm",
            config={"action": "summarize"},
            category="ai",
            data_type="FILE_LIST",
            output_data_type="TEXT",
            role="middle",
        )
        assert node.category == "ai"
        assert node.output_data_type == "TEXT"


class TestWorkflowExecuteRequest:
    def test_valid(self):
        req = WorkflowExecuteRequest(
            workflow_id="wf_1",
            user_id="usr_1",
            credentials={"google": "token123"},
            nodes=[NodeDefinition(id="n1", type="input")],
            edges=[EdgeDefinition(source="n1", target="n2")],
        )
        assert req.workflow_id == "wf_1"
        assert len(req.nodes) == 1

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            WorkflowExecuteRequest(workflow_id="wf_1")


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
        assert req.context is None


class TestRollbackRequest:
    def test_optional_target(self):
        req = RollbackRequest()
        assert req.target_node_id is None

    def test_with_target(self):
        req = RollbackRequest(target_node_id="node_2")
        assert req.target_node_id == "node_2"


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
            workflow_id="wf_1",
            status="running",
            message="Started",
        )
        assert result.status == "running"
