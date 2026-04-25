from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.errors import FlowifyException
from app.core.engine.executor import WorkflowExecutor
from app.core.engine.state import WorkflowState
from app.models.workflow import EdgeDefinition, NodeDefinition


@pytest.fixture()
def mock_db():
    """모의 MongoDB 데이터베이스."""
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.workflow_executions = collection
    return db


def _make_nodes(*types: str) -> list[NodeDefinition]:
    return [NodeDefinition(id=f"node_{i + 1}", type=t, config={}) for i, t in enumerate(types)]


def _make_edges(*pairs: tuple[str, str]) -> list[EdgeDefinition]:
    return [EdgeDefinition(source=s, target=t) for s, t in pairs]


class TestTopologicalSort:
    def test_linear_chain(self):
        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))
        order = WorkflowExecutor._topological_sort(nodes, edges)
        assert order == ["node_1", "node_2", "node_3"]

    def test_single_node(self):
        nodes = _make_nodes("input")
        order = WorkflowExecutor._topological_sort(nodes, [])
        assert order == ["node_1"]

    def test_diamond_shape(self):
        nodes = _make_nodes("input", "llm", "llm", "output")
        edges = _make_edges(
            ("node_1", "node_2"),
            ("node_1", "node_3"),
            ("node_2", "node_4"),
            ("node_3", "node_4"),
        )
        order = WorkflowExecutor._topological_sort(nodes, edges)
        assert order[0] == "node_1"
        assert order[-1] == "node_4"
        assert set(order[1:3]) == {"node_2", "node_3"}

    def test_cycle_raises(self):
        nodes = _make_nodes("input", "llm")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_1"))
        with pytest.raises(FlowifyException):
            WorkflowExecutor._topological_sort(nodes, edges)


class TestSanitizeForLog:
    def test_removes_credentials(self):
        data = {"key": "value", "credentials": {"google": "token"}}
        result = WorkflowExecutor._sanitize_for_log(data)
        assert "credentials" not in result
        assert result["key"] == "value"

    def test_empty_data(self):
        assert WorkflowExecutor._sanitize_for_log({}) == {}

    def test_none_data(self):
        assert WorkflowExecutor._sanitize_for_log(None) == {}

    def test_no_credentials_key(self):
        data = {"key": "value"}
        result = WorkflowExecutor._sanitize_for_log(data)
        assert result == {"key": "value"}


def _mock_factory(side_effect=None, return_value=None):
    """테스트용 mock factory를 생성합니다.

    v2: create_from_node_def를 mock하고, execute는 (node, input_data, service_tokens) 시그니처.
    """
    factory = MagicMock()
    mock_node = AsyncMock()
    if side_effect:
        mock_node.execute = AsyncMock(side_effect=side_effect)
    elif return_value is not None:
        mock_node.execute = AsyncMock(return_value=return_value)
    factory.create_from_node_def.return_value = mock_node
    return factory


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_linear_success(self, mock_db):
        """input -> llm -> output 선형 워크플로우 성공 테스트."""
        executor = WorkflowExecutor(mock_db)
        executor._factory = _mock_factory(
            side_effect=lambda node, input_data, service_tokens: {"type": "TEXT", "content": "ok"}
        )

        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_test1",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={"google": "token"},
        )

        assert result.state == WorkflowState.SUCCESS
        assert len(result.nodeLogs) == 3
        assert all(log.status == "success" for log in result.nodeLogs)

    @pytest.mark.asyncio
    async def test_node_failure_marks_rollback_available(self, mock_db):
        """노드 실패 시 이후 노드 skip, 상태 ROLLBACK_AVAILABLE."""
        executor = WorkflowExecutor(mock_db)

        call_count = 0

        async def side_effect(node, input_data, service_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # 두 번째 노드(llm)에서 실패
                raise RuntimeError("LLM failed")
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_test2",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.ROLLBACK_AVAILABLE
        assert result.nodeLogs[0].status == "success"
        assert result.nodeLogs[1].status == "failed"
        assert result.nodeLogs[2].status == "skipped"

    @pytest.mark.asyncio
    async def test_credentials_stripped_from_logs(self, mock_db):
        """로그에 credentials가 포함되지 않는지 확인."""
        executor = WorkflowExecutor(mock_db)
        executor._factory = _mock_factory(
            return_value={
                "type": "TEXT",
                "content": "ok",
                "credentials": {"secret": "should_be_stripped"},
            }
        )

        nodes = _make_nodes("input")
        edges = []

        result = await executor.execute(
            execution_id="exec_test3",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={"google": "secret_token"},
        )

        log = result.nodeLogs[0]
        assert "credentials" not in (log.outputData or {})


class TestGenerateExecutionId:
    def test_format(self):
        eid = WorkflowExecutor.generate_execution_id()
        assert eid.startswith("exec_")
        assert len(eid) == 17  # "exec_" + 12 hex chars

    def test_unique(self):
        ids = {WorkflowExecutor.generate_execution_id() for _ in range(100)}
        assert len(ids) == 100
